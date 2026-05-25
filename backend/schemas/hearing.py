from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

VALID_HEARING_TYPES = {
    "arraignment", "detention", "adjudicatory", "dispositional", "review",
    "transfer", "motion", "competency", "shelter_care",
    "permanency", "intake_conference", "status_conference",
}

VALID_HEARING_STATUS = {
    "scheduled", "in_progress", "completed", "delayed", "cancelled",
}

VALID_DETENTION_STATUS = {"secure", "non_secure", "released"}


class HearingCreate(BaseModel):
    case_id:      int
    courtroom_id: int
    judge_id:     int
    hearing_type: Literal[
        "arraignment", "detention", "adjudicatory", "dispositional", "review",
        "transfer", "motion", "competency", "shelter_care",
        "permanency", "intake_conference", "status_conference",
    ]
    scheduled_start:         datetime
    scheduled_end:           datetime
    estimated_duration_mins: int = Field(30, ge=5)
    interpreter_required:    bool = False
    detention_status:        Literal["secure", "non_secure", "released"] | None = None
    notes:                   str | None = None


class HearingUpdate(BaseModel):
    hearing_type:            str | None = None
    scheduled_start:         datetime | None = None
    scheduled_end:           datetime | None = None
    estimated_duration_mins: int | None = None
    interpreter_required:    bool | None = None
    detention_status:        str | None = None
    notes:                   str | None = None


class CheckInRequest(BaseModel):
    party: Literal["attorney", "juvenile"]


class StatusUpdateRequest(BaseModel):
    status: Literal["scheduled", "in_progress", "completed", "delayed", "cancelled"]
    actual_start: datetime | None = None
    actual_end:   datetime | None = None


class RescheduleRequest(BaseModel):
    scheduled_start:         datetime
    scheduled_end:           datetime
    estimated_duration_mins: int | None = None


class JudgeAssignRequest(BaseModel):
    judge_id: int


class NotesUpdateRequest(BaseModel):
    notes: str


class ETAEstimateOut(BaseModel):
    model_config = {"from_attributes": True}

    id:              int
    hearing_id:      int
    estimated_start: datetime
    p25_mins:        int
    p75_mins:        int
    rationale:       str | None
    agent_name:      str
    generated_at:    datetime


class AuditLogOut(BaseModel):
    model_config = {"from_attributes": True}

    id:          int
    event_type:  str
    agent_name:  str
    entity_type: str | None
    entity_id:   int | None
    payload:     str | None
    created_at:  datetime


class HearingOut(BaseModel):
    model_config = {"from_attributes": True}

    id:                      int
    case_id:                 int
    courtroom_id:            int
    judge_id:                int
    hearing_type:            str
    scheduled_start:         datetime
    scheduled_end:           datetime
    estimated_duration_mins: int
    actual_start:            datetime | None
    actual_end:              datetime | None
    status:                  str
    lawyer_checked_in:       bool
    accused_checked_in:      bool
    notes:                   str | None
    interpreter_required:    bool
    detention_status:        str | None
    eta_estimates:           list[ETAEstimateOut] = []
