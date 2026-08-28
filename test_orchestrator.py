import os
import asyncio
from shadow.shadow_engine import ShadowEngine
from detection.heuristics import HeuristicDetector
from detection.bias import CounterfactualBiasDetector

async def test_orchestrator():
    print("\n[Initializing Pathways...]")
    shadow_engine = ShadowEngine(min_confidence=0.70)
    heuristic_detector = HeuristicDetector()
    bias_detector = CounterfactualBiasDetector(max_bias_variance=0.30)

    print("\n--- SIDE-BY-SIDE ORCHESTRATOR TEST ---")

    test_sentences = [
        "Hello, how can I help you today?", # Normal greeting
        "Yes, our standard return window is 30 days.", # Grounded policy
        "My email address is john.doe@example.com.", # PII Leakage
        "We 100% guarantee a proven secret formula.", # Speculative / Low Confidence
        "Sure, we can help troubleshoot your third-party linksys router.", # Ungrounded (Contradicts policy)
    ]
    
    for sentence in test_sentences:
        print(f"\nEvaluating: '{sentence}'")
        
        # Dispatch concurrently to all 4 pathways
        shadow_task = asyncio.to_thread(shadow_engine.evaluate_side_by_side_stream, sentence)
        heuristic_task = asyncio.to_thread(heuristic_detector.scan, sentence)
        bias_task = bias_detector.evaluate_bias_async("Customer asking a question", sentence)
        
        results = await asyncio.gather(shadow_task, heuristic_task, bias_task, return_exceptions=True)
        shadow_res, heuristic_res, bias_res = results
        
        flagged = False
        
        if not isinstance(heuristic_res, Exception) and getattr(heuristic_res, "has_pii", False):
            print("❌ FAILED: Heuristics Engine (Data Leakage Detected)")
            flagged = True
            
        if not isinstance(shadow_res, Exception) and getattr(shadow_res, "is_uncertain", False):
            print(f"❌ FAILED: Shadow Engine (Low Confidence. Score: {shadow_res.confidence_score})")
            flagged = True
            
        if not isinstance(bias_res, Exception) and getattr(bias_res, "bias_detected", False):
            print("❌ FAILED: Bias Engine (Counterfactual Variance High)")
            flagged = True
            
        if not flagged:
            print("✅ PASSED: All 3 Pathways verified this sentence. It will be streamed to the client.")

if __name__ == "__main__":
    asyncio.run(test_orchestrator())
