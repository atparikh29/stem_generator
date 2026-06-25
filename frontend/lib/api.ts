const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";
export const API_BASE = BASE;

async function req(path: string, opts: RequestInit = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
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

  events: (studentId: string) => req(`/students/${studentId}/events`),

  skills: (): Promise<{ id: string; domain: string; method: string }[]> => req("/skills"),

  contexts: (): Promise<{ id: string; noun: string; narrative: string; interest_tags: string[] }[]> =>
    req("/contexts"),

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

  sessionStreamUrl: (id: string) => `${API_BASE}/sessions/${id}/next-problem/stream`,
};
