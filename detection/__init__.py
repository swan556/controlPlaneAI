"""
Detection Package: Tier 1 Heuristics & Tier 3 Bias Evaluation
"""
from .heuristics import HeuristicDetector, HeuristicDetectionResult
from .bias import CounterfactualBiasDetector, BiasEvaluationResult

__all__ = [
    "HeuristicDetector",
    "HeuristicDetectionResult",
    "CounterfactualBiasDetector",
    "BiasEvaluationResult"
]
