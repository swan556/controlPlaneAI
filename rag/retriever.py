"""
RAG Retriever & Policy Compliance Engine
Evaluates whether LLM responses are faithful to provided context documents AND
whether they violate explicit policy prohibitions extracted from policy documents.

Key improvements over the previous version:
  1. Section Chunking     — policy documents are indexed per Markdown section (## heading),
                            not as a single blob, so retrieval is precise and targeted.
  2. Prohibition Extraction — each section's explicit "must not / never / DO NOT" rules are
                              parsed and stored as structured prohibition rules.
  3. Contextual Relevance Gate — if the prompt doesn't match any policy section above a
                                  minimum relevance threshold, grounding returns True immediately
                                  (no false-positives for general questions unrelated to policy).
  4. Policy Violation Detection — checks if the LLM response affirmatively does something that
                                   a relevant policy section explicitly forbids.
"""

import re
import math
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic result models
# ---------------------------------------------------------------------------

class GroundingCheckResult(BaseModel):
    """Result of a RAG grounding / policy compliance evaluation."""
    grounding_score: float = Field(description="Faithfulness score 0.0 (hallucinated) → 1.0 (grounded)")
    is_grounded: bool = Field(description="False if a policy violation or hallucination is detected")
    policy_violated: bool = Field(default=False, description="True if a prohibition rule was explicitly breached")
    violated_rule: Optional[str] = Field(default=None, description="The exact prohibition rule that was breached")
    violated_section: Optional[str] = Field(default=None, description="Policy section title containing the violated rule")
    unsupported_claims: List[str] = Field(default_factory=list, description="Sentences lacking grounding evidence")
    matching_chunks: List[str] = Field(default_factory=list, description="Context chunks supporting the response")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Stopwords excluded when extracting key terms from prohibition sentences.
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "and", "or", "in", "for", "on", "at", "by", "with", "from",
    "that", "this", "they", "it", "he", "she", "we", "you", "i", "not",
    "do", "does", "did", "will", "would", "could", "should", "may", "must",
    "shall", "can", "after", "before", "during", "their", "all", "any",
    "only", "if", "when", "where", "how", "than", "then", "but", "so",
    "nor", "as", "up", "out", "about", "into", "through", "over", "such",
    "no", "its", "our", "your", "my", "who", "which", "what",
}

# Trigger keywords indicating a sentence contains an explicit prohibition rule.
_PROHIBITION_TRIGGERS = [
    "must not", "must never", "never", "do not", "don't", "cannot", "can not",
    "prohibited", "forbidden", "strictly forbidden", "strictly prohibited",
    "not allowed", "not permitted", "not offer", "not provide", "not support",
    "not recommend", "not disclose", "not share", "not export", "not install",
    "not use", "not register", "will not", "shall not", "do not offer",
    "is not", "are not", "may not",
]

# Affirmative intent signals in an LLM response that suggest it is doing the prohibited action.
_AFFIRMATIVE_SIGNALS = [
    "i can", "i will", "i'll", "i'd be happy", "sure", "of course", "happy to",
    "let me", "certainly", "absolutely", "yes,", "yes!", "here is", "here's",
    "step", "steps", "please follow", "to troubleshoot", "to help", "to assist",
    "i can assist", "i can help", "i can support", "i can guide", "i can provide",
    "to fix", "to resolve", "here are", "to proceed", "let's", "first,",
    "absolutely", "no problem", "my pleasure", "glad to",
]

