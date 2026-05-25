// ── Auth ─────────────────────────────────────────────────────────────────────

export type Role = "admin" | "clerk" | "attorney" | "judge" | "public";

export interface MeResponse {
  id:        number;
  username:  string;
  role:      Role;
  lawyer_id: number | null;
  judge_id:  number | null;
}

export interface TokenResponse {
  role:     Role;
  username: string;
}

// ── Courtrooms ────────────────────────────────────────────────────────────────

export interface CourtroomOut {
  id:       number;
  name:     string;
  floor:    number;
  judge_id: number | null;
}

export interface CourtroomOverview {
  id:            number;
  name:          string;
  floor:         number;
  judge_id:      number | null;
  judge_name:    string | null;
  hearing_count: number;
  next_start:    string | null;
}

export interface QueueItem {
  hearing_id:              number;
  case_id:                 number;
  case_number:             string;
  case_type:               string;
  hearing_type:            string;
  respondent_name:         string;
  attorney_name:           string;
  scheduled_start:         string;
  estimated_duration_mins: number;
  status:                  HearingStatus;
  attorney_checked_in:     boolean;
  juvenile_checked_in:     boolean;
  p25_mins:                number | null;
  p75_mins:                number | null;
  rationale:               string | null;
}

// ── Cases ─────────────────────────────────────────────────────────────────────

export type CaseType   = "delinquency" | "dependency" | "status_offense";
export type Complexity = "low" | "medium" | "high";

export interface AccusedOut {
  id:             number;
  name:           string;
  phone:          string | null;
  guardian_name:  string | null;
  guardian_phone: string | null;
}

export interface CaseOut {
  id:                number;
  case_number:       string;
  case_type:         CaseType;
  complexity:        Complexity;
  status:            "active" | "closed";
  is_confidential:   boolean;
  defense_lawyer_id: number;
  respondents:       AccusedOut[];
}

export interface HearingSummaryForCase {
  id:                      number;
  hearing_type:            string;
  scheduled_start:         string;
  scheduled_end:           string;
  estimated_duration_mins: number;
  actual_start:            string | null;
  actual_end:              string | null;
  status:                  HearingStatus;
  courtroom_id:            number;
  courtroom_name:          string | null;
  judge_id:                number;
  lawyer_checked_in:       boolean;
  accused_checked_in:      boolean;
  interpreter_required:    boolean;
  detention_status:        string | null;
  notes:                   string | null;
}

export interface CaseTimeline {
  id:                   number;
  case_number:          string;
  case_type:            CaseType;
  complexity:           Complexity;
  status:               "active" | "closed";
  is_confidential:      boolean;
  defense_lawyer_id:    number;
  defense_lawyer_name:  string | null;
  respondents:          AccusedOut[];
  hearings:             HearingSummaryForCase[];
}

export interface BulkUploadResult {
  created: number;
  skipped: number;
  errors:  string[];
  cases:   CaseOut[];
}

// ── Hearings ──────────────────────────────────────────────────────────────────

export type HearingStatus =
  | "scheduled"
  | "in_progress"
  | "completed"
  | "delayed"
  | "cancelled";

export interface ETAEstimateOut {
  id:              number;
  hearing_id:      number;
  estimated_start: string;
  p25_mins:        number;
  p75_mins:        number;
  rationale:       string | null;
  agent_name:      string;
  generated_at:    string;
}

export interface HearingOut {
  id:                      number;
  case_id:                 number;
  courtroom_id:            number;
  judge_id:                number;
  hearing_type:            string;
  scheduled_start:         string;
  scheduled_end:           string;
  estimated_duration_mins: number;
  actual_start:            string | null;
  actual_end:              string | null;
  status:                  HearingStatus;
  lawyer_checked_in:       boolean;
  accused_checked_in:      boolean;
  notes:                   string | null;
  interpreter_required:    boolean;
  detention_status:        string | null;
  eta_estimates:           ETAEstimateOut[];
}

export interface AuditLogOut {
  id:          number;
  event_type:  string;
  agent_name:  string;
  entity_type: string | null;
  entity_id:   number | null;
  payload:     string | null;
  created_at:  string;
}

// ── Attorneys ─────────────────────────────────────────────────────────────────

export interface AttorneyOut {
  id:         number;
  name:       string;
  bar_number: string;
  phone:      string | null;
  email:      string | null;
}

export interface AttorneyScheduleItem {
  hearing_id:      number;
  case_id:         number;
  case_number:     string;
  case_type:       string;
  hearing_type:    string;
  courtroom_name:  string;
  scheduled_start: string;
  scheduled_end:   string;
  status:          HearingStatus;
}

// ── Conflicts ─────────────────────────────────────────────────────────────────

export interface ConflictHearingSummary {
  id:              number;
  scheduled_start: string;
  courtroom_name:  string;
  case_number:     string;
}

export interface ConflictDetail {
  id:            number;
  lawyer_id:     number;
  lawyer_name:   string;
  hearing_a:     ConflictHearingSummary;
  hearing_b:     ConflictHearingSummary;
  overlap_start: string;
  overlap_end:   string;
  resolved:      boolean;
  detected_at:   string;
}

// Legacy flat shape returned by GET /conflicts/{id}
export interface ConflictOut {
  id:            number;
  lawyer_id:     number;
  hearing_a_id:  number;
  hearing_b_id:  number;
  overlap_start: string;
  overlap_end:   string;
  resolved:      boolean;
  detected_at:   string;
}

// ── Users (admin) ─────────────────────────────────────────────────────────────

export interface UserOut {
  id:         number;
  username:   string;
  email:      string | null;
  role:       Role;
  lawyer_id:  number | null;
  judge_id:   number | null;
  is_active:  boolean;
  created_at: string;
  last_login: string | null;
}

// ── PDF Import ────────────────────────────────────────────────────────────────

export type PDFMatchStatus = "matched" | "new_case" | "error";

export interface PDFHearingPreviewRow {
  row_index:            number;
  participant:          string;
  fid_number:           string | null;
  juv_id:               string | null;
  docket_number:        string;
  calendar_event:       string;
  hearing_type:         string;
  date:                 string;
  time:                 string;
  judge_name:           string;
  case_worker_po:       string | null;
  judge_id:             number | null;
  courtroom_id:         number | null;
  case_id:              number | null;
  existing_case_number: string | null;
  case_type:            string;
  match_status:         PDFMatchStatus;
  issues:               string[];
  include:              boolean;
}

export interface PDFImportPreviewResponse {
  hearing_date: string;
  judge_name:   string;
  total_rows:   number;
  matched:      number;
  new_cases:    number;
  errors:       number;
  rows:         PDFHearingPreviewRow[];
}

export interface PDFImportResult {
  hearings_created: number;
  cases_created:    number;
  skipped:          number;
  errors:           string[];
}
