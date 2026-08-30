"""
Tier 1 Detection Module: PII, Privacy Leakage, & Hierarchical RBAC Heuristics
Fast regex-based pattern matching and rule engines for detecting sensitive data leakage and access control violations.
"""

import re
import unicodedata
import difflib
from typing import List, Optional
from pydantic import BaseModel, Field
from config import UserRole, DocumentClassification


class HeuristicDetectionResult(BaseModel):
    """Result of Tier 1 heuristic & RBAC analysis."""
    has_pii: bool = Field(description="True if PII or privacy leakage patterns were detected")
    detected_pii_types: List[str] = Field(default_factory=list, description="Categories of PII or privacy data found")
    pii_matches_count: int = Field(default=0, description="Total count of PII occurrences")
    has_prompt_injection: bool = Field(description="True if prompt injection / jailbreak patterns were flagged")
    injection_vector_types: List[str] = Field(default_factory=list, description="Categories of prompt injection flagged")
    has_rbac_violation: bool = Field(default=False, description="True if user role lacks permission for document classification")
    rbac_details: Optional[str] = Field(default=None, description="Explanation of role access violation")
    sanitized_text: str = Field(description="Raw text (unmodified as flagging-only is enabled)")
    tier1_risk_score: float = Field(description="Composite Tier 1 risk score between 0.0 and 1.0")


