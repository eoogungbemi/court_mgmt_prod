from pydantic import BaseModel


class StatusBreakdown(BaseModel):
    scheduled:   int
    in_progress: int
    completed:   int
    delayed:     int
    cancelled:   int


class CaseTypeCount(BaseModel):
    case_type: str
    count:     int


class CourtroomStat(BaseModel):
    courtroom_id:   int
    courtroom_name: str
    hearing_count:  int
    completed:      int


class ETAAccuracy(BaseModel):
    sample_size:         int
    avg_estimated_mins:  float
    avg_actual_mins:     float
    mean_abs_error_mins: float  # MAE: lower is better


class AnalyticsSummary(BaseModel):
    run_date:                 str
    total_hearings:           int
    completion_rate_pct:      float   # % of non-cancelled hearings completed
    status_breakdown:         StatusBreakdown
    by_case_type:             list[CaseTypeCount]
    by_courtroom:             list[CourtroomStat]
    eta_accuracy:             ETAAccuracy | None  # None if no completed hearings yet
    conflicts_unresolved:     int
    conflicts_detected_today: int
    conflicts_resolved_today: int
