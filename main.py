"""
ControlPlane Main FastAPI Proxy Server
Integrates Tier 1 (Heuristics & RBAC), Tier 2 (RAG Grounding & SmolLM2 Side-by-Side Shadow Engine), and Tier 3 (Async Bias Detection).
Outputs risk flags, confidence scores, cost telemetry, and audit records.
"""

import time
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import config, ControlPlaneConfig, ConfidenceThresholds, RiskWeights, UserRole, DocumentClassification
from detection import HeuristicDetector, CounterfactualBiasDetector
from rag import RAGRetriever
from shadow import ShadowEngine, SideBySideEvaluationResult
from ledger import ledger, AuditLogEntry, AggregateMetrics
from fetchInput import router as fetch_input_router

# Initialize FastAPI App
app = FastAPI(
    title="ControlPlane AI Guardrail Proxy",
    description="Enterprise AI safety control plane with SmolLM2 shadow evaluation, Tier 1-3 risk scoring, and audit logging.",
    version="2.0.0"
)

# Enable CORS for dashboard and frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the Mistral agent router from fetchInput.py
app.include_router(fetch_input_router)

# Initialize Component Engines
heuristic_detector = HeuristicDetector()
rag_retriever = RAGRetriever(min_grounding_score=config.thresholds.min_grounding_score)
shadow_engine = ShadowEngine(
    model_name=config.shadow.model_name,
    min_confidence=config.thresholds.min_confidence_score,
    use_fallback=config.shadow.use_fallback
)
bias_detector = CounterfactualBiasDetector(max_bias_variance=0.30)


class ProxyEvaluationRequest(BaseModel):
    """Payload for evaluating prompts or LLM generation responses."""
    prompt: str = Field(..., description="User query or input prompt")
    response: Optional[str] = Field(None, description="Mistral LLM generated output")
    context: Optional[str] = Field(None, description="RAG retrieved context documents")
    user_role: UserRole = Field(default=UserRole.EMPLOYEE, description="User role ('GUEST', 'EMPLOYEE', 'MANAGER', 'EXECUTIVE')")
    document_classification: DocumentClassification = Field(default=DocumentClassification.PUBLIC, description="Target document security classification ('PUBLIC', 'INTERNAL', 'RESTRICTED', 'CONFIDENTIAL')")


class ProxyEvaluationResponse(BaseModel):
    """Response returned by the ControlPlane proxy engine."""
    action: str = Field(description="'ALLOWED', 'FLAGGED', or 'BLOCKED'")
    decision_reason: str = Field(description="Summary explanation for proxy decision")
    confidence_score: float = Field(description="SLM shadow engine output confidence score (0.0 to 1.0)")
    risk_score: float = Field(description="Aggregate composite risk score (0.0 to 1.0)")
    overconfidence_index: float = Field(description="Degree of ungrounded main model overconfidence (0.0 to 1.0)")
    token_divergence_score: float = Field(description="Mean token stream divergence")
    grounding_score: float = Field(description="RAG context faithfulness score")
    bias_variance: float = Field(description="Counterfactual output variance")
    flags: List[str] = Field(default_factory=list, description="Active risk flags raised across pillars")
    cost_metrics: Dict[str, Any] = Field(default_factory=dict, description="Token usage, cost in $, and compute savings")
    latency_ms: float = Field(description="Total processing time in milliseconds")


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "shadow_engine_loaded": shadow_engine._is_loaded,
        "shadow_model": shadow_engine.model_name,
        "main_model": config.costs.main_model_name,
        "version": "2.0.0"
    }


@app.post("/evaluate/stream", response_model=SideBySideEvaluationResult)
def evaluate_side_by_side_stream(req: ProxyEvaluationRequest):
    """Real-time Side-by-Side Token Streaming Evaluation endpoint (Mistral vs SmolLM2)."""
    text_to_eval = req.response if req.response else req.prompt
    return shadow_engine.evaluate_side_by_side_stream(text=text_to_eval, prompt=req.prompt)