class HeuristicDetector:
    """Tier 1 guardrail detector for PII, Privacy Leakage, & Hierarchical RBAC."""

    # PII and Confidential Data Regex patterns
    PII_PATTERNS = {
        "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
        "SSN": r'\b(?!000|666)[0-8]\d{2}[- ]?(?!00)\d{2}[- ]?(?!0000)\d{4}\b',
        "CREDIT_CARD": r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b',
        "PHONE_NUMBER": r'\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b',
        "API_KEY": r'\b(?:sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|bearer\s+[A-Za-z0-9._\-]{20,})\b',
        "INTERNAL_SALARY_DATA": r'\b(salary|compensation|bonus\s+pool|stock\s+options)\s*[:=]\s*\$?\d+[\d,]*\b',
        "CONFIDENTIAL_MARKING": r'\b(confidential|internal\s+only|do\s+not\s+distribute|top\s+secret|restricted\s+data)\b',

        # --- HR & Employee Record PII (catches structured data card dumps) ---

        # Employee ID in any common format: EMP001, EMP-4821, E-12345, ID: EMP..., Employee ID: ...
        "EMPLOYEE_ID": (
            r'\b(employee\s*(?:id|number|no|#)\s*[:=]?\s*[A-Z0-9\-]{2,12})'
            r'|\b(emp[-]?\d+[A-Z0-9]{0,6})\b'
            r'|\b([Ee]-\d{3,8})\b'
        ),

        # Labeled HR fields: "Name:", "Full Name:", "Department:", "Division:",
        # "Current Role:", "Job Title:", "Position:", "Designation:"
        "HR_DATA_FIELD": (
            r'\b(full\s+name|employee\s+name|name)\s*[:=]\s*[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+'
            r'|\b(department|division|business\s+unit|team)\s*[:=]\s*\w[\w\s]{1,40}'
            r'|\b(current\s+role|job\s+title|position|designation|title|role)\s*[:=]\s*\w[\w\s]{1,50}'
            r'|\b(manager|reporting\s+to|direct\s+report|supervisor)\s*[:=]\s*[A-Z][a-zA-Z\s]{2,40}'
            r'|\b(date\s+of\s+(?:birth|joining|hire)|dob|start\s+date|joining\s+date)\s*[:=]\s*[\d\w\s,/-]{4,20}'
            r'|\b(location|office|site|work\s+location)\s*[:=]\s*\w[\w\s,.-]{1,40}'
        ),

        # Person name immediately following a "Name:" labeled field
        # Matches: "Name: John Smith", "Employee Name: Sarah Jenkins"
        "PERSON_NAME_LABELED": (
            r'(?:name|employee|candidate|applicant|worker|staff)\s*[:=]\s*'
            r'([A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){1,3})'
        ),

        # Salary / compensation figures without $ sign (e.g. "Salary: 95000", "CTC: 12,00,000")
        "SALARY_NUMERIC": (
            r'\b(salary|ctc|compensation|package|annual\s+pay|base\s+pay|gross\s+pay|net\s+pay|remuneration)'
            r'\s*[:=]\s*[\$\u20B9\u00A3\u20AC]?\s*[\d,]{4,}'
        ),

        # Performance ratings tied to named employees (e.g. "Rating: 4.5", "Score: Exceeds Expectations")
        "PERFORMANCE_DATA": (
            r'\b(performance\s+rating|review\s+score|appraisal\s+score|kpi\s+score|okr\s+score)'
            r'\s*[:=]\s*[\d.]+'
            r'|\b(exceeds?\s+expectations?|meets?\s+expectations?|needs?\s+improvement|outstanding\s+performer|low\s+performer)\b'
        ),
    }

    # Structural HR data block: fires when 2+ labeled HR fields appear within a short window of text.
    # This catches full employee record dumps even when individual fields appear innocuous.
    HR_BLOCK_FIELD_PATTERNS = [
        re.compile(p, re.IGNORECASE) for p in [
            r'\b(name|full\s+name|employee\s+name)\s*[:=]',
            r'\b(department|division|team|business\s+unit)\s*[:=]',
            r'\b(role|title|position|designation|current\s+role|job\s+title)\s*[:=]',
            r'\b(employee\s*(?:id|number|no)|emp[-]?[A-Z0-9]{2,})',
            r'\b(salary|ctc|compensation|package)\s*[:=]',
            r'\b(manager|supervisor|reporting\s+to)\s*[:=]',
            r'\b(date\s+of\s+(?:birth|joining|hire)|dob|start\s+date)\s*[:=]',
            r'\b(performance\s+rating|appraisal|review\s+score)\s*[:=]',
        ]
    ]

    # Prompt Injection & Jailbreak Heuristic Keywords
    INJECTION_PATTERNS = {
        "SYSTEM_OVERRIDE": [
            r'ignore\s+all\s+(previous|prior)\s+instructions',
            r'disregard\s+(your|all)\s+system\s+prompts?',
            r'forget\s+all\s+rules',
            r'you\s+are\n\s*now\s+in\s+developer\s+mode',
            r'override\s+safety\s+filter'
        ],
        "JAILBREAK_ROLEPLAY": [
            r'do\s+anything\s+now',
            r'\bdan\s+mode\b',
            r'evil\s+twin\s+persona',
            r'act\s+as\s+an?\s+unrestricted\s+ai',
            r'bypass\s+ethical\s+guidelines',
            r'^sudo\b'
        ],
        "DELIMITER_HIJACK": [
            r'```system\s*[\s\S]*?```',
            r'\[system\s*message\]',
            r'<\|im_start\|>system',
            r'</?system_override>'
        ]
    }

    # Leetspeak / l33tspeak character substitution table.
    # Maps digit/symbol lookalikes back to their alphabetic equivalents.
    # Applied ONLY to characters inside word-like tokens to avoid false-positives
    # on standalone numbers (e.g. "$130,000" should not become "$I3O,OOO").
    _LEET_TABLE = str.maketrans({
        '4': 'a', '@': 'a',
        '3': 'e',
        '1': 'i', '!': 'i',
        '0': 'o',
        '7': 't',
        '5': 's', '$': 's',
        '6': 'g',
        '8': 'b',
    })

    def _normalize_text(self, text: str) -> str:
        """
        Produce a de-obfuscated version of *text* for heuristic scanning.

        Steps:
          1. Unicode NFKD decomposition + ASCII encode/decode strips accents and
             homoglyphs (e.g. Cyrillic 'а' -> 'a', 'Thorné' -> 'Thorne').
          2. Word-level Leetspeak translation maps digit lookalikes back to their
             alphabetic form (e.g. 'S4r4h' -> 'Sarah', 'c0mp3ns4t10n' -> 'compensation').

        The original text is always scanned alongside the normalized version so
        that genuinely numeric patterns (SSNs, salary figures, phone numbers) are
        still caught by the standard regexes.
        """
        # Step 1 – Unicode normalization (strip accents / homoglyphs)
        try:
            nfkd = unicodedata.normalize('NFKD', text)
            ascii_text = nfkd.encode('ascii', 'ignore').decode('ascii')
        except Exception:
            ascii_text = text

        # Step 2 – Leetspeak de-obfuscation (only inside word-like tokens)
        # Matches any non-whitespace run containing letters + leet digits,
        # the hallmark of leetspeak (e.g. 'S4r4h', 'J3nk1ns', '0n3').
        # We deliberately avoid \b here because it fails on alpha-digit boundaries.
        leet_pattern = re.compile(r'\S+')

        def _deleet_token(m: re.Match) -> str:
            token = m.group()
            # Only apply the leet table if the token mixes letters AND digit-lookalikes.
            # _LEET_TABLE is an ordinal (int) keyed dict from str.maketrans, so
            # we must check ord(c) — not c — for membership.
            has_alpha = any(c.isalpha() for c in token)
            has_leet  = any(ord(c) in self._LEET_TABLE for c in token)
            if has_alpha and has_leet:
                return token.translate(self._LEET_TABLE)
            return token

        normalized = leet_pattern.sub(_deleet_token, ascii_text)
        return normalized

    def __init__(self):
        self.compiled_pii = {key: re.compile(pat, re.IGNORECASE) for key, pat in self.PII_PATTERNS.items()}

        # Exact Data Match (EDM) for internal employee names — both strict regex
        # AND a fuzzy name list used by the SequenceMatcher n-gram scanner.
        import json
        import os
        self.internal_names: List[str] = []  # lowercased full names for fuzzy matching
        try:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            emp_path = os.path.join(base_dir, 'employees.json')
            with open(emp_path, 'r') as f:
                employees = json.load(f)
                names = [emp['name'] for emp in employees if 'name' in emp]
                # Store normalized lowercase names for fuzzy matching
                self.internal_names = [self._normalize_text(n).lower() for n in names]
                # Build strict EDM regex for exact matches
                escaped = [re.escape(n) for n in names]
                if escaped:
                    edm_pattern = r'\b(?:' + '|'.join(escaped) + r')\b'
                    self.compiled_pii["INTERNAL_EMPLOYEE_NAME"] = re.compile(edm_pattern, re.IGNORECASE)
        except Exception:
            pass  # Fallback gracefully if database missing

        self.compiled_injections = {}
        for category, patterns in self.INJECTION_PATTERNS.items():
            combined = "|".join(f"(?:{p})" for p in patterns)
            self.compiled_injections[category] = re.compile(combined, re.IGNORECASE)

    def _fuzzy_name_scan(self, normalized_text: str) -> int:
        """
        N-gram fuzzy matching against the internal employee name list.

        Splits the normalized text into overlapping 2-word and 3-word windows
        (n-grams) and computes a SequenceMatcher similarity ratio against each
        known employee name.  A ratio above FUZZY_THRESHOLD is treated as a
        probable name match — catching typos like 'Davd Chen' vs 'David Chen'.

        Returns the number of fuzzy name matches found.
        """
        FUZZY_THRESHOLD = 0.82  # tunable — 0.82 catches 1-char typos cleanly
        if not self.internal_names:
            return 0

        # Strip punctuation and markdown (like **, commas) before splitting
        clean_text = re.sub(r'[^\w\s]', '', normalized_text.lower())
        words = clean_text.split()
        
        hits = 0
        # Slide a window of width 2 and 3 over the word list
        for width in (2, 3):
            for i in range(len(words) - width + 1):
                ngram = " ".join(words[i:i + width])
                for known_name in self.internal_names:
                    ratio = difflib.SequenceMatcher(None, ngram, known_name).ratio()
                    if ratio >= FUZZY_THRESHOLD:
                        hits += 1
                        break  # one match per window position is enough
        return hits

    def scan(
        self,
        text: str,
        user_role: UserRole = UserRole.EMPLOYEE,
        content_classification: DocumentClassification = DocumentClassification.PUBLIC
    ) -> HeuristicDetectionResult:
        """
        Scan text for PII, Privacy Leaks, Prompt Injection, and Hierarchical RBAC compliance.

        The scanner operates on BOTH the raw text and a de-obfuscated normalized
        copy, so Leetspeak, homoglyphs, and accented characters are caught by the
        same regex rules without any changes to those patterns.
        """
        if not text:
            return HeuristicDetectionResult(
                has_pii=False,
                detected_pii_types=[],
                pii_matches_count=0,
                has_prompt_injection=False,
                injection_vector_types=[],
                has_rbac_violation=False,
                rbac_details=None,
                sanitized_text="",
                tier1_risk_score=0.0
            )

        # Produce a de-obfuscated copy for heuristic scanning
        normalized_text = self._normalize_text(text)

        detected_pii_types = []
        pii_count = 0

        # 1. Privacy & PII Scan — run each regex on BOTH raw and normalized text
        #    so we catch both plain-text and obfuscated variants.
        for pii_type, regex in self.compiled_pii.items():
            matches = regex.findall(text)
            # Also scan the normalized (de-obfuscated) version
            norm_matches = regex.findall(normalized_text)
            all_matches = matches or norm_matches
            if all_matches:
                detected_pii_types.append(pii_type)
                pii_count += len(all_matches)

        # 1c. Fuzzy EDM — catches typo-obfuscated employee names (e.g. 'Davd Chen')
        fuzzy_hits = self._fuzzy_name_scan(normalized_text)
        if fuzzy_hits > 0 and "INTERNAL_EMPLOYEE_NAME" not in detected_pii_types:
            detected_pii_types.append("INTERNAL_EMPLOYEE_NAME_FUZZY")
            pii_count += fuzzy_hits

        # 1b. Structural HR Data Block Scan
        # Fires when 2+ labeled HR fields appear together — catches full employee record dumps
        # (e.g. "Name: X\nRole: Y\nDepartment: Z\nEmployee ID: EMP...") even if each field
        # individually seems innocuous in isolation.
        # Also scan the normalized copy so obfuscated HR blocks are caught.
        hr_fields_found = sum(
            1 for pattern in self.HR_BLOCK_FIELD_PATTERNS
            if pattern.search(text) or pattern.search(normalized_text)
        )
        if hr_fields_found >= 2:
            if "HR_EMPLOYEE_RECORD_DUMP" not in detected_pii_types:
                detected_pii_types.append("HR_EMPLOYEE_RECORD_DUMP")
                pii_count += hr_fields_found

        # 2. Prompt Injection Scan — on both raw and normalized text
        detected_injections = []
        for category, regex in self.compiled_injections.items():
            if regex.search(text) or regex.search(normalized_text):
                detected_injections.append(category)

        # 3. Hierarchical RBAC Verification
        has_rbac_violation = False
        rbac_details = None
        if int(user_role) < int(content_classification):
            has_rbac_violation = True
            rbac_details = f"Role '{user_role.name}' (Level {int(user_role)}) cannot access content classified as '{content_classification.name}' (Level {int(content_classification)})."

        has_pii = len(detected_pii_types) > 0
        has_injection = len(detected_injections) > 0

        # Composite Risk Score Calculation
        risk_score = 0.0
        if has_rbac_violation:
            risk_score += 0.70
        if has_injection:
            risk_score += 0.50
        if has_pii:
            risk_score += min(0.40, pii_count * 0.15)

        risk_score = round(min(1.0, risk_score), 3)

        return HeuristicDetectionResult(
            has_pii=has_pii,
            detected_pii_types=detected_pii_types,
            pii_matches_count=pii_count,
            has_prompt_injection=has_injection,
            injection_vector_types=detected_injections,
            has_rbac_violation=has_rbac_violation,
            rbac_details=rbac_details,
            sanitized_text=text,
            tier1_risk_score=risk_score
        )

