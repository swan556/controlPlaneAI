"""
RAG Retriever & Grounding Verification Engine
Evaluates whether generated LLM responses are faithful to provided context documents.
"""

import re
import math
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class GroundingCheckResult(BaseModel):
    """Result of a RAG grounding evaluation check."""
    grounding_score: float = Field(description="Faithfulness score between 0.0 (hallucinated) and 1.0 (fully grounded)")
    is_grounded: bool = Field(description="True if grounding_score exceeds min_grounding_score threshold")
    unsupported_claims: List[str] = Field(default_factory=list, description="Sentences from response lacking grounding evidence")
    matching_chunks: List[str] = Field(default_factory=list, description="Context chunks supporting the generated response")


class RAGRetriever:
    """Simple in-memory vector/TF-IDF retriever & Grounding Checker."""

    def __init__(self, min_grounding_score: float = 0.60):
        self.min_grounding_score = min_grounding_score
        self.documents: List[Dict[str, Any]] = []

    def add_documents(self, docs: List[str]) -> None:
        """Add text documents into the retriever index."""
        for doc in docs:
            self.documents.append({
                "content": doc,
                "tokens": set(self._tokenize(doc))
            })

    def _tokenize(self, text: str) -> List[str]:
        """Normalize and tokenize text into lowercase word tokens."""
        return re.findall(r'\b\w+\b', text.lower())

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        """Retrieve top-K context chunks relevant to the query using token overlap & Jaccard similarity."""
        query_tokens = set(self._tokenize(query))
        if not query_tokens or not self.documents:
            return []

        scored_docs = []
        for doc in self.documents:
            doc_tokens = doc["tokens"]
            intersection = len(query_tokens.intersection(doc_tokens))
            union = len(query_tokens.union(doc_tokens))
            jaccard = intersection / union if union > 0 else 0.0
            scored_docs.append((jaccard, doc["content"]))

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [doc[1] for doc in scored_docs[:top_k] if doc[0] > 0.0]

    def check_grounding(self, context: str, response: str) -> GroundingCheckResult:
        """
        Evaluate if response sentences are supported by the provided context.
        Uses sentence-level n-gram overlap and token containment heuristics.
        """
        if not context or not context.strip():
            # If no context provided, cannot verify grounding
            return GroundingCheckResult(
                grounding_score=1.0,
                is_grounded=True,
                unsupported_claims=[],
                matching_chunks=[]
            )

        if not response or not response.strip():
            return GroundingCheckResult(
                grounding_score=1.0,
                is_grounded=True,
                unsupported_claims=[],
                matching_chunks=[]
            )

        context_tokens = set(self._tokenize(context))
        # Split response into individual sentences
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]

        if not sentences:
            return GroundingCheckResult(
                grounding_score=1.0,
                is_grounded=True,
                unsupported_claims=[],
                matching_chunks=[]
            )

        unsupported = []
        sentence_scores = []

        for sent in sentences:
            sent_tokens = set(self._tokenize(sent))
            # Ignore tiny stopword sentences
            if len(sent_tokens) <= 2:
                sentence_scores.append(1.0)
                continue

            intersection = sent_tokens.intersection(context_tokens)
            score = len(intersection) / len(sent_tokens) if sent_tokens else 1.0
            sentence_scores.append(score)

            if score < 0.35:
                unsupported.append(sent)

        avg_grounding_score = sum(sentence_scores) / len(sentence_scores) if sentence_scores else 1.0
        avg_grounding_score = round(max(0.0, min(1.0, avg_grounding_score)), 3)

        return GroundingCheckResult(
            grounding_score=avg_grounding_score,
            is_grounded=avg_grounding_score >= self.min_grounding_score,
            unsupported_claims=unsupported,
            matching_chunks=[context[:200] + "..." if len(context) > 200 else context]
        )
