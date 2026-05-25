import { cookies } from "next/headers";
import Link         from "next/link";
import { Users, Clock, AlertTriangle, TriangleAlert } from "lucide-react";
import { formatTime, todayDateString } from "@/lib/auth";
import type { MeResponse, CourtroomOverview, ConflictDetail } from "@/lib/types";
import PageLayout      from "@/components/layout/PageLayout";
import Card            from "@/components/ui/Card";
import PDFImportButton from "@/components/ui/PDFImportButton";

async function fetchJson<T>(path: string, cookieHeader: string): Promise<T | null> {
  const base = process.env.INTERNAL_API_URL ?? "http://backend:8000";
  const res  = await fetch(`${base}${path}`, {
    headers: { Cookie: cookieHeader },
    cache:   "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

// ── Conflict alert panel ──────────────────────────────────────────────────────

function ConflictAlert({ conflict }: { conflict: ConflictDetail }) {
  const fmtTime = (iso: string) =>
    new Date(iso).toLocaleTimeString("en-US", {
      hour: "numeric", minute: "2-digit", timeZone: "America/New_York",
    });

  return (
    <div className="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
      <TriangleAlert className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-500" />
      <div className="flex-1 text-sm">
        <span className="font-semibold text-amber-900">{conflict.lawyer_name}</span>
        <span className="text-amber-700">
          {" "}has overlapping hearings —{" "}
          <strong>{conflict.hearing_a.case_number}</strong> in {conflict.hearing_a.courtroom_name} at {fmtTime(conflict.hearing_a.scheduled_start)}
          {" "}and <strong>{conflict.hearing_b.case_number}</strong> in {conflict.hearing_b.courtroom_name} at {fmtTime(conflict.hearing_b.scheduled_start)}
        </span>
        <span className="ml-2 text-xs text-amber-500">
          (overlap {fmtTime(conflict.overlap_start)}–{fmtTime(conflict.overlap_end)})
        </span>
      </div>
      {/* Resolution is done in the room view — link to first affected room */}
      <Link
        href={`/clerk/${conflict.hearing_a.id}`}
        className="shrink-0 text-xs text-amber-700 underline hover:text-amber-900"
      >
        View
      </Link>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function ClerkOverviewPage() {
  const cookieStore  = await cookies();
  const cookieHeader = cookieStore.toString();
  const date         = todayDateString();

  let user:      MeResponse | null         = null;
  let overview:  CourtroomOverview[]       = [];
  let conflicts: ConflictDetail[]          = [];

  try {
    const [me, ov] = await Promise.all([
      fetchJson<MeResponse>("/api/auth/me", cookieHeader),
      fetchJson<CourtroomOverview[]>(`/api/courtrooms/overview?run_date=${date}`, cookieHeader),
    ]);
    user     = me;
    overview = ov ?? [];

    const raw = await fetchJson<ConflictDetail[]>("/api/conflicts?resolved=false", cookieHeader);
    conflicts = raw ?? [];
  } catch {}

  const totalHearings = overview.reduce((s, cr) => s + cr.hearing_count, 0);
  const nextStart     = overview
    .map((cr) => cr.next_start)
    .filter(Boolean)
    .sort()[0];

  return (
    <PageLayout
      user={user}
      heading="Clerk Dashboard"
      subheading={`Today's docket — ${new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}`}
    >
      {/* ── Conflict alert banner ──────────────────────────────────────────── */}
      {conflicts.length > 0 && (
        <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <div className="mb-3 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <span className="font-semibold text-amber-800">
              {conflicts.length} Scheduling Conflict{conflicts.length !== 1 ? "s" : ""} Detected
            </span>
            <span className="text-xs text-amber-600">— AI agent flagged these automatically</span>
          </div>
          <div className="space-y-2">
            {conflicts.map((c) => <ConflictAlert key={c.id} conflict={c} />)}
          </div>
        </div>
      )}

      {/* ── Actions bar ───────────────────────────────────────────────────── */}
      <div className="mb-4 flex justify-end">
        <PDFImportButton />
      </div>

      {/* ── Summary strip ─────────────────────────────────────────────────── */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div className="rounded-lg bg-court-navy p-4 text-white">
          <div className="text-3xl font-bold">{totalHearings}</div>
          <div className="mt-1 text-sm opacity-75">Total Hearings</div>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-gray-200">
          <div className="flex items-center gap-2 text-court-navy">
            <Clock className="h-5 w-5" />
            <span className="text-xl font-bold">{nextStart ? formatTime(nextStart) : "—"}</span>
          </div>
          <div className="mt-1 text-sm text-gray-500">Next Hearing</div>
        </div>
        <div className="rounded-lg bg-white p-4 ring-1 ring-gray-200">
          <div className="flex items-center gap-2 text-court-navy">
            <Users className="h-5 w-5" />
            <span className="text-xl font-bold">{overview.length}</span>
          </div>
          <div className="mt-1 text-sm text-gray-500">Active Courtrooms</div>
        </div>
      </div>

      {/* ── Room cards ────────────────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {overview.map((cr) => (
          <Link key={cr.id} href={`/clerk/${cr.id}`} className="group block">
            <Card className="transition-shadow group-hover:shadow-md">
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-semibold text-court-navy">{cr.name}</p>
                  <p className="mt-0.5 text-xs text-gray-500">
                    {cr.judge_name ?? "Judge TBD"}
                    {" · Floor "}{cr.floor}
                  </p>
                </div>
                <span className="rounded-full bg-court-navy px-2.5 py-0.5 text-xs font-medium text-white">
                  {cr.hearing_count}
                </span>
              </div>
              {cr.next_start && (
                <p className="mt-3 text-xs text-gray-500">
                  Next: <strong>{formatTime(cr.next_start)}</strong>
                </p>
              )}
              {cr.hearing_count === 0 && (
                <p className="mt-3 text-xs text-gray-400">No hearings today</p>
              )}
            </Card>
          </Link>
        ))}
      </div>

      {overview.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-20 text-gray-400">
          <AlertTriangle className="h-8 w-8" />
          <p>No courtroom data available</p>
        </div>
      )}
    </PageLayout>
  );
}
