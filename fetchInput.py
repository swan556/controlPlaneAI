import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from mistralai.client import Mistral
from pydantic import BaseModel

# Import Detection Pathways
from shadow.shadow_engine import ShadowEngine
from detection.heuristics import HeuristicDetector
from detection.bias import CounterfactualBiasDetector
from rag.retriever import RAGRetriever

load_dotenv()

app = FastAPI()
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

# Initialize Pathways Globally
shadow_engine = ShadowEngine(min_confidence=0.70)
heuristic_detector = HeuristicDetector()
bias_detector = CounterfactualBiasDetector(max_bias_variance=0.30)
rag_retriever = RAGRetriever(min_grounding_score=0.10)

mock_policies_path = os.path.join(os.path.dirname(__file__), "mock_policies.md")
company_policies = ""
if os.path.exists(mock_policies_path):
    with open(mock_policies_path, "r") as f:
        company_policies = f.read()
        rag_retriever.add_documents([company_policies])

class PromptRequest(BaseModel):
    prompt: str

# Helper to run synchronous RAG check in thread
def run_rag_check(text: str) -> bool:
    contexts = rag_retriever.retrieve(text)
    context_str = " ".join(contexts) if contexts else ""
    result = rag_retriever.check_grounding(context_str, text)
    return result.is_grounded

# --- 1. Real-Time Streaming Endpoint ---
@app.post("/stream-check")
async def stream_with_controlplane(payload: PromptRequest):
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY not configured.")

    async def token_stream_generator():
        try:
            stream_response = await client.agents.stream_async(
                agent_id="ag_01a048474f7872db90a903ea31477b48",
                messages=[{"role": "user", "content": payload.prompt}]
            )

            current_sentence = ""
            stream_halted = False

            async for chunk in stream_response:
                token = chunk.data.choices[0].delta.content
                if token:
                    current_sentence += token

                    import re
                    # Accurately split completed sentences using regex
                    sentences = re.split(r'(?<=[.!?])\s+', current_sentence)
                    
                    # If we have a completed sentence (split by space after punctuation) OR buffer is too large
                    if len(sentences) > 1 or len(current_sentence.split()) >= 30:
                        sentence_to_check = sentences[0].strip() if len(sentences) > 1 else current_sentence.strip()
                        
                        if not sentence_to_check:
                            current_sentence = ""
                            continue
                            
                        # Keep the remainder in the buffer
                        current_sentence = " ".join(sentences[1:]) if len(sentences) > 1 else ""

                        # Execute pathways concurrently
                        shadow_task = asyncio.to_thread(shadow_engine.evaluate_side_by_side_stream, sentence_to_check)
                        heuristic_task = asyncio.to_thread(heuristic_detector.scan, sentence_to_check)
                        rag_task = asyncio.to_thread(run_rag_check, sentence_to_check)
                        bias_task = bias_detector.evaluate_bias_async(payload.prompt, sentence_to_check)

                        results = await asyncio.gather(shadow_task, heuristic_task, rag_task, bias_task, return_exceptions=True)
                        
                        shadow_res, heuristic_res, rag_res, bias_res = results

                        # Fail-Fast Halting Checks
                        if isinstance(heuristic_res, Exception) or getattr(heuristic_res, "has_pii", False) or getattr(heuristic_res, "has_prompt_injection", False):
                            yield "\n\n⚠️ [ControlPlane Alert: Stream halted by Tier 1 Heuristics (PII/Injection)]\n"
                            stream_halted = True
                            break
                        
                        if isinstance(shadow_res, Exception) or getattr(shadow_res, "is_uncertain", False):
                            yield "\n\n⚠️ [ControlPlane Alert: Stream halted by Shadow Engine (Overconfidence/Hallucination)]\n"
                            stream_halted = True
                            break
                            
                        if isinstance(bias_res, Exception) or getattr(bias_res, "bias_detected", False):
                            yield "\n\n⚠️ [ControlPlane Alert: Stream halted by Bias Engine (Counterfactual Variance High)]\n"
                            stream_halted = True
                            break

                        if isinstance(rag_res, Exception) or not rag_res:
                            yield "\n\n⚠️ [ControlPlane Alert: Stream halted by RAG Engine (Response contradicts company policy)]\n"
                            stream_halted = True
                            break

                        # If all pass, yield the verified sentence to the client (with spacing)
                        # await asyncio.sleep(0.3)  # Artificial delay so the human eye can see the chunking
                        yield sentence_to_check + " "

            # Yield any remaining text in the buffer after stream ends
            if current_sentence.strip() and not stream_halted:
                # Perform one final check on the remainder
                sentence_to_check = current_sentence.strip()
                shadow_task = asyncio.to_thread(shadow_engine.evaluate_side_by_side_stream, sentence_to_check)
                heuristic_task = asyncio.to_thread(heuristic_detector.scan, sentence_to_check)
                rag_task = asyncio.to_thread(run_rag_check, sentence_to_check)
                bias_task = bias_detector.evaluate_bias_async(payload.prompt, sentence_to_check)

                results = await asyncio.gather(shadow_task, heuristic_task, rag_task, bias_task, return_exceptions=True)
                shadow_res, heuristic_res, rag_res, bias_res = results
                
                if (isinstance(heuristic_res, Exception) or getattr(heuristic_res, "has_pii", False) or getattr(heuristic_res, "has_prompt_injection", False) or 
                    isinstance(shadow_res, Exception) or getattr(shadow_res, "is_uncertain", False) or 
                    isinstance(bias_res, Exception) or getattr(bias_res, "bias_detected", False) or
                    isinstance(rag_res, Exception) or not rag_res):
                    yield "\n\n⚠️ [ControlPlane Alert: Final chunk halted due to policy violation]\n"
                else:
                    yield current_sentence

        except Exception as e:
            yield f"\n[Stream Error: {str(e)}]"

    return StreamingResponse(token_stream_generator(), media_type="text/event-stream")


