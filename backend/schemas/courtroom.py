from datetime import datetime
from pydantic import BaseModel


class CourtroomOut(BaseModel):
    id:       int
    name:     str
    floor:    int
    judge_id: int | None = None


class QueueItem(BaseModel):
    hearing_id:              int
    case_id:                 int
    case_number:             str
    case_type:               str
    hearing_type:            str
    respondent_name:         str
    attorney_name:           str
    scheduled_start:         datetime
    estimated_duration_mins: int
    status:                  str
    attorney_checked_in:     bool
    juvenile_checked_in:     bool
    # Latest ETA, if generated
    p25_mins:   int | None = None
    p75_mins:   int | None = None
    rationale:  str | None = None


class CourtroomOverview(BaseModel):
    id:            int
    name:          str
    floor:         int
    judge_id:      int | None
    judge_name:    str | None
    hearing_count: int
    next_start:    datetime | None
