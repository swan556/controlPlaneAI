"""
Audit Ledger & Metrics Engine
Provides in-memory audit logging, request tracing, real-time security metrics, and telemetry aggregation.
"""

import time
import uuid
import threading
from typing import List, Dict, Any, Optional
from collections import deque
from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    """Structured audit record for every evaluated request."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=time.time)
    action: str = Field(description="'ALLOWED', 'REDACTED', or 'BLOCKED'")
    prompt: str
    response: Optional[str] = None
    sanitized_prompt: Optional[str] = None
    sanitized_response: Optional[str] = None
    confidence_score: float
    risk_score: float
    grounding_score: float
    bias_variance: float
    flags: List[str] = Field(default_factory=list)
    latency_ms: float = Field(description="Processing latency in milliseconds")


class AggregateMetrics(BaseModel):
    """Real-time system telemetry and threat metrics."""
    total_requests: int = 0
    allowed_count: int = 0
    redacted_count: int = 0
    blocked_count: int = 0
    pii_flags_count: int = 0
    injection_flags_count: int = 0
    grounding_failures_count: int = 0
    bias_flags_count: int = 0
    avg_confidence_score: float = 0.0
    avg_risk_score: float = 0.0
    avg_latency_ms: float = 0.0


class AuditLedger:
    """Thread-safe audit logging & analytics engine."""

    def __init__(self, max_capacity: int = 2000):
        self.max_capacity = max_capacity
        self.logs: deque = deque(maxlen=max_capacity)
        self._lock = threading.Lock()

    def record(self, entry: AuditLogEntry) -> None:
        """Add a new audit entry to the ledger."""
        with self._lock:
            self.logs.appendleft(entry)

    def get_logs(self, limit: int = 50, action_filter: Optional[str] = None) -> List[AuditLogEntry]:
        """Fetch recent audit entries with optional action filter."""
        with self._lock:
            entries = list(self.logs)
        
        if action_filter:
            entries = [e for e in entries if e.action.upper() == action_filter.upper()]

        return entries[:limit]

    def get_metrics(self) -> AggregateMetrics:
        """Compute live telemetry metrics across recorded audit logs."""
        with self._lock:
            entries = list(self.logs)

        if not entries:
            return AggregateMetrics()

        total = len(entries)
        allowed = sum(1 for e in entries if e.action == "ALLOWED")
        redacted = sum(1 for e in entries if e.action == "REDACTED")
        blocked = sum(1 for e in entries if e.action == "BLOCKED")

        pii_cnt = sum(1 for e in entries if "PII_DETECTED" in e.flags)
        inj_cnt = sum(1 for e in entries if "PROMPT_INJECTION" in e.flags)
        grd_cnt = sum(1 for e in entries if "GROUNDING_FAILED" in e.flags)
        bias_cnt = sum(1 for e in entries if "BIAS_FLAGGED" in e.flags)

        avg_conf = sum(e.confidence_score for e in entries) / total
        avg_risk = sum(e.risk_score for e in entries) / total
        avg_lat = sum(e.latency_ms for e in entries) / total

        return AggregateMetrics(
            total_requests=total,
            allowed_count=allowed,
            redacted_count=redacted,
            blocked_count=blocked,
            pii_flags_count=pii_cnt,
            injection_flags_count=inj_cnt,
            grounding_failures_count=grd_cnt,
            bias_flags_count=bias_cnt,
            avg_confidence_score=round(avg_conf, 3),
            avg_risk_score=round(avg_risk, 3),
            avg_latency_ms=round(avg_lat, 2)
        )

    def clear(self) -> None:
        """Reset all in-memory audit logs."""
        with self._lock:
            self.logs.clear()


# Global audit ledger instance
ledger = AuditLedger()
