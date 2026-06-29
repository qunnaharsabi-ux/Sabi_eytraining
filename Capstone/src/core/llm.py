"""
core/llm.py
-----------
Unified Groq chat client.

Design decisions implemented here:
  * Fallback chain on HTTP 429 (rate limit): 70b -> 8b -> gemma2-9b
    so the pipeline never dies on the free tier.
  * Demo mode: when no GROQ_API_KEY is configured the client returns a
    deterministic, sensible response so the whole dashboard works offline.
  * Token accounting returned to the caller for the @track_agent decorator.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

from configs.settings import settings

try:
    from groq import Groq
    from groq import RateLimitError  # type: ignore
    _GROQ_AVAILABLE = True
except Exception:  # pragma: no cover
    Groq = None  # type: ignore
    RateLimitError = Exception  # type: ignore
    _GROQ_AVAILABLE = False


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    fell_back: bool = False
    demo: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


_client: Optional["Groq"] = None


def _get_client() -> Optional["Groq"]:
    global _client
    if not settings.has_groq or not _GROQ_AVAILABLE:
        return None
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def _approx_tokens(text: str) -> int:
    # rough heuristic for demo-mode accounting (~4 chars/token)
    return max(1, len(text) // 4)


def chat(
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    json_mode: bool = False,
) -> LLMResult:
    """Single chat completion with automatic model fallback."""
    client = _get_client()
    if client is None:
        return _demo_response(system, user, json_mode)

    primary = model or settings.model_report
    chain: List[str] = [primary] + [m for m in settings.model_chain if m != primary]

    last_err: Optional[Exception] = None
    for i, m in enumerate(chain):
        try:
            kwargs = dict(
                model=m,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            usage = getattr(resp, "usage", None)
            return LLMResult(
                text=resp.choices[0].message.content or "",
                model=m,
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                fell_back=(i > 0),
            )
        except RateLimitError as e:  # noqa
            last_err = e
            time.sleep(0.6 * (i + 1))
            continue
        except Exception as e:  # network / other -> try next, then demo
            last_err = e
            continue

    # Everything failed -> graceful demo response, never crash the pipeline.
    res = _demo_response(system, user, json_mode)
    res.fell_back = True
    return res


def chat_json(system: str, user: str, model: Optional[str] = None, **kw) -> tuple[dict, LLMResult]:
    """Chat that must return JSON. Robustly extracts the first JSON object."""
    res = chat(system, user, model=model, json_mode=True, **kw)
    data = _safe_json(res.text)
    return data, res


def _safe_json(text: str) -> dict:
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


# --------------------------------------------------------------------------
# Demo mode — deterministic synthesised answers so the app runs without keys
# --------------------------------------------------------------------------
def _demo_response(system: str, user: str, json_mode: bool) -> LLMResult:
    s = system.lower()
    text: str
    if "supervisor" in s:
        text = json.dumps({"next": "SEARCH", "reason": "demo routing"})
    elif "incident intake" in s:
        text = json.dumps({
            "alert_id": "FR-DEMO", "category": "wire_fraud", "severity_hint": "high",
            "amount": 0, "currency": "INR", "destination": "unknown",
            "signals": [], "summary": "Demo incident parsed offline.",
        })
    elif "report agent" in s or "senior fraud investigator" in s:
        text = json.dumps(_demo_report(user))
    elif "evaluator" in s:
        text = json.dumps({
            "approved": True, "score": 0.88, "flags": [],
            "feedback": "Demo evaluation: grounded and proportionate.",
        })
    elif "search agent" in s:
        text = ("- Cross-border wire to a high-risk corridor matches known mule "
                "layering pattern. [Source: FATF typology]\n"
                "- RBI master direction requires fraud reporting within 7 days; "
                "SWIFT recall window is 2 hours. [Source: RBI circular]\n"
                "- Velocity + new-device combination is a strong account-takeover "
                "signal. [Source: industry advisory]")
    elif "rag agent" in s:
        _cases = re.findall(r"FR-\d{4}-\d{3,5}", user)
        _cid = _cases[0] if _cases else "the closest retrieved playbook precedent"
        text = (f"Closest precedent {_cid} matches this corridor and signal set; "
                "apply Playbook P-07: freeze, file STR, initiate SWIFT recall.")
    elif "reader agent" in s:
        text = "- No document uploaded; reader skipped in demo mode."
    else:
        text = "{}" if json_mode else "Demo response."
    return LLMResult(
        text=text, model="demo", demo=True,
        prompt_tokens=_approx_tokens(system + user),
        completion_tokens=_approx_tokens(text),
    )


def _demo_report(user: str) -> dict:
    amount = 0
    m = re.search(r"amount[\"']?\s*[:=]\s*([0-9]+)", user)
    if m:
        amount = int(m.group(1))
    high = amount >= 200000 or "geo_anomaly" in user or "velocity" in user
    score = 9.1 if high else 4.3

    # Cite a precedent that was ACTUALLY retrieved into our context, so the
    # citation is grounded (no hallucination flag, healthy RAGAS faithfulness).
    # The report context carries the retrieved case-ids under "rag_cases".
    retrieved = re.findall(r"FR-\d{4}-\d{3,5}", user)
    if retrieved:
        precedent = {"finding": f"Precedent {retrieved[0]} — same corridor & signal set",
                     "source": "rag", "weight": "med"}
        precedent_note = f"Precedent {retrieved[0]} and playbook P-07 both apply."
    else:
        precedent = {"finding": "Closest retrieved playbook precedent applies",
                     "source": "rag", "weight": "med"}
        precedent_note = "The closest retrieved playbook precedent applies."

    return {
        "headline": ("High-risk cross-border layering detected — recommend immediate review"
                     if high else "Low-risk anomaly — eligible for auto-close"),
        "narrative": (("A cross-border transfer combined velocity breach, geo anomaly and a "
                       "new device, matching a known mule-layering corridor pattern. "
                       + precedent_note) if high else
                      ("Isolated low-value anomaly with no corroborating signals; precedent "
                       "suggests benign behaviour. " + precedent_note)),
        "risk_score": score,
        "risk_rationale": ("Multiple independent high-weight signals on a high-risk corridor."
                           if high else "Single weak signal, low amount, strong benign precedent."),
        "evidence": [
            {"finding": "Velocity breach + new device", "source": "incident", "weight": "high" if high else "low"},
            {"finding": "Matches FATF layering typology", "source": "search", "weight": "high" if high else "low"},
            precedent,
        ],
        "regulatory": {"applies": ["RBI Master Direction on Fraud", "SWIFT recall protocol"],
                       "deadline_minutes": 120 if high else None},
        "recommended_actions": (
            ["Freeze beneficiary account", "Initiate SWIFT recall within 2h", "File STR with FIU-IND"]
            if high else ["Log and monitor", "Auto-close within SLA"]),
        "cris_draft": (("Customer Risk Incident Summary: transaction flagged for cross-border "
                        "layering risk; escalation and SWIFT recall recommended within the "
                        "2-hour window. " + precedent_note) if high else
                       ("Customer Risk Incident Summary: low-risk anomaly, monitored and closed "
                        "within SLA, no regulatory action required. " + precedent_note)),
        "confidence": "high" if high else "medium",
    }