# Synonym expansion: maps common LLM response words back to policy vocabulary.
# Used in prohibition matching so 'help' counts as evidence of 'support/offer',
# 'device' counts as 'router/modem', third-party brand names count as 'third-party'.
_SYNONYM_EXPANSIONS = {
    # return / refund synonyms
    "return":         ["refund", "refunds", "returns", "returned", "money", "cancellation"],
    "returns":        ["refund", "refunds", "return", "returned", "money"],
    "refund":         ["refunds", "return", "returns", "returned", "money", "prorated"],
    "refunds":        ["refund", "return", "returns", "returned", "money", "prorated"],
    "cancel":         ["cancellation", "cancelling", "cancelled", "subscription", "downgrade"],
    "cancellation":   ["cancel", "cancelling", "cancelled", "subscription", "downgrade"],
    "pricing":        ["price", "cost", "plan", "plans", "subscription", "starter", "business", "enterprise", "billing", "bill"],
    "price":          ["pricing", "cost", "plan", "plans", "subscription", "starter", "business", "enterprise", "billing", "bill"],
    "cost":           ["pricing", "price", "plan", "plans", "subscription", "starter", "business", "enterprise", "billing", "bill"],
    "plan":           ["plans", "subscription", "starter", "business", "enterprise", "pricing", "tier"],
    "plans":          ["plan", "subscription", "starter", "business", "enterprise", "pricing", "tier"],
    "trial":          ["trials", "free", "business"],
    # support / offer synonyms
    "help":           ["support", "offer", "assist", "guide"],
    "assist":         ["support", "offer", "help"],
    "fix":            ["troubleshoot", "support"],
    "resolve":        ["troubleshoot", "support"],
    "reset":          ["troubleshoot"],
    "guide":          ["support"],
    "walk":           ["support"],
    # device / hardware synonyms
    "device":         ["router", "modem", "hardware", "equipment"],
    "router":         ["routers", "modem"],
    "hardware":       ["equipment", "edge", "router"],
    "netgear":        ["third", "party", "routers"],
    "asus":           ["third", "party", "routers"],
    "tp-link":        ["third", "party", "routers"],
    "linksys":        ["third", "party", "routers"],
    "dlink":          ["third", "party", "routers"],
    "amazon":         ["third", "party"],
    # data / privacy synonyms
    "salary":         ["compensation", "salary", "pay", "wage"],
    "pay":            ["salary", "compensation", "wage"],
    "wage":           ["salary", "compensation", "pay"],
    "share":          ["disclose", "shared", "reveal"],
    "tell":           ["disclose", "shared", "reveal"],
    "reveal":         ["disclose", "shared", "tell"],
    "give":           ["provide", "shared"],
    "wifi":           ["wi-fi", "public"],
    "wireless":       ["wi-fi"],
    "bar":            ["alcohol"],
    "drink":          ["alcohol"],
    "beer":           ["alcohol"],
    "wine":           ["alcohol"],
    "liquor":         ["alcohol"],
    # product announcement synonyms
    "planning":       ["upcoming", "unannounced"],
    "plan":           ["upcoming", "unannounced"],
    "launching":      ["upcoming", "unannounced"],
    "launch":         ["upcoming", "unannounced"],
    "releasing":      ["upcoming", "unannounced"],
    "release":        ["upcoming", "unannounced"],
    "new":            ["upcoming", "unannounced"],
    "announce":       ["disclose", "upcoming"],
    "announcing":     ["disclose", "upcoming"],
    "feature":        ["features", "unannounced", "capabilities"],
    "product":        ["features", "unannounced", "cloud", "edge", "monitor", "api", "backup"],
}


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokenizer."""
    return re.findall(r'\b[a-z0-9]+\b', text.lower())


def _key_terms(text: str) -> set:
    """Return content words (non-stopword tokens) from text."""
    return set(_tokenize(text)) - _STOPWORDS


def _split_sentences(text: str) -> List[str]:
    """Split text into individual sentences, handling newline bullets too."""
    # Split on sentence boundaries and newline bullet points
    raw = re.split(r'(?<=[.!?])\s+|\n[-•*]\s*', text)
    return [s.strip().lstrip("-•* ") for s in raw if s.strip()]


def _jaccard(tokens_a: set, tokens_b: set) -> float:
    union = len(tokens_a | tokens_b)
    return len(tokens_a & tokens_b) / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# RAGRetriever
# ---------------------------------------------------------------------------

class RAGRetriever:
    """
    Policy-aware RAG retriever with section chunking and prohibition enforcement.

    Usage:
        retriever = RAGRetriever()
        retriever.add_policy_document(policy_markdown_text)   # for policy docs
        retriever.add_documents([some_other_context])          # for general docs
        result = retriever.check_policy_compliance(prompt, llm_response)
    """

    def __init__(
        self,
        min_grounding_score: float = 0.60,
        min_retrieval_relevance: float = 0.04,
    ):
        self.min_grounding_score = min_grounding_score
        # Minimum Jaccard relevance for a policy section to be considered applicable.
        # Below this, the query is treated as unrelated to policy → no false-positives.
        self.min_retrieval_relevance = min_retrieval_relevance

        # General (non-policy) documents
        self.documents: List[Dict[str, Any]] = []
        # Structured policy section chunks
        self.policy_sections: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def add_documents(self, docs: List[str]) -> None:
        """Add generic text documents to the retrieval index."""
        for doc in docs:
            self.documents.append({
                "content": doc,
                "tokens": set(_tokenize(doc)),
            })

    def add_policy_document(self, policy_text: str) -> None:
        """
        Parse a Markdown policy document and index it section by section.

        Each ## heading creates an isolated PolicySection chunk with:
          - title        : the heading text
          - content      : the section body
          - tokens       : tokenized content set (for Jaccard retrieval)
          - prohibitions : list of explicit prohibition rule sentences extracted
                           from this section
        """
        # Split on Markdown ## headings (keep the heading text with its content)
        raw_sections = re.split(r'^##\s+', policy_text, flags=re.MULTILINE)

        for raw in raw_sections:
            raw = raw.strip()
            if not raw:
                continue

            lines = raw.split('\n')
            title = lines[0].strip()
            body = '\n'.join(lines[1:]).strip() if len(lines) > 1 else raw

            if not body:
                continue

            prohibitions = self._extract_prohibitions(body)
            full_section_text = f"## {title}\n{body}"
            title_tokens = set(_tokenize(title)) - _STOPWORDS
            body_tokens = set(_tokenize(body)) - _STOPWORDS

            self.policy_sections.append({
                "title": title,
                "content": full_section_text,
                "title_tokens": title_tokens,
                "body_tokens": body_tokens,
                "tokens": title_tokens | body_tokens,
                "prohibitions": prohibitions,
            })

    def _extract_prohibitions(self, section_text: str) -> List[str]:
        """
        Extract sentences from a section that express explicit prohibition rules.
        Uses keyword trigger matching to identify "must not", "never", "DO NOT" etc.
        """
        sentences = _split_sentences(section_text)
        prohibitions = []
        for sent in sentences:
            lower = sent.lower()
            if any(trigger in lower for trigger in _PROHIBITION_TRIGGERS):
                prohibitions.append(sent)
        return prohibitions

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        """
        Retrieve top-K relevant context strings for a query using relevance-weighted term matching.
        """
        query_raw_tokens = set(_tokenize(query))
        query_key = query_raw_tokens - _STOPWORDS
        if not query_key:
            query_key = query_raw_tokens
        if not query_key:
            return []

        expanded_query: set = set(query_key)
        for t in query_key:
            if t in _SYNONYM_EXPANSIONS:
                expanded_query.update(_SYNONYM_EXPANSIONS[t])

        scored: List[Tuple[float, str]] = []

        for sec in self.policy_sections:
            title_matches = len(expanded_query & sec.get("title_tokens", set()))
            body_matches = len(expanded_query & sec.get("body_tokens", sec["tokens"]))
            
            # Stem / prefix matches
            stem_matches = 0
            for qt in expanded_query:
                if len(qt) >= 4:
                    if any(st.startswith(qt[:4]) for st in sec["tokens"]):
                        stem_matches += 0.5

            score = (title_matches * 3.5) + body_matches + stem_matches
            if score > 0:
                scored.append((score, sec["content"]))

        for doc in self.documents:
            doc_tokens = doc["tokens"] - _STOPWORDS
            matches = len(expanded_query & doc_tokens)
            if matches > 0:
                scored.append((float(matches), doc["content"]))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [content for _, content in scored[:top_k]]

    def _retrieve_sections_with_scores(
        self, query: str, top_k: int = 3
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """Internal: return (score, section_dict) pairs for policy sections."""
        query_raw_tokens = set(_tokenize(query))
        query_key = query_raw_tokens - _STOPWORDS
        if not query_key:
            query_key = query_raw_tokens
        if not query_key:
            return []

        expanded_query: set = set(query_key)
        for t in query_key:
            if t in _SYNONYM_EXPANSIONS:
                expanded_query.update(_SYNONYM_EXPANSIONS[t])

        scored = []
        for sec in self.policy_sections:
            title_matches = len(expanded_query & sec.get("title_tokens", set()))
            body_matches = len(expanded_query & sec.get("body_tokens", sec["tokens"]))
            stem_matches = 0
            for qt in expanded_query:
                if len(qt) >= 4:
                    if any(st.startswith(qt[:4]) for st in sec["tokens"]):
                        stem_matches += 0.5
            score = (title_matches * 3.5) + body_matches + stem_matches
            if score > 0:
                scored.append((score, sec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Policy violation detection
    # ------------------------------------------------------------------

    def _check_prohibition_violation(
        self, response: str, prohibitions: List[str]
    ) -> Optional[str]:
        """
        Determine if the LLM response is doing something that a prohibition rule forbids.

        Logic:
          For each prohibition rule:
            1. Extract key SUBJECT/OBJECT terms from the rule (filter out qualifier words
               like 'never', 'strictly', 'confidential' that describe the prohibition
               itself rather than the prohibited topic).
            2. Use substring matching (handles plurals / verb inflections).
            3. If enough subject terms appear in the response AND the response is
               affirmative in tone → flag as violation.
        """
        response_lower = response.lower()
        has_affirmative = any(signal in response_lower for signal in _AFFIRMATIVE_SIGNALS)

        # Build an expanded set of terms: actual response tokens + their policy-vocab synonyms.
        # e.g. if response contains 'help', add 'support'/'offer'; 'netgear' adds 'third'/'party'/'routers'
        response_tokens = set(_tokenize(response_lower))
        expanded_response_terms: set = set(response_tokens)
        for token in response_tokens:
            if token in _SYNONYM_EXPANSIONS:
                expanded_response_terms.update(_SYNONYM_EXPANSIONS[token])

        # Words that describe the prohibition itself — not useful for topic matching
        _qualifier_words = {
            "never", "strictly", "must", "not", "confidential", "prohibited",
            "forbidden", "unauthorized", "unauthorized", "illegal", "external",
            "shared", "exported", "permitted", "allowed", "restricted",
        }

        for rule in prohibitions:
            # Use only meaningful subject/object terms (drop qualifiers and stopwords)
            rule_terms = _key_terms(rule) - _qualifier_words
            if len(rule_terms) < 2:
                continue

            matched_terms = 0
            for rule_term in rule_terms:
                # Direct match against expanded response vocabulary
                if rule_term in expanded_response_terms:
                    matched_terms += 1
                    continue
                # Prefix match against raw response text for morphological variants
                # (e.g. rule term 'troubleshooting' matched by 'troubleshoot' in response)
                found = False
                for prefix_len in range(len(rule_term) - 1, 4, -1):
                    if rule_term[:prefix_len] in response_lower:
                        found = True
                        break
                if found:
                    matched_terms += 1

            overlap_ratio = matched_terms / len(rule_terms)

            # Violation: enough subject-matter overlap + affirmative response tone.
            # Threshold of 0.35 balances precision (avoiding false positives on valid
            # in-scope responses) vs recall (catching real policy breaches).
            if overlap_ratio >= 0.35 and has_affirmative:
                return rule

        return None

    # ------------------------------------------------------------------
    # Pre-flight prompt intent check
    # ------------------------------------------------------------------

    def check_prompt_intent(self, prompt: str) -> GroundingCheckResult:
        """
        Pre-flight policy check: evaluates whether the user's PROMPT is requesting
        something that policy documents explicitly prohibit, BEFORE calling the LLM.

        This catches prompts like "reveal the employee data" or "what are the salaries"
        by matching the prompt's intent against prohibition rules in policy sections.

        Returns a GroundingCheckResult with policy_violated=True if the prompt
        semantically targets a prohibited topic.
        """
        # Retrieve policy sections relevant to the prompt
        scored_sections = self._retrieve_sections_with_scores(prompt, top_k=3)

        if not scored_sections or scored_sections[0][0] < self.min_retrieval_relevance:
            # Prompt is unrelated to any policy — no pre-flight block
            return GroundingCheckResult(
                grounding_score=1.0,
                is_grounded=True,
                policy_violated=False,
            )

        # Check if the prompt is asking for something a policy section prohibits.
        # We treat the prompt as if it were an "affirmative response" — i.e., if
        # the user is asking for X, and X is prohibited, flag it.
        prompt_lower = prompt.lower()
        prompt_tokens = set(_tokenize(prompt_lower))
        expanded_prompt_terms: set = set(prompt_tokens)
        for token in prompt_tokens:
            if token in _SYNONYM_EXPANSIONS:
                expanded_prompt_terms.update(_SYNONYM_EXPANSIONS[token])

        # Intent signals that suggest the user is requesting/probing for data
        _request_signals = [
            "what", "tell", "show", "give", "list", "reveal", "display",
            "provide", "share", "get", "fetch", "dump", "extract", "output",
            "print", "how much", "who", "which", "where",
        ]
        has_request_intent = any(signal in prompt_lower for signal in _request_signals)

        if not has_request_intent:
            return GroundingCheckResult(
                grounding_score=1.0,
                is_grounded=True,
                policy_violated=False,
            )

        # Words that describe the prohibition itself — not useful for topic matching
        _qualifier_words = {
            "never", "strictly", "must", "not", "confidential", "prohibited",
            "forbidden", "unauthorized", "illegal", "external",
            "shared", "exported", "permitted", "allowed", "restricted",
        }

        for _relevance_score, section in scored_sections:
            for rule in section.get("prohibitions", []):
                rule_terms = _key_terms(rule) - _qualifier_words
                if len(rule_terms) < 2:
                    continue

                matched_terms = 0
                for rule_term in rule_terms:
                    if rule_term in expanded_prompt_terms:
                        matched_terms += 1
                        continue
                    # Prefix match for morphological variants
                    found = False
                    for prefix_len in range(len(rule_term) - 1, 4, -1):
                        if rule_term[:prefix_len] in prompt_lower:
                            found = True
                            break
                    if found:
                        matched_terms += 1

                overlap_ratio = matched_terms / len(rule_terms)

                # Lower threshold than response-level check (0.30 vs 0.35)
                # because prompts are shorter and have fewer terms to match on
                if overlap_ratio >= 0.30:
                    return GroundingCheckResult(
                        grounding_score=0.0,
                        is_grounded=False,
                        policy_violated=True,
                        violated_rule=rule,
                        violated_section=section["title"],
                        unsupported_claims=[prompt[:300]],
                        matching_chunks=[section["content"][:200] + "..."],
                    )

        return GroundingCheckResult(
            grounding_score=1.0,
            is_grounded=True,
            policy_violated=False,
        )

    # ------------------------------------------------------------------
    # Public grounding / compliance API
    # ------------------------------------------------------------------

    def check_policy_compliance(self, prompt: str, response: str) -> GroundingCheckResult:
        """
        Primary policy enforcement method for streaming guardrails.

        Steps:
          1. Retrieve the most relevant policy sections for the (prompt + response) query.
          2. Contextual relevance gate: if no section is relevant enough
             (jaccard < min_retrieval_relevance), return is_grounded=True immediately.
             This prevents false-positives on general questions unrelated to policy.
          3. Check whether the response violates any prohibition rule in the relevant sections.
          4. If no violation is found, run a sentence-level grounding check as a final pass.
        """
        # Step 1: Retrieve relevant policy sections
        combined_query = f"{prompt} {response}"
        scored_sections = self._retrieve_sections_with_scores(combined_query, top_k=3)

        # Step 2: Contextual relevance gate
        if not scored_sections or scored_sections[0][0] < self.min_retrieval_relevance:
            return GroundingCheckResult(
                grounding_score=1.0,
                is_grounded=True,
                policy_violated=False,
            )

        # Step 3: Prohibition violation check against relevant sections
        for relevance_score, section in scored_sections:
            violated_rule = self._check_prohibition_violation(
                response, section["prohibitions"]
            )
            if violated_rule:
                return GroundingCheckResult(
                    grounding_score=0.0,
                    is_grounded=False,
                    policy_violated=True,
                    violated_rule=violated_rule,
                    violated_section=section["title"],
                    unsupported_claims=[response[:300]],
                    matching_chunks=[section["content"][:200] + "..."],
                )

        # Step 4: Grounding check against best matching section
        best_context = scored_sections[0][1]["content"]
        return self.check_grounding(context=best_context, response=response)

    def check_grounding(self, context: str, response: str) -> GroundingCheckResult:
        """
        Sentence-level grounding check: evaluates whether response sentences are
        supported by the provided context using token containment heuristics.
        Preserved for backward compatibility with the /evaluate endpoint.
        """
        if not context or not context.strip():
            return GroundingCheckResult(
                grounding_score=1.0,
                is_grounded=True,
                unsupported_claims=[],
                matching_chunks=[],
            )

        if not response or not response.strip():
            return GroundingCheckResult(
                grounding_score=1.0,
                is_grounded=True,
                unsupported_claims=[],
                matching_chunks=[],
            )

        context_tokens = set(_tokenize(context))
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]

        if not sentences:
            return GroundingCheckResult(
                grounding_score=1.0,
                is_grounded=True,
                unsupported_claims=[],
                matching_chunks=[],
            )

        unsupported = []
        sentence_scores = []

        for sent in sentences:
            sent_tokens = set(_tokenize(sent))
            if len(sent_tokens) <= 2:
                sentence_scores.append(1.0)
                continue

            intersection = sent_tokens & context_tokens
            score = len(intersection) / len(sent_tokens) if sent_tokens else 1.0

            # Strict numerical hallucination check: numbers in the response
            # that don't appear anywhere in the context are a strong signal of fabrication.
            numbers_in_sent = re.findall(r'\b\d+\b', sent)
            for num in numbers_in_sent:
                if num not in context:
                    score = 0.0
                    break

            sentence_scores.append(score)
            if score < 0.35:
                unsupported.append(sent)

        avg_score = sum(sentence_scores) / len(sentence_scores) if sentence_scores else 1.0
        avg_score = round(max(0.0, min(1.0, avg_score)), 3)

        return GroundingCheckResult(
            grounding_score=avg_score,
            is_grounded=avg_score >= self.min_grounding_score,
            unsupported_claims=unsupported,
            matching_chunks=[context[:200] + "..." if len(context) > 200 else context],
        )
