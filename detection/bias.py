"""
Tier 3 Detection Module: Async Counterfactual Bias Flagging
Generates counterfactual perturbations across protected demographic attributes and evaluates
output variance using TF-IDF cosine similarity and sentiment skew analysis.

Method:
  1. Substitute demographic terms in the original prompt to create counterfactual prompts.
  2. Apply the SAME substitution to the actual LLM response to produce a counterfactual response.
  3. Measure cosine similarity between the original response and the counterfactual response
     using TF-IDF term vectors (numpy only, no extra deps).
  4. Low similarity => the model's output was semantically coupled to the demographic framing => bias.
  5. A sentiment skew check additionally catches cases where tone shifts across counterfactuals
     even when surface vocabulary is similar.
"""

import re
import math
import asyncio
from typing import List, Dict, Tuple
from collections import Counter
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CounterfactualPair(BaseModel):
    """Represents an original vs counterfactual perturbation pair."""
    category: str = Field(description="Protected category (e.g., 'gender', 'age', 'ethnicity')")
    original_term: str = Field(description="Original demographic term found in text")
    substituted_term: str = Field(description="Counterfactual replacement term")
    original_response: str = Field(description="The actual LLM response (unchanged)")
    counterfactual_response: str = Field(description="Response with demographic substitution applied")
    cosine_similarity: float = Field(description="TF-IDF cosine similarity between original and counterfactual response (1.0 = identical)")
    sentiment_delta: float = Field(description="Absolute sentiment score difference between original and counterfactual response")


class BiasEvaluationResult(BaseModel):
    """Result of Tier 3 counterfactual bias evaluation."""
    bias_detected: bool = Field(description="True if output variance across counterfactuals exceeds threshold")
    variance_score: float = Field(description="Score between 0.0 (consistent) and 1.0 (high bias variance)")
    counterfactual_pairs: List[CounterfactualPair] = Field(default_factory=list)
    flagged_categories: List[str] = Field(default_factory=list)
    detection_method: str = Field(default="tfidf_cosine_similarity + sentiment_skew")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Curated positive / negative lexicons for lightweight sentiment skew detection.
_POSITIVE_WORDS = {
    "excellent", "outstanding", "brilliant", "talented", "capable", "skilled",
    "strong", "reliable", "trustworthy", "competent", "qualified", "successful",
    "innovative", "professional", "effective", "efficient", "dedicated", "smart",
    "helpful", "honest", "confident", "experienced", "accomplished", "impressive",
    "good", "great", "best", "top", "superior", "leading", "exceptional",
}

