const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";
export const API_BASE = BASE;
export const SID_KEY = "stemgen.sid"; // login-session id, tagged onto the event log

function sid(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem(SID_KEY) : null;
}

async function req(path: string, opts: RequestInit = {}) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const s = sid();
  if (s) headers["X-Session-Id"] = s;
  const res = await fetch(`${BASE}${path}`, { ...opts, headers: { ...headers, ...(opts.headers as any) } });
  if (res.status === 429) {
    // The backend caps requests per client, tighter on auth and on the LLM loop.
    // Callers show e.message directly, so make it a sentence rather than a JSON dump.
    const wait = Number(res.headers.get("Retry-After") || 0);
    throw new Error(`429: Too many requests. Try again in ${wait > 0 ? `${wait}s` : "a moment"}.`);
  }
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

/** The user-facing sentence from a 429, or null if the error was something else. */
export function rateLimitNotice(e: unknown): string | null {
  const msg = String((e as any)?.message ?? "");
  return msg.startsWith("429:") ? msg.slice(4).trim() : null;
}

export interface Problem {
  id: number;
  skill: string;
  domain: string;
  difficulty_target: number;
  statement: string;
  solution: string;
  task: any;
}

export const api = {
  createStudent: (name: string, interests: string[]) =>
    req("/students", { method: "POST", body: JSON.stringify({ name, interests }) }),

  nextProblem: (studentId: string) =>
    req(`/students/${studentId}/next-problem`, { method: "POST" }),

  submitAttempt: (studentId: string, problemId: number, answer: string) =>
    req(`/students/${studentId}/attempts`, {
      method: "POST",
      body: JSON.stringify({ problem_id: problemId, answer }),
    }),

  events: (userId: string, sessionId?: string) =>
    req(`/students/${userId}/events${sessionId ? `?session_id=${sessionId}` : ""}`),

  stats: (userId: string) => req(`/students/${userId}/stats`),

  // Fire-and-forget: record a GUI action into the event log (never blocks the UI).
  logUi: (userId: string, action: string, detail: Record<string, any> = {}) =>
    req(`/students/${userId}/ui-events`, {
      method: "POST",
      body: JSON.stringify({ action, detail }),
    }).catch(() => {}),

  skills: (): Promise<{ id: string; domain: string; method: string; difficulties: number[] }[]> =>
    req("/skills"),

  contexts: (): Promise<{ id: string; noun: string; narrative: string; interest_tags: string[] }[]> =>
    req("/contexts"),

  // ----- auth -----
  register: (body: {
    username: string; password: string; context_id: string; skill: string;
    difficulty: number; model: string;
  }) => req("/auth/register", { method: "POST", body: JSON.stringify(body) }),

  login: (username: string, password: string) =>
    req("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),

  forgotPassword: (username: string) =>
    req("/auth/forgot-password", { method: "POST", body: JSON.stringify({ username }) }),

  resetPassword: (username: string, token: string, new_password: string) =>
    req("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ username, token, new_password }),
    }),

  // ----- session flow -----
  createSession: (body: {
    name?: string; context_id: string; skill: string; difficulty: number; model: string;
  }) => req("/sessions", { method: "POST", body: JSON.stringify(body) }),

  getSession: (id: string) => req(`/sessions/${id}`),

  adjustSettings: (id: string, body: {
    context_id?: string; skill?: string; difficulty?: number; model?: string;
  }) => req(`/sessions/${id}/settings`, { method: "POST", body: JSON.stringify(body) }),

  preStored: (id: string, opts: { skill?: string; difficulty?: number; context?: string } = {}) => {
    const p = new URLSearchParams();
    if (opts.skill) p.set("skill", opts.skill);
    if (opts.difficulty) p.set("difficulty", String(opts.difficulty));
    if (opts.context) p.set("context", opts.context);
    return req(`/sessions/${id}/pre-stored?${p}`);
  },

  sessionAttempt: (id: string, problemId: number, answer: string) =>
    req(`/sessions/${id}/attempts`, {
      method: "POST",
      body: JSON.stringify({ problem_id: problemId, answer }),
    }),

  sessionStreamUrl: (id: string, opts: { skill?: string; difficulty?: number; logPrompt?: boolean; semanticLlm?: boolean } = {}) => {
    const p = new URLSearchParams();
    if (opts.skill) p.set("skill", opts.skill);
    if (opts.difficulty) p.set("difficulty", String(opts.difficulty));
    if (opts.logPrompt) p.set("log_prompt", "1");
    if (opts.semanticLlm !== undefined) p.set("semantic_llm", String(opts.semanticLlm));
    const s = sid();
    if (s) p.set("sid", s); // EventSource can't set headers, so pass it as a query param
    const qs = p.toString();
    return `${API_BASE}/sessions/${id}/next-problem/stream${qs ? `?${qs}` : ""}`;
  },
};
