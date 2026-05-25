"""
LLM-backed (Claude Haiku). Produces a P25-P75 duration range and a
plain-English rationale for a single hearing.  Falls back to rule-based
estimates if the API is unavailable or returns invalid output.

PII policy: names, case numbers, and guardian details are deliberately
excluded from the LLM prompt.  Only structural signals (case type, hearing
type, complexity, queue position, presence flags) are sent to the API.
"""

import json
import logging
from datetime import datetime
from sqlalchemy.orm import Session

import anthropic
from anthropic import APIError

from config import ANTHROPIC_API_KEY, HEARING_DURATIONS, COMPLEXITY_MULTIPLIER
from db.models import Hearing, Case, ETAEstimate, AuditLog
from graph.state import CourtState, ETAEstimate as ETAEstimateState, AuditEvent
import utils.cache as cache

logger = logging.getLogger(__name__)
AGENT_NAME = "DurationEstimatorAgent"

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """You are an AI assistant supporting the Allegheny County Juvenile Court \
scheduling system in Pittsburgh, Pennsylvania (Court of Common Pleas, Family Division — \
Juvenile Branch).

Your job is to estimate how long a court hearing will take based on structured inputs.

The court handles three dockets:
- delinquency: cases involving juveniles alleged to have committed delinquent acts
- dependency: cases involving abused, neglected, or dependent children (CYF petitioner)
- status_offense (CHINS): truancy, underage alcohol, runaway situations

Rules:
- Output ONLY valid JSON with no markdown and no text outside the JSON object.
- p25_mins must be strictly less than p75_mins.
- Rationale must be 1-2 sentences, plain English, suitable for a court clerk.
- Account for case type, hearing type, complexity, and any contextual signals provided.
- Do NOT include or request any personally identifiable information.

Output format:
{"p25_mins": <int>, "p75_mins": <int>, "rationale": "<string>"}"""


def _llm_estimate(case_type: str, hearing_type: str,
                  complexity: str, context: dict) -> dict | None:
    """
    Send only structural, non-PII signals to the LLM:
    - case_type, hearing_type, complexity
    - courtroom (room label, not linked to a person)
    - queue_position (numeric)
    - all_parties_present (boolean)
    Names, case numbers, and guardian details are intentionally omitted.
    """
    prompt = (
        f"Case type: {case_type}\n"
        f"Hearing type: {hearing_type}\n"
        f"Complexity: {complexity}\n"
        f"Queue position: {context.get('queue_position', 0)}\n"
        f"All parties present: {context.get('all_parties_present', False)}\n"
        f"Interpreter required: {context.get('interpreter_required', False)}\n"
        "Provide a duration estimate."
    )
    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw    = response.content[0].text.strip()
        result = json.loads(raw)
        if (
            isinstance(result.get("p25_mins"), int)
            and isinstance(result.get("p75_mins"), int)
            and result["p25_mins"] < result["p75_mins"]
            and isinstance(result.get("rationale"), str)
        ):
            return result
    except (APIError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("LLM estimation failed: %s — using rule-based fallback", exc)
    return None


def _rule_estimate(case_type: str, hearing_type: str, complexity: str) -> dict:
    lo, hi = HEARING_DURATIONS.get(case_type, {}).get(hearing_type, (20, 40))
    mult   = COMPLEXITY_MULTIPLIER[complexity]
    p25    = max(5, int(lo * mult))
    p75    = max(p25 + 5, int(hi * mult))
    return {
        "p25_mins": p25,
        "p75_mins": p75,
        "rationale": (
            f"Rule-based estimate for {complexity}-complexity "
            f"{hearing_type.replace('_', ' ')} ({case_type} docket). "
            "LLM unavailable."
        ),
    }


def _cache_key(case_type: str, hearing_type: str, complexity: str,
               queue_position: int, all_parties: bool, interpreter: bool) -> str:
    bucket = "early" if queue_position <= 2 else "mid" if queue_position <= 5 else "late"
    return f"eta:{case_type}:{hearing_type}:{complexity}:{bucket}:{all_parties}:{interpreter}"


def run(state: CourtState, db: Session) -> CourtState:
    hearing_id: int = state["trigger_payload"].get("hearing_id")
    hearing = db.get(Hearing, hearing_id)
    if hearing is None:
        return state

    case: Case = hearing.case
    queue_position = next(
        (i for i, h in enumerate(state["queue"]) if h["hearing_id"] == hearing_id), 0
    )
    all_parties     = hearing.lawyer_checked_in and hearing.accused_checked_in
    interpreter     = hearing.interpreter_required
    context = {
        "queue_position":      queue_position,
        "all_parties_present": all_parties,
        "interpreter_required": interpreter,
        "courtroom": state["courtroom_name"],
    }

    ck         = _cache_key(case.case_type, hearing.hearing_type, case.complexity,
                            queue_position, all_parties, interpreter)
    result     = cache.get(ck)
    agent_used = AGENT_NAME
    if result is None:
        result = _llm_estimate(case.case_type, hearing.hearing_type, case.complexity, context)
        if result:
            cache.set(ck, result)
    if result is None:
        result     = _rule_estimate(case.case_type, hearing.hearing_type, case.complexity)
        agent_used = f"{AGENT_NAME}(fallback)"

    db.add(ETAEstimate(
        hearing_id=hearing_id,
        estimated_start=hearing.scheduled_start,
        p25_mins=result["p25_mins"],
        p75_mins=result["p75_mins"],
        rationale=result["rationale"],
        agent_name=agent_used,
    ))
    db.commit()

    eta_state = ETAEstimateState(
        hearing_id=hearing_id,
        estimated_start=hearing.scheduled_start.isoformat(),
        p25_mins=result["p25_mins"],
        p75_mins=result["p75_mins"],
        rationale=result["rationale"],
        agent_name=agent_used,
        generated_at=datetime.now().isoformat(),
    )

    event = AuditEvent(
        event_type="ETA_ESTIMATED", agent_name=agent_used,
        entity_type="hearing", entity_id=hearing_id,
        payload=result, created_at=datetime.now().isoformat(),
    )
    db.add(AuditLog(
        event_type=event["event_type"], agent_name=event["agent_name"],
        entity_type=event["entity_type"], entity_id=event["entity_id"],
        payload=json.dumps(event["payload"]),
    ))
    db.commit()

    return {
        **state,
        "eta_estimates": {**state["eta_estimates"], hearing_id: eta_state},
        "trigger":       "eta_ready",
        "audit_events":  [event],
    }
