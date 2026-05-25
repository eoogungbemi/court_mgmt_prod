"""
PDF docket import — two-step flow.

  POST /pdf-import/preview   Upload a court calendar PDF; returns extracted rows
                             with DB match status. No writes occur.

  POST /pdf-import/confirm   Commit a previously-previewed list of rows.
                             Creates missing Case/Accused records and Hearings.
"""
import base64
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import anthropic
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependencies import AnyAuthenticated
from api.limiter import limiter
from config import ANTHROPIC_API_KEY
from db.database import get_db
from db.models import Accused, AuditLog, Case, Courtroom, Hearing, Judge, User
from schemas.pdf_import import (
    AddJudgeRequest,
    AddJudgeResponse,
    PDFConfirmRequest,
    PDFHearingPreviewRow,
    PDFImportPreviewResponse,
    PDFImportResult,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pdf-import", tags=["pdf-import"])

# ── Constants ─────────────────────────────────────────────────────────────────

HEARING_TYPE_MAP: dict[str, str] = {
    "permanency review hearing":    "permanency",
    "permanency hearing":           "permanency",
    "status conference":            "status_conference",
    "adjudicatory hearing":         "adjudicatory",
    "dispositional hearing":        "dispositional",
    "detention hearing":            "detention",
    "review hearing":               "review",
    "arraignment":                  "arraignment",
    "transfer hearing":             "transfer",
    "motion hearing":               "motion",
    "competency hearing":           "competency",
    "shelter care hearing":         "shelter_care",
    "intake conference":            "intake_conference",
}

DEFAULT_DURATION_MINS: dict[str, int] = {
    "permanency":       45,
    "status_conference": 20,
    "adjudicatory":     60,
    "dispositional":    30,
    "detention":        20,
    "review":           20,
    "arraignment":      15,
    "transfer":         60,
    "motion":           30,
    "competency":       45,
    "shelter_care":     20,
    "intake_conference": 20,
}

EXTRACTION_PROMPT = """
You are a careful legal data extraction assistant.

I have uploaded a court hearing list PDF. Extract ALL data from the document, judge by judge, without skipping any entry.

Return ONLY a JSON object — no markdown, no explanation — with this exact structure:

{
  "hearing_date": "YYYY-MM-DD",
  "judges": [
    {
      "judge_name": "Full Name exactly as written in the document",
      "total_events_stated": 12,
      "rows": [
        {
          "row_index": 1,
          "time": "HH:MM",
          "participant": "Lastname Firstname",
          "fid_number": "02-FN-XXXXXX-YYYY or null",
          "juv_id": "JPXXXX or null",
          "docket_number": "CP-02-DP-XXXXXXX-YYYY",
          "calendar_event": "Permanency Review Hearing",
          "case_worker_po": "Lastname Firstname; Lastname Firstname or null"
        }
      ]
    }
  ]
}

Critical rules — follow every one:
1. Process EVERY page of the document. Do not stop at page 1.
2. Include a separate entry in "judges" for every judge or hearing officer section found.
3. row_index must be globally sequential across all judges (1, 2, 3 … N total).
4. If one numbered entry contains multiple docket numbers, participants, or event types, create a SEPARATE row for each distinct docket/event.
5. Do NOT merge different docket numbers into one row.
6. Do NOT omit repeated participants — if the same name appears with a different docket or event type, list each occurrence as its own row.
7. Handle wrapped lines carefully: participant names, hearing types, and case worker names may wrap onto the next line — join them before outputting.
8. Separate joined fields: a Juv. ID (JP...) immediately followed by a docket number (CP-...) must be split into their respective fields.
9. time must be 24-hour HH:MM (e.g. "09:00", "13:30"). If a row shares the prior row's time, repeat it.
10. participant: "Lastname Firstname" title case, no comma.
11. Multiple case workers separated by semicolons.
12. juv_id: only the JP... identifier; null if the column is blank.
13. docket_number: the CP-... number only (not the JP... part).
14. total_events_stated: copy the exact integer shown as "Total Events Scheduled" in the PDF for that judge/hearing officer section.
15. Use null for any field that is blank in the document. Never guess or fabricate values.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise_hearing_type(raw: str) -> str:
    return HEARING_TYPE_MAP.get(raw.strip().lower(), "review")


def _case_type_from_docket(docket: str) -> str:
    upper = docket.upper()
    if "-DP-" in upper:
        return "dependency"
    if "-JD-" in upper:
        return "delinquency"
    if "-SO-" in upper:
        return "status_offense"
    return "dependency"


def _parse_datetime(date_str: str, time_str: str) -> datetime:
    """Combine YYYY-MM-DD + HH:MM into a timezone-aware UTC datetime."""
    naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    # Court times are US/Eastern; store as UTC (UTC-4 in summer, UTC-5 in winter).
    # Use a fixed offset of -4 h (EDT) — adjust if needed.
    eastern_offset = timedelta(hours=-4)
    return (naive - eastern_offset).replace(tzinfo=timezone.utc)


async def _extract_with_claude(pdf_bytes: bytes) -> dict:
    """Send the PDF to Claude (async) and return the parsed JSON payload."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY is not configured; PDF extraction is unavailable.",
        )

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    b64 = base64.standard_b64encode(pdf_bytes).decode()

    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": EXTRACTION_PROMPT},
                ],
            }
        ],
    )

    text = message.content[0].text.strip()
    logger.info("Claude extraction: stop_reason=%s output_tokens=%s",
                message.stop_reason, message.usage.output_tokens)

    # Strip accidental markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    if message.stop_reason == "max_tokens":
        logger.warning("Claude response was truncated — output_tokens=%s; JSON may be incomplete",
                       message.usage.output_tokens)

    return json.loads(text)


