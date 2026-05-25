import { cookies }  from "next/headers";
import { BrainCircuit, CheckCircle2, AlertTriangle, Clock } from "lucide-react";
import { todayDateString } from "@/lib/auth";
import type { MeResponse } from "@/lib/types";
import PageLayout from "@/components/layout/PageLayout";
import Card       from "@/components/ui/Card";

// ── Types ─────────────────────────────────────────────────────────────────────

interface StatusBreakdown {
  scheduled: number; in_progress: number;
  completed: number; delayed: number; cancelled: number;
}
interface CaseTypeCount    { case_type: string; count: number }
interface CourtroomStat    { courtroom_id: number; courtroom_name: string; hearing_count: number; completed: number }
interface ETAAccuracy      { sample_size: number; avg_estimated_mins: number; avg_actual_mins: number; mean_abs_error_mins: number }
interface AnalyticsSummary {
  run_date: string;
  total_hearings: number;
  completion_rate_pct: number;
  status_breakdown: StatusBreakdown;
  by_case_type: CaseTypeCount[];
  by_courtroom: CourtroomStat[];
  eta_accuracy: ETAAccuracy | null;
  conflicts_unresolved: number;
  conflicts_detected_today: number;
  conflicts_resolved_today: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function fetchJson<T>(path: string, cookieHeader: string): Promise<T | null> {
  const base = process.env.INTERNAL_API_URL ?? "http://backend:8000";
  const res  = await fetch(`${base}${path}`, {
    headers: { Cookie: cookieHeader },
    cache:   "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

function ProgressBar({ value, max, color = "bg-court-navy" }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 overflow-hidden rounded-full bg-gray-100 h-2">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right text-xs text-gray-500">{value}</span>
    </div>
  );
}

const CASE_TYPE_LABEL: Record<string, string> = {
  delinquency:    "Delinquency",
  dependency:     "Dependency",
  status_offense: "Status Offense (CHINS)",
};

const STATUS_COLOR: Record<string, string> = {
  completed:   "bg-green-500",
  in_progress: "bg-blue-500",
  scheduled:   "bg-court-navy",
  delayed:     "bg-amber-500",
  cancelled:   "bg-red-400",
};

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function AnalyticsPage() {
  const cookieStore  = await cookies();
  const cookieHeader = cookieStore.toString();
  const date         = todayDateString();
  const dateLabel    = new Date().toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  let user:    MeResponse | null      = null;
  let summary: AnalyticsSummary | null = null;

  try {
    [user, summary] = await Promise.all([
      fetchJson<MeResponse>("/api/auth/me", cookieHeader),
      fetchJson<AnalyticsSummary>(`/api/analytics/summary?run_date=${date}`, cookieHeader),
    ]);
  } catch {}

  if (!summary) {
    return (
      <PageLayout user={user} heading="Analytics" subheading={dateLabel}>
        <p className="py-20 text-center text-gray-400">Unable to load analytics.</p>
      </PageLayout>
    );
  }

  const { status_breakdown: sb } = summary;
  const statusRows = [
    { label: "Completed",   value: sb.completed,   color: "bg-green-500" },
    { label: "Scheduled",   value: sb.scheduled,   color: "bg-court-navy" },
    { label: "In Progress", value: sb.in_progress, color: "bg-blue-500" },
    { label: "Delayed",     value: sb.delayed,     color: "bg-amber-500" },
    { label: "Cancelled",   value: sb.cancelled,   color: "bg-red-400" },
  ];

  return (
    <PageLayout user={user} heading="Court Analytics" subheading={dateLabel}>

      {/* ── KPI strip ────────────────────────────────────────────────────── */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {/* Total hearings */}
        <div className="rounded-lg bg-court-navy p-5 text-white">
          <div className="text-4xl font-bold">{summary.total_hearings}</div>
          <div className="mt-1 text-sm opacity-75">Total Hearings Today</div>
        </div>

        {/* Completion rate */}
        <div className="rounded-lg bg-white p-5 ring-1 ring-gray-200">
          <div className="flex items-center gap-2 text-green-600">
            <CheckCircle2 className="h-5 w-5" />
            <span className="text-3xl font-bold">{summary.completion_rate_pct}%</span>
          </div>
          <div className="mt-1 text-sm text-gray-500">Completion Rate</div>
        </div>

        {/* AI ETA accuracy */}
        <div className="rounded-lg bg-white p-5 ring-1 ring-gray-200">
          <div className="flex items-center gap-2 text-court-navy">
            <BrainCircuit className="h-5 w-5" />
            {summary.eta_accuracy ? (
              <span className="text-3xl font-bold">±{summary.eta_accuracy.mean_abs_error_mins} min</span>
            ) : (
              <span className="text-xl font-semibold text-gray-400">No data yet</span>
            )}
          </div>
          <div className="mt-1 text-sm text-gray-500">
            AI ETA Mean Error
            {summary.eta_accuracy && (
              <span className="ml-1 text-xs text-gray-400">
                (n={summary.eta_accuracy.sample_size})
              </span>
            )}
          </div>
        </div>

        {/* Conflicts */}
        <div className="rounded-lg bg-white p-5 ring-1 ring-gray-200">
          <div className="flex items-center gap-2 text-amber-600">
            <AlertTriangle className="h-5 w-5" />
            <span className="text-3xl font-bold">{summary.conflicts_detected_today}</span>
          </div>
          <div className="mt-1 text-sm text-gray-500">
            Conflicts Detected Today
            {summary.conflicts_unresolved > 0 && (
              <span className="ml-1 font-medium text-amber-600">
                ({summary.conflicts_unresolved} unresolved)
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── Main grid ────────────────────────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-3">

        {/* Hearing status breakdown */}
        <Card title="Status Breakdown">
          <div className="space-y-3">
            {statusRows.map(({ label, value, color }) => (
              <div key={label}>
                <div className="mb-1 flex justify-between text-xs text-gray-600">
                  <span>{label}</span>
                  <span className="font-medium">
                    {summary.total_hearings > 0
                      ? `${Math.round((value / summary.total_hearings) * 100)}%`
                      : "0%"}
                  </span>
                </div>
                <ProgressBar value={value} max={summary.total_hearings} color={color} />
              </div>
            ))}
          </div>
        </Card>

        {/* Case type distribution */}
        <Card title="Docket Composition">
          {summary.by_case_type.length === 0 ? (
            <p className="py-4 text-center text-sm text-gray-400">No hearings today</p>
          ) : (
            <div className="space-y-3">
              {summary.by_case_type.map(({ case_type, count }) => (
                <div key={case_type}>
                  <div className="mb-1 flex justify-between text-xs text-gray-600">
                    <span>{CASE_TYPE_LABEL[case_type] ?? case_type}</span>
                    <span className="font-medium">{count}</span>
                  </div>
                  <ProgressBar value={count} max={summary.total_hearings} color="bg-court-gold" />
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* AI ETA accuracy detail */}
        <Card title="AI Scheduling Accuracy">
          {summary.eta_accuracy ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-md bg-gray-50 p-3 text-center">
                  <div className="text-2xl font-bold text-court-navy">
                    {summary.eta_accuracy.avg_estimated_mins} min
                  </div>
                  <div className="mt-1 text-xs text-gray-500">Avg AI Estimate (p50)</div>
                </div>
                <div className="rounded-md bg-gray-50 p-3 text-center">
                  <div className="text-2xl font-bold text-court-navy">
                    {summary.eta_accuracy.avg_actual_mins} min
                  </div>
                  <div className="mt-1 text-xs text-gray-500">Avg Actual Duration</div>
                </div>
              </div>
              <div className="rounded-md border border-green-100 bg-green-50 p-3 text-center">
                <div className="text-2xl font-bold text-green-700">
                  ±{summary.eta_accuracy.mean_abs_error_mins} min
                </div>
                <div className="mt-1 text-xs text-green-600">Mean Absolute Error</div>
              </div>
              <p className="text-xs text-gray-400">
                Based on {summary.eta_accuracy.sample_size} completed hearing
                {summary.eta_accuracy.sample_size !== 1 ? "s" : ""} with recorded
                actual times. Estimates from{" "}
                <span className="font-medium">DurationEstimatorAgent</span> (Claude Haiku,
                rule-based fallback).
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <BrainCircuit className="h-8 w-8 text-gray-300" />
              <p className="text-sm text-gray-400">
                Accuracy data available once hearings complete with recorded actual times.
              </p>
            </div>
          )}
        </Card>
      </div>

      {/* ── Per-courtroom table ───────────────────────────────────────────── */}
      {summary.by_courtroom.length > 0 && (
        <div className="mt-6">
          <Card title="Courtroom Utilisation">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-gray-500">
                    <th className="pb-2 pr-6 font-medium">Courtroom</th>
                    <th className="pb-2 pr-6 font-medium">Hearings</th>
                    <th className="pb-2 pr-6 font-medium">Completed</th>
                    <th className="pb-2 font-medium">Progress</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_courtroom.map((cr) => (
                    <tr key={cr.courtroom_id} className="border-t border-gray-50">
                      <td className="py-2.5 pr-6 font-medium text-court-navy">{cr.courtroom_name}</td>
                      <td className="py-2.5 pr-6">{cr.hearing_count}</td>
                      <td className="py-2.5 pr-6 text-green-600">{cr.completed}</td>
                      <td className="py-2.5 w-40">
                        <ProgressBar
                          value={cr.completed}
                          max={cr.hearing_count}
                          color="bg-green-500"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* ── Conflict summary ──────────────────────────────────────────────── */}
      <div className="mt-6">
        <Card title="AI Conflict Detection">
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="rounded-md bg-amber-50 p-4">
              <div className="text-3xl font-bold text-amber-700">{summary.conflicts_detected_today}</div>
              <div className="mt-1 text-xs text-amber-600">Detected Today</div>
            </div>
            <div className="rounded-md bg-green-50 p-4">
              <div className="text-3xl font-bold text-green-700">{summary.conflicts_resolved_today}</div>
              <div className="mt-1 text-xs text-green-600">Resolved Today</div>
            </div>
            <div className="rounded-md bg-red-50 p-4">
              <div className="text-3xl font-bold text-red-700">{summary.conflicts_unresolved}</div>
              <div className="mt-1 text-xs text-red-600">Still Unresolved</div>
            </div>
          </div>
          <p className="mt-4 text-xs text-gray-400">
            Conflicts are detected automatically by the LangGraph{" "}
            <span className="font-medium">ConflictDetectorAgent</span> when an
            attorney is scheduled for overlapping hearings. Clerks are alerted in
            real time and can resolve conflicts from the room dashboard.
          </p>
        </Card>
      </div>

    </PageLayout>
  );
}
