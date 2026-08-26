"""
ControlPlane Configuration Module
Defines configurable confidence thresholds, risk weights, model identifiers, and system parameters.
"""

from enum import IntEnum
from typing import Dict
from pydantic import BaseModel, Field


class UserRole(IntEnum):
    """Hierarchical user access roles."""
    GUEST = 1
    EMPLOYEE = 2
    MANAGER = 3
    EXECUTIVE = 4


class DocumentClassification(IntEnum):
    """Security classification levels for company data."""
    PUBLIC = 1
    INTERNAL = 2
    RESTRICTED = 3
    CONFIDENTIAL = 4


class RiskWeights(BaseModel):
    """Weights for calculating composite risk scores across detection tiers."""
    privacy_pii_weight: float = Field(default=0.35, description="Weight for PII exposure risk")
    rbac_violation_weight: float = Field(default=0.35, description="Weight for Hierarchical Access Violation")
    overconfidence_weight: float = Field(default=0.20, description="Weight for high token divergence / overconfidence")
    grounding_weight: float = Field(default=0.10, description="Weight for low RAG grounding score")


class ConfidenceThresholds(BaseModel):
    """Threshold limits for safety enforcement and proxy decisions."""
    min_confidence_score: float = Field(default=0.70, description="Minimum allowed SLM confidence score")
    max_risk_score: float = Field(default=0.65, description="Maximum allowed aggregate risk score before blocking")
    min_grounding_score: float = Field(default=0.60, description="Minimum required grounding faithfulness score")
    max_token_divergence: float = Field(default=0.45, description="Maximum allowed token stream divergence")


class ModelCostConfig(BaseModel):
    """Cost rates per 1,000,000 tokens for telemetry calculation."""
    main_model_name: str = "Mistral-7B-Instruct-v0.2"
    main_model_cost_per_m_tokens: float = 0.60  # $0.60 per 1M tokens
    shadow_model_name: str = "SmolLM2-135M-Instruct"
    shadow_model_cost_per_m_tokens: float = 0.02  # $0.02 per 1M tokens


class ShadowEngineConfig(BaseModel):
    """Configuration for the SmolLM2 shadow evaluation engine."""
    model_name: str = Field(default="HuggingFaceTB/SmolLM2-135M-Instruct", description="HuggingFace model ID")
    device: str = Field(default="auto", description="Device to load model on ('cpu', 'cuda', 'auto')")
    max_length: int = Field(default=512, description="Max token length for perplexity calculation")
    use_fallback: bool = Field(default=True, description="Enable fast local fallback when model is unreachable")


class ControlPlaneConfig(BaseModel):
    """Master ControlPlane configuration object."""
    environment: str = "production"
    debug: bool = False
    port: int = 8000
    thresholds: ConfidenceThresholds = Field(default_factory=ConfidenceThresholds)
    risk_weights: RiskWeights = Field(default_factory=RiskWeights)
    costs: ModelCostConfig = Field(default_factory=ModelCostConfig)
    shadow: ShadowEngineConfig = Field(default_factory=ShadowEngineConfig)


# Global default configuration instance
config = ControlPlaneConfig()

