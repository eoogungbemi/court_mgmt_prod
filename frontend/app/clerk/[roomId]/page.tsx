"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams }  from "next/navigation";
import Link           from "next/link";
import { RefreshCw, TriangleAlert, CalendarPlus }  from "lucide-react";
import { courtrooms, hearings as hearingsApi, agentsApi, conflicts as conflictsApi, cases as casesApi } from "@/lib/api";
import { formatTime, todayDateString }                               from "@/lib/auth";
import type { QueueItem, HearingStatus, ConflictDetail, CaseOut, CourtroomOut } from "@/lib/types";
import { useCurrentUser }   from "@/lib/useCurrentUser";
import PageLayout   from "@/components/layout/PageLayout";
import { StatusBadge, CaseTypeBadge } from "@/components/ui/Badge";
import Button       from "@/components/ui/Button";
import Input        from "@/components/ui/Input";
import Spinner      from "@/components/ui/Spinner";
import { useQueueSocket } from "@/lib/useQueueSocket";

const REFRESH_MS = 20_000;

const NEXT_STATUS: Partial<Record<HearingStatus, HearingStatus>> = {
  scheduled:   "in_progress",
  in_progress: "completed",
  delayed:     "in_progress",
};

const STATUS_LABEL: Partial<Record<HearingStatus, string>> = {
  scheduled:   "Start",
  in_progress: "Complete",
  delayed:     "Resume",
};

const HEARING_TYPES = [
  { value: "arraignment",       label: "Arraignment" },
  { value: "adjudicatory",      label: "Adjudicatory Hearing" },
  { value: "dispositional",     label: "Dispositional Hearing" },
  { value: "review",            label: "Review Hearing" },
  { value: "detention",         label: "Detention Hearing" },
  { value: "status_conference", label: "Status Conference" },
  { value: "transfer",          label: "Transfer Hearing" },
  { value: "motion",            label: "Motion Hearing" },
  { value: "competency",        label: "Competency Hearing" },
  { value: "shelter_care",      label: "Shelter Care Hearing" },
  { value: "permanency",        label: "Permanency Hearing" },
  { value: "intake_conference", label: "Intake Conference" },
];

const DEFAULT_DURATION: Record<string, number> = {
  arraignment: 15, adjudicatory: 45, dispositional: 30,
  review: 20, detention: 20, status_conference: 20,
  transfer: 60, motion: 30, competency: 45,
  shelter_care: 20, permanency: 45, intake_conference: 20,
};

// ── Schedule Hearing modal ────────────────────────────────────────────────────

