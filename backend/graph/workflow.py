"""
LangGraph workflow for a single courtroom instance.

Trigger → Router → Agent(s) → AuditAgent → END

                  checkin ──► CheckInAgent ──► ETAOrchestrator
                  overrun ──► DurationEstimator ──► ETAOrchestrator
                  tick    ──► QueueMonitor ──► (overrun | complete | nominal)
                  complete ──► ConflictDetector ──► ETAOrchestrator
                              └─────────────────────────────────► AuditAgent ──► END
"""

from sqlalchemy.orm import Session, selectinload
from langgraph.graph import StateGraph, END

from graph.state import CourtState
from agents import (
    checkin_agent,
    queue_monitor_agent,
    duration_estimator_agent,
    conflict_detector_agent,
    eta_orchestrator_agent,
    audit_agent,
)


def _wrap(agent_module, db: Session):
    """Bind db session to agent run function."""
    def node(state: CourtState) -> CourtState:
        return agent_module.run(state, db)
    node.__name__ = agent_module.AGENT_NAME
    return node


def _router(state: CourtState) -> str:
    return state.get("trigger", "nominal")


def _monitor_router(state: CourtState) -> str:
    trigger = state.get("trigger", "nominal")
    if trigger == "overrun":
        return "overrun"
    if trigger == "complete":
        return "complete"
    return "nominal"


def build_graph(db: Session) -> StateGraph:
    graph = StateGraph(CourtState)

    graph.add_node("CheckInAgent",           _wrap(checkin_agent, db))
    graph.add_node("QueueMonitorAgent",      _wrap(queue_monitor_agent, db))
    graph.add_node("DurationEstimatorAgent", _wrap(duration_estimator_agent, db))
    graph.add_node("ConflictDetectorAgent",  _wrap(conflict_detector_agent, db))
    graph.add_node("ETAOrchestratorAgent",   _wrap(eta_orchestrator_agent, db))
    graph.add_node("AuditAgent",             _wrap(audit_agent, db))

    graph.set_conditional_entry_point(
        _router,
        {
            "checkin":  "CheckInAgent",
            "tick":     "QueueMonitorAgent",
            "complete": "ConflictDetectorAgent",
            "overrun":  "DurationEstimatorAgent",
            "nominal":  "AuditAgent",
        },
    )

    graph.add_edge("CheckInAgent",           "ETAOrchestratorAgent")

    graph.add_conditional_edges(
        "QueueMonitorAgent",
        _monitor_router,
        {
            "overrun":  "DurationEstimatorAgent",
            "complete": "ConflictDetectorAgent",
            "nominal":  "AuditAgent",
        },
    )

    graph.add_edge("DurationEstimatorAgent", "ETAOrchestratorAgent")
    graph.add_edge("ConflictDetectorAgent",  "ETAOrchestratorAgent")
    graph.add_edge("ETAOrchestratorAgent",   "AuditAgent")
    graph.add_edge("AuditAgent",             END)

    return graph.compile()


def load_queue(courtroom_id: int, run_date: str, db: Session) -> list:
    """
    Build initial queue state — eager-loads case, respondents, and lawyer
    in 3 queries total (selectinload), not N×3.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from db.models import Case, Hearing

    target    = datetime.strptime(run_date, "%Y-%m-%d").date()
    day_start = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
    day_end   = day_start + timedelta(days=1)

    hearings = db.execute(
        select(Hearing)
        .where(
            Hearing.courtroom_id    == courtroom_id,
            Hearing.scheduled_start >= day_start,
            Hearing.scheduled_start <  day_end,
        )
        .options(
            selectinload(Hearing.case).options(
                selectinload(Case.respondents),
                selectinload(Case.defense_lawyer),
            ),
        )
        .order_by(Hearing.scheduled_start)
    ).scalars().all()

    queue = []
    for h in hearings:
        case       = h.case
        respondent = case.respondents[0] if case.respondents else None
        lawyer     = case.defense_lawyer
        queue.append({
            "hearing_id":              h.id,
            "case_number":             case.case_number,
            "case_type":               case.case_type,
            "hearing_type":            h.hearing_type,
            "attorney_name":           lawyer.name    if lawyer     else "Unknown",
            "respondent_name":         respondent.name if respondent else "Unknown",
            "scheduled_start":         h.scheduled_start.isoformat(),
            "estimated_duration_mins": h.estimated_duration_mins,
            "status":                  h.status,
            "attorney_checked_in":     h.lawyer_checked_in,
            "juvenile_checked_in":     h.accused_checked_in,
        })
    return queue


def make_initial_state(
    courtroom_id: int,
    courtroom_name: str,
    run_date: str,
    db: Session,
    trigger: str = "tick",
    trigger_payload: dict | None = None,
) -> CourtState:
    return CourtState(
        courtroom_id    = courtroom_id,
        courtroom_name  = courtroom_name,
        run_date        = run_date,
        queue           = load_queue(courtroom_id, run_date, db),
        eta_estimates   = {},
        conflicts       = [],
        audit_events    = [],
        trigger         = trigger,
        trigger_payload = trigger_payload or {},
    )
