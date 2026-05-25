from typing import Literal
from pydantic import BaseModel


class PDFHearingPreviewRow(BaseModel):
    row_index: int

    # Extracted from PDF
    participant: str
    fid_number: str | None
    juv_id: str | None
    docket_number: str
    calendar_event: str       # raw string from PDF
    hearing_type: str         # normalised internal value
    date: str                 # YYYY-MM-DD
    time: str                 # HH:MM (24 h)
    judge_name: str
    case_worker_po: str | None

    # Resolved against DB
    judge_id: int | None
    courtroom_id: int | None
    case_id: int | None             # set when an existing case matches docket_number
    existing_case_number: str | None
    case_type: str                  # derived from docket prefix

    # Import decision
    match_status: Literal["matched", "new_case", "error"]
    issues: list[str]
    include: bool = True            # clerk can deselect rows before confirming


class PDFImportPreviewResponse(BaseModel):
    hearing_date: str
    judge_name: str
    total_rows: int
    matched: int
    new_cases: int
    errors: int
    rows: list[PDFHearingPreviewRow]


class PDFConfirmRequest(BaseModel):
    rows: list[PDFHearingPreviewRow]
    default_complexity: str = "medium"


class PDFImportResult(BaseModel):
    hearings_created: int
    cases_created: int
    skipped: int
    errors: list[str]


class AddJudgeRequest(BaseModel):
    name: str
    courtroom_name: str
    floor: int = 1


class AddJudgeResponse(BaseModel):
    id: int
    name: str
    courtroom_id: int
    courtroom_name: str
