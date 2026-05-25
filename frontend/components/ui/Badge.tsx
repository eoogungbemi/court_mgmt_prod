import clsx from "clsx";
import type { HearingStatus } from "@/lib/types";

// Status badge
const statusClass: Record<HearingStatus, string> = {
  scheduled:   "status-scheduled",
  in_progress: "status-in_progress",
  completed:   "status-completed",
  delayed:     "status-delayed",
  cancelled:   "status-cancelled",
};

const statusLabel: Record<HearingStatus, string> = {
  scheduled:   "Scheduled",
  in_progress: "In Progress",
  completed:   "Completed",
  delayed:     "Delayed",
  cancelled:   "Cancelled",
};

export function StatusBadge({ status }: { status: HearingStatus }) {
  return (
    <span className={clsx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", statusClass[status])}>
      {statusLabel[status]}
    </span>
  );
}

// Case type badge
const caseClass: Record<string, string> = {
  delinquency:    "case-delinquency",
  dependency:     "case-dependency",
  status_offense: "case-status_offense",
};

const caseLabel: Record<string, string> = {
  delinquency:    "Delinquency",
  dependency:     "Dependency",
  status_offense: "Status Offense",
};

export function CaseTypeBadge({ caseType }: { caseType: string }) {
  return (
    <span className={clsx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", caseClass[caseType] ?? "bg-gray-100 text-gray-800")}>
      {caseLabel[caseType] ?? caseType}
    </span>
  );
}

// Generic badge
export function Badge({ label, color = "gray" }: { label: string; color?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full bg-${color}-100 text-${color}-800 px-2.5 py-0.5 text-xs font-medium`}>
      {label}
    </span>
  );
}
