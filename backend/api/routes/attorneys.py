from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import LawyerConflict, Lawyer, Hearing, User
from schemas.attorney import AttorneyAvailability, AttorneyOut, AttorneyScheduleItem
from api.dependencies import AnyAuthenticated, ClerkOrAdmin

router = APIRouter(prefix="/attorneys", tags=["attorneys"])


@router.get("", response_model=list[AttorneyOut])
def list_attorneys(
    db: Session = Depends(get_db),
    _: User = AnyAuthenticated,
):
    return db.execute(select(Lawyer).order_by(Lawyer.name)).scalars().all()


@router.get("/{attorney_id}", response_model=AttorneyOut)
def get_attorney(
    attorney_id: int,
    db: Session = Depends(get_db),
    _: User = AnyAuthenticated,
):
    lawyer = db.get(Lawyer, attorney_id)
    if lawyer is None:
        raise HTTPException(status_code=404, detail="Attorney not found")
    return lawyer


@router.get("/{attorney_id}/schedule", response_model=list[AttorneyScheduleItem])
def attorney_schedule(
    attorney_id: int,
    run_date: date | None = Query(None),
    db: Session = Depends(get_db),
    _: User = AnyAuthenticated,
):
    """All hearings for an attorney on a given date (defaults to today)."""
    if not db.get(Lawyer, attorney_id):
        raise HTTPException(status_code=404, detail="Attorney not found")

    target = run_date or datetime.now(timezone.utc).date()

    hearings = db.execute(
        select(Hearing)
        .join(Hearing.case)
        .where(
            Hearing.case.has(defense_lawyer_id=attorney_id),
            Hearing.status != "cancelled",
        )
        .order_by(Hearing.scheduled_start)
    ).scalars().all()

    return [
        AttorneyScheduleItem(
            hearing_id      = h.id,
            case_id         = h.case.id,
            case_number     = h.case.case_number,
            case_type       = h.case.case_type,
            hearing_type    = h.hearing_type,
            courtroom_name  = h.courtroom.name,
            scheduled_start = h.scheduled_start,
            scheduled_end   = h.scheduled_end,
            status          = h.status,
        )
        for h in hearings
        if h.scheduled_start.date() == target
    ]


@router.get("/{attorney_id}/availability", response_model=AttorneyAvailability)
def attorney_availability(
    attorney_id: int,
    run_date: date | None = Query(None),
    db: Session = Depends(get_db),
    _: User = AnyAuthenticated,
):
    """Schedule + conflict flag for an attorney on a given date."""
    lawyer = db.get(Lawyer, attorney_id)
    if lawyer is None:
        raise HTTPException(status_code=404, detail="Attorney not found")

    target = run_date or datetime.now(timezone.utc).date()

    schedule = attorney_schedule(attorney_id, target, db, _)

    # Any unresolved conflict involving this attorney today
    has_conflicts = db.execute(
        select(LawyerConflict).where(
            LawyerConflict.lawyer_id == attorney_id,
            LawyerConflict.resolved  == False,
        )
    ).scalars().first() is not None

    starts = [s.scheduled_start for s in schedule]
    ends   = [s.scheduled_end   for s in schedule]

    return AttorneyAvailability(
        attorney_id   = attorney_id,
        attorney_name = lawyer.name,
        date          = target,
        available_from = min(starts) if starts else None,
        available_to   = max(ends)   if ends   else None,
        hearings       = schedule,
        has_conflicts  = has_conflicts,
    )
