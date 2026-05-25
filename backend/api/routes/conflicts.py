import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db.database import get_db
from db.models import AuditLog, Case, Courtroom, LawyerConflict, User
from db.models import Hearing
from schemas.conflict import ConflictDetail, ConflictOut, ConflictResolveRequest, HearingSummary
from api.dependencies import ClerkOrAdmin

router = APIRouter(prefix="/conflicts", tags=["conflicts"])


def _hearing_summary(h: Hearing) -> HearingSummary:
    return HearingSummary(
        id              = h.id,
        scheduled_start = h.scheduled_start,
        courtroom_name  = h.courtroom.name if h.courtroom else f"Room {h.courtroom_id}",
        case_number     = h.case.case_number if h.case else "—",
    )


def _to_detail(c: LawyerConflict) -> ConflictDetail:
    return ConflictDetail(
        id           = c.id,
        lawyer_id    = c.lawyer_id,
        lawyer_name  = c.lawyer.name if c.lawyer else f"Lawyer #{c.lawyer_id}",
        hearing_a    = _hearing_summary(c.hearing_a),
        hearing_b    = _hearing_summary(c.hearing_b),
        overlap_start = c.overlap_start,
        overlap_end   = c.overlap_end,
        resolved      = c.resolved,
        detected_at   = c.detected_at,
    )


def _load_options():
    return [
        selectinload(LawyerConflict.lawyer),
        selectinload(LawyerConflict.hearing_a).options(
            selectinload(Hearing.courtroom),
            selectinload(Hearing.case),
        ),
        selectinload(LawyerConflict.hearing_b).options(
            selectinload(Hearing.courtroom),
            selectinload(Hearing.case),
        ),
    ]


@router.get("", response_model=list[ConflictDetail])
def list_conflicts(
    resolved:  bool | None = Query(None, description="Filter by resolved status"),
    lawyer_id: int | None  = Query(None),
    db: Session = Depends(get_db),
    _: User     = ClerkOrAdmin,
):
    stmt = (
        select(LawyerConflict)
        .options(*_load_options())
        .order_by(LawyerConflict.detected_at.desc())
    )
    if resolved is not None:
        stmt = stmt.where(LawyerConflict.resolved == resolved)
    if lawyer_id is not None:
        stmt = stmt.where(LawyerConflict.lawyer_id == lawyer_id)

    return [_to_detail(c) for c in db.execute(stmt).scalars().all()]


@router.get("/{conflict_id}", response_model=ConflictOut)
def get_conflict(
    conflict_id: int,
    db: Session  = Depends(get_db),
    _: User      = ClerkOrAdmin,
):
    c = db.get(LawyerConflict, conflict_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return c


@router.patch("/{conflict_id}", response_model=ConflictOut)
def resolve_conflict(
    conflict_id: int,
    body: ConflictResolveRequest,
    db: Session  = Depends(get_db),
    _: User      = ClerkOrAdmin,
):
    c = db.get(LawyerConflict, conflict_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Conflict not found")

    c.resolved = body.resolved
    db.add(AuditLog(
        event_type="CONFLICT_RESOLVED", agent_name="API",
        entity_type="conflict", entity_id=conflict_id,
        payload=json.dumps({"resolved": body.resolved}),
    ))
    db.commit()
    db.refresh(c)
    return c
