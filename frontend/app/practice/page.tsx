"use client";

import { useState } from "react";
import { api, Problem } from "../../lib/api";

export default function Practice() {
  const [studentId, setStudentId] = useState<string | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [report, setReport] = useState<any>(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true);
    try {
      const s = await api.createStudent("Pilot Student", ["sports", "skateboarding"]);
      setStudentId(s.id);
      await loadNext(s.id);
    } finally {
      setBusy(false);
    }
  }

  async function loadNext(id: string) {
    setBusy(true);
    setFeedback(null);
    setAnswer("");
    try {
      const res = await api.nextProblem(id);
      setProblem(res.problem);
      setReport(res.report);
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!studentId || !problem) return;
    setBusy(true);
    try {
      const res = await api.submitAttempt(studentId, problem.id, answer);
      setFeedback(
        res.correct
          ? "✅ Correct!"
          : `❌ ${res.detail} (new mastery: ${res.new_mastery})`
      );
    } finally {
      setBusy(false);
    }
  }

  if (!studentId) {
    return (
      <main>
        <h1>Practice</h1>
        <button onClick={start} disabled={busy}>
          {busy ? "Starting…" : "Begin session"}
        </button>
      </main>
    );
  }

  return (
    <main>
      <h1>Practice</h1>
      {problem && (
        <section>
          <p style={{ color: "#666", fontSize: 14 }}>
            {problem.domain} · {problem.skill} · difficulty {problem.difficulty_target}
            {report ? ` · verified in ${report.checks?.core?.passed ? "1" : "?"} pass` : ""}
          </p>
          <p style={{ fontSize: 18 }}>{problem.statement}</p>
          <input
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Your answer"
            style={{ padding: 8, width: "60%" }}
          />{" "}
          <button onClick={submit} disabled={busy || !answer}>
            Submit
          </button>
          {feedback && <p>{feedback}</p>}
          {feedback && (
            <details>
              <summary>Show solution</summary>
              <p>{problem.solution}</p>
            </details>
          )}
          <p>
            <button onClick={() => loadNext(studentId)} disabled={busy}>
              Next problem →
            </button>
          </p>
        </section>
      )}
    </main>
  );
}
