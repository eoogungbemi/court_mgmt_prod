import io
import json
import logging
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api.limiter import limiter

from db.database import get_db
from db.models import Accused, AuditLog, Case, Hearing, Lawyer, User
from schemas.case import (
    BulkUploadResult, BulkRow,
    CaseCreate, CaseOut, CaseTimeline, CaseUpdate,
    HearingSummaryForCase,
    VALID_CASE_TYPES, VALID_COMPLEXITY,
)
from schemas.common import MessageResponse
from api.dependencies import AnyAuthenticated, ClerkOrAdmin, check_case_access, can_see_case

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cases", tags=["cases"])

_BULK_REQUIRED = {"case_type", "respondent_name", "defense_lawyer_id"}


def _next_case_number(case_type: str, db: Session) -> str:
    prefix_map = {
        "delinquency":    "JD",
        "dependency":     "DP",
        "status_offense": "SO",
    }
    prefix = prefix_map.get(case_type, "XX")
    year   = datetime.now(timezone.utc).year
    like   = f"{year}-{prefix}-%"
    count  = db.execute(
        select(Case).where(Case.case_number.like(like))
    ).scalars().all()
    return f"{year}-{prefix}-{len(count) + 1:05d}"


def _get_case_or_404(case_id: int, db: Session) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def _audit(db: Session, event_type: str, entity_id: int, payload: dict) -> None:
    db.add(AuditLog(
        event_type=event_type, agent_name="API",
        entity_type="case", entity_id=entity_id,
        payload=json.dumps(payload),
    ))


# ── List / search ─────────────────────────────────────────────────────────────

