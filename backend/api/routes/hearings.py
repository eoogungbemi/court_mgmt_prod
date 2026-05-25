import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import AuditLog, Case, Courtroom, Hearing, Judge, User
from schemas.hearing import (
    AuditLogOut, CheckInRequest, ETAEstimateOut, HearingCreate,
    HearingOut, HearingUpdate, JudgeAssignRequest, NotesUpdateRequest,
    RescheduleRequest, StatusUpdateRequest,
    VALID_HEARING_TYPES, VALID_HEARING_STATUS, VALID_DETENTION_STATUS,
)
from schemas.common import MessageResponse
from api.dependencies import AnyAuthenticated, ClerkOrAdmin, JudgeOrAbove, check_case_access
from api.routes.ws import manager as ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/hearings", tags=["hearings"])


def _get_hearing_or_404(hearing_id: int, db: Session) -> Hearing:
    h = db.get(Hearing, hearing_id)
    if h is None:
        raise HTTPException(status_code=404, detail="Hearing not found")
    return h


def _audit(db: Session, event_type: str, hearing_id: int, payload: dict) -> None:
    db.add(AuditLog(
        event_type=event_type, agent_name="API",
        entity_type="hearing", entity_id=hearing_id,
        payload=json.dumps(payload),
    ))


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=HearingOut, status_code=201)
def create_hearing(
    body: HearingCreate,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    if body.hearing_type not in VALID_HEARING_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid hearing_type. Must be one of {VALID_HEARING_TYPES}")
    if body.scheduled_start >= body.scheduled_end:
        raise HTTPException(status_code=400, detail="scheduled_start must be before scheduled_end")
    if not db.get(Case, body.case_id):
        raise HTTPException(status_code=400, detail="Case not found")
    if not db.get(Courtroom, body.courtroom_id):
        raise HTTPException(status_code=400, detail="Courtroom not found")
    if not db.get(Judge, body.judge_id):
        raise HTTPException(status_code=400, detail="Judge not found")

    h = Hearing(
        case_id                 = body.case_id,
        courtroom_id            = body.courtroom_id,
        judge_id                = body.judge_id,
        hearing_type            = body.hearing_type,
        scheduled_start         = body.scheduled_start,
        scheduled_end           = body.scheduled_end,
        estimated_duration_mins = body.estimated_duration_mins,
        interpreter_required    = body.interpreter_required,
        detention_status        = body.detention_status,
        notes                   = body.notes,
    )
    db.add(h)
    db.flush()
    _audit(db, "HEARING_CREATED", h.id, {"hearing_type": h.hearing_type})
    db.commit()
    db.refresh(h)
    return h


# ── Get one ───────────────────────────────────────────────────────────────────

@router.get("/{hearing_id}", response_model=HearingOut)
def get_hearing(
    hearing_id: int,
    db: Session = Depends(get_db),
    current_user: User = AnyAuthenticated,
):
    h = _get_hearing_or_404(hearing_id, db)
    check_case_access(h.case, current_user)
    return h


# ── Update (general patch) ────────────────────────────────────────────────────

@router.patch("/{hearing_id}", response_model=HearingOut)
def update_hearing(
    hearing_id: int,
    body: HearingUpdate,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    h = _get_hearing_or_404(hearing_id, db)
    if body.hearing_type and body.hearing_type not in VALID_HEARING_TYPES:
        raise HTTPException(status_code=400, detail="Invalid hearing_type")
    if body.detention_status and body.detention_status not in VALID_DETENTION_STATUS:
        raise HTTPException(status_code=400, detail="Invalid detention_status")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(h, field, value)

    _audit(db, "HEARING_UPDATED", h.id, body.model_dump(exclude_none=True))
    db.commit()
    db.refresh(h)
    return h


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{hearing_id}", status_code=204)
def delete_hearing(
    hearing_id: int,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    h = _get_hearing_or_404(hearing_id, db)
    _audit(db, "HEARING_DELETED", h.id, {"hearing_type": h.hearing_type})
    db.delete(h)
    db.commit()


# ── Check-in ──────────────────────────────────────────────────────────────────

@router.post("/{hearing_id}/checkin", response_model=HearingOut)
def checkin(
    hearing_id: int,
    body: CheckInRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    h = _get_hearing_or_404(hearing_id, db)

    if body.party == "attorney":
        h.lawyer_checked_in = True
    else:
        h.accused_checked_in = True

    _audit(db, "PARTY_CHECKED_IN", h.id, {
        "party":           body.party,
        "attorney_ready":  h.lawyer_checked_in,
        "juvenile_ready":  h.accused_checked_in,
        "all_ready":       h.lawyer_checked_in and h.accused_checked_in,
    })
    db.commit()
    db.refresh(h)
    background_tasks.add_task(
        ws_manager.broadcast,
        h.courtroom_id,
        {"type": "queue_update", "room_id": h.courtroom_id},
    )
    return h


# ── Status update ─────────────────────────────────────────────────────────────

@router.post("/{hearing_id}/status", response_model=HearingOut)
def update_status(
    hearing_id: int,
    body: StatusUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    h = _get_hearing_or_404(hearing_id, db)
    h.status = body.status
    if body.actual_start:
        h.actual_start = body.actual_start
    if body.actual_end:
        h.actual_end = body.actual_end

    _audit(db, "HEARING_STATUS_CHANGED", h.id, {"status": body.status})
    db.commit()
    db.refresh(h)
    background_tasks.add_task(
        ws_manager.broadcast,
        h.courtroom_id,
        {"type": "queue_update", "room_id": h.courtroom_id},
    )
    return h


# ── Reschedule ────────────────────────────────────────────────────────────────

@router.post("/{hearing_id}/reschedule", response_model=HearingOut)
def reschedule(
    hearing_id: int,
    body: RescheduleRequest,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    if body.scheduled_start >= body.scheduled_end:
        raise HTTPException(status_code=400, detail="scheduled_start must be before scheduled_end")

    h = _get_hearing_or_404(hearing_id, db)
    old_start = h.scheduled_start.isoformat()
    h.scheduled_start = body.scheduled_start
    h.scheduled_end   = body.scheduled_end
    if body.estimated_duration_mins:
        h.estimated_duration_mins = body.estimated_duration_mins
    h.status = "scheduled"

    _audit(db, "HEARING_RESCHEDULED", h.id, {
        "old_start": old_start,
        "new_start": body.scheduled_start.isoformat(),
    })
    db.commit()
    db.refresh(h)
    return h


# ── Judge assignment ──────────────────────────────────────────────────────────

@router.post("/{hearing_id}/judge", response_model=HearingOut)
def assign_judge(
    hearing_id: int,
    body: JudgeAssignRequest,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    h = _get_hearing_or_404(hearing_id, db)
    if not db.get(Judge, body.judge_id):
        raise HTTPException(status_code=400, detail="Judge not found")

    old_judge = h.judge_id
    h.judge_id = body.judge_id
    _audit(db, "JUDGE_ASSIGNED", h.id, {"old_judge_id": old_judge, "new_judge_id": body.judge_id})
    db.commit()
    db.refresh(h)
    return h


# ── Notes ─────────────────────────────────────────────────────────────────────

@router.patch("/{hearing_id}/notes", response_model=HearingOut)
def update_notes(
    hearing_id: int,
    body: NotesUpdateRequest,
    db: Session = Depends(get_db),
    _: User = JudgeOrAbove,
):
    h = _get_hearing_or_404(hearing_id, db)
    h.notes = body.notes
    _audit(db, "NOTES_UPDATED", h.id, {})
    db.commit()
    db.refresh(h)
    return h


# ── ETA history ───────────────────────────────────────────────────────────────

@router.get("/{hearing_id}/eta", response_model=list[ETAEstimateOut])
def get_eta_history(
    hearing_id: int,
    db: Session = Depends(get_db),
    _: User = AnyAuthenticated,
):
    h = _get_hearing_or_404(hearing_id, db)
    return sorted(h.eta_estimates, key=lambda e: e.generated_at, reverse=True)


# ── Audit trail for one hearing ───────────────────────────────────────────────

@router.get("/{hearing_id}/audit", response_model=list[AuditLogOut])
def get_hearing_audit(
    hearing_id: int,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    _get_hearing_or_404(hearing_id, db)
    logs = db.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == "hearing", AuditLog.entity_id == hearing_id)
        .order_by(AuditLog.created_at.desc())
    ).scalars().all()
    return logs