def _resolve_rows_for_judge(
    judge_name: str,
    raw_rows: list[dict],
    hearing_date: str,
    db: Session,
    global_index: list[int],  # mutable counter shared across judges
) -> list[PDFHearingPreviewRow]:
    """Build preview rows for a single judge section."""
    judge_record: Judge | None = db.execute(
        select(Judge).where(Judge.name.ilike(f"%{judge_name}%"))
    ).scalar_one_or_none()

    rows: list[PDFHearingPreviewRow] = []
    for raw in raw_rows:
        issues: list[str] = []
        judge_id     = judge_record.id          if judge_record else None
        courtroom_id = judge_record.courtroom_id if judge_record else None

        if not judge_record:
            issues.append(f"Judge '{judge_name}' not found in the system")

        docket       = raw.get("docket_number", "")
        case_type    = _case_type_from_docket(docket)
        hearing_type = _normalise_hearing_type(raw.get("calendar_event", ""))

        existing: Case | None = db.execute(
            select(Case).where(Case.case_number == docket)
        ).scalar_one_or_none() if docket else None

        case_id              = existing.id          if existing else None
        existing_case_number = existing.case_number if existing else None

        if not docket:
            issues.append("Missing docket number")

        if issues:
            match_status = "error"
        elif existing:
            match_status = "matched"
        else:
            match_status = "new_case"

        global_index[0] += 1
        rows.append(
            PDFHearingPreviewRow(
                row_index            = global_index[0],
                participant          = raw.get("participant", ""),
                fid_number           = raw.get("fid_number"),
                juv_id               = raw.get("juv_id"),
                docket_number        = docket,
                calendar_event       = raw.get("calendar_event", ""),
                hearing_type         = hearing_type,
                date                 = hearing_date,
                time                 = raw.get("time", "09:00"),
                judge_name           = judge_name,
                case_worker_po       = raw.get("case_worker_po"),
                judge_id             = judge_id,
                courtroom_id         = courtroom_id,
                case_id              = case_id,
                existing_case_number = existing_case_number,
                case_type            = case_type,
                match_status         = match_status,  # type: ignore[arg-type]
                issues               = issues,
            )
        )
    return rows