# --- 2. Complete Response Endpoint ---
@app.post("/generate-full")
async def generate_full_response(payload: PromptRequest):
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY not configured.")

    response = await client.agents.complete_async(
        agent_id="ag_01a048474f7872db90a903ea31477b48",
        messages=[{"role": "user", "content": payload.prompt}]
    )

    full_text = response.choices[0].message.content
    
    # Run all checks on full text
    shadow_task = asyncio.to_thread(shadow_engine.evaluate_confidence, full_text)
    heuristic_task = asyncio.to_thread(heuristic_detector.scan, full_text)
    rag_task = asyncio.to_thread(run_rag_check, full_text)
    bias_task = bias_detector.evaluate_bias_async(payload.prompt, full_text)

    results = await asyncio.gather(shadow_task, heuristic_task, rag_task, bias_task, return_exceptions=True)
    shadow_res, heuristic_res, rag_res, bias_res = results
    
    is_flagged = False
    flag_reasons = []

    if isinstance(heuristic_res, Exception) or getattr(heuristic_res, "has_pii", False) or getattr(heuristic_res, "has_prompt_injection", False):
        is_flagged = True
        flag_reasons.append("Heuristics (Leakage/Injection)")
    if isinstance(shadow_res, Exception) or getattr(shadow_res, "is_uncertain", False):
        is_flagged = True
        flag_reasons.append("Shadow Engine (Low Confidence)")
    if isinstance(bias_res, Exception) or getattr(bias_res, "bias_detected", False):
        is_flagged = True
        flag_reasons.append("Bias Engine (High Variance)")
    if isinstance(rag_res, Exception) or not rag_res:
        is_flagged = True
        flag_reasons.append("RAG Engine (Ungrounded)")

    return {
        "response": full_text,
        "status": "FLAGGED" if is_flagged else "ALLOWED",
        "flag_reasons": flag_reasons,
        "confidence_score": getattr(shadow_res, 'confidence_score', None) if not isinstance(shadow_res, Exception) else None
    }