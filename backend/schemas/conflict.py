from datetime import datetime
from pydantic import BaseModel


class ConflictResolveRequest(BaseModel):
    resolved: bool = True


# Minimal hearing info embedded in conflict responses
class HearingSummary(BaseModel):
    model_config = {"from_attributes": True}

    id:              int
    scheduled_start: datetime
    courtroom_name:  str
    case_number:     str


# Thin response kept for the GET /{id} route (no eager-load cost)
class ConflictOut(BaseModel):
    model_config = {"from_attributes": True}

    id:            int
    lawyer_id:     int
    hearing_a_id:  int
    hearing_b_id:  int
    overlap_start: datetime
    overlap_end:   datetime
    resolved:      bool
    detected_at:   datetime


# Rich response for the list endpoint — includes attorney name and hearing context
class ConflictDetail(BaseModel):
    id:           int
    lawyer_id:    int
    lawyer_name:  str
    hearing_a:    HearingSummary
    hearing_b:    HearingSummary
    overlap_start: datetime
    overlap_end:   datetime
    resolved:      bool
    detected_at:   datetime