@app.post("/evaluate", response_model=ProxyEvaluationResponse)
async def evaluate_proxy(req: ProxyEvaluationRequest):
    """
    Main ControlPlane evaluation proxy route.
    Flags responses as ALLOWED, FLAGGED, or BLOCKED based on 3 Pillars (Overconfidence, Cost Telemetry, Privacy & Hierarchical RBAC).
    """
    start_time = time.time()
    flags = []

    # 1. Tier 1: PII, Privacy Leakage, & Hierarchical RBAC Scanning
    tier1_res = heuristic_detector.scan(
        text=f"{req.prompt} {req.response or ''}",
        user_role=req.user_role,
        content_classification=req.document_classification
    )
    
    if tier1_res.has_pii:
        flags.append(f"PII_PRIVACY_LEAK ({', '.join(tier1_res.detected_pii_types)})")
    if tier1_res.has_prompt_injection:
        flags.append(f"PROMPT_INJECTION ({', '.join(tier1_res.injection_vector_types)})")
    if tier1_res.has_rbac_violation:
        flags.append(f"HIERARCHICAL_ACCESS_VIOLATION ({tier1_res.rbac_details})")

    # 2. Pillar 1: Side-by-Side Shadow SLM Confidence & Overconfidence Evaluation
    text_to_eval = req.response if req.response else req.prompt
    shadow_res = shadow_engine.evaluate_side_by_side_stream(text_to_eval, prompt=req.prompt)

    if shadow_res.overconfidence_index > 0.45:
        flags.append(f"OVERCONFIDENT_HALLUCINATION (Index: {shadow_res.overconfidence_index})")
    if shadow_res.confidence_score < config.thresholds.min_confidence_score:
        flags.append(f"LOW_SHADOW_CONFIDENCE (Score: {shadow_res.confidence_score})")

    # 3. RAG Grounding Verification (if context is present)
    grounding_res = rag_retriever.check_grounding(context=req.context or "", response=req.response or "")
    if not grounding_res.is_grounded and req.context:
        flags.append(f"UNGROUNDED_RAG_CLAIM (Score: {grounding_res.grounding_score})")

    # 4. Tier 3 Bias Evaluation
    bias_res = await bias_detector.evaluate_bias_async(req.prompt, req.response or "")
    if bias_res.bias_detected:
        flags.append(f"COUNTERFACTUAL_BIAS (Score: {bias_res.variance_score})")

    # 5. Composite Risk Score & Policy Decision (Flagging Only)
    risk_score = round(
        (tier1_res.tier1_risk_score * 0.40) +
        (shadow_res.overconfidence_index * 0.30) +
        ((1.0 - grounding_res.grounding_score) * 0.20) +
        (bias_res.variance_score * 0.10),
        3
    )

    if tier1_res.has_rbac_violation or tier1_res.has_prompt_injection or risk_score >= config.thresholds.max_risk_score:
        action = "BLOCKED"
        decision_reason = "High safety risk or hierarchical access violation detected."
    elif len(flags) > 0 or shadow_res.confidence_score < config.thresholds.min_confidence_score:
        action = "FLAGGED"
        decision_reason = "Potential overconfidence, privacy leak, or low confidence flagged for review."
    else:
        action = "ALLOWED"
        decision_reason = "Response satisfies performance, privacy, and governance thresholds."

    latency_ms = round((time.time() - start_time) * 1000, 2)

    # 6. Pillar 2: Cost Effectiveness & Compute Telemetry Calculation
    prompt_tokens = len(req.prompt.split())
    response_tokens = len((req.response or "").split())
    shadow_tokens = len(text_to_eval.split())

    main_cost = (prompt_tokens + response_tokens) * (config.costs.main_model_cost_per_m_tokens / 1_000_000)
    shadow_cost = shadow_tokens * (config.costs.shadow_model_cost_per_m_tokens / 1_000_000)
    total_cost_usd = round(main_cost + shadow_cost, 6)

    # Savings from early flagging/blocking compared to full downstream execution
    compute_savings_usd = round(main_cost * 1.5, 6) if action in ["BLOCKED", "FLAGGED"] else 0.0

    cost_metrics = {
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "shadow_tokens": shadow_tokens,
        "main_model_cost_usd": round(main_cost, 6),
        "shadow_model_cost_usd": round(shadow_cost, 6),
        "total_cost_usd": total_cost_usd,
        "compute_savings_usd": compute_savings_usd
    }

    # Record Audit Entry in Ledger
    ledger.record(AuditLogEntry(
        prompt=req.prompt,
        response=req.response,
        action=action,
        decision_reason=decision_reason,
        confidence_score=shadow_res.confidence_score,
        risk_score=risk_score,
        grounding_score=grounding_res.grounding_score,
        bias_variance=bias_res.variance_score,
        flags=flags,
        has_pii=tier1_res.has_pii,
        has_prompt_injection=tier1_res.has_prompt_injection,
        latency_ms=latency_ms
    ))

    return ProxyEvaluationResponse(
        action=action,
        decision_reason=decision_reason,
        confidence_score=shadow_res.confidence_score,
        risk_score=risk_score,
        overconfidence_index=shadow_res.overconfidence_index,
        token_divergence_score=shadow_res.mean_token_divergence,
        grounding_score=grounding_res.grounding_score,
        bias_variance=bias_res.variance_score,
        flags=flags,
        cost_metrics=cost_metrics,
        latency_ms=latency_ms
    )


@app.get("/metrics", response_model=AggregateMetrics)
def get_metrics():
    """Retrieve real-time aggregate telemetry metrics from the audit ledger."""
    return ledger.get_metrics()


@app.get("/logs", response_model=List[AuditLogEntry])
def get_audit_logs(
    limit: int = Query(default=50, ge=1, le=500),
    action: Optional[str] = Query(default=None, description="Filter by action ('ALLOWED', 'FLAGGED', 'BLOCKED')")
):
    """Retrieve audit logs stored in the ledger."""
    return ledger.get_logs(limit=limit, action_filter=action)


if __name__ == "__main__":
    import uvicorn
    import subprocess
    import sys

    # Launch the Streamlit dashboard as a background process (bypassing the email prompt)
    print("🚀 Launching ControlPlane Dashboard...")
    subprocess.Popen([sys.executable, "-m", "streamlit", "run", "dashboard.py", "--server.headless=true", "--browser.gatherUsageStats=false"])

    # Run the FastAPI server without reload to avoid spawning multiple dashboard processes
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
