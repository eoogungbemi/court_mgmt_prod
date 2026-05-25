"use client";

import { Suspense, useState, FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Scale } from "lucide-react";
import { auth } from "@/lib/api";
import { ROLE_HOME } from "@/lib/auth";
import type { Role, TokenResponse } from "@/lib/types";
import Button from "@/components/ui/Button";
import Input  from "@/components/ui/Input";

function LoginForm() {
  const router   = useRouter();
  const params   = useSearchParams();
  const nextPath = params.get("next");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await auth.login(username, password) as TokenResponse;
      router.push(nextPath ?? ROLE_HOME[res.role as Role] ?? "/queue");
      router.refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg bg-white p-6 shadow-sm ring-1 ring-gray-200 space-y-4">
      <Input
        label="Username"
        type="text"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        autoComplete="username"
        required
      />
      <Input
        label="Password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="current-password"
        required
      />

      {error && (
        <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      <Button type="submit" loading={loading} className="w-full justify-center">
        Sign in
      </Button>
    </form>
  );
}

export default function LoginPage() {
  const courtName = process.env.NEXT_PUBLIC_COURT_NAME ?? "Allegheny County Juvenile Court";

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-court-navy">
            <Scale className="h-7 w-7 text-court-gold" />
          </div>
          <h1 className="text-xl font-bold text-court-navy">{courtName}</h1>
          <p className="mt-1 text-sm text-gray-500">Case Management System — Staff Sign In</p>
        </div>

        <Suspense fallback={<div className="rounded-lg bg-white p-6 shadow-sm ring-1 ring-gray-200 h-48" />}>
          <LoginForm />
        </Suspense>

      </div>
    </div>
  );
}
