import type { Role } from "@/lib/types";

/**
 * Decode the JWT payload without verification (verification happens server-side
 * in middleware and on every API call).  Only used client-side to read claims
 * already trusted by the server.
 */
export function decodeToken(token: string): { sub: string; username: string; role: Role; exp: number } | null {
  try {
    const payload = token.split(".")[1];
    const decoded = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return decoded;
  } catch {
    return null;
  }
}

export const ROLE_HOME: Record<Role, string> = {
  admin:    "/admin",
  clerk:    "/clerk",
  attorney: "/attorney",
  judge:    "/judge",
  public:   "/queue",
};

export const ROLE_LABEL: Record<Role, string> = {
  admin:    "Administrator",
  clerk:    "Court Clerk",
  attorney: "Attorney",
  judge:    "Judge",
  public:   "Public Access",
};

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour:   "2-digit",
    minute: "2-digit",
    hour12: true,
    timeZone: "America/New_York",
  });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "long",
    year:    "numeric",
    month:   "long",
    day:     "numeric",
    timeZone: "America/New_York",
  });
}

export function todayDateString(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" }); // YYYY-MM-DD
}
