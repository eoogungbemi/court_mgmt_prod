import { cookies }  from "next/headers";
import Link         from "next/link";
import { formatTime, todayDateString } from "@/lib/auth";
import type { MeResponse, AttorneyScheduleItem, AttorneyOut } from "@/lib/types";
import PageLayout      from "@/components/layout/PageLayout";
import { StatusBadge } from "@/components/ui/Badge";
import Card            from "@/components/ui/Card";

async function fetchJson<T>(path: string, cookieHeader: string): Promise<T> {
  const base = process.env.INTERNAL_API_URL ?? "http://backend:8000";
  const res  = await fetch(`${base}${path}`, {
    headers: { Cookie: cookieHeader },
    cache:   "no-store",
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export default async function AttorneyPage() {
  const cookieStore  = await cookies();
  const cookieHeader = cookieStore.toString();
  const date         = todayDateString();

  let user:     MeResponse | null           = null;
  let schedule: AttorneyScheduleItem[]      = [];
  let me:       AttorneyOut  | null         = null;

  try {
    user = await fetchJson<MeResponse>("/api/auth/me", cookieHeader);
    if (user?.lawyer_id) {
      [me, schedule] = await Promise.all([
        fetchJson<AttorneyOut>(`/api/attorneys/${user.lawyer_id}`, cookieHeader),
        fetchJson<AttorneyScheduleItem[]>(
          `/api/attorneys/${user.lawyer_id}/schedule?run_date=${date}`,
          cookieHeader
        ),
      ]);
    }
  } catch {}

  return (
    <PageLayout
      user={user}
      heading={me ? `${me.name} — Schedule` : "Attorney Schedule"}
      subheading={`Today · ${new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}`}
    >
      {me && (
        <div className="mb-4 flex flex-wrap gap-4 text-sm text-gray-600">
          {me.bar_number && <span>Bar no. {me.bar_number}</span>}
          {me.phone      && <span>{me.phone}</span>}
          {me.email      && <span>{me.email}</span>}
        </div>
      )}

      {schedule.length === 0 ? (
        <Card>
          <p className="py-8 text-center text-gray-400">No hearings scheduled for today</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {schedule.map((item) => (
            <div key={item.hearing_id} className="rounded-lg bg-white px-5 py-4 shadow-sm ring-1 ring-gray-200">
              <div className="flex flex-wrap items-start gap-3">
                <div className="min-w-[90px]">
                  <p className="font-mono text-sm font-semibold">{formatTime(item.scheduled_start)}</p>
                  <p className="font-mono text-xs text-gray-400">→ {formatTime(item.scheduled_end)}</p>
                </div>
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/cases/${item.case_id}`}
                      className="font-mono text-sm font-semibold text-court-navy hover:underline"
                    >
                      {item.case_number}
                    </Link>
                    <StatusBadge status={item.status} />
                  </div>
                  <p className="mt-0.5 text-sm text-gray-600">
                    {item.hearing_type.replace(/_/g, " ")} · {item.courtroom_name}
                  </p>
                  <p className="mt-0.5 text-xs text-gray-400 capitalize">{item.case_type.replace(/_/g, " ")} docket</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </PageLayout>
  );
}
