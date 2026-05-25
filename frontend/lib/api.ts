/**
 * Typed fetch wrapper. All requests go through Next.js rewrites → backend.
 * Cookies are sent automatically (same-origin after rewrite).
 */

const BASE = "/api";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    ...options,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export const auth = {
  login:          (username: string, password: string) =>
    request("/auth/login",           { method: "POST", body: JSON.stringify({ username, password }) }),
  logout:         ()                   => request("/auth/logout",          { method: "POST" }),
  refresh:        ()                   => request("/auth/refresh",         { method: "POST" }),
  me:             ()                   => request("/auth/me"),
  changePassword: (current: string, next: string) =>
    request("/auth/change-password",  { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) }),
};

// ── Courtrooms ────────────────────────────────────────────────────────────────

export const courtrooms = {
  list:     ()                              => request("/courtrooms"),
  get:      (id: number)                    => request(`/courtrooms/${id}`),
  overview: (date?: string)                 => request(`/courtrooms/overview${date ? `?run_date=${date}` : ""}`),
  queue:    (id: number, date?: string)     => request(`/courtrooms/${id}/queue${date ? `?run_date=${date}` : ""}`),
};

// ── Cases ─────────────────────────────────────────────────────────────────────

export const cases = {
  search: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => [k, String(v)])
    ).toString();
    return request(`/cases${qs ? `?${qs}` : ""}`);
  },
  get:      (id: number)       => request(`/cases/${id}`),
  timeline: (id: number)     => request(`/cases/${id}/timeline`),
  create: (body: unknown)    => request("/cases",           { method: "POST", body: JSON.stringify(body) }),
  update: (id: number, body: unknown) =>
    request(`/cases/${id}`,   { method: "PATCH", body: JSON.stringify(body) }),
  seal:   (id: number)       => request(`/cases/${id}/seal`, { method: "POST" }),
  bulkUpload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/cases/bulk-upload`, {
      method:      "POST",
      credentials: "include",
      body:        form,
    }).then(async (res) => {
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, body.detail ?? res.statusText);
      }
      return res.json();
    });
  },
};

// ── Hearings ──────────────────────────────────────────────────────────────────

export const hearings = {
  get:        (id: number)               => request(`/hearings/${id}`),
  create:     (body: unknown)            => request("/hearings", { method: "POST", body: JSON.stringify(body) }),
  update:     (id: number, body: unknown) => request(`/hearings/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  delete:     (id: number)               => request(`/hearings/${id}`, { method: "DELETE" }),
  checkin:    (id: number, party: "attorney" | "juvenile") =>
    request(`/hearings/${id}/checkin`,    { method: "POST", body: JSON.stringify({ party }) }),
  setStatus:  (id: number, body: unknown) =>
    request(`/hearings/${id}/status`,     { method: "POST", body: JSON.stringify(body) }),
  reschedule: (id: number, body: unknown) =>
    request(`/hearings/${id}/reschedule`, { method: "POST", body: JSON.stringify(body) }),
  assignJudge:(id: number, judge_id: number) =>
    request(`/hearings/${id}/judge`,      { method: "POST", body: JSON.stringify({ judge_id }) }),
  updateNotes:(id: number, notes: string) =>
    request(`/hearings/${id}/notes`,      { method: "PATCH", body: JSON.stringify({ notes }) }),
  eta:        (id: number)               => request(`/hearings/${id}/eta`),
  audit:      (id: number)               => request(`/hearings/${id}/audit`),
};

// ── Attorneys ─────────────────────────────────────────────────────────────────

export const attorneys = {
  list:         ()                      => request("/attorneys"),
  get:          (id: number)            => request(`/attorneys/${id}`),
  schedule:     (id: number, date?: string) =>
    request(`/attorneys/${id}/schedule${date ? `?run_date=${date}` : ""}`),
  availability: (id: number, date?: string) =>
    request(`/attorneys/${id}/availability${date ? `?run_date=${date}` : ""}`),
};

// ── Conflicts ─────────────────────────────────────────────────────────────────

export const conflicts = {
  list: (params?: { resolved?: boolean; lawyer_id?: number }) => {
    const qs = new URLSearchParams(
      Object.entries(params ?? {})
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => [k, String(v)])
    ).toString();
    return request(`/conflicts${qs ? `?${qs}` : ""}`);
  },
  get:     (id: number)         => request(`/conflicts/${id}`),
  resolve: (id: number)         => request(`/conflicts/${id}`, { method: "PATCH", body: JSON.stringify({ resolved: true }) }),
};

// ── Export ────────────────────────────────────────────────────────────────────

export const exportApi = {
  docket: (courtroomId?: number, date?: string) => {
    const params = new URLSearchParams();
    if (courtroomId !== undefined) params.set("courtroom_id", String(courtroomId));
    if (date) params.set("run_date", date);
    const qs = params.toString();
    return fetch(`${BASE}/export/docket${qs ? `?${qs}` : ""}`, { credentials: "include" });
  },
  audit: (params: { event_type?: string; entity_type?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => [k, String(v)])
    ).toString();
    return request(`/export/audit${qs ? `?${qs}` : ""}`);
  },
};

// ── Agents ────────────────────────────────────────────────────────────────────

export const agentsApi = {
  trigger: (body: unknown) => request("/agents/trigger", { method: "POST", body: JSON.stringify(body) }),
};

// ── Users (admin) ─────────────────────────────────────────────────────────────

export const users = {
  list:          ()                          => request("/users"),
  get:           (id: number)                => request(`/users/${id}`),
  create:        (body: unknown)             => request("/users", { method: "POST", body: JSON.stringify(body) }),
  update:        (id: number, body: unknown) => request(`/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  resetPassword: (id: number, new_password: string) =>
    request(`/users/${id}/reset-password`,    { method: "POST", body: JSON.stringify({ new_password }) }),
  deactivate:    (id: number)                => request(`/users/${id}`, { method: "DELETE" }),
  reactivate:    (id: number)                => request(`/users/${id}`, { method: "PATCH", body: JSON.stringify({ is_active: true }) }),
};

// ── PDF Import ────────────────────────────────────────────────────────────────

export const pdfImport = {
  preview: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/pdf-import/preview`, {
      method:      "POST",
      credentials: "include",
      body:        form,
    }).then(async (res) => {
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, body.detail ?? res.statusText);
      }
      return res.json();
    });
  },

  confirm: (body: unknown) =>
    request("/pdf-import/confirm", { method: "POST", body: JSON.stringify(body) }),

  addJudge: (name: string, courtroom_name: string, floor: number) =>
    request("/pdf-import/add-judge", {
      method: "POST",
      body: JSON.stringify({ name, courtroom_name, floor }),
    }),
};

export { ApiError };
