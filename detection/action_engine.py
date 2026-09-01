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
        # 1. BLOCK: Prompt Injection (Malicious)
        if getattr(heuristic_res, "has_prompt_injection", False):
            return ActionResult(verdict=ActionVerdict.BLOCK, reason="Tier 1 Heuristics (Injection Detected)", risk_score_to_add=0.5)

        # 2. EDIT: PII Detection
        if getattr(heuristic_res, "has_pii", False):
            return ActionResult(verdict=ActionVerdict.EDIT, reason="Tier 1 Heuristics (PII Detected)", correction_text="`[REDACTED SENSITIVE DATA]`", risk_score_to_add=0.3)
        
        # 3. EDIT: RAG Policy Violation
        if not isinstance(rag_res, Exception) and getattr(rag_res, "policy_violated", False):
            rule = getattr(rag_res, 'violated_rule', 'Explicit prohibition violated')
            return ActionResult(verdict=ActionVerdict.EDIT, reason=f"Policy Violation: {rule}", correction_text="`[REDACTED: INTERNAL POLICY VIOLATION]`", risk_score_to_add=0.4)

        # 4. EDIT: Hallucination (Shadow uncertainty or RAG ungrounded)
        needs_edit = False
        edit_reason = ""
        if isinstance(shadow_res, Exception) or getattr(shadow_res, "is_uncertain", False):
            needs_edit = True
            edit_reason = "Shadow Engine Disagreement (Low Confidence / Hallucination)"
        elif not isinstance(rag_res, Exception) and not getattr(rag_res, "is_grounded", True):
            needs_edit = True
            edit_reason = "RAG Engine Disagreement (Ungrounded Claims)"

        if needs_edit:
            return ActionResult(
                verdict=ActionVerdict.EDIT, 
                reason=edit_reason,
                correction_text="`[REDACTED: UNVERIFIED CLAIM DETECTED]`",
                risk_score_to_add=0.1
            )

        # 5. FLAG FOR REVIEW: Bias detected
        if isinstance(bias_res, Exception) or getattr(bias_res, "bias_detected", False):
            return ActionResult(
                verdict=ActionVerdict.FLAG,
                reason="Bias Engine (Counterfactual Demographic Variance High)",
                risk_score_to_add=0.2
            )

        # 6. ALLOW: All clear
        return ActionResult(verdict=ActionVerdict.ALLOW, reason="All safety and grounding checks passed", risk_score_to_add=0.0)

action_engine = ActionEngine()
