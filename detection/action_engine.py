from enum import Enum
from typing import Tuple, Optional, Any
from pydantic import BaseModel

class ActionVerdict(Enum):
    ALLOW = "ALLOW"
    EDIT = "EDIT"
    FLAG = "FLAG"
    BLOCK = "BLOCK"

class ActionResult(BaseModel):
    verdict: ActionVerdict
    reason: str
    correction_text: Optional[str] = None
    risk_score_to_add: float = 0.0

class ActionEngine:
    def evaluate(
        self,
        prompt: str,
        sentence_to_check: str,
        heuristic_res: Any,
        shadow_res: Any,
        rag_res: Any,
        bias_res: Any,
        rag_retriever: Any
    ) -> ActionResult:
        # 1. BLOCK: Heuristic failure or RAG explicit policy violation
        if isinstance(heuristic_res, Exception) or getattr(heuristic_res, "has_pii", False) or getattr(heuristic_res, "has_prompt_injection", False):
            return ActionResult(verdict=ActionVerdict.BLOCK, reason="Tier 1 Heuristics (PII/Injection)", risk_score_to_add=0.5)
        
        # rag_res is now the full GroundingCheckResult
        if not isinstance(rag_res, Exception) and getattr(rag_res, "policy_violated", False):
            rule = getattr(rag_res, 'violated_rule', 'Explicit prohibition violated')
            return ActionResult(verdict=ActionVerdict.BLOCK, reason=f"Policy Violation: {rule}", risk_score_to_add=0.4)

        # 2. EDIT: Hallucination (Shadow uncertainty or RAG ungrounded but NOT a policy violation)
        needs_edit = False
        edit_reason = ""
        if isinstance(shadow_res, Exception) or getattr(shadow_res, "is_uncertain", False):
            needs_edit = True
            edit_reason = "Shadow Engine (Overconfidence/Hallucination)"
        elif not isinstance(rag_res, Exception) and not getattr(rag_res, "is_grounded", True):
            needs_edit = True
            edit_reason = "RAG Engine (Ungrounded/Unsupported claims)"

        if needs_edit:
            # Fetch correction from RAG Retriever
            correction = "No factual context found."
            if rag_retriever:
                contexts = rag_retriever.retrieve(prompt, top_k=1)
                if contexts:
                    correction = contexts[0]
            
            # Keep it concise
            if len(correction) > 300:
                correction = correction[:300] + "..."
                
            return ActionResult(
                verdict=ActionVerdict.EDIT, 
                reason=edit_reason,
                correction_text=f"\\n\\n\u26a0\ufe0f [ControlPlane Edit: The model hallucinated. Correct information: {correction}]\\n",
                risk_score_to_add=0.1
            )

        # 3. FLAG FOR REVIEW: Bias detected
        if isinstance(bias_res, Exception) or getattr(bias_res, "bias_detected", False):
            return ActionResult(
                verdict=ActionVerdict.FLAG,
                reason="Bias Engine (Counterfactual Variance High)",
                risk_score_to_add=0.2
            )

        # 4. ALLOW: All clear
        return ActionResult(verdict=ActionVerdict.ALLOW, reason="All checks passed", risk_score_to_add=0.0)

action_engine = ActionEngine()