function ScheduleModal({
  room,
  onClose,
  onScheduled,
}: {
  room: CourtroomOut;
  onClose: () => void;
  onScheduled: () => void;
}) {
  const [caseQuery,    setCaseQuery]    = useState("");
  const [caseResults,  setCaseResults]  = useState<CaseOut[]>([]);
  const [selectedCase, setSelectedCase] = useState<CaseOut | null>(null);
  const [searching,    setSearching]    = useState(false);
  const [hearingType,  setHearingType]  = useState("adjudicatory");
  const [date,         setDate]         = useState(todayDateString());
  const [time,         setTime]         = useState("09:00");
  const [duration,     setDuration]     = useState(45);
  const [interpreter,  setInterpreter]  = useState(false);
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState("");

  async function searchCases() {
    if (!caseQuery.trim()) return;
    setSearching(true);
    try {
      const data = await casesApi.search({ q: caseQuery, page_size: 8 }) as CaseOut[];
      setCaseResults(data);
    } finally {
      setSearching(false);
    }
  }

  function pickCase(c: CaseOut) {
    setSelectedCase(c);
    setCaseResults([]);
    setCaseQuery(c.case_number);
  }

  function onTypeChange(t: string) {
    setHearingType(t);
    setDuration(DEFAULT_DURATION[t] ?? 30);
  }

  function endTime() {
    const [h, m] = time.split(":").map(Number);
    const totalMins = h * 60 + m + duration;
    return `${String(Math.floor(totalMins / 60) % 24).padStart(2, "0")}:${String(totalMins % 60).padStart(2, "0")}`;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedCase) { setError("Select a case first"); return; }
    if (!room.judge_id) { setError("This courtroom has no assigned judge"); return; }
    setError("");
    setLoading(true);
    try {
      const start = new Date(`${date}T${time}:00`).toISOString();
      const end   = new Date(`${date}T${endTime()}:00`).toISOString();
      await hearingsApi.create({
        case_id:                 selectedCase.id,
        courtroom_id:            room.id,
        judge_id:                room.judge_id,
        hearing_type:            hearingType,
        scheduled_start:         start,
        scheduled_end:           end,
        estimated_duration_mins: duration,
        interpreter_required:    interpreter,
      });
      onScheduled();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to schedule hearing");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-court-navy">
          Schedule Hearing — {room.name}
        </h2>
        <form onSubmit={submit} className="space-y-4">
          {/* Case search */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Case</label>
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
                placeholder="Case number or respondent name…"
                value={caseQuery}
                onChange={(e) => { setCaseQuery(e.target.value); setSelectedCase(null); }}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), searchCases())}
              />
              <Button type="button" size="sm" variant="secondary" loading={searching} onClick={searchCases}>
                Search
              </Button>
            </div>
            {caseResults.length > 0 && !selectedCase && (
              <div className="mt-1 max-h-40 overflow-y-auto rounded-md border border-gray-200 bg-white shadow-sm">
                {caseResults.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className="w-full px-3 py-2 text-left text-sm hover:bg-gray-50"
                    onClick={() => pickCase(c)}
                  >
                    <span className="font-mono font-medium">{c.case_number}</span>
                    <span className="ml-2 text-gray-500">
                      {c.respondents[0]?.name ?? "—"} · {c.case_type.replace(/_/g, " ")}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {selectedCase && (
              <p className="mt-1 text-xs text-green-700">
                Selected: <strong>{selectedCase.case_number}</strong> — {selectedCase.respondents[0]?.name}
              </p>
            )}
          </div>

          {/* Hearing type */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Hearing Type</label>
            <select
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
              value={hearingType}
              onChange={(e) => onTypeChange(e.target.value)}
            >
              {HEARING_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>

          {/* Date + time */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Date</label>
              <input
                type="date"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Start Time</label>
              <input
                type="time"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                required
              />
            </div>
          </div>

          {/* Duration + end time preview */}
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium text-gray-700">Duration (minutes)</label>
              <input
                type="number"
                min={5}
                max={480}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                required
              />
            </div>
            <p className="pb-2 text-sm text-gray-500">Ends at {endTime()}</p>
          </div>

          {/* Interpreter */}
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-gray-300 text-court-navy"
              checked={interpreter}
              onChange={(e) => setInterpreter(e.target.checked)}
            />
            Interpreter required
          </label>

          {error && <p className="text-xs text-red-600">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={loading}>Schedule Hearing</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Reschedule modal ──────────────────────────────────────────────────────────

function RescheduleModal({
  item,
  onClose,
  onRescheduled,
}: {
  item: QueueItem;
  onClose: () => void;
  onRescheduled: () => void;
}) {
  const existing   = new Date(item.scheduled_start);
  const [date,     setDate]     = useState(existing.toISOString().slice(0, 10));
  const [time,     setTime]     = useState(existing.toTimeString().slice(0, 5));
  const [duration, setDuration] = useState(item.estimated_duration_mins);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  function endTime() {
    const [h, m] = time.split(":").map(Number);
    const totalMins = h * 60 + m + duration;
    return `${String(Math.floor(totalMins / 60) % 24).padStart(2, "0")}:${String(totalMins % 60).padStart(2, "0")}`;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const start = new Date(`${date}T${time}:00`).toISOString();
      const end   = new Date(`${date}T${endTime()}:00`).toISOString();
      await hearingsApi.reschedule(item.hearing_id, {
        scheduled_start: start,
        scheduled_end:   end,
        estimated_duration_mins: duration,
      });
      onRescheduled();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to reschedule");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-semibold text-court-navy">Reschedule Hearing</h2>
        <p className="mb-4 text-sm text-gray-500">
          {item.case_number} — {item.respondent_name}
        </p>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Date</label>
              <input
                type="date"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Start Time</label>
              <input
                type="time"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium text-gray-700">Duration (min)</label>
              <input
                type="number"
                min={5}
                max={480}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                required
              />
            </div>
            <p className="pb-2 text-sm text-gray-500">Ends {endTime()}</p>
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={loading}>Reschedule</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ClerkRoomPage() {
  const currentUser   = useCurrentUser();
  const { roomId }    = useParams<{ roomId: string }>();
  const id            = Number(roomId);
  const date          = todayDateString();

  const [room,        setRoom]        = useState<CourtroomOut | null>(null);
  const [queue,       setQueue]       = useState<QueueItem[]>([]);
  const [conflicts,   setConflicts]   = useState<ConflictDetail[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [busy,        setBusy]        = useState<number | null>(null);
  const [showSchedule, setShowSchedule] = useState(false);
  const [rescheduleItem, setRescheduleItem] = useState<QueueItem | null>(null);
  const [lastRefresh, setRefresh]     = useState(new Date());

  const loadQueue = useCallback(async () => {
    try {
      const [roomData, queueData, conflictData] = await Promise.all([
        courtrooms.get(id) as Promise<CourtroomOut>,
        courtrooms.queue(id, date) as Promise<QueueItem[]>,
        conflictsApi.list({ resolved: false }) as Promise<ConflictDetail[]>,
      ]);
      setRoom(roomData);
      setQueue(queueData);
      setConflicts(conflictData);
    } catch {}
    setLoading(false);
    setRefresh(new Date());
  }, [id, date]);

  // WebSocket for instant updates; polling every 20 s as fallback.
  useQueueSocket(id, loadQueue);

  useEffect(() => {
    loadQueue();
    const t = setInterval(loadQueue, REFRESH_MS);
    return () => clearInterval(t);
  }, [loadQueue]);

  async function handleCheckin(hearingId: number, party: "attorney" | "juvenile") {
    setBusy(hearingId);
    try {
      await hearingsApi.checkin(hearingId, party);
      // trigger LangGraph checkin event
      await agentsApi.trigger({
        courtroom_id:    id,
        run_date:        date,
        trigger:         "checkin",
        trigger_payload: { hearing_id: hearingId, party },
      }).catch(() => {});
      await loadQueue();
    } finally {
      setBusy(null);
    }
  }

  async function handleStatusChange(hearingId: number, newStatus: HearingStatus) {
    setBusy(hearingId);
    try {
      const body: Record<string, unknown> = { status: newStatus };
      if (newStatus === "in_progress") body.actual_start = new Date().toISOString();
      if (newStatus === "completed")   body.actual_end   = new Date().toISOString();
      await hearingsApi.setStatus(hearingId, body);
      if (newStatus === "completed") {
        await agentsApi.trigger({
          courtroom_id:    id,
          run_date:        date,
          trigger:         "complete",
          trigger_payload: { hearing_id: hearingId },
        }).catch(() => {});
      }
      await loadQueue();
    } finally {
      setBusy(null);
    }
  }

  async function handleDelay(hearingId: number) {
    setBusy(hearingId);
    try {
      await hearingsApi.setStatus(hearingId, { status: "delayed" });
      await agentsApi.trigger({
        courtroom_id:    id,
        run_date:        date,
        trigger:         "overrun",
        trigger_payload: { hearing_id: hearingId },
      }).catch(() => {});
      await loadQueue();
    } finally {
      setBusy(null);
    }
  }

  async function handleResolveConflict(conflictId: number) {
    try {
      await conflictsApi.resolve(conflictId);
      setConflicts((prev) => prev.filter((c) => c.id !== conflictId));
    } catch {}
  }

  // Build a set of hearing IDs involved in any unresolved conflict in this room
  const queueIds = new Set(queue.map((q) => q.hearing_id));
  const conflictedHearingIds = new Set(
    conflicts
      .filter((c) => queueIds.has(c.hearing_a.id) || queueIds.has(c.hearing_b.id))
      .flatMap((c) => [c.hearing_a.id, c.hearing_b.id])
  );
  const roomConflicts = conflicts.filter(
    (c) => queueIds.has(c.hearing_a.id) || queueIds.has(c.hearing_b.id)
  );

  const roomName = room?.name ?? `Courtroom ${id}`;

  return (
    <PageLayout
      user={currentUser}
      heading={roomName}
      subheading="Live docket management"
    >
      {/* Modals */}
      {showSchedule && room && (
        <ScheduleModal
          room={room}
          onClose={() => setShowSchedule(false)}
          onScheduled={loadQueue}
        />
      )}
      {rescheduleItem && (
        <RescheduleModal
          item={rescheduleItem}
          onClose={() => setRescheduleItem(null)}
          onRescheduled={loadQueue}
        />
      )}

      {/* Refresh indicator + Schedule button */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500">{queue.length} hearing{queue.length !== 1 ? "s" : ""} today</span>
          <div className="flex items-center gap-1 text-xs text-gray-400">
            <RefreshCw className="h-3 w-3" />
            {lastRefresh.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
          </div>
        </div>
        {room && (
          <Button size="sm" onClick={() => setShowSchedule(true)}>
            <CalendarPlus className="mr-1 h-4 w-4" /> Schedule Hearing
          </Button>
        )}
      </div>

      {/* ── Conflict alerts ─────────────────────────────────────────────── */}
      {roomConflicts.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-amber-800">
            <TriangleAlert className="h-4 w-4" />
            {roomConflicts.length} Scheduling Conflict{roomConflicts.length !== 1 ? "s" : ""} — AI Detected
          </div>
          <div className="space-y-2">
            {roomConflicts.map((c) => (
              <div key={c.id} className="flex items-start justify-between gap-3 text-sm text-amber-700">
                <span>
                  <strong>{c.lawyer_name}</strong>: {c.hearing_a.case_number} ({c.hearing_a.courtroom_name})
                  {" ↔ "}
                  {c.hearing_b.case_number} ({c.hearing_b.courtroom_name})
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleResolveConflict(c.id)}
                  className="shrink-0 text-amber-700 hover:text-amber-900"
                >
                  Resolve
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>
      ) : (
        <div className="space-y-3">
          {queue.map((item) => {
            const isBusy      = busy === item.hearing_id;
            const nextStatus  = NEXT_STATUS[item.status];
            const actionLabel = STATUS_LABEL[item.status];
            const hasConflict = conflictedHearingIds.has(item.hearing_id);

            return (
              <div
                key={item.hearing_id}
                className={`rounded-lg bg-white shadow-sm ring-1 ${hasConflict ? "ring-amber-400" : "ring-gray-200"}`}
              >
                <div className="flex flex-wrap items-start gap-3 px-5 py-4">
                  {/* Time + case info */}
                  <div className="min-w-[80px]">
                    <p className="font-mono text-sm font-semibold">{formatTime(item.scheduled_start)}</p>
                    <Link
                      href={`/cases/${item.case_id}`}
                      className="font-mono text-xs text-court-navy opacity-70 hover:opacity-100 hover:underline"
                    >
                      {item.case_number}
                    </Link>
                  </div>

                  <div className="flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{item.respondent_name}</span>
                      <CaseTypeBadge caseType={item.case_type} />
                      <StatusBadge   status={item.status} />
                      {hasConflict && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                          <TriangleAlert className="h-3 w-3" /> Conflict
                        </span>
                      )}
                      {item.p25_mins !== null && (
                        <span className="text-xs text-gray-400">{item.p25_mins}–{item.p75_mins} min ETA</span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {item.hearing_type.replace(/_/g, " ")} · Atty: {item.attorney_name}
                    </p>
                  </div>

                  {/* Check-in dots */}
                  <div className="flex flex-col gap-1 text-xs">
                    <button
                      disabled={item.attorney_checked_in || isBusy}
                      onClick={() => handleCheckin(item.hearing_id, "attorney")}
                      className={`flex items-center gap-1.5 rounded px-2 py-1 transition-colors ${
                        item.attorney_checked_in
                          ? "bg-green-50 text-green-700"
                          : "bg-gray-50 text-gray-500 hover:bg-green-50 hover:text-green-700"
                      }`}
                    >
                      <span className={`h-2 w-2 rounded-full ${item.attorney_checked_in ? "bg-green-500" : "bg-gray-300"}`} />
                      Attorney
                    </button>
                    <button
                      disabled={item.juvenile_checked_in || isBusy}
                      onClick={() => handleCheckin(item.hearing_id, "juvenile")}
                      className={`flex items-center gap-1.5 rounded px-2 py-1 transition-colors ${
                        item.juvenile_checked_in
                          ? "bg-green-50 text-green-700"
                          : "bg-gray-50 text-gray-500 hover:bg-green-50 hover:text-green-700"
                      }`}
                    >
                      <span className={`h-2 w-2 rounded-full ${item.juvenile_checked_in ? "bg-green-500" : "bg-gray-300"}`} />
                      Juvenile
                    </button>
                  </div>

                  {/* Action buttons */}
                  {item.status !== "completed" && item.status !== "cancelled" && (
                    <div className="flex items-center gap-2">
                      {nextStatus && actionLabel && (
                        <Button
                          size="sm"
                          loading={isBusy}
                          onClick={() => handleStatusChange(item.hearing_id, nextStatus)}
                        >
                          {actionLabel}
                        </Button>
                      )}
                      {item.status === "in_progress" && (
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={isBusy}
                          onClick={() => handleDelay(item.hearing_id)}
                        >
                          Delay
                        </Button>
                      )}
                      {item.status === "scheduled" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setRescheduleItem(item)}
                        >
                          Reschedule
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {queue.length === 0 && (
            <p className="py-20 text-center text-gray-400">No hearings scheduled today</p>
          )}
        </div>
      )}
    </PageLayout>
  );
}
