"""
Court analytics endpoint.
All queries scoped to a single run_date (default: today UTC).
ETA accuracy compares the AI agent's p50 estimate to the recorded actual duration
for completed hearings — the core metric demonstrating the value of the
LangGraph DurationEstimatorAgent.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db.database import get_db
from db.models import Hearing, Case, LawyerConflict, User
from schemas.analytics import (
    AnalyticsSummary, CaseTypeCount, CourtroomStat,
    ETAAccuracy, StatusBreakdown,
)
from api.dependencies import AnyAuthenticated

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _day_bounds(target: date) -> tuple[datetime, datetime]:
    start = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


@router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary(
    run_date: date | None = Query(None),
    db: Session = Depends(get_db),
    _: User = AnyAuthenticated,
):
    target             = run_date or datetime.now(timezone.utc).date()
    day_start, day_end = _day_bounds(target)

    # All hearings today — eager-load what we need to avoid N+1
    hearings = db.execute(
        select(Hearing)
        .options(
            selectinload(Hearing.case),
            selectinload(Hearing.courtroom),
            selectinload(Hearing.eta_estimates),
        )
        .where(
            Hearing.scheduled_start >= day_start,
            Hearing.scheduled_start <  day_end,
        )
    ).scalars().all()

    # ── Status breakdown ──────────────────────────────────────────────────────
    status_counts = Counter(h.status for h in hearings)
    non_cancelled = [h for h in hearings if h.status != "cancelled"]
    completed_n   = status_counts.get("completed", 0)
    completion_rate = (completed_n / len(non_cancelled) * 100) if non_cancelled else 0.0

    # ── Case-type breakdown ───────────────────────────────────────────────────
    case_type_counts: Counter[str] = Counter()
    for h in hearings:
        if h.case:
            case_type_counts[h.case.case_type] += 1

    # ── Per-courtroom stats ───────────────────────────────────────────────────
    room_map: dict[int, list[Hearing]] = defaultdict(list)
    for h in hearings:
        room_map[h.courtroom_id].append(h)

    by_courtroom = sorted(
        [
            CourtroomStat(
                courtroom_id   = cid,
                courtroom_name = hs[0].courtroom.name if hs[0].courtroom else f"Room {cid}",
                hearing_count  = len(hs),
                completed      = sum(1 for h in hs if h.status == "completed"),
            )
            for cid, hs in room_map.items()
        ],
        key=lambda s: -s.hearing_count,
    )

    # ── ETA accuracy (the AI agent's performance metric) ─────────────────────
    accuracy_samples: list[tuple[float, float]] = []  # (estimated_p50, actual_mins)
    for h in hearings:
        if (
            h.status == "completed"
            and h.actual_start
            and h.actual_end
            and h.eta_estimates
        ):
            actual_mins    = (h.actual_end - h.actual_start).total_seconds() / 60
            if actual_mins <= 0:
                continue
            latest_eta     = max(h.eta_estimates, key=lambda e: e.generated_at)
            estimated_p50  = (latest_eta.p25_mins + latest_eta.p75_mins) / 2
            accuracy_samples.append((estimated_p50, actual_mins))

    eta_accuracy: ETAAccuracy | None = None
    if accuracy_samples:
        avg_est = sum(e for e, _ in accuracy_samples) / len(accuracy_samples)
        avg_act = sum(a for _, a in accuracy_samples) / len(accuracy_samples)
        mae     = sum(abs(e - a) for e, a in accuracy_samples) / len(accuracy_samples)
        eta_accuracy = ETAAccuracy(
            sample_size         = len(accuracy_samples),
            avg_estimated_mins  = round(avg_est, 1),
            avg_actual_mins     = round(avg_act, 1),
            mean_abs_error_mins = round(mae, 1),
        )

    # ── Conflict summary ──────────────────────────────────────────────────────
    all_conflicts = db.execute(select(LawyerConflict)).scalars().all()
    conflicts_unresolved     = sum(1 for c in all_conflicts if not c.resolved)
    conflicts_detected_today = sum(
        1 for c in all_conflicts
        if c.detected_at and c.detected_at.date() == target
    )
    conflicts_resolved_today = sum(
        1 for c in all_conflicts
        if c.resolved and c.detected_at and c.detected_at.date() == target
    )

    return AnalyticsSummary(
        run_date                 = str(target),
        total_hearings           = len(hearings),
        completion_rate_pct      = round(completion_rate, 1),
        status_breakdown         = StatusBreakdown(
            scheduled   = status_counts.get("scheduled",   0),
            in_progress = status_counts.get("in_progress", 0),
            completed   = status_counts.get("completed",   0),
            delayed     = status_counts.get("delayed",     0),
            cancelled   = status_counts.get("cancelled",   0),
        ),
        by_case_type             = [
            CaseTypeCount(case_type=ct, count=cnt)
            for ct, cnt in case_type_counts.most_common()
        ],
        by_courtroom             = by_courtroom,
        eta_accuracy             = eta_accuracy,
        conflicts_unresolved     = conflicts_unresolved,
        conflicts_detected_today = conflicts_detected_today,
        conflicts_resolved_today = conflicts_resolved_today,
    )
