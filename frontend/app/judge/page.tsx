import { cookies }  from "next/headers";
import Link          from "next/link";
import { formatTime, todayDateString } from "@/lib/auth";
import type { MeResponse, QueueItem, CourtroomOverview } from "@/lib/types";
import PageLayout      from "@/components/layout/PageLayout";
import { StatusBadge, CaseTypeBadge } from "@/components/ui/Badge";
import Card            from "@/components/ui/Card";
import PrintButton     from "@/components/ui/PrintButton";

async function fetchJson<T>(path: string, cookieHeader: string): Promise<T> {
  const base = process.env.INTERNAL_API_URL ?? "http://backend:8000";
  const res  = await fetch(`${base}${path}`, {
    headers: { Cookie: cookieHeader },
    cache:   "no-store",
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export default async function JudgePage() {
  const cookieStore  = await cookies();
  const cookieHeader = cookieStore.toString();
  const date         = todayDateString();
  const dateLabel    = new Date().toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  let user:     MeResponse | null   = null;
  let overview: CourtroomOverview[] = [];
  let myRoom:   CourtroomOverview | undefined;
  let queue:    QueueItem[]         = [];

  try {
    user     = await fetchJson<MeResponse>("/api/auth/me", cookieHeader);
    overview = await fetchJson<CourtroomOverview[]>(
      `/api/courtrooms/overview?run_date=${date}`, cookieHeader
    );
    myRoom = overview[0];
    if (myRoom) {
      queue = await fetchJson<QueueItem[]>(
        `/api/courtrooms/${myRoom.id}/queue?run_date=${date}`, cookieHeader
      );
    }
  } catch {}

  const completed  = queue.filter((h) => h.status === "completed").length;
  const inProgress = queue.filter(
    (h) => h.status === "in_progress" || h.status === "delayed"
  ).length;

  return (
    <>
      {/* ── Print-only header (hidden on screen) ─────────────────────────── */}
      <div className="hidden print:block mb-6">
        <p className="text-lg font-bold">Allegheny County Juvenile Court</p>
        <p className="text-sm">Court of Common Pleas — Family Division, Juvenile Branch</p>
        <p className="text-sm">{myRoom?.name ?? "Courtroom"} · {dateLabel}</p>
        {myRoom?.judge_name && (
          <p className="text-sm">Presiding: {myRoom.judge_name}</p>
        )}
        <hr className="my-3" />
      </div>

      <PageLayout
        user={user}
        heading={myRoom ? `${myRoom.name} — Today's Docket` : "Judge Docket"}
        subheading={dateLabel}
      >
        {/* Screen-only actions */}
        <div className="mb-6 flex items-center justify-between print:hidden">
          <div className="grid grid-cols-3 gap-4 flex-1 mr-4">
            <Card>
              <div className="text-center">
                <div className="text-3xl font-bold text-court-navy">{queue.length}</div>
                <div className="mt-1 text-xs text-gray-500">Total Hearings</div>
              </div>
            </Card>
            <Card>
              <div className="text-center">
                <div className="text-3xl font-bold text-green-600">{completed}</div>
                <div className="mt-1 text-xs text-gray-500">Completed</div>
              </div>
            </Card>
            <Card>
              <div className="text-center">
                <div className="text-3xl font-bold text-yellow-600">{inProgress}</div>
                <div className="mt-1 text-xs text-gray-500">In Progress / Delayed</div>
              </div>
            </Card>
          </div>
          <PrintButton />
        </div>

        {/* Print-only summary */}
        <div className="hidden print:flex print:gap-8 print:mb-4 text-sm">
          <span><strong>Total:</strong> {queue.length}</span>
          <span><strong>Completed:</strong> {completed}</span>
          <span><strong>In Progress:</strong> {inProgress}</span>
        </div>

        {/* Docket table */}
        {queue.length === 0 ? (
          <Card>
            <p className="py-8 text-center text-gray-400">No hearings on today&apos;s docket</p>
          </Card>
        ) : (
          <div className="overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-gray-200 print:shadow-none print:ring-0">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 print:bg-white">
                <tr className="text-left text-xs text-gray-500 border-b">
                  <th className="px-4 py-3 font-medium">#</th>
                  <th className="px-4 py-3 font-medium">Time</th>
                  <th className="px-4 py-3 font-medium">Case No.</th>
                  <th className="px-4 py-3 font-medium">Respondent</th>
                  <th className="px-4 py-3 font-medium">Attorney</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Hearing</th>
                  <th className="px-4 py-3 font-medium print:hidden">Status</th>
                  <th className="px-4 py-3 font-medium hidden lg:table-cell print:hidden">ETA</th>
                  <th className="px-4 py-3 font-medium hidden print:table-cell">Notes</th>
                </tr>
              </thead>
              <tbody>
                {queue.map((item, i) => (
                  <tr
                    key={item.hearing_id}
                    className="border-t border-gray-100 hover:bg-gray-50 print:hover:bg-white print:border-gray-300"
                  >
                    <td className="px-4 py-3 text-gray-400 print:text-black">{i + 1}</td>
                    <td className="px-4 py-3 font-mono text-xs font-semibold">
                      {formatTime(item.scheduled_start)}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs print:text-black">
                      <Link
                        href={`/cases/${item.case_id}`}
                        className="text-court-navy hover:underline print:no-underline"
                      >
                        {item.case_number}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-medium">{item.respondent_name}</td>
                    <td className="px-4 py-3 text-gray-600 print:text-black">{item.attorney_name}</td>
                    <td className="px-4 py-3 print:hidden">
                      <CaseTypeBadge caseType={item.case_type} />
                    </td>
                    <td className="px-4 py-3 capitalize text-xs hidden print:table-cell">
                      {item.case_type.replace(/_/g, " ")}
                    </td>
                    <td className="px-4 py-3 text-xs capitalize text-gray-600">
                      {item.hearing_type.replace(/_/g, " ")}
                    </td>
                    <td className="px-4 py-3 print:hidden">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell text-xs text-gray-500 print:hidden">
                      {item.p25_mins !== null ? `${item.p25_mins}–${item.p75_mins} min` : "—"}
                    </td>
                    {/* Blank Notes column for hand-written annotations on paper */}
                    <td className="px-4 py-3 hidden print:table-cell border-l border-gray-200 w-32" />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Print footer */}
        <div className="hidden print:block mt-6 text-xs text-gray-400">
          <p>Printed: {new Date().toLocaleString("en-US", { timeZone: "America/New_York" })} ET</p>
          <p>Court of Common Pleas of Allegheny County · Family Division — Juvenile Branch · Pittsburgh, PA</p>
          <p className="mt-1 font-medium">CONFIDENTIAL — FOR COURT USE ONLY</p>
        </div>
      </PageLayout>
    </>
  );
}
