import csv
import io
import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db.database import get_db
from db.models import AuditLog, Case, Hearing, User
from schemas.hearing import AuditLogOut
from api.dependencies import AdminOnly, ClerkOrAdmin

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/docket")
def export_docket(
    courtroom_id: int | None = Query(None),
    run_date: date | None    = Query(None),
    db: Session = Depends(get_db),
    current_user: User = ClerkOrAdmin,
):
    """Download today's (or specified date's) docket as CSV. Audit-logged."""
    target = run_date or datetime.now(timezone.utc).date()

    stmt = (
        select(Hearing)
        .options(
            selectinload(Hearing.case).options(
                selectinload(Case.respondents),
                selectinload(Case.defense_lawyer),
            ),
            selectinload(Hearing.courtroom),
            selectinload(Hearing.judge),
        )
        .where(Hearing.status != "cancelled")
        .order_by(Hearing.courtroom_id, Hearing.scheduled_start)
    )
    if courtroom_id is not None:
        stmt = stmt.where(Hearing.courtroom_id == courtroom_id)

    hearings = [
        h for h in db.execute(stmt).scalars().all()
        if h.scheduled_start.date() == target
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "case_number", "case_type", "hearing_type", "courtroom",
        "judge", "respondent", "attorney",
        "scheduled_start", "scheduled_end", "estimated_duration_mins",
        "status", "attorney_checked_in", "juvenile_checked_in",
        "interpreter_required", "detention_status",
    ])

    for h in hearings:
        case       = h.case
        respondent = case.respondents[0] if case.respondents else None
        lawyer     = case.defense_lawyer
        writer.writerow([
            case.case_number,
            case.case_type,
            h.hearing_type,
            h.courtroom.name if h.courtroom else "",
            h.judge.name     if h.judge     else "",
            respondent.name  if respondent  else "",
            lawyer.name      if lawyer      else "",
            h.scheduled_start.isoformat(),
            h.scheduled_end.isoformat(),
            h.estimated_duration_mins,
            h.status,
            h.lawyer_checked_in,
            h.accused_checked_in,
            h.interpreter_required,
            h.detention_status or "",
        ])

    db.add(AuditLog(
        event_type="DOCKET_EXPORTED", agent_name="API",
        entity_type="courtroom", entity_id=courtroom_id,
        payload=json.dumps({
            "exported_by": current_user.username,
            "date": str(target),
            "row_count": len(hearings),
        }),
    ))
    db.commit()

    output.seek(0)
    filename = f"docket_{target}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit", response_model=list[AuditLogOut])
def export_audit(
    event_type:  str | None  = Query(None),
    entity_type: str | None  = Query(None),
    entity_id:   int | None  = Query(None),
    limit:       int          = Query(100, ge=1, le=500),
    offset:      int          = Query(0, ge=0),
    db: Session  = Depends(get_db),
    _: User      = AdminOnly,
):
    """Paginated audit log for the admin compliance view."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if event_type:
        stmt = stmt.where(AuditLog.event_type == event_type)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    stmt = stmt.offset(offset).limit(limit)
    return db.execute(stmt).scalars().all()
