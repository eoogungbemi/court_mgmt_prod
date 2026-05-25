"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw } from "lucide-react";
import { courtrooms } from "@/lib/api";
import { formatTime, formatDate, todayDateString } from "@/lib/auth";
import type { CourtroomOverview, QueueItem } from "@/lib/types";
import { useCurrentUser }  from "@/lib/useCurrentUser";
import Navbar              from "@/components/layout/Navbar";
import { StatusBadge }     from "@/components/ui/Badge";
import { CaseTypeBadge }   from "@/components/ui/Badge";
import Spinner             from "@/components/ui/Spinner";
import { useQueueSocket }  from "@/lib/useQueueSocket";

// Polling is the fallback when WebSocket is unavailable.
const REFRESH_MS = 30_000;

function ETARange({ p25, p75 }: { p25: number | null; p75: number | null }) {
  if (p25 === null || p75 === null) return <span className="text-gray-400">—</span>;
  return <span className="text-xs text-gray-600">{p25}–{p75} min</span>;
}

function CheckDot({ checked }: { checked: boolean }) {
  return (
    <span className={`inline-block h-2.5 w-2.5 rounded-full ${checked ? "bg-green-500" : "bg-gray-300"}`} />
  );
}

function RoomQueue({ roomId, date }: { roomId: number; date: string }) {
  const [items,   setItems]   = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await courtrooms.queue(roomId, date) as QueueItem[];
      setItems(data);
    } catch {}
    setLoading(false);
  }, [roomId, date]);

  // WebSocket for instant updates; polling every 30 s as fallback.
  useQueueSocket(roomId, load);

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  if (loading) return <div className="py-4 text-center"><Spinner className="h-5 w-5 inline-block" /></div>;
  if (!items.length) return <p className="py-4 text-center text-sm text-gray-400">No hearings scheduled today</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
            <th className="pb-2 pr-4 font-medium">Time</th>
            <th className="pb-2 pr-4 font-medium">Case</th>
            <th className="pb-2 pr-4 font-medium">Type</th>
            <th className="pb-2 pr-4 font-medium">Respondent</th>
            <th className="pb-2 pr-4 font-medium hidden md:table-cell">Attorney</th>
            <th className="pb-2 pr-4 font-medium">Status</th>
            <th className="pb-2 pr-4 font-medium hidden lg:table-cell">ETA</th>
            <th className="pb-2 font-medium hidden lg:table-cell">Present</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.hearing_id} className="border-b border-gray-50 hover:bg-gray-50">
              <td className="py-2.5 pr-4 font-mono text-xs">{formatTime(item.scheduled_start)}</td>
              <td className="py-2.5 pr-4 font-mono text-xs text-gray-600">{item.case_number}</td>
              <td className="py-2.5 pr-4"><CaseTypeBadge caseType={item.case_type} /></td>
              <td className="py-2.5 pr-4 font-medium">{item.respondent_name}</td>
              <td className="py-2.5 pr-4 hidden text-gray-600 md:table-cell">{item.attorney_name}</td>
              <td className="py-2.5 pr-4"><StatusBadge status={item.status} /></td>
              <td className="py-2.5 pr-4 hidden lg:table-cell">
                <ETARange p25={item.p25_mins} p75={item.p75_mins} />
              </td>
              <td className="py-2.5 hidden gap-1 lg:flex">
                <CheckDot checked={item.attorney_checked_in} />
                <CheckDot checked={item.juvenile_checked_in} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function QueuePage() {
  const currentUser               = useCurrentUser();
  const [overview, setOverview]   = useState<CourtroomOverview[]>([]);
  const [loading,  setLoading]    = useState(true);
  const [lastRefresh, setRefresh] = useState(new Date());
  const date                      = todayDateString();

  const loadOverview = useCallback(async () => {
    try {
      const data = await courtrooms.overview(date) as CourtroomOverview[];
      setOverview(data);
    } catch {}
    setLoading(false);
    setRefresh(new Date());
  }, [date]);

  useEffect(() => {
    loadOverview();
    const t = setInterval(loadOverview, REFRESH_MS);
    return () => clearInterval(t);
  }, [loadOverview]);

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar user={currentUser} />

      <main className="mx-auto max-w-7xl px-4 py-6">
        {/* Header */}
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-court-navy">Live Courtroom Queue</h1>
            <p className="mt-1 text-sm text-gray-500">{formatDate(new Date().toISOString())}</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <RefreshCw className="h-3.5 w-3.5" />
            Updated {lastRefresh.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>
        ) : (
          <div className="space-y-6">
            {overview.map((cr) => (
              <div key={cr.id} className="rounded-lg bg-white shadow-sm ring-1 ring-gray-200">
                {/* Room header */}
                <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
                  <div>
                    <span className="font-semibold text-court-navy">{cr.name}</span>
                    {cr.judge_name && (
                      <span className="ml-2 text-sm text-gray-500">· Hon. {cr.judge_name}</span>
                    )}
                  </div>
                  <span className="text-xs text-gray-400">
                    {cr.hearing_count} hearing{cr.hearing_count !== 1 ? "s" : ""}
                    {cr.next_start && ` · next at ${formatTime(cr.next_start)}`}
                  </span>
                </div>
                <div className="px-5 py-3">
                  <RoomQueue roomId={cr.id} date={date} />
                </div>
              </div>
            ))}

            {overview.length === 0 && (
              <p className="py-20 text-center text-gray-400">No courtrooms found</p>
            )}
          </div>
        )}
      </main>

      <footer className="mt-12 border-t border-gray-200 py-4 text-center text-xs text-gray-400">
        Allegheny County Juvenile Court · Refreshes every 30 seconds
      </footer>
    </div>
  );
}
