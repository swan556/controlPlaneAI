import os
import asyncio
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from mistralai.client import Mistral
from pydantic import BaseModel

# Import Detection Pathways
from shadow.shadow_engine import ShadowEngine
from detection.heuristics import HeuristicDetector
from detection.bias import CounterfactualBiasDetector
from rag.retriever import RAGRetriever
from detection.session import session_manager
from database import log_incident

load_dotenv()

router = APIRouter()
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
        rag_retriever.add_policy_document(company_policies)

class PromptRequest(BaseModel):
    prompt: str
    session_id: str = "default-session"

# Helper to run synchronous policy compliance check in a thread
def run_rag_check(prompt: str, text: str) -> bool:
    result = rag_retriever.check_policy_compliance(prompt=prompt, response=text)
    return result.is_grounded

# --- 1. Raw Streaming Endpoint (Mistral Only) ---
@router.post("/stream-raw")
async def stream_raw(payload: PromptRequest):
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY not configured.")

    async def token_stream_generator():
        try:
            stream_response = await client.agents.stream_async(
                agent_id="ag_01a048474f7872db90a903ea31477b48",
                messages=[{"role": "user", "content": payload.prompt}]
            )
            async for chunk in stream_response:
                token = chunk.data.choices[0].delta.content
                if token:
                    # Adding space or yielding raw, we can yield raw but dashboard reads words.
                    # Yielding token directly without processing.
                    yield token
        except Exception as e:
            yield f"\n[Stream Error: {str(e)}]"

    return StreamingResponse(token_stream_generator(), media_type="text/event-stream")

# --- 2. Real-Time Streaming Endpoint (ControlPlane) ---
@router.post("/stream-check")
async def stream_with_controlplane(payload: PromptRequest):
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY not configured.")

    # 0. PRE-FLIGHT SCAN (User Query Check)
    if not payload.prompt.lstrip().lower().startswith("sudo"):
        preflight = heuristic_detector.scan(payload.prompt)
        if preflight.has_pii or preflight.has_prompt_injection:
            async def early_halt():
                yield "\n\n⚠️ [ControlPlane Alert: Request halted by Tier 1 Heuristics (PII/Injection found in prompt)]\n"
            return StreamingResponse(early_halt(), media_type="text/event-stream")

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
                        rag_task = asyncio.to_thread(run_rag_check, payload.prompt, sentence_to_check)
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
                rag_task = asyncio.to_thread(run_rag_check, payload.prompt, sentence_to_check)
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

