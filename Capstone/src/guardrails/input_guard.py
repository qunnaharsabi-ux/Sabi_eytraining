"""
guardrails/input_guard.py
-------------------------
Runs BEFORE any LLM call. Four layers:
  1. Format check     - size / structure / required fields
  2. Injection detect - 10 prompt-injection regex patterns
  3. Toxicity filter  - basic abusive-content screen
  4. PII redaction    - mask names, mobiles, emails, PAN, Aadhaar, full accounts
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from configs.settings import settings
from monitoring.metrics import record_guardrail
from monitoring.logger import write_run_event

# ---- 1. injection patterns (10) -----------------------------------------
INJECTION_PATTERNS = [
    r"ignore (all|previous|prior) (instructions|prompts)",
    r"disregard (the )?(above|previous|system)",
    r"you are now (a|an|the)\b",
    r"system prompt",
    r"reveal your (instructions|prompt|system)",
    r"act as (?!a fraud)",                       # role hijack (allow our own role)
    r"jailbreak|developer mode|do anything now|\bDAN\b",
    r"</?(system|assistant|user)>",              # fake chat turns
    r"print (your )?(api[_ ]?key|secret|token)",
    r"begin (your )?response with",
]

TOXIC_PATTERNS = [r"\bk+i+l+l+\b", r"\bidiot\b", r"\bstupid\b", r"\bhate you\b"]

# ---- 4. PII patterns -----------------------------------------------------
PII_PATTERNS = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}",
    "mobile": r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)",
    "pan": r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
    "aadhaar": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    "full_account": r"(?<!\*)(?<!\d)\d{11,18}(?!\d)",
}


@dataclass
class GuardResult:
    ok: bool
    reason: str = ""
    cleaned: Dict[str, Any] = field(default_factory=dict)
    redacted_fields: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)


def _stringify(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, default=str)


def _redact_text(text: str) -> Tuple[str, List[str]]:
    hit: List[str] = []
    for name, pat in PII_PATTERNS.items():
        if re.search(pat, text):
            text = re.sub(pat, f"<{name.upper()}_REDACTED>", text)
            hit.append(name)
    return text, hit


def check_input(payload: Dict[str, Any], run_id: str = "unknown") -> GuardResult:
    raw = _stringify(payload)

    # 1. format / size
    if len(raw) > settings.max_alert_chars:
        record_guardrail("format", "warning")
        return GuardResult(False, f"Alert exceeds {settings.max_alert_chars} chars")
    if "alert_id" not in payload or "amount" not in payload:
        record_guardrail("format", "warning")
        return GuardResult(False, "Missing required fields: alert_id / amount")

    lowered = raw.lower()

    # 2. injection
    for pat in INJECTION_PATTERNS:
        if re.search(pat, lowered):
            record_guardrail("injection", "critical")
            write_run_event(run_id, {"event": "guardrail.injection_blocked",
                                     "level": "warning", "pattern": pat})
            return GuardResult(False, "Prompt-injection attempt blocked", flags=["injection"])

    # 3. toxicity
    for pat in TOXIC_PATTERNS:
        if re.search(pat, lowered):
            record_guardrail("toxicity", "warning")
            return GuardResult(False, "Toxic content blocked", flags=["toxicity"])

    # 4. PII redaction (non-blocking — we mask and continue)
    cleaned = json.loads(raw)
    redacted: List[str] = []
    for k, v in list(cleaned.items()):
        if isinstance(v, str):
            new, hit = _redact_text(v)
            if hit:
                cleaned[k] = new
                redacted.extend(hit)
    if redacted:
        record_guardrail("pii", "warning")
        write_run_event(run_id, {"event": "guardrail.pii_redacted",
                                 "level": "warning", "fields": sorted(set(redacted))})

    return GuardResult(True, "ok", cleaned=cleaned, redacted_fields=sorted(set(redacted)))
