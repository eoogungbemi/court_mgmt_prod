"use client";

import { useState, useRef, useEffect, FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Scale, ChevronDown, KeyRound, LogOut } from "lucide-react";
import { auth } from "@/lib/api";
import type { MeResponse } from "@/lib/types";
import { ROLE_LABEL } from "@/lib/auth";

interface Props {
  user: MeResponse | null;
}

// ── Change-password modal ─────────────────────────────────────────────────────

function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [current,  setCurrent]  = useState("");
  const [next,     setNext]     = useState("");
  const [confirm,  setConfirm]  = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [done,     setDone]     = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (next !== confirm) { setError("Passwords do not match"); return; }
    if (next.length < 8)  { setError("New password must be at least 8 characters"); return; }
    setError("");
    setLoading(true);
    try {
      await auth.changePassword(current, next);
      setDone(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to change password");
    } finally {
      setLoading(false);
    }
  }

  function handleDone() {
    onClose();
    // Server revoked all tokens — force a fresh login
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Change Password</h2>

        {done ? (
          <div className="space-y-4">
            <p className="text-sm text-green-700">
              Password updated. You will be signed out of all devices.
            </p>
            <button
              onClick={handleDone}
              className="w-full rounded-md bg-court-navy px-4 py-2 text-sm font-medium text-white hover:bg-court-navy/90"
            >
              Sign in again
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">Current password</label>
              <input
                type="password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                required
                autoComplete="current-password"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">New password</label>
              <input
                type="password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">Confirm new password</label>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                autoComplete="new-password"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-court-navy"
              />
            </div>
            {error && <p className="text-xs text-red-600">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="rounded-md bg-court-navy px-4 py-2 text-sm font-medium text-white hover:bg-court-navy/90 disabled:opacity-50"
              >
                {loading ? "Saving…" : "Update password"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

// ── User menu dropdown ────────────────────────────────────────────────────────

function UserMenu({ user }: { user: MeResponse }) {
  const router  = useRouter();
  const [open,  setOpen]  = useState(false);
  const [showPw, setShowPw] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  async function handleLogout() {
    setOpen(false);
    await auth.logout().catch(() => {});
    router.push("/login");
    router.refresh();
  }

  return (
    <>
      {showPw && <ChangePasswordModal onClose={() => setShowPw(false)} />}

      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-1.5 rounded border border-white/30 px-3 py-1 text-xs hover:bg-white/10"
        >
          <span className="hidden sm:inline">
            {user.username} · {ROLE_LABEL[user.role]}
          </span>
          <span className="sm:hidden">{user.username}</span>
          <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>

        {open && (
          <div className="absolute right-0 top-full z-40 mt-1.5 w-44 rounded-md border border-gray-200 bg-white py-1 shadow-lg">
            <button
              onClick={() => { setOpen(false); setShowPw(true); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
            >
              <KeyRound className="h-3.5 w-3.5 text-gray-400" />
              Change password
            </button>
            <hr className="my-1 border-gray-100" />
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
            >
              <LogOut className="h-3.5 w-3.5 text-gray-400" />
              Sign out
            </button>
          </div>
        )}
      </div>
    </>
  );
}

// ── Navbar ────────────────────────────────────────────────────────────────────

export default function Navbar({ user }: Props) {
  const courtName = process.env.NEXT_PUBLIC_COURT_NAME ?? "Allegheny County Juvenile Court";

  return (
    <header className="bg-court-navy text-white shadow-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2 text-sm font-semibold tracking-wide">
          <Scale className="h-5 w-5 text-court-gold" />
          <span className="hidden sm:inline">{courtName}</span>
          <span className="sm:hidden">CMS</span>
        </Link>

        <nav className="flex items-center gap-4 text-sm">
          <Link href="/queue"    className="opacity-80 hover:opacity-100">Queue</Link>
          {user?.role === "clerk"    && <Link href="/clerk"    className="opacity-80 hover:opacity-100">Clerk</Link>}
          {user?.role === "attorney" && <Link href="/attorney" className="opacity-80 hover:opacity-100">Schedule</Link>}
          {user?.role === "judge"    && <Link href="/judge"    className="opacity-80 hover:opacity-100">Docket</Link>}
          {user?.role === "admin"    && <Link href="/admin"    className="opacity-80 hover:opacity-100">Admin</Link>}
          {user && user.role !== "attorney" && (
            <Link href="/analytics" className="opacity-80 hover:opacity-100">Analytics</Link>
          )}

          {user ? (
            <UserMenu user={user} />
          ) : (
            <Link href="/login" className="rounded border border-white/30 px-3 py-1 text-xs hover:bg-white/10">
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
