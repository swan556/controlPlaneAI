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
from rag.retriever import RAGRetriever, GroundingCheckResult
from detection.session import session_manager
from database import log_incident
from detection.action_engine import action_engine, ActionVerdict

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

product_desc_path = os.path.join(os.path.dirname(__file__), "product_description.md")
product_description = ""
if os.path.exists(product_desc_path):
    with open(product_desc_path, "r") as f:
        product_description = f.read()
        rag_retriever.add_policy_document(product_description)

# Default agent IDs
HALLUCINATING_AGENT_ID = "ag_01a048474f7872db90a903ea31477b48"
GOOD_AGENT_ID = "ag_01a05e48d29a7723abdb5978b5d22dbd"

class PromptRequest(BaseModel):
    prompt: str
    session_id: str = "default-session"
    agent_id: str = HALLUCINATING_AGENT_ID  # Default to hallucinating agent for backward compat

# Helper to run synchronous policy compliance check in a thread
def run_rag_check(prompt: str, text: str) -> GroundingCheckResult:
    result = rag_retriever.check_policy_compliance(prompt=prompt, response=text)
    return result

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

    async def token_stream_generator():
        # Phase 2: Check Session Blocklist immediately
        if session_manager.is_blocked(payload.session_id):
            log_incident(payload.session_id, payload.prompt, "", "BLOCKED (Multi-turn Aggregator)", 1.0, "SessionAggregator")
            yield "\n\n⚠️ [ControlPlane Alert: Connection severed. Cumulative session risk threshold exceeded.]\n"
            return

        # Pre-flight scan
        preflight = heuristic_detector.scan(payload.prompt)
        if preflight.has_pii or preflight.has_prompt_injection:
            session_manager.add_risk(payload.session_id, preflight.tier1_risk_score)
            log_incident(payload.session_id, payload.prompt, "", "BLOCKED (Preflight)", preflight.tier1_risk_score, "HeuristicDetector")
            yield "\n\n⚠️ [ControlPlane Alert: Request halted (PII/Injection found in prompt)]\n"
            return

        # Pre-flight RAG policy intent check
        rag_preflight = rag_retriever.check_prompt_intent(payload.prompt)
        if rag_preflight.policy_violated:
            session_manager.add_risk(payload.session_id, 0.4)
            log_incident(payload.session_id, payload.prompt, "", "BLOCKED (RAG Preflight)", 0.4, "RAGRetriever")
            yield f"\n\n⚠️ [ControlPlane Alert: Request halted — Policy violation detected: {rag_preflight.violated_rule}]\n"
            return

        try:
            stream_response = await client.agents.stream_async(
                agent_id=payload.agent_id,
                messages=[{"role": "user", "content": payload.prompt}]
            )

            current_sentence = ""
            previous_tail = ""
            cp_halted = False

            async for chunk in stream_response:
                token = chunk.data.choices[0].delta.content
                if token and not cp_halted:
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
                        previous_tail = " ".join(sentence_chunk.split()[-10:])

                        shadow_task = asyncio.to_thread(shadow_engine.evaluate_side_by_side_stream, sentence_to_check)
                        heuristic_task = asyncio.to_thread(heuristic_detector.scan, sentence_to_check)
                        rag_task = asyncio.to_thread(run_rag_check, payload.prompt, sentence_to_check)
                        bias_task = bias_detector.evaluate_bias_async(payload.prompt, sentence_to_check)

                        results = await asyncio.gather(shadow_task, heuristic_task, rag_task, bias_task, return_exceptions=True)
                        shadow_res, heuristic_res, rag_res, bias_res = results

                        action = action_engine.evaluate(
                            prompt=payload.prompt,
                            sentence_to_check=sentence_to_check,
                            heuristic_res=heuristic_res,
                            shadow_res=shadow_res,
                            rag_res=rag_res,
                            bias_res=bias_res,
                            rag_retriever=rag_retriever
                        )
                        
                        session_manager.add_risk(payload.session_id, action.risk_score_to_add)

                        if action.verdict == ActionVerdict.BLOCK:
                            yield f"\n\n⚠️ [ControlPlane Alert: {action.reason}]\n"
                            cp_halted = True
                            break
                        elif action.verdict == ActionVerdict.EDIT:
                            yield sentence_chunk + " "
                            yield action.correction_text
                        elif action.verdict == ActionVerdict.FLAG:
                            yield sentence_chunk + " "
                            yield f"\n\n⚠️ [ControlPlane Flag: {action.reason}]\n"
                        else:
                            yield sentence_chunk + " "

            # Yield any remaining text in the buffer after stream ends
            if current_sentence.strip() and not cp_halted:
                sentence_chunk = current_sentence.strip()
                sentence_to_check = (previous_tail + " " + sentence_chunk).strip()
                shadow_task = asyncio.to_thread(shadow_engine.evaluate_side_by_side_stream, sentence_to_check)
                heuristic_task = asyncio.to_thread(heuristic_detector.scan, sentence_to_check)
                rag_task = asyncio.to_thread(run_rag_check, payload.prompt, sentence_to_check)
                bias_task = bias_detector.evaluate_bias_async(payload.prompt, sentence_to_check)
                results = await asyncio.gather(shadow_task, heuristic_task, rag_task, bias_task, return_exceptions=True)
                shadow_res, heuristic_res, rag_res, bias_res = results
                
                action = action_engine.evaluate(
                    prompt=payload.prompt,
                    sentence_to_check=sentence_to_check,
                    heuristic_res=heuristic_res,
                    shadow_res=shadow_res,
                    rag_res=rag_res,
                    bias_res=bias_res,
                    rag_retriever=rag_retriever
                )
                session_manager.add_risk(payload.session_id, action.risk_score_to_add)

                if action.verdict == ActionVerdict.BLOCK:
                    yield f"\n\n⚠️ [ControlPlane Alert: {action.reason}]\n"
                elif action.verdict == ActionVerdict.EDIT:
                    yield current_sentence + " "
                    yield action.correction_text
                elif action.verdict == ActionVerdict.FLAG:
                    yield current_sentence
                    yield f"\n\n⚠️ [ControlPlane Flag: {action.reason}]\n"
                else:
                    yield current_sentence

            # Audit Logging
            final_verdict = "BLOCKED" if cp_halted else "ALLOWED"
            current_risk = session_manager.get_cumulative_risk(payload.session_id)
            log_incident(payload.session_id, payload.prompt, current_sentence, final_verdict, current_risk, "StreamCheck")

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
            yield json.dumps({"cp": "\n\n> 🛑 **[ControlPlane Intervention — BLOCKED]**  \n> *Connection severed: Cumulative session threat threshold exceeded (Multi-turn Salami-Slicing Mitigated).*  \n", "action": "BLOCK"}) + "\n"
            return

        # Pre-flight scan
        prompt_halted = False
        preflight = heuristic_detector.scan(payload.prompt)
        if preflight.has_pii or preflight.has_prompt_injection:
            prompt_halted = True
            session_manager.add_risk(payload.session_id, preflight.tier1_risk_score)
            log_incident(payload.session_id, payload.prompt, "", "BLOCKED (Preflight)", preflight.tier1_risk_score, "HeuristicDetector")
            yield json.dumps({"cp": "\n\n> 🛑 **[ControlPlane Intervention — BLOCKED]**  \n> *Prompt contains direct prompt injection or sensitive data probes.*  \n", "action": "BLOCK"}) + "\n"

        # Pre-flight RAG policy intent check
        if not prompt_halted:
            rag_preflight = rag_retriever.check_prompt_intent(payload.prompt)
            if rag_preflight.policy_violated:
                session_manager.add_risk(payload.session_id, 0.2)
                yield json.dumps({"cp": f"\n\n> 🚩 **[ControlPlane Pre-Flight Warning]**  \n> **Prompt Flags Policy Violation:** {rag_preflight.violated_rule}  \n> *Proceeding to LLM, but output is being strictly monitored for leaks.*  \n", "action": "FLAG"}) + "\n"

        import asyncio
        queue = asyncio.Queue()

        async def run_good_agent():
            try:
                res = await client.agents.stream_async(
                    agent_id=GOOD_AGENT_ID,
                    messages=[{"role": "user", "content": payload.prompt}]
                )
                async for chunk in res:
                    token = chunk.data.choices[0].delta.content
                    if token:
                        await queue.put({"good": token})
            except Exception as e:
                await queue.put({"good": f"\n[Error: {str(e)}]"})
            await queue.put({"good_done": True})

        async def run_bad_agent_with_cp():
            try:
                stream_response = await client.agents.stream_async(
                    agent_id=HALLUCINATING_AGENT_ID,
                    messages=[{"role": "user", "content": payload.prompt}]
                )

                current_sentence = ""
                previous_tail = ""
                cp_halted = prompt_halted  # If prompt was halted, CP is already halted
                
                # Track highest action severity for the final verdict
                severity_map = {"ALLOW": 1, "FLAG": 2, "EDIT": 3, "BLOCK": 4}
                highest_severity = severity_map["BLOCK"] if prompt_halted else severity_map["ALLOW"]
                highest_verdict = "BLOCKED" if prompt_halted else "ALLOWED"

                async for chunk in stream_response:
                    token = chunk.data.choices[0].delta.content
                    if token:
                        # ALWAYS stream the raw token
                        await queue.put({"raw": token})

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

                            action = action_engine.evaluate(
                                prompt=payload.prompt,
                                sentence_to_check=sentence_to_check,
                                heuristic_res=heuristic_res,
                                shadow_res=shadow_res,
                                rag_res=rag_res,
                                bias_res=bias_res,
                                rag_retriever=rag_retriever
                            )
                            
                            session_manager.add_risk(payload.session_id, action.risk_score_to_add)

                            current_severity = severity_map.get(action.verdict.value, 1)
                            if current_severity > highest_severity:
                                highest_severity = current_severity
                                highest_verdict = action.verdict.value

                            if action.verdict == ActionVerdict.BLOCK:
                                await queue.put({"cp": f"\n\n> 🛑 **[ControlPlane Intervention — BLOCKED]**  \n> **Trigger:** {action.reason}  \n> *Stream severed to prevent policy violation or data leak.*  \n", "action": highest_verdict})
                                cp_halted = True
                            elif action.verdict == ActionVerdict.EDIT:
                                await queue.put({"cp": " " + action.correction_text + " ", "action": highest_verdict})
                            elif action.verdict == ActionVerdict.FLAG:
                                await queue.put({"cp": sentence_chunk + " "})
                                await queue.put({"cp": f"\n\n> 🚩 **[ControlPlane Warning — FLAGGED]**  \n> **Note:** {action.reason} *(Logged for human review)*  \n", "action": highest_verdict})
                            else:
                                await queue.put({"cp": sentence_chunk + " "})

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
                    
                    action = action_engine.evaluate(
                        prompt=payload.prompt,
                        sentence_to_check=sentence_to_check,
                        heuristic_res=heuristic_res,
                        shadow_res=shadow_res,
                        rag_res=rag_res,
                        bias_res=bias_res,
                        rag_retriever=rag_retriever
                    )
                    session_manager.add_risk(payload.session_id, action.risk_score_to_add)

                    current_severity = severity_map.get(action.verdict.value, 1)
                    if current_severity > highest_severity:
                        highest_severity = current_severity
                        highest_verdict = action.verdict.value

                    if action.verdict == ActionVerdict.BLOCK:
                        await queue.put({"cp": f"\n\n> 🛑 **[ControlPlane Intervention — BLOCKED]**  \n> **Trigger:** {action.reason}  \n> *Stream severed to prevent policy violation or data leak.*  \n", "action": highest_verdict})
                    elif action.verdict == ActionVerdict.EDIT:
                        await queue.put({"cp": " " + action.correction_text + " ", "action": highest_verdict})
                    elif action.verdict == ActionVerdict.FLAG:
                        await queue.put({"cp": current_sentence})
                        await queue.put({"cp": f"\n\n> 🚩 **[ControlPlane Warning — FLAGGED]**  \n> **Note:** {action.reason} *(Logged for human review)*  \n", "action": highest_verdict})
                    else:
                        await queue.put({"cp": current_sentence})
                
                # Phase 3: Log full generated text at the end of the stream
                if cp_halted:
                    highest_verdict = "BLOCKED"
                
                current_risk = session_manager.get_cumulative_risk(payload.session_id)
                log_incident(payload.session_id, payload.prompt, current_sentence, highest_verdict, current_risk, "StreamDualArena")
                
                # Signal the final verdict to the UI
                await queue.put({"action": highest_verdict})

            except Exception as e:
                await queue.put({"raw": f"\n[Error: {str(e)}]", "cp": f"\n[Error: {str(e)}]"})
            
            await queue.put({"bad_done": True})

        # Launch background tasks and stream from queue
        asyncio.create_task(run_good_agent())
        asyncio.create_task(run_bad_agent_with_cp())

        good_done = False
        bad_done = False
        while not (good_done and bad_done):
            msg = await queue.get()
            if "good_done" in msg:
                good_done = True
            elif "bad_done" in msg:
                bad_done = True
            else:
                yield json.dumps(msg) + "\n"

    return StreamingResponse(token_stream_generator(), media_type="application/x-ndjson")


