from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

VALID_CASE_TYPES  = {"delinquency", "dependency", "status_offense"}
VALID_COMPLEXITY  = {"low", "medium", "high"}
VALID_CASE_STATUS = {"active", "closed"}


class AccusedCreate(BaseModel):
    name:           str
    phone:          str | None = None
    guardian_name:  str | None = None
    guardian_phone: str | None = None


class AccusedOut(BaseModel):
    model_config = {"from_attributes": True}

    id:             int
    name:           str
    phone:          str | None
    guardian_name:  str | None
    guardian_phone: str | None


class CaseCreate(BaseModel):
    case_type:         Literal["delinquency", "dependency", "status_offense"]
    complexity:        Literal["low", "medium", "high"] = "medium"
    defense_lawyer_id: int
    respondents:       list[AccusedCreate] = Field(min_length=1)
    is_confidential:   bool = False


class CaseUpdate(BaseModel):
    complexity:        Literal["low", "medium", "high"] | None = None
    defense_lawyer_id: int | None = None
    status:            Literal["active", "closed"] | None = None
    is_confidential:   bool | None = None


class CaseOut(BaseModel):
    model_config = {"from_attributes": True}

    id:               int
    case_number:      str
    case_type:        str
    complexity:       str
    status:           str
    is_confidential:  bool
    defense_lawyer_id: int
    respondents:      list[AccusedOut]


class CaseSearch(BaseModel):
    """Query parameters for case search."""
    q:         str | None = None    # free-text (case_number or respondent name)
    case_type: str | None = None
    status:    str | None = None
    lawyer_id: int | None = None
    page:      int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class HearingSummaryForCase(BaseModel):
    model_config = {"from_attributes": True}

    id:                      int
    hearing_type:            str
    scheduled_start:         datetime
    scheduled_end:           datetime
    estimated_duration_mins: int
    actual_start:            datetime | None
    actual_end:              datetime | None
    status:                  str
    courtroom_id:            int
    courtroom_name:          str | None = None
    judge_id:                int
    lawyer_checked_in:       bool
    accused_checked_in:      bool
    interpreter_required:    bool
    detention_status:        str | None
    notes:                   str | None


class CaseTimeline(BaseModel):
    id:                int
    case_number:       str
    case_type:         str
    complexity:        str
    status:            str
    is_confidential:   bool
    defense_lawyer_id: int
    defense_lawyer_name: str | None
    respondents:       list[AccusedOut]
    hearings:          list[HearingSummaryForCase]


class BulkRow(BaseModel):
    """One row parsed from the bulk-upload spreadsheet."""
    case_type:         Literal["delinquency", "dependency", "status_offense"]
    complexity:        Literal["low", "medium", "high"] = "medium"
    respondent_name:   str
    defense_lawyer_id: int
    guardian_name:     str | None = None
    guardian_phone:    str | None = None
    is_confidential:   bool = False


class BulkUploadResult(BaseModel):
    created:  int
    skipped:  int
    errors:   list[str]
    cases:    list[CaseOut]
