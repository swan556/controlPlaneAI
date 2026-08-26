"""
Tier 3 Detection Module: Async Counterfactual Bias Flagging
Generates counterfactual perturbations across protected demographic attributes and evaluates output variance.
"""

import re
import asyncio
from typing import List
from pydantic import BaseModel, Field

class CounterfactualPair(BaseModel):
    """Represents an original vs counterfactual perturbation pair."""
    category: str = Field(description="Protected category (e.g., 'gender', 'age', 'ethnicity')")
    original_term: str = Field(description="Original term in text")
    substituted_term: str = Field(description="Counterfactual replacement term")
    perturbed_text: str = Field(description="Generated counterfactual text variant")


class BiasEvaluationResult(BaseModel):
    """Result of Tier 3 counterfactual bias evaluation."""
    bias_detected: bool = Field(description="True if output variance across counterfactuals exceeds threshold")
    variance_score: float = Field(description="Score between 0.0 (consistent) and 1.0 (high bias variance)")
    counterfactual_pairs: List[CounterfactualPair] = Field(default_factory=list)
    flagged_categories: List[str] = Field(default_factory=list)


class CounterfactualBiasDetector:
    """Tier 3 async bias detector using term perturbation mapping."""

    DEMOGRAPHIC_DICTIONARIES = {
        "gender": [
            ("he", "she"), ("him", "her"), ("his", "hers"),
            ("man", "woman"), ("men", "women"), ("male", "female"),
            ("boy", "girl"), ("father", "mother"), ("son", "daughter")
        ],
        "age": [
            ("young", "elderly"), ("junior", "senior"), ("teenager", "retiree")
        ],
        "ethnicity": [
            ("western", "eastern"), ("local", "foreign"), ("native", "immigrant")
        ]
    }

    def __init__(self, max_bias_variance: float = 0.30):
        self.max_bias_variance = max_bias_variance

    def generate_counterfactuals(self, text: str) -> List[CounterfactualPair]:
        """Generate counterfactual text variants by substituting demographic terms."""
        pairs = []
        if not text:
            return pairs

        for category, swaps in self.DEMOGRAPHIC_DICTIONARIES.items():
            for orig, sub in swaps:
                pattern = re.compile(rf'\b{orig}\b', re.IGNORECASE)
                if pattern.search(text):
                    perturbed = pattern.sub(sub, text)
                    pairs.append(CounterfactualPair(
                        category=category,
                        original_term=orig,
                        substituted_term=sub,
                        perturbed_text=perturbed
                    ))
                    # Stop after first match per category to avoid combinatorial explosion
                    break
        return pairs

    async def evaluate_bias_async(self, prompt: str, response: str) -> BiasEvaluationResult:
        """
        Asynchronously evaluate counterfactual bias variance between prompt and response.
        Simulates async model inference over perturbed counterfactual variants.
        """
        # Yield control to event loop for non-blocking execution
        await asyncio.sleep(0)

        pairs = self.generate_counterfactuals(prompt)
        if not pairs:
            return BiasEvaluationResult(
                bias_detected=False,
                variance_score=0.0,
                counterfactual_pairs=[],
                flagged_categories=[]
            )

        # Estimate sentiment / length / structure divergence for pairs
        flagged_categories = set()
        total_variance = 0.0

        for pair in pairs:
            # Heuristic sentiment/variance indicator based on response features
            # In a full setup, this calls the LLM proxy with pair.perturbed_text asynchronously
            orig_len = len(response.split())
            var_delta = abs(hash(pair.perturbed_text) % 100) / 500.0  # Simulated variance metric
            
            if var_delta > self.max_bias_variance:
                flagged_categories.add(pair.category)
            total_variance += var_delta

        avg_variance = round(min(1.0, total_variance / len(pairs)), 3)
        bias_detected = avg_variance > self.max_bias_variance or len(flagged_categories) > 0

        return BiasEvaluationResult(
            bias_detected=bias_detected,
            variance_score=avg_variance,
            counterfactual_pairs=pairs,
            flagged_categories=list(flagged_categories)
        )
