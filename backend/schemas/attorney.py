from datetime import date, datetime
from pydantic import BaseModel


class AttorneyOut(BaseModel):
    model_config = {"from_attributes": True}

    id:         int
    name:       str
    bar_number: str
    phone:      str | None
    email:      str | None


class AttorneyScheduleItem(BaseModel):
    hearing_id:      int
    case_id:         int
    case_number:     str
    case_type:       str
    hearing_type:    str
    courtroom_name:  str
    scheduled_start: datetime
    scheduled_end:   datetime
    status:          str


class AttorneyAvailability(BaseModel):
    attorney_id:    int
    attorney_name:  str
    date:           date
    available_from: datetime | None
    available_to:   datetime | None
    hearings:       list[AttorneyScheduleItem]
    has_conflicts:  bool