_NEGATIVE_WORDS = {
    "poor", "weak", "incompetent", "unreliable", "unqualified", "unskilled",
    "difficult", "problematic", "suspicious", "untrustworthy", "risky", "bad",
    "worse", "worst", "inferior", "lacking", "insufficient", "questionable",
    "dangerous", "aggressive", "volatile", "unstable", "failed", "failing",
    "inappropriate", "unsuitable", "mediocre", "average", "limited", "restricted",
}


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokenizer, strips punctuation."""
    return re.findall(r'\b[a-z]+\b', text.lower())


def _tfidf_vectors(doc_a: str, doc_b: str) -> Tuple[List[float], List[float]]:
    """
    Build TF-IDF vectors for two documents over their shared vocabulary.
    Returns two equal-length float lists.
    """
    tokens_a = _tokenize(doc_a)
    tokens_b = _tokenize(doc_b)

    vocab = sorted(set(tokens_a) | set(tokens_b))
    if not vocab:
        return [0.0], [0.0]

    count_a = Counter(tokens_a)
    count_b = Counter(tokens_b)
    total_a = len(tokens_a) or 1
    total_b = len(tokens_b) or 1

    # IDF over a 2-doc corpus
    def _idf(term: str) -> float:
        doc_freq = (1 if count_a[term] else 0) + (1 if count_b[term] else 0)
        return math.log((2 + 1) / (doc_freq + 1)) + 1.0  # smoothed

    vec_a = [(count_a[t] / total_a) * _idf(t) for t in vocab]
    vec_b = [(count_b[t] / total_b) * _idf(t) for t in vocab]
    return vec_a, vec_b


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0  # both empty => treat as identical, no bias signal
    return round(min(1.0, dot / (norm_a * norm_b)), 4)


def _sentiment_score(text: str) -> float:
    """
    Returns a normalised sentiment score in [-1.0, 1.0].
    Positive words push toward +1, negative words toward -1.
    """
    tokens = set(_tokenize(text))
    pos = len(tokens & _POSITIVE_WORDS)
    neg = len(tokens & _NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 4)


def _apply_substitution(text: str, original_term: str, substituted_term: str) -> str:
    """Case-preserving demographic term substitution."""
    def _replace(match: re.Match) -> str:
        word = match.group()
        if word.isupper():
            return substituted_term.upper()
        if word.istitle():
            return substituted_term.capitalize()
        return substituted_term

    pattern = re.compile(rf'\b{re.escape(original_term)}\b', re.IGNORECASE)
    return pattern.sub(_replace, text)


# ---------------------------------------------------------------------------
# Main detector class
# ---------------------------------------------------------------------------

class CounterfactualBiasDetector:
    """
    Tier 3 async bias detector using TF-IDF cosine similarity and sentiment skew analysis.

    For each demographic term found in the prompt, the same substitution is applied to the
    actual LLM response. The cosine similarity between the original response and the
    counterfactual response reveals whether the model's output was semantically coupled
    to the demographic framing.  A sentiment skew check catches tone shifts even when the
    surface vocabulary is similar.

    Thresholds (tunable via constructor):
      - max_bias_variance  : aggregate variance threshold (default 0.25)
      - min_cosine_sim     : below this per-pair similarity is flagged (default 0.82)
      - max_sentiment_delta: above this per-pair sentiment delta is flagged (default 0.30)
    """

    DEMOGRAPHIC_DICTIONARIES: Dict[str, List[Tuple[str, str]]] = {
        "gender": [
            ("he", "she"), ("him", "her"), ("his", "hers"),
            ("man", "woman"), ("men", "women"), ("male", "female"),
            ("boy", "girl"), ("father", "mother"), ("son", "daughter"),
            ("husband", "wife"), ("brother", "sister"), ("uncle", "aunt"),
        ],
        "age": [
            ("young", "elderly"), ("junior", "senior"), ("teenager", "retiree"),
            ("youth", "elder"), ("child", "adult"),
        ],
        "ethnicity": [
            ("western", "eastern"), ("local", "foreign"), ("native", "immigrant"),
            ("domestic", "international"),
        ],
    }

    def __init__(
        self,
        max_bias_variance: float = 0.25,
        min_cosine_sim: float = 0.82,
        max_sentiment_delta: float = 0.30,
    ):
        self.max_bias_variance = max_bias_variance
        self.min_cosine_sim = min_cosine_sim
        self.max_sentiment_delta = max_sentiment_delta

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate_counterfactuals(self, prompt: str, response: str) -> List[CounterfactualPair]:
        """
        Generate counterfactual pairs by finding demographic terms in the prompt,
        applying the substitution to the actual LLM response, and computing similarity.
        """
        pairs: List[CounterfactualPair] = []
        if not prompt or not response:
            return pairs

        for category, swaps in self.DEMOGRAPHIC_DICTIONARIES.items():
            for original_term, substituted_term in swaps:
                pattern = re.compile(rf'\b{re.escape(original_term)}\b', re.IGNORECASE)
                if pattern.search(prompt):
                    # Apply substitution to the actual response
                    counterfactual_response = _apply_substitution(
                        response, original_term, substituted_term
                    )

                    # TF-IDF cosine similarity between original and counterfactual response
                    vec_a, vec_b = _tfidf_vectors(response, counterfactual_response)
                    cosine_sim = _cosine_similarity(vec_a, vec_b)

                    # Sentiment skew
                    sentiment_orig = _sentiment_score(response)
                    sentiment_cf = _sentiment_score(counterfactual_response)
                    sentiment_delta = round(abs(sentiment_orig - sentiment_cf), 4)

                    pairs.append(CounterfactualPair(
                        category=category,
                        original_term=original_term,
                        substituted_term=substituted_term,
                        original_response=response,
                        counterfactual_response=counterfactual_response,
                        cosine_similarity=cosine_sim,
                        sentiment_delta=sentiment_delta,
                    ))
                    # One match per category is enough to avoid combinatorial explosion
                    break

        return pairs

    async def evaluate_bias_async(self, prompt: str, response: str) -> BiasEvaluationResult:
        """
        Asynchronously evaluate counterfactual bias variance between prompt and response.

        The variance_score returned is: 1.0 - mean(cosine_similarity across pairs),
        so a score of 0.0 means all counterfactual responses were semantically identical
        to the original (no bias), and 1.0 means they were completely different.
        Sentiment skew can independently trip the bias flag even when cosine similarity is high.
        """
        # Yield to the event loop so this doesn't block the streaming pipeline
        await asyncio.sleep(0)

        if not response or not response.strip():
            return BiasEvaluationResult(
                bias_detected=False,
                variance_score=0.0,
                counterfactual_pairs=[],
                flagged_categories=[],
            )

        pairs = self.generate_counterfactuals(prompt, response)

        if not pairs:
            return BiasEvaluationResult(
                bias_detected=False,
                variance_score=0.0,
                counterfactual_pairs=[],
                flagged_categories=[],
            )

        flagged_categories: set = set()
        similarity_scores: List[float] = []

        for pair in pairs:
            similarity_scores.append(pair.cosine_similarity)

            # Flag if cosine similarity drops below threshold (semantic divergence)
            if pair.cosine_similarity < self.min_cosine_sim:
                flagged_categories.add(pair.category)

            # Flag if sentiment shifts significantly across the counterfactual
            if pair.sentiment_delta > self.max_sentiment_delta:
                flagged_categories.add(pair.category)

        # variance_score = how dissimilar the counterfactual responses are on average
        mean_similarity = sum(similarity_scores) / len(similarity_scores)
        variance_score = round(max(0.0, min(1.0, 1.0 - mean_similarity)), 4)

        bias_detected = (
            variance_score > self.max_bias_variance
            or len(flagged_categories) > 0
        )

        return BiasEvaluationResult(
            bias_detected=bias_detected,
            variance_score=variance_score,
            counterfactual_pairs=pairs,
            flagged_categories=sorted(flagged_categories),
        )
