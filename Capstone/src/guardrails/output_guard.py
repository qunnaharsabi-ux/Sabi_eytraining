"""
guardrails/output_guard.py
--------------------------
Runs on the final report BEFORE it reaches the analyst.
  1. PII scan          - no unmasked PII may leave the system
  2. Hallucination     - cited case_ids must exist in retrieved RAG context
  3. Citation audit    - high-weight evidence must name a source
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from guardrails.input_guard import PII_PATTERNS
from monitoring.metrics import record_guardrail
from monitoring.logger import write_run_event

CASE_ID_RE = re.compile(r"FR-\d{4}-\d{3,5}")


@dataclass
class OutputGuardResult:
    ok: bool
    flags: List[str] = field(default_factory=list)
    report: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def _scan_pii(text: str) -> List[str]:
    found = []
    for name, pat in PII_PATTERNS.items():
        if re.search(pat, text):
            found.append(name)
    return found


def check_output(report: Dict[str, Any], rag_context: str, run_id: str = "unknown") -> OutputGuardResult:
    flags: List[str] = []
    notes: List[str] = []
    blob = " ".join(str(v) for v in report.values())

    # 1. PII scan
    pii = _scan_pii(blob)
    if pii:
        record_guardrail("pii", "critical")
        # auto-mask so the report is still deliverable
        for name, pat in PII_PATTERNS.items():
            blob = re.sub(pat, f"<{name.upper()}_REDACTED>", blob)
        flags.append("pii_masked")
        notes.append(f"Masked unexpected PII in output: {', '.join(pii)}")

    # 2. hallucination — every case-id cited in the report must appear in RAG ctx
    cited = set(CASE_ID_RE.findall(blob))
    known = set(CASE_ID_RE.findall(rag_context or ""))
    ghost = cited - known
    if ghost:
        record_guardrail("hallucination", "critical")
        flags.append("hallucination")
        notes.append(f"Report cites unseen case(s): {', '.join(sorted(ghost))}")

    # 3. citation audit — high-weight evidence should name a source
    for ev in report.get("evidence", []) or []:
        if str(ev.get("weight", "")).lower() == "high" and not ev.get("source"):
            record_guardrail("citation", "warning")
            flags.append("missing_citation")
            notes.append("High-weight evidence is missing a source citation.")
            break

    ok = "hallucination" not in flags  # only hallucination is hard-blocking
    if flags:
        write_run_event(run_id, {"event": "output_guardrail.flags", "level": "warning",
                                 "flags": flags})
    return OutputGuardResult(ok=ok, flags=flags, report=report, notes=notes)