def _build_preview_rows(
    extracted: dict,
    db: Session,
) -> list[PDFHearingPreviewRow]:
    hearing_date  = extracted.get("hearing_date", "")
    global_index  = [0]  # mutable so sub-function can increment it
    all_rows: list[PDFHearingPreviewRow] = []

    # New multi-judge format: {"judges": [{judge_name, rows}, ...]}
    if "judges" in extracted:
        for section in extracted["judges"]:
            judge_name = section.get("judge_name", "")
            raw_rows   = section.get("rows", [])
            all_rows.extend(
                _resolve_rows_for_judge(judge_name, raw_rows, hearing_date, db, global_index)
            )
    else:
        # Fallback: old single-judge format {"judge_name": ..., "rows": [...]}
        judge_name = extracted.get("judge_name", "")
        raw_rows   = extracted.get("rows", [])
        all_rows.extend(
            _resolve_rows_for_judge(judge_name, raw_rows, hearing_date, db, global_index)
        )

    return all_rows


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/preview", response_model=PDFImportPreviewResponse)
@limiter.limit("10/minute")
async def preview_pdf(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = AnyAuthenticated,
):
    """
    Upload a court calendar PDF. Returns extracted rows with DB match status.
    No data is written to the database.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF must be under 20 MB.")

    try:
        extracted = await _extract_with_claude(pdf_bytes)
    except json.JSONDecodeError as exc:
        logger.error("Claude returned unparseable JSON: %s", exc)
        raise HTTPException(status_code=422, detail=f"Claude returned unparseable JSON: {exc}")
    except anthropic.APIError as exc:
        logger.error("Anthropic API error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Claude API error: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error during PDF extraction")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")

    rows = _build_preview_rows(extracted, db)

    # Build a display-friendly judge name summary
    if "judges" in extracted:
        judge_names = [s.get("judge_name", "") for s in extracted["judges"] if s.get("judge_name")]
        judge_display = ", ".join(judge_names)
    else:
        judge_display = extracted.get("judge_name", "")

    return PDFImportPreviewResponse(
        hearing_date = extracted.get("hearing_date", ""),
        judge_name   = judge_display,
        total_rows   = len(rows),
        matched      = sum(1 for r in rows if r.match_status == "matched"),
        new_cases    = sum(1 for r in rows if r.match_status == "new_case"),
        errors       = sum(1 for r in rows if r.match_status == "error"),
        rows         = rows,
    )


@router.post("/confirm", response_model=PDFImportResult, status_code=201)
def confirm_import(
    body: PDFConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = AnyAuthenticated,
):
    """
    Commit selected rows from a previous /preview call.
    Creates missing Case + Accused records and schedules Hearings.
    """
    included   = [r for r in body.rows if r.include and r.match_status != "error"]
    skipped    = len(body.rows) - len(included)
    errors: list[str] = []
    cases_created    = 0
    hearings_created = 0

    for row in included:
        try:
            # ── Resolve / create Case ─────────────────────────────────────
            if row.case_id:
                case = db.get(Case, row.case_id)
            else:
                # New case — use the docket number directly as case_number
                case = Case(
                    case_number       = row.docket_number,
                    case_type         = row.case_type,
                    complexity        = body.default_complexity,
                    defense_lawyer_id = None,
                )
                db.add(case)
                db.flush()

                db.add(Accused(
                    case_id = case.id,
                    name    = row.participant,
                ))

                db.add(AuditLog(
                    event_type  = "CASE_PDF_IMPORTED",
                    agent_name  = current_user.username,
                    entity_type = "case",
                    entity_id   = case.id,
                    payload     = json.dumps({
                        "case_number":  row.docket_number,
                        "fid_number":   row.fid_number,
                        "juv_id":       row.juv_id,
                        "case_worker":  row.case_worker_po,
                    }),
                ))
                cases_created += 1

            # ── Validate courtroom / judge still available ────────────────
            if not row.courtroom_id or not row.judge_id:
                errors.append(
                    f"Row {row.row_index} ({row.participant}): "
                    "judge/courtroom could not be resolved — skipped."
                )
                skipped += 1
                continue

            # ── Skip duplicate hearings (same case + courtroom + start) ──
            scheduled_start = _parse_datetime(row.date, row.time)
            duration        = DEFAULT_DURATION_MINS.get(row.hearing_type, 30)
            scheduled_end   = scheduled_start + timedelta(minutes=duration)

            duplicate = db.execute(
                select(Hearing).where(
                    Hearing.case_id      == case.id,
                    Hearing.courtroom_id == row.courtroom_id,
                    Hearing.scheduled_start == scheduled_start,
                )
            ).scalar_one_or_none()

            if duplicate:
                skipped += 1
                continue

            # ── Create Hearing ────────────────────────────────────────────
            hearing = Hearing(
                case_id                 = case.id,
                courtroom_id            = row.courtroom_id,
                judge_id                = row.judge_id,
                hearing_type            = row.hearing_type,
                scheduled_start         = scheduled_start,
                scheduled_end           = scheduled_end,
                estimated_duration_mins = duration,
                status                  = "scheduled",
                notes                   = (
                    f"Imported from PDF docket. "
                    f"FID: {row.fid_number or 'n/a'}. "
                    f"Juv ID: {row.juv_id or 'n/a'}. "
                    f"Case worker/PO: {row.case_worker_po or 'n/a'}."
                ),
            )
            db.add(hearing)
            db.flush()

            db.add(AuditLog(
                event_type  = "HEARING_PDF_IMPORTED",
                agent_name  = current_user.username,
                entity_type = "hearing",
                entity_id   = hearing.id,
                payload     = json.dumps({
                    "case_number":   row.docket_number,
                    "hearing_type":  row.hearing_type,
                    "scheduled_start": scheduled_start.isoformat(),
                }),
            ))
            hearings_created += 1

        except Exception as exc:
            logger.exception("PDF import error on row %s", row.row_index)
            errors.append(f"Row {row.row_index} ({row.participant}): {exc}")
            skipped += 1

    db.commit()

    return PDFImportResult(
        hearings_created = hearings_created,
        cases_created    = cases_created,
        skipped          = skipped,
        errors           = errors,
    )


@router.post("/add-judge", response_model=AddJudgeResponse, status_code=201)
def add_judge_to_system(
    body: AddJudgeRequest,
    db: Session = Depends(get_db),
    current_user: User = AnyAuthenticated,
):
    """
    Register a new judge or hearing officer encountered during PDF import.
    Creates a new Courtroom and links the Judge to it.
    If a judge with the same name already exists, returns that record.
    """
    existing = db.execute(
        select(Judge).where(Judge.name.ilike(f"%{body.name}%"))
    ).scalar_one_or_none()
    if existing:
        room = db.get(Courtroom, existing.courtroom_id)
        return AddJudgeResponse(
            id             = existing.id,
            name           = existing.name,
            courtroom_id   = existing.courtroom_id,
            courtroom_name = room.name if room else "",
        )

    courtroom = Courtroom(name=body.courtroom_name.strip(), floor=body.floor)
    db.add(courtroom)
    db.flush()

    judge = Judge(name=body.name.strip(), courtroom_id=courtroom.id)
    db.add(judge)
    db.flush()

    db.add(AuditLog(
        event_type  = "JUDGE_ADDED",
        agent_name  = current_user.username,
        entity_type = "judge",
        entity_id   = judge.id,
        payload     = json.dumps({
            "name":           judge.name,
            "courtroom_name": courtroom.name,
            "floor":          courtroom.floor,
        }),
    ))
    db.commit()
    db.refresh(judge)

    return AddJudgeResponse(
        id             = judge.id,
        name           = judge.name,
        courtroom_id   = judge.courtroom_id,
        courtroom_name = courtroom.name,
    )