@router.get("", response_model=list[CaseOut])
def search_cases(
    q:         str | None = Query(None, description="Case number or respondent name"),
    case_type: str | None = Query(None),
    status:    str | None = Query(None),
    lawyer_id: int | None = Query(None),
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = AnyAuthenticated,
):
    stmt = select(Case)

    if q:
        stmt = stmt.outerjoin(Case.respondents).where(
            or_(
                Case.case_number.ilike(f"%{q}%"),
                Accused.name.ilike(f"%{q}%"),
            )
        ).distinct()

    if case_type:
        stmt = stmt.where(Case.case_type == case_type)
    if status:
        stmt = stmt.where(Case.status == status)
    if lawyer_id:
        stmt = stmt.where(Case.defense_lawyer_id == lawyer_id)

    # Attorneys only see their own cases
    if current_user.role == "attorney" and current_user.lawyer_id:
        stmt = stmt.where(Case.defense_lawyer_id == current_user.lawyer_id)

    # Non-privileged roles never see sealed cases in search results
    if current_user.role not in ("admin", "clerk", "judge"):
        stmt = stmt.where(Case.is_confidential == False)

    stmt = stmt.order_by(Case.id.desc()).offset((page - 1) * page_size).limit(page_size)
    return db.execute(stmt).scalars().all()


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=CaseOut, status_code=201)
def create_case(
    body: CaseCreate,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    if not db.get(Lawyer, body.defense_lawyer_id):
        raise HTTPException(status_code=400, detail="Lawyer not found")

    case = Case(
        case_number       = _next_case_number(body.case_type, db),
        case_type         = body.case_type,
        complexity        = body.complexity,
        defense_lawyer_id = body.defense_lawyer_id,
        is_confidential   = body.is_confidential,
    )
    db.add(case)
    db.flush()  # get case.id before adding respondents

    for r in body.respondents:
        db.add(Accused(
            case_id        = case.id,
            name           = r.name,
            phone          = r.phone,
            guardian_name  = r.guardian_name,
            guardian_phone = r.guardian_phone,
        ))

    _audit(db, "CASE_CREATED", case.id, {"case_number": case.case_number})
    db.commit()
    db.refresh(case)
    return case


# ── Get one ───────────────────────────────────────────────────────────────────

@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = AnyAuthenticated,
):
    case = _get_case_or_404(case_id, db)

    # Attorney access: own cases only
    if (
        current_user.role == "attorney"
        and current_user.lawyer_id != case.defense_lawyer_id
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    # Sealed-case guard (raises 403 for unauthorised roles)
    check_case_access(case, current_user)

    # Audit every read of a sealed case (42 Pa.C.S. § 6307 compliance)
    if case.is_confidential:
        _audit(db, "SEALED_CASE_ACCESSED", case.id,
               {"accessed_by": current_user.username, "role": current_user.role})
        db.commit()

    return case


# ── Timeline ──────────────────────────────────────────────────────────────────

@router.get("/{case_id}/timeline", response_model=CaseTimeline)
def get_case_timeline(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = AnyAuthenticated,
):
    from sqlalchemy.orm import selectinload
    case = db.execute(
        select(Case)
        .options(
            selectinload(Case.respondents),
            selectinload(Case.defense_lawyer),
            selectinload(Case.hearings).options(
                selectinload(Hearing.courtroom),
            ),
        )
        .where(Case.id == case_id)
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    if current_user.role == "attorney" and current_user.lawyer_id != case.defense_lawyer_id:
        raise HTTPException(status_code=403, detail="Access denied")
    check_case_access(case, current_user)

    hearings_sorted = sorted(case.hearings, key=lambda h: h.scheduled_start)
    return CaseTimeline(
        id=case.id,
        case_number=case.case_number,
        case_type=case.case_type,
        complexity=case.complexity,
        status=case.status,
        is_confidential=case.is_confidential,
        defense_lawyer_id=case.defense_lawyer_id,
        defense_lawyer_name=case.defense_lawyer.name if case.defense_lawyer else None,
        respondents=case.respondents,
        hearings=[
            HearingSummaryForCase(
                id=h.id,
                hearing_type=h.hearing_type,
                scheduled_start=h.scheduled_start,
                scheduled_end=h.scheduled_end,
                estimated_duration_mins=h.estimated_duration_mins,
                actual_start=h.actual_start,
                actual_end=h.actual_end,
                status=h.status,
                courtroom_id=h.courtroom_id,
                courtroom_name=h.courtroom.name if h.courtroom else None,
                judge_id=h.judge_id,
                lawyer_checked_in=h.lawyer_checked_in,
                accused_checked_in=h.accused_checked_in,
                interpreter_required=h.interpreter_required,
                detention_status=h.detention_status,
                notes=h.notes,
            )
            for h in hearings_sorted
        ],
    )


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int,
    body: CaseUpdate,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    case = _get_case_or_404(case_id, db)
    if body.defense_lawyer_id and not db.get(Lawyer, body.defense_lawyer_id):
        raise HTTPException(status_code=400, detail="Lawyer not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(case, field, value)

    _audit(db, "CASE_UPDATED", case.id, body.model_dump(exclude_none=True))
    db.commit()
    db.refresh(case)
    return case


# ── Seal (confidential flag) ──────────────────────────────────────────────────

@router.post("/{case_id}/seal", response_model=MessageResponse)
def seal_case(
    case_id: int,
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    case = _get_case_or_404(case_id, db)
    case.is_confidential = True
    _audit(db, "CASE_SEALED", case.id, {})
    db.commit()
    return {"message": f"Case {case.case_number} sealed"}


# ── Bulk upload ───────────────────────────────────────────────────────────────

@router.post("/bulk-upload", response_model=BulkUploadResult, status_code=201)
@limiter.limit("5/minute")
def bulk_upload(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = ClerkOrAdmin,
):
    """
    Accept a CSV or Excel file. Required columns:
      case_type, respondent_name, defense_lawyer_id
    Optional:
      complexity, guardian_name, guardian_phone, is_confidential
    """
    content = file.file.read()
    try:
        if file.filename and file.filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")

    missing = _BULK_REQUIRED - set(df.columns.str.strip().str.lower())
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")

    df.columns = df.columns.str.strip().str.lower()

    created_cases: list[Case] = []
    errors: list[str]         = []
    skipped                   = 0

    for i, row in df.iterrows():
        row_num = i + 2  # 1-based + header row
        try:
            parsed = BulkRow(
                case_type         = str(row["case_type"]).strip().lower(),
                complexity        = str(row.get("complexity", "medium")).strip().lower(),
                respondent_name   = str(row["respondent_name"]).strip(),
                defense_lawyer_id = int(row["defense_lawyer_id"]),
                guardian_name     = row.get("guardian_name") or None,
                guardian_phone    = row.get("guardian_phone") or None,
                is_confidential   = bool(row.get("is_confidential", False)),
            )
        except Exception as exc:
            errors.append(f"Row {row_num}: validation error — {exc}")
            skipped += 1
            continue

        if not db.get(Lawyer, parsed.defense_lawyer_id):
            errors.append(f"Row {row_num}: lawyer_id {parsed.defense_lawyer_id} not found")
            skipped += 1
            continue

        case = Case(
            case_number       = _next_case_number(parsed.case_type, db),
            case_type         = parsed.case_type,
            complexity        = parsed.complexity,
            defense_lawyer_id = parsed.defense_lawyer_id,
            is_confidential   = parsed.is_confidential,
        )
        db.add(case)
        db.flush()

        db.add(Accused(
            case_id        = case.id,
            name           = parsed.respondent_name,
            guardian_name  = parsed.guardian_name,
            guardian_phone = parsed.guardian_phone,
        ))

        _audit(db, "CASE_BULK_CREATED", case.id, {"case_number": case.case_number, "row": row_num})
        created_cases.append(case)

    db.commit()
    for case in created_cases:
        db.refresh(case)

    return BulkUploadResult(
        created=len(created_cases),
        skipped=skipped,
        errors=errors,
        cases=created_cases,
    )
