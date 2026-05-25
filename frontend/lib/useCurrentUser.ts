"use client";

import { useEffect, useState } from "react";
import { auth } from "@/lib/api";
import type { MeResponse } from "@/lib/types";

export function useCurrentUser(): MeResponse | null {
  const [user, setUser] = useState<MeResponse | null>(null);
  useEffect(() => {
    auth.me()
      .then((u) => setUser(u as MeResponse))
      .catch(() => {});
  }, []);
  return user;
}
