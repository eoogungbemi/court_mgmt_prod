from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db.database import get_db
from db.models import Case, Courtroom, Hearing, User
from schemas.courtroom import CourtroomOut, CourtroomOverview, QueueItem
from api.dependencies import OptionalUser, AnyAuthenticated, can_see_case

router = APIRouter(prefix="/courtrooms", tags=["courtrooms"])

_SEALED_LABEL = "Confidential"


def _day_bounds(target: date) -> tuple[datetime, datetime]:
    start = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


@router.get("", response_model=list[CourtroomOut])
def list_courtrooms(
    db: Session = Depends(get_db),
    _: User = AnyAuthenticated,
):
    rooms = db.execute(
        select(Courtroom)
        .options(selectinload(Courtroom.judge))
        .order_by(Courtroom.floor, Courtroom.name)
    ).scalars().all()
    return [
        CourtroomOut(id=cr.id, name=cr.name, floor=cr.floor,
                     judge_id=cr.judge.id if cr.judge else None)
        for cr in rooms
    ]


@router.get("/overview", response_model=list[CourtroomOverview])
def courtrooms_overview(
    run_date: date | None = None,
    db: Session = Depends(get_db),
    _: User = AnyAuthenticated,
):
    """Summary card for every courtroom — 2 queries total regardless of room count."""
    target             = run_date or datetime.now(timezone.utc).date()
    day_start, day_end = _day_bounds(target)

    courtrooms = db.execute(
        select(Courtroom)
        .options(selectinload(Courtroom.judge))
        .order_by(Courtroom.floor, Courtroom.name)
    ).scalars().all()

    hearings_today = db.execute(
        select(Hearing).where(
            Hearing.scheduled_start >= day_start,
            Hearing.scheduled_start <  day_end,
            Hearing.status          != "cancelled",
        )
    ).scalars().all()

    hearing_map: dict[int, list[Hearing]] = defaultdict(list)
    for h in hearings_today:
        hearing_map[h.courtroom_id].append(h)

    result = []
    for cr in courtrooms:
        day_hs = sorted(hearing_map[cr.id], key=lambda h: h.scheduled_start)
        result.append(CourtroomOverview(
            id            = cr.id,
            name          = cr.name,
            floor         = cr.floor,
            judge_id      = cr.judge.id   if cr.judge else None,
            judge_name    = cr.judge.name if cr.judge else None,
            hearing_count = len(day_hs),
            next_start    = day_hs[0].scheduled_start if day_hs else None,
        ))
    return result


@router.get("/{courtroom_id}", response_model=CourtroomOut)
def get_courtroom(
    courtroom_id: int,
    db: Session = Depends(get_db),
    _: User = AnyAuthenticated,
):
    cr = db.execute(
        select(Courtroom)
        .options(selectinload(Courtroom.judge))
        .where(Courtroom.id == courtroom_id)
    ).scalar_one_or_none()
    if cr is None:
        raise HTTPException(status_code=404, detail="Courtroom not found")
    return CourtroomOut(id=cr.id, name=cr.name, floor=cr.floor,
                        judge_id=cr.judge.id if cr.judge else None)


@router.get("/{courtroom_id}/queue", response_model=list[QueueItem])
def courtroom_queue(
    courtroom_id: int,
    run_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = AnyAuthenticated,
):
    """
    Ordered queue — requires authentication (public role or above).
    Sealed cases are included in the queue (so counts stay accurate) but all
    identifying fields are replaced with "Confidential" for non-privileged roles.
    """
    if not db.get(Courtroom, courtroom_id):
        raise HTTPException(status_code=404, detail="Courtroom not found")

    target             = run_date or datetime.now(timezone.utc).date()
    day_start, day_end = _day_bounds(target)

    hearings = db.execute(
        select(Hearing)
        .where(
            Hearing.courtroom_id    == courtroom_id,
            Hearing.scheduled_start >= day_start,
            Hearing.scheduled_start <  day_end,
            Hearing.status          != "cancelled",
        )
        .options(
            selectinload(Hearing.case).options(
                selectinload(Case.respondents),
                selectinload(Case.defense_lawyer),
            ),
            selectinload(Hearing.eta_estimates),
        )
        .order_by(Hearing.scheduled_start)
    ).scalars().all()

    queue = []
    for h in hearings:
        case       = h.case
        privileged = can_see_case(case, current_user)
        respondent = case.respondents[0] if case.respondents else None
        lawyer     = case.defense_lawyer
        latest_eta = (
            max(h.eta_estimates, key=lambda e: e.generated_at)
            if h.eta_estimates else None
        )

        queue.append(QueueItem(
            hearing_id              = h.id,
            case_id                 = case.id,
            case_number             = case.case_number if privileged else _SEALED_LABEL,
            case_type               = case.case_type,
            hearing_type            = h.hearing_type,
            respondent_name         = (respondent.name if respondent else "Unknown") if privileged else _SEALED_LABEL,
            attorney_name           = (lawyer.name if lawyer else "Unknown")         if privileged else _SEALED_LABEL,
            scheduled_start         = h.scheduled_start,
            estimated_duration_mins = h.estimated_duration_mins,
            status                  = h.status,
            attorney_checked_in     = h.lawyer_checked_in,
            juvenile_checked_in     = h.accused_checked_in,
            p25_mins   = latest_eta.p25_mins  if latest_eta else None,
            p75_mins   = latest_eta.p75_mins  if latest_eta else None,
            rationale  = latest_eta.rationale if latest_eta and privileged else None,
        ))

    return queue
