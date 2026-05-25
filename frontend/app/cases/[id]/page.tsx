import { cookies }       from "next/headers";
import { notFound }      from "next/navigation";
import Link              from "next/link";
import type { ReactNode } from "react";
import { Clock, CheckCircle2, AlertTriangle, Ban, Play, Calendar } from "lucide-react";
import type { MeResponse, CaseTimeline, HearingSummaryForCase } from "@/lib/types";
import PageLayout        from "@/components/layout/PageLayout";
import Card              from "@/components/ui/Card";
import { formatTime } from "@/lib/auth";

// ── Server-side fetch ─────────────────────────────────────────────────────────

async function fetchJson<T>(path: string, cookieHeader: string): Promise<T | null> {
  const base = process.env.INTERNAL_API_URL ?? "http://backend:8000";
  const res  = await fetch(`${base}${path}`, {
    headers: { Cookie: cookieHeader },
    cache:   "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

// ── Status styling ────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; icon: ReactNode; chip: string }> = {
  scheduled:   { label: "Scheduled",   icon: <Calendar  className="h-4 w-4" />, chip: "bg-slate-100 text-slate-700"  },
  in_progress: { label: "In Progress", icon: <Play      className="h-4 w-4" />, chip: "bg-blue-100 text-blue-700"   },
  completed:   { label: "Completed",   icon: <CheckCircle2 className="h-4 w-4" />, chip: "bg-green-100 text-green-700" },
  delayed:     { label: "Delayed",     icon: <AlertTriangle className="h-4 w-4" />, chip: "bg-amber-100 text-amber-700" },
  cancelled:   { label: "Cancelled",   icon: <Ban       className="h-4 w-4" />, chip: "bg-red-100 text-red-600"    },
};

const CASE_TYPE_LABEL: Record<string, string> = {
  delinquency:    "Delinquency",
  dependency:     "Dependency",
  status_offense: "Status Offense (CHINS)",
};

const HEARING_TYPE_LABEL: Record<string, string> = {
  arraignment:       "Arraignment",
  detention:         "Detention Hearing",
  adjudicatory:      "Adjudicatory Hearing",
  dispositional:     "Dispositional Hearing",
  review:            "Review Hearing",
  status_conference: "Status Conference",
  transfer:          "Transfer Hearing",
  motion:            "Motion Hearing",
  competency:        "Competency Hearing",
  shelter_care:      "Shelter Care Hearing",
  permanency:        "Permanency Hearing",
  intake_conference: "Intake Conference",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusChip({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, icon: null, chip: "bg-gray-100 text-gray-600" };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${cfg.chip}`}>
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

function DurationPill({ h }: { h: HearingSummaryForCase }) {
  if (h.actual_start && h.actual_end) {
    const actual = Math.round(
      (new Date(h.actual_end).getTime() - new Date(h.actual_start).getTime()) / 60000
    );
    return (
      <span className="text-xs text-gray-500">
        <span className="font-medium text-gray-700">{actual} min</span> actual
        <span className="mx-1 text-gray-300">·</span>
        {h.estimated_duration_mins} min est.
      </span>
    );
  }
  return <span className="text-xs text-gray-500">{h.estimated_duration_mins} min est.</span>;
}

function TimelineEntry({ h, index, total }: { h: HearingSummaryForCase; index: number; total: number }) {
  const cfg          = STATUS_CONFIG[h.status] ?? STATUS_CONFIG.scheduled;
  const isLast       = index === total - 1;
  const date         = new Date(h.scheduled_start);
  const dateStr      = date.toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York",
  });

  return (
    <div className="flex gap-4">
      {/* Timeline spine */}
      <div className="flex flex-col items-center">
        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ring-2 ring-white
          ${h.status === "completed" ? "bg-green-500 text-white"
          : h.status === "cancelled" ? "bg-red-200 text-red-600"
          : h.status === "in_progress" ? "bg-blue-500 text-white"
          : h.status === "delayed" ? "bg-amber-400 text-white"
          : "bg-slate-200 text-slate-500"}`}>
          {cfg.icon}
        </div>
        {!isLast && <div className="mt-1 w-px flex-1 bg-gray-200" />}
      </div>

      {/* Entry card */}
      <div className={`mb-6 flex-1 rounded-lg border p-4 ${
        h.status === "in_progress" ? "border-blue-200 bg-blue-50"
        : h.status === "delayed"   ? "border-amber-200 bg-amber-50"
        : "border-gray-100 bg-white"
      }`}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">{dateStr}</p>
            <h3 className="mt-0.5 font-semibold text-court-navy">
              {HEARING_TYPE_LABEL[h.hearing_type] ?? h.hearing_type}
            </h3>
          </div>
          <StatusChip status={h.status} />
        </div>

        <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm text-gray-600 sm:grid-cols-3">
          <div>
            <span className="block text-xs text-gray-400">Time</span>
            {formatTime(h.scheduled_start)} – {formatTime(h.scheduled_end)}
          </div>
          <div>
            <span className="block text-xs text-gray-400">Courtroom</span>
            {h.courtroom_name ?? `Room ${h.courtroom_id}`}
          </div>
          <div>
            <span className="block text-xs text-gray-400">Duration</span>
            <DurationPill h={h} />
          </div>
        </div>

        {/* Check-in status row */}
        <div className="mt-3 flex flex-wrap gap-3 text-xs">
          <span className={h.lawyer_checked_in  ? "text-green-600" : "text-gray-400"}>
            {h.lawyer_checked_in  ? "✓" : "○"} Attorney checked in
          </span>
          <span className={h.accused_checked_in ? "text-green-600" : "text-gray-400"}>
            {h.accused_checked_in ? "✓" : "○"} Juvenile checked in
          </span>
          {h.interpreter_required && (
            <span className="text-amber-600">Interpreter required</span>
          )}
          {h.detention_status && (
            <span className="text-slate-500 capitalize">
              Detention: {h.detention_status.replace("_", " ")}
            </span>
          )}
        </div>

        {h.notes && (
          <p className="mt-3 rounded bg-gray-50 px-3 py-2 text-xs text-gray-500 italic">
            {h.notes}
          </p>
        )}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

interface Props {
  params: Promise<{ id: string }>;
}

export default async function CaseTimelinePage({ params }: Props) {
  const { id }        = await params;
  const cookieStore   = await cookies();
  const cookieHeader  = cookieStore.toString();

  let user: MeResponse | null   = null;
  let timeline: CaseTimeline | null = null;

  try {
    [user, timeline] = await Promise.all([
      fetchJson<MeResponse>("/api/auth/me", cookieHeader),
      fetchJson<CaseTimeline>(`/api/cases/${id}/timeline`, cookieHeader),
    ]);
  } catch {}

  if (!timeline) return notFound();

  const completed = timeline.hearings.filter(h => h.status === "completed").length;
  const total     = timeline.hearings.length;
  const primary   = timeline.respondents[0];

  return (
    <PageLayout
      user={user}
      heading={`Case ${timeline.case_number}`}
      subheading={
        `${CASE_TYPE_LABEL[timeline.case_type] ?? timeline.case_type} · ` +
        `${timeline.complexity.charAt(0).toUpperCase() + timeline.complexity.slice(1)} complexity`
      }
    >
      {/* ── Case summary strip ─────────────────────────────────────────────── */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="rounded-lg bg-court-navy p-4 text-white">
          <p className="text-xs opacity-70">Respondent</p>
          <p className="mt-1 font-semibold truncate">
            {timeline.is_confidential ? "Confidential" : (primary?.name ?? "—")}
          </p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-gray-200">
          <p className="text-xs text-gray-400">Defense Attorney</p>
          <p className="mt-1 font-semibold text-court-navy truncate">
            {timeline.is_confidential ? "Confidential" : (timeline.defense_lawyer_name ?? "—")}
          </p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-gray-200">
          <p className="text-xs text-gray-400">Case Status</p>
          <p className={`mt-1 font-semibold capitalize ${timeline.status === "closed" ? "text-gray-400" : "text-green-600"}`}>
            {timeline.status}
          </p>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-gray-200">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-court-gold" />
            <span className="text-xs text-gray-400">Hearings</span>
          </div>
          <p className="mt-1 font-semibold text-court-navy">
            {completed} / {total} completed
          </p>
        </div>
      </div>

      {/* ── Timeline ──────────────────────────────────────────────────────── */}
      <Card title="Hearing Timeline">
        {total === 0 ? (
          <p className="py-8 text-center text-sm text-gray-400">No hearings scheduled for this case.</p>
        ) : (
          <div className="mt-2">
            {timeline.hearings.map((h, i) => (
              <TimelineEntry key={h.id} h={h} index={i} total={total} />
            ))}
          </div>
        )}
      </Card>

      {/* ── Co-respondents (if any) ───────────────────────────────────────── */}
      {timeline.respondents.length > 1 && !timeline.is_confidential && (
        <div className="mt-6">
          <Card title="Co-Respondents">
            <ul className="divide-y divide-gray-50">
              {timeline.respondents.map(r => (
                <li key={r.id} className="flex items-center justify-between py-2.5 text-sm">
                  <span className="font-medium text-court-navy">{r.name}</span>
                  {r.phone && <span className="text-gray-400">{r.phone}</span>}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}

      {/* ── Back navigation ──────────────────────────────────────────────── */}
      <div className="mt-6">
        <Link
          href={user?.role === "judge" ? "/judge" : user?.role === "attorney" ? "/attorney" : "/clerk"}
          className="text-sm text-court-navy opacity-70 hover:opacity-100"
        >
          ← Back to dashboard
        </Link>
      </div>
    </PageLayout>
  );
}
