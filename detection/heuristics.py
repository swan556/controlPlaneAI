"""
Tier 1 Detection Module: PII, Privacy Leakage, & Hierarchical RBAC Heuristics
Fast regex-based pattern matching and rule engines for detecting sensitive data leakage and access control violations.
"""

import re
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
            r'|\b(emp[-]?[A-Z0-9]{2,10})\b'
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
            r'bypass\s+ethical\s+guidelines'
        ],
        "DELIMITER_HIJACK": [
            r'```system\s*[\s\S]*?```',
            r'\[system\s*message\]',
            r'<\|im_start\|>system',
            r'</?system_override>'
        ]
    }

    def __init__(self):
        self.compiled_pii = {key: re.compile(pat, re.IGNORECASE) for key, pat in self.PII_PATTERNS.items()}
        self.compiled_injections = {}
        for category, patterns in self.INJECTION_PATTERNS.items():
            combined = "|".join(f"(?:{p})" for p in patterns)
            self.compiled_injections[category] = re.compile(combined, re.IGNORECASE)

    def scan(
        self,
        text: str,
        user_role: UserRole = UserRole.EMPLOYEE,
        content_classification: DocumentClassification = DocumentClassification.PUBLIC
    ) -> HeuristicDetectionResult:
        """
        Scan text for PII, Privacy Leaks, Prompt Injection, and Hierarchical RBAC compliance.
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

        detected_pii_types = []
        pii_count = 0

        # 1. Privacy & PII Scan (individual field patterns)
        for pii_type, regex in self.compiled_pii.items():
            matches = regex.findall(text)
            if matches:
                detected_pii_types.append(pii_type)
                pii_count += len(matches)

        # 1b. Structural HR Data Block Scan
        # Fires when 2+ labeled HR fields appear together — catches full employee record dumps
        # (e.g. "Name: X\nRole: Y\nDepartment: Z\nEmployee ID: EMP...") even if each field
        # individually seems innocuous in isolation.
        hr_fields_found = sum(
            1 for pattern in self.HR_BLOCK_FIELD_PATTERNS if pattern.search(text)
        )
        if hr_fields_found >= 2:
            if "HR_EMPLOYEE_RECORD_DUMP" not in detected_pii_types:
                detected_pii_types.append("HR_EMPLOYEE_RECORD_DUMP")
                pii_count += hr_fields_found

        # 2. Prompt Injection Scan
        detected_injections = []
        for category, regex in self.compiled_injections.items():
            if regex.search(text):
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

