const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";

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
};