# --- 3. Dual-Stream Multiplexed Endpoint (Testing Mode) ---
@router.post("/stream-dual")
async def stream_dual_arena(payload: PromptRequest):
    """
    Makes ONE call to Mistral and multiplexes the output into JSON lines:
    {"raw": "token"} and {"cp": "evaluated sentence"}.
    This guarantees both sides of the UI are judging the EXACT same generation!
    """
    import json
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY not configured.")

    async def token_stream_generator():
        # Phase 2: Check Session Blocklist immediately
        if session_manager.is_blocked(payload.session_id):
            log_incident(payload.session_id, payload.prompt, "", "BLOCKED (Multi-turn Aggregator)", 1.0, "SessionAggregator")
            yield json.dumps({"cp": "\n\n⚠️ [ControlPlane Alert: Connection severed. Cumulative session risk threshold exceeded.]\n"}) + "\n"
            return

        # Pre-flight scan
        prompt_halted = False
        if not payload.prompt.lstrip().lower().startswith("sudo"):
            preflight = heuristic_detector.scan(payload.prompt)
            if preflight.has_pii or preflight.has_prompt_injection:
                prompt_halted = True
                session_manager.add_risk(payload.session_id, preflight.tier1_risk_score)
                log_incident(payload.session_id, payload.prompt, "", "BLOCKED (Preflight)", preflight.tier1_risk_score, "HeuristicDetector")
                yield json.dumps({"cp": "\n\n⚠️ [ControlPlane Alert: Request halted (PII/Injection found in prompt)]\n"}) + "\n"

        try:
            stream_response = await client.agents.stream_async(
                agent_id="ag_01a048474f7872db90a903ea31477b48",
                messages=[{"role": "user", "content": payload.prompt}]
            )

            current_sentence = ""
            previous_tail = ""
            cp_halted = prompt_halted  # If prompt was halted, CP is already halted

            async for chunk in stream_response:
                token = chunk.data.choices[0].delta.content
                if token:
                    # ALWAYS stream the raw token
                    yield json.dumps({"raw": token}) + "\n"

                    # Only process ControlPlane logic if not already halted
                    if not cp_halted:
                        current_sentence += token
                        import re
                        sentences = re.split(r'(?<=[.!?])\s+', current_sentence)
                        
                        if len(sentences) > 1 or len(current_sentence.split()) >= 30:
                            sentence_chunk = sentences[0].strip() if len(sentences) > 1 else current_sentence.strip()
                            if not sentence_chunk:
                                current_sentence = ""
                                continue
                                
                            current_sentence = " ".join(sentences[1:]) if len(sentences) > 1 else ""

                            # Sliding Window Accumulator: prepend tail of previous chunk
                            sentence_to_check = (previous_tail + " " + sentence_chunk).strip()
                            # Update previous_tail with the last 10 words of the current chunk
                            previous_tail = " ".join(sentence_chunk.split()[-10:])

                            shadow_task = asyncio.to_thread(shadow_engine.evaluate_side_by_side_stream, sentence_to_check)
                            heuristic_task = asyncio.to_thread(heuristic_detector.scan, sentence_to_check)
                            rag_task = asyncio.to_thread(run_rag_check, payload.prompt, sentence_to_check)
                            bias_task = bias_detector.evaluate_bias_async(payload.prompt, sentence_to_check)

                            results = await asyncio.gather(shadow_task, heuristic_task, rag_task, bias_task, return_exceptions=True)
                            shadow_res, heuristic_res, rag_res, bias_res = results

                            if isinstance(heuristic_res, Exception) or getattr(heuristic_res, "has_pii", False) or getattr(heuristic_res, "has_prompt_injection", False):
                                session_manager.add_risk(payload.session_id, 0.5)
                                yield json.dumps({"cp": "\n\n⚠️ [ControlPlane Alert: Stream halted by Tier 1 Heuristics (PII/Injection)]\n"}) + "\n"
                                cp_halted = True
                            elif isinstance(shadow_res, Exception) or getattr(shadow_res, "is_uncertain", False):
                                yield json.dumps({"cp": "\n\n⚠️ [ControlPlane Alert: Stream halted by Shadow Engine (Overconfidence/Hallucination)]\n"}) + "\n"
                                cp_halted = True
                            elif isinstance(bias_res, Exception) or getattr(bias_res, "bias_detected", False):
                                yield json.dumps({"cp": "\n\n⚠️ [ControlPlane Alert: Stream halted by Bias Engine (Counterfactual Variance High)]\n"}) + "\n"
                                cp_halted = True
                            elif isinstance(rag_res, Exception) or not rag_res:
                                session_manager.add_risk(payload.session_id, 0.4)
                                yield json.dumps({"cp": "\n\n⚠️ [ControlPlane Alert: Stream halted by RAG Engine (Response contradicts policy)]\n"}) + "\n"
                                cp_halted = True
                            else:
                                # We only yield the new chunk to the user, not the overlapping tail!
                                yield json.dumps({"cp": sentence_chunk + " "}) + "\n"

            # Final chunk
            if current_sentence.strip() and not cp_halted:
                sentence_chunk = current_sentence.strip()
                sentence_to_check = (previous_tail + " " + sentence_chunk).strip()
                shadow_task = asyncio.to_thread(shadow_engine.evaluate_side_by_side_stream, sentence_to_check)
                heuristic_task = asyncio.to_thread(heuristic_detector.scan, sentence_to_check)
                rag_task = asyncio.to_thread(run_rag_check, payload.prompt, sentence_to_check)
                bias_task = bias_detector.evaluate_bias_async(payload.prompt, sentence_to_check)
                results = await asyncio.gather(shadow_task, heuristic_task, rag_task, bias_task, return_exceptions=True)
                shadow_res, heuristic_res, rag_res, bias_res = results
                
                if (isinstance(heuristic_res, Exception) or getattr(heuristic_res, "has_pii", False) or getattr(heuristic_res, "has_prompt_injection", False) or 
                    isinstance(shadow_res, Exception) or getattr(shadow_res, "is_uncertain", False) or 
                    isinstance(bias_res, Exception) or getattr(bias_res, "bias_detected", False) or
                    isinstance(rag_res, Exception) or not rag_res):
                    session_manager.add_risk(payload.session_id, 0.5)
                    yield json.dumps({"cp": "\n\n⚠️ [ControlPlane Alert: Final chunk halted due to policy violation]\n"}) + "\n"
                else:
                    yield json.dumps({"cp": current_sentence}) + "\n"
            
            # Phase 3: Log full generated text at the end of the stream
            final_verdict = "BLOCKED" if cp_halted else "ALLOWED"
            current_risk = session_manager.get_cumulative_risk(payload.session_id)
            log_incident(payload.session_id, payload.prompt, current_sentence, final_verdict, current_risk, "StreamDualArena")

        except Exception as e:
            yield json.dumps({"raw": f"\n[Error: {str(e)}]", "cp": f"\n[Error: {str(e)}]"}) + "\n"

    return StreamingResponse(token_stream_generator(), media_type="application/x-ndjson")


# --- 2. Complete Response Endpoint ---
@router.post("/generate-full")
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