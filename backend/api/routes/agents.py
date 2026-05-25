import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Courtroom, User
from schemas.agent import AgentTriggerRequest, AgentTriggerResponse
from api.dependencies import ClerkOrAdmin
from api.limiter import limiter
from graph.workflow import build_graph, make_initial_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/trigger", response_model=AgentTriggerResponse)
@limiter.limit("30/minute")
def trigger_agent(
    request: Request,
    body: AgentTriggerRequest,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    """
    Invoke the LangGraph courtroom pipeline for a single trigger event.

    Triggers:
    - tick: periodic queue health check (safe to call every minute)
    - checkin: party arrived; trigger_payload must include hearing_id and party
    - overrun: hearing is running long; trigger_payload must include hearing_id
    - complete: hearing finished; trigger_payload must include hearing_id
    """
    cr = db.get(Courtroom, body.courtroom_id)
    if cr is None:
        raise HTTPException(status_code=404, detail="Courtroom not found")

    try:
        graph = build_graph(db)
        initial = make_initial_state(
            courtroom_id   = body.courtroom_id,
            courtroom_name = cr.name,
            run_date       = body.run_date,
            db             = db,
            trigger        = body.trigger,
            trigger_payload = body.trigger_payload,
        )
        final = graph.invoke(initial)
    except Exception as exc:
        logger.exception("Agent pipeline failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Agent pipeline error: {exc}")

    return AgentTriggerResponse(
        courtroom_id = body.courtroom_id,
        run_date     = body.run_date,
        trigger      = body.trigger,
        audit_count  = len(final.get("audit_events", [])),
        conflicts    = len(final.get("conflicts", [])),
        eta_count    = len(final.get("eta_estimates", {})),
    )
