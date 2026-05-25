"use client";

import { useEffect, useState, useCallback } from "react";
import { UserPlus, RefreshCw, ShieldCheck } from "lucide-react";
import { users as usersApi, exportApi } from "@/lib/api";
import type { UserOut, Role, AuditLogOut } from "@/lib/types";
import { ROLE_LABEL }                      from "@/lib/auth";
import { useCurrentUser }                  from "@/lib/useCurrentUser";
import PageLayout      from "@/components/layout/PageLayout";
import Button          from "@/components/ui/Button";
import Input           from "@/components/ui/Input";
import Card            from "@/components/ui/Card";
import PDFImportButton from "@/components/ui/PDFImportButton";

const ROLES: Role[] = ["admin", "clerk", "attorney", "judge", "public"];

// ── Create user modal ─────────────────────────────────────────────────────────

function CreateUserModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({
    username: "", password: "", email: "", role: "clerk" as Role,
    lawyer_id: "", judge_id: "",
  });
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await usersApi.create({
        username:  form.username,
        password:  form.password,
        email:     form.email || undefined,
        role:      form.role,
        lawyer_id: form.lawyer_id ? Number(form.lawyer_id) : undefined,
        judge_id:  form.judge_id  ? Number(form.judge_id)  : undefined,
      });
      onCreated();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create user");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-court-navy">Create User</h2>
        <form onSubmit={submit} className="space-y-3">
          <Input label="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
          <Input label="Password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
          <Input label="Email (optional)" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Role</label>
            <select
              className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
            >
              {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select>
          </div>
          {form.role === "attorney" && (
            <Input label="Lawyer ID" type="number" value={form.lawyer_id} onChange={(e) => setForm({ ...form, lawyer_id: e.target.value })} required />
          )}
          {form.role === "judge" && (
            <Input label="Judge ID" type="number" value={form.judge_id} onChange={(e) => setForm({ ...form, judge_id: e.target.value })} required />
          )}
          {error && <p className="text-xs text-red-600">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={loading}>Create</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Reset password modal ──────────────────────────────────────────────────────

function ResetPasswordModal({ user, onClose }: { user: UserOut; onClose: () => void }) {
  const [password, setPassword] = useState("");
  const [confirm,  setConfirm]  = useState("");
  const [loading,  setLoading]  = useState(false);
  const [done,     setDone]     = useState(false);
  const [error,    setError]    = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) { setError("Passwords do not match"); return; }
    if (password.length < 8)  { setError("Password must be at least 8 characters"); return; }
    setError("");
    setLoading(true);
    try {
      await usersApi.resetPassword(user.id, password);
      setDone(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to reset password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-semibold text-court-navy">Reset Password</h2>
        <p className="mb-4 text-sm text-gray-500">User: <strong>{user.username}</strong></p>
        {done ? (
          <div>
            <p className="mb-4 text-sm text-green-700">Password reset successfully.</p>
            <div className="flex justify-end">
              <Button onClick={onClose}>Close</Button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <Input label="New Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            <Input label="Confirm Password" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            {error && <p className="text-xs text-red-600">{error}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
              <Button type="submit" loading={loading}>Reset</Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}


// ── Audit trail ───────────────────────────────────────────────────────────────

const EVENT_FILTERS = [
  "", "LOGIN", "LOGOUT", "PASSWORD_CHANGED",
  "PARTY_CHECKED_IN", "HEARING_STATUS_CHANGED",
  "SEALED_CASE_ACCESSED", "DOCKET_EXPORTED", "ETA_ESTIMATED",
];

function AuditTrail() {
  const [logs,      setLogs]      = useState<AuditLogOut[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [filter,    setFilter]    = useState("");
  const [offset,    setOffset]    = useState(0);
  const PAGE = 50;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await exportApi.audit({
        event_type: filter || undefined,
        limit: PAGE,
        offset,
      }) as AuditLogOut[];
      setLogs(data);
    } finally {
      setLoading(false);
    }
  }, [filter, offset]);

  useEffect(() => { load(); }, [load]);

  function handleFilter(v: string) { setFilter(v); setOffset(0); }

  return (
    <Card
      title="Audit Trail"
      action={
        <div className="flex items-center gap-2">
          <select
            className="rounded border border-gray-300 px-2 py-1 text-xs"
            value={filter}
            onChange={(e) => handleFilter(e.target.value)}
          >
            {EVENT_FILTERS.map((f) => (
              <option key={f} value={f}>{f || "All events"}</option>
            ))}
          </select>
          <Button size="sm" variant="ghost" onClick={load}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      }
    >
      {loading ? (
        <p className="py-6 text-center text-sm text-gray-400">Loading…</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-2 pr-4 font-medium">Time (ET)</th>
                  <th className="pb-2 pr-4 font-medium">Event</th>
                  <th className="pb-2 pr-4 font-medium hidden md:table-cell">Agent</th>
                  <th className="pb-2 pr-4 font-medium hidden lg:table-cell">Entity</th>
                  <th className="pb-2 font-medium hidden lg:table-cell">Details</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-t border-gray-50">
                    <td className="py-2 pr-4 font-mono text-gray-500">
                      {new Date(log.created_at).toLocaleString("en-US", {
                        timeZone: "America/New_York",
                        month: "2-digit", day: "2-digit",
                        hour: "2-digit", minute: "2-digit", second: "2-digit",
                      })}
                    </td>
                    <td className="py-2 pr-4 font-medium">{log.event_type}</td>
                    <td className="py-2 pr-4 hidden text-gray-500 md:table-cell">{log.agent_name}</td>
                    <td className="py-2 pr-4 hidden text-gray-500 lg:table-cell">
                      {log.entity_type && log.entity_id
                        ? `${log.entity_type} #${log.entity_id}`
                        : log.entity_type ?? "—"}
                    </td>
                    <td className="py-2 hidden max-w-xs truncate text-gray-400 lg:table-cell">
                      {log.payload ? log.payload.slice(0, 80) : "—"}
                    </td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr><td colSpan={5} className="py-6 text-center text-gray-400">No events found</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
            <span>{logs.length} events shown</span>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                ← Prev
              </Button>
              <Button size="sm" variant="ghost" disabled={logs.length < PAGE} onClick={() => setOffset(offset + PAGE)}>
                Next →
              </Button>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const currentUser                   = useCurrentUser();
  const [userList,    setUserList]    = useState<UserOut[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [showCreate,  setShowCreate]  = useState(false);
  const [resetTarget, setResetTarget] = useState<UserOut | null>(null);
  const [busyId,      setBusyId]      = useState<number | null>(null);

  async function loadUsers() {
    setLoading(true);
    try {
      const data = await usersApi.list() as UserOut[];
      setUserList(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadUsers(); }, []);

  async function deactivate(id: number) {
    if (!confirm("Deactivate this user? They will not be able to log in.")) return;
    setBusyId(id);
    try {
      await usersApi.deactivate(id);
      await loadUsers();
    } finally {
      setBusyId(null);
    }
  }

  async function reactivate(id: number) {
    setBusyId(id);
    try {
      await usersApi.reactivate(id);
      await loadUsers();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <PageLayout user={currentUser} heading="Admin Panel" subheading="User management &amp; audit trail">
      {showCreate && (
        <CreateUserModal onClose={() => setShowCreate(false)} onCreated={loadUsers} />
      )}
      {resetTarget && (
        <ResetPasswordModal user={resetTarget} onClose={() => setResetTarget(null)} />
      )}

      {/* ── Users ───────────────────────────────────────────────────────────── */}
      <div className="mb-8">
        <Card
          title="System Users"
          action={
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={loadUsers}>
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
              <Button size="sm" onClick={() => setShowCreate(true)}>
                <UserPlus className="h-4 w-4 mr-1" /> Add User
              </Button>
            </div>
          }
        >
          {loading ? (
            <p className="py-6 text-center text-sm text-gray-400">Loading…</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-gray-500">
                    <th className="pb-2 pr-4 font-medium">Username</th>
                    <th className="pb-2 pr-4 font-medium">Role</th>
                    <th className="pb-2 pr-4 font-medium hidden md:table-cell">Email</th>
                    <th className="pb-2 pr-4 font-medium hidden lg:table-cell">Last Login</th>
                    <th className="pb-2 pr-4 font-medium">Status</th>
                    <th className="pb-2 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {userList.map((u) => (
                    <tr key={u.id} className="border-t border-gray-50">
                      <td className="py-2.5 pr-4 font-medium">{u.username}</td>
                      <td className="py-2.5 pr-4 capitalize">{ROLE_LABEL[u.role]}</td>
                      <td className="py-2.5 pr-4 hidden text-gray-500 md:table-cell">{u.email ?? "—"}</td>
                      <td className="py-2.5 pr-4 hidden text-xs text-gray-400 lg:table-cell">
                        {u.last_login
                          ? new Date(u.last_login).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                          : "Never"}
                      </td>
                      <td className="py-2.5 pr-4">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          u.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                        }`}>
                          {u.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="py-2.5 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setResetTarget(u)}
                          >
                            Reset Password
                          </Button>
                          {u.is_active ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              loading={busyId === u.id}
                              onClick={() => deactivate(u.id)}
                              className="text-red-600 hover:text-red-700"
                            >
                              Deactivate
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              variant="ghost"
                              loading={busyId === u.id}
                              onClick={() => reactivate(u.id)}
                              className="text-green-600 hover:text-green-700"
                            >
                              Reactivate
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* ── PDF docket import ───────────────────────────────────────────────── */}
      <div className="mb-8 flex justify-end">
        <PDFImportButton />
      </div>

      {/* ── Audit trail ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 mb-3">
        <ShieldCheck className="h-4 w-4 text-court-navy" />
        <span className="text-sm font-semibold text-court-navy">
          Compliance — 42 Pa.C.S. § 6307 Access Log
        </span>
      </div>
      <AuditTrail />
    </PageLayout>
  );
}
