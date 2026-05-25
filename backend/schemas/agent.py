from typing import Any, Literal
from pydantic import BaseModel


class AgentTriggerRequest(BaseModel):
    courtroom_id:    int
    run_date:        str                    # YYYY-MM-DD
    trigger:         Literal["tick", "checkin", "overrun", "complete"]
    trigger_payload: dict[str, Any] = {}


class AgentTriggerResponse(BaseModel):
    courtroom_id: int
    run_date:     str
    trigger:      str
    audit_count:  int
    conflicts:    int
    eta_count:    int