# --- 2. Complete Response Endpoint ---
@router.post("/generate-full")
async def generate_full_response(payload: PromptRequest):
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY not configured.")

    # Session blocklist check (matches streaming endpoints)
    if session_manager.is_blocked(payload.session_id):
        log_incident(payload.session_id, payload.prompt, "", "BLOCKED (Multi-turn Aggregator)", 1.0, "SessionAggregator")
        return {
            "response": "",
            "status": "BLOCK",
            "flag_reasons": ["Cumulative session risk threshold exceeded (Multi-turn Salami-Slicing Mitigated)."],
            "confidence_score": None
        }

    # Pre-flight heuristic scan on the prompt itself
    preflight = heuristic_detector.scan(payload.prompt)
    if preflight.has_pii or preflight.has_prompt_injection:
        session_manager.add_risk(payload.session_id, preflight.tier1_risk_score)
        log_incident(payload.session_id, payload.prompt, "", "BLOCKED (Preflight)", preflight.tier1_risk_score, "HeuristicDetector")
        return {
            "response": "",
            "status": "BLOCK",
            "flag_reasons": ["Prompt blocked at pre-flight: " + ", ".join(preflight.injection_vector_types + preflight.detected_pii_types)],
            "confidence_score": None
        }

    # Pre-flight RAG policy check on the prompt
    rag_preflight = rag_retriever.check_prompt_intent(payload.prompt)
    if rag_preflight.policy_violated:
        session_manager.add_risk(payload.session_id, 0.4)
        log_incident(payload.session_id, payload.prompt, "", "BLOCKED (RAG Preflight)", 0.4, "RAGRetriever")
        return {
            "response": "",
            "status": "BLOCK",
            "flag_reasons": [f"Prompt blocked at pre-flight: Policy violation detected — {rag_preflight.violated_rule}"],
            "confidence_score": None
        }

    response = await client.agents.complete_async(
        agent_id="ag_01a048474f7872db90a903ea31477b48",
        messages=[{"role": "user", "content": payload.prompt}]
    )

    full_text = response.choices[0].message.content
    
    # Run all checks on full text
    shadow_task = asyncio.to_thread(shadow_engine.evaluate_confidence, full_text)
    heuristic_task = asyncio.to_thread(heuristic_detector.scan, full_text)
    rag_task = asyncio.to_thread(run_rag_check, payload.prompt, full_text)
    bias_task = bias_detector.evaluate_bias_async(payload.prompt, full_text)

    results = await asyncio.gather(shadow_task, heuristic_task, rag_task, bias_task, return_exceptions=True)
    shadow_res, heuristic_res, rag_res, bias_res = results
    
    action = action_engine.evaluate(
        prompt=payload.prompt,
        sentence_to_check=full_text,
        heuristic_res=heuristic_res,
        shadow_res=shadow_res,
        rag_res=rag_res,
        bias_res=bias_res,
        rag_retriever=rag_retriever
    )
    
    session_manager.add_risk(payload.session_id, action.risk_score_to_add)
    log_incident(payload.session_id, payload.prompt, full_text, action.verdict.value, session_manager.get_cumulative_risk(payload.session_id), "GenerateFull")

    return {
        "response": action.correction_text if action.verdict == ActionVerdict.EDIT else full_text,
        "status": action.verdict.value,
        "flag_reasons": [action.reason] if action.reason else [],
        "confidence_score": getattr(shadow_res, 'confidence_score', None) if not isinstance(shadow_res, Exception) else None
    }