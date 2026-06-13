"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api, API_BASE, Problem } from "../../lib/api";

interface Attempt {
  status: string;
  attempt?: number;
  skill?: string;
  difficulty_target?: number;
  statement?: string;
  answer?: string;
  failures?: string[];
  details?: { code: string; label: string; detail?: string }[];
}

export default function Practice() {
  const [studentId, setStudentId] = useState<string | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [regen, setRegen] = useState<number | null>(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Demo controls
  const [model, setModel] = useState("mock");
  const [skillSel, setSkillSel] = useState("auto");
  const [diffSel, setDiffSel] = useState("auto");
  const [skills, setSkills] = useState<{ id: string; domain: string; method: string }[]>([]);

  useEffect(() => {
    api.skills().then(setSkills).catch(() => {});
  }, []);

  async function start() {
    setBusy(true);
    try {
      const s = await api.createStudent("Pilot Student", ["sports", "skateboarding"]);
      setStudentId(s.id);
      loadNext(s.id);
    } finally {
      // streaming sets busy=false when it finishes
    }
  }

  // Stream the regenerate-until-valid loop live via Server-Sent Events.
  function loadNext(id: string) {
    setBusy(true);
    setProblem(null);
    setAttempts([]);
    setRegen(null);
    setFeedback(null);
    setAnswer("");

    const params = new URLSearchParams();
    if (model) params.set("provider", model);
    if (skillSel !== "auto") params.set("skill", skillSel);
    if (diffSel !== "auto") params.set("difficulty", diffSel);
    const es = new EventSource(`${API_BASE}/students/${id}/next-problem/stream?${params}`);
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.type === "progress") {
        setAttempts((a) => [...a, ev as Attempt]);
      } else if (ev.type === "result") {
        if (ev.accepted) setProblem(ev.problem as Problem);
        setRegen(ev.regen_count);
        setBusy(false);
        es.close();
      } else if (ev.type === "error") {
        setBusy(false);
        es.close();
      }
    };
    es.onerror = () => {
      setBusy(false);
      es.close();
    };
  }

  async function submit() {
    if (!studentId || !problem) return;
    setBusy(true);
    try {
      const res = await api.submitAttempt(studentId, problem.id, answer);
      setFeedback(
        res.correct ? "✅ Correct!" : `❌ ${res.detail} (new mastery: ${res.new_mastery})`
      );
    } finally {
      setBusy(false);
    }
  }

  function row(key: number, accent: string, children: ReactNode) {
    return (
      <div
        key={key}
        style={{
          borderLeft: `3px solid ${accent}`,
          padding: "6px 10px",
          margin: "4px 0",
          background: "#fff",
          borderRadius: 4,
        }}
      >
        {children}
      </div>
    );
  }

  function renderAttempt(a: Attempt, i: number) {
    const tag = (n?: number) => (
      <span style={{ color: "#6b7280", fontVariantNumeric: "tabular-nums" }}>
        attempt {n}
      </span>
    );
    if (a.status === "plan")
      return row(i, "#9ca3af",
        <span style={{ color: "#374151" }}>
          🧭 Planner selected <b>{a.skill}</b> · difficulty {a.difficulty_target}
        </span>);
    if (a.status === "generating")
      return row(i, "#f59e0b",
        <span style={{ color: "#92400e" }}>{tag(a.attempt)} · generating… <span className="pulse">⏳</span></span>);
    if (a.status === "accepted")
      return row(i, "#16a34a",
        <span style={{ color: "#166534", fontWeight: 600 }}>{tag(a.attempt)} · ✓ accepted &amp; delivered</span>);
    if (a.status === "rejected")
      return row(i, "#dc2626",
        <div>
          <span style={{ color: "#991b1b", fontWeight: 600 }}>{tag(a.attempt)} · ✗ rejected</span>
          {a.statement && (
            <div style={{ color: "#6b7280", fontSize: 13, margin: "3px 0" }}>
              “{a.statement.slice(0, 90)}…” &nbsp;→&nbsp; claimed <b>{a.answer}</b>
            </div>
          )}
          {(a.details || []).map((d, j) => (
            <div key={j} style={{ fontSize: 13, color: "#b91c1c" }}>
              • <b>{d.code}</b>{d.detail ? ` — ${d.detail}` : ` — ${d.label}`}
            </div>
          ))}
          {!a.details && a.failures && (
            <div style={{ fontSize: 13, color: "#b91c1c" }}>• {a.failures.join(", ")}</div>
          )}
        </div>);
    if (a.status === "exhausted")
      return row(i, "#dc2626",
        <span style={{ color: "#991b1b" }}>⚠ Budget exhausted — no valid problem this round. Click Next to retry.</span>);
    return null;
  }

  const domains = Array.from(new Set(skills.map((s) => s.domain)));
  const selStyle = { padding: 6, marginLeft: 6 } as const;
  const controls = (
    <section
      style={{
        display: "flex",
        gap: 18,
        flexWrap: "wrap",
        alignItems: "center",
        padding: "12px 14px",
        background: "#eef2ff",
        border: "1px solid #c7d2fe",
        borderRadius: 10,
        marginBottom: 16,
      }}
    >
      <label>
        Model
        <select value={model} onChange={(e) => setModel(e.target.value)} disabled={busy} style={selStyle}>
          <option value="mock">Mock (instant, offline)</option>
          <option value="openai">Llama (local, slow)</option>
          <option value="anthropic">Claude (needs key)</option>
        </select>
      </label>
      <label>
        Skill
        <select value={skillSel} onChange={(e) => setSkillSel(e.target.value)} disabled={busy} style={selStyle}>
          <option value="auto">Auto (planner picks)</option>
          <option value="random">🎲 Random</option>
          {domains.map((d) => (
            <optgroup key={d} label={d}>
              {skills
                .filter((s) => s.domain === d)
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.id}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </label>
      <label>
        Difficulty
        <select value={diffSel} onChange={(e) => setDiffSel(e.target.value)} disabled={busy} style={selStyle}>
          <option value="auto">Auto</option>
          {[1, 2, 3, 4, 5].map((n) => (
            <option key={n} value={String(n)}>
              {n}
            </option>
          ))}
        </select>
      </label>
    </section>
  );

  if (!studentId) {
    return (
      <main>
        <h1>Practice</h1>
        {controls}
        <button onClick={start} disabled={busy}>
          {busy ? "Starting…" : "Begin session"}
        </button>
      </main>
    );
  }

  return (
    <main>
      <h1>Practice</h1>
      {controls}

      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}} .pulse{display:inline-block;animation:pulse 1s ease-in-out infinite}`}</style>

      {/* Live loop progress (most useful with a slow real model) */}
      {(busy || attempts.length > 0) && !problem && (
        <section
          style={{
            background: "#f3f4f6",
            border: "1px solid #e5e7eb",
            padding: 14,
            borderRadius: 10,
            marginBottom: 16,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: 14,
          }}
        >
          <p style={{ margin: "0 0 8px", fontWeight: 700, fontFamily: "system-ui, sans-serif" }}>
            {busy ? (
              <>
                <span className="pulse">⏳</span> Regenerate-until-valid loop — the verifier
                is checking each candidate live
              </>
            ) : (
              "Loop finished"
            )}
          </p>
          {attempts.map(renderAttempt)}
        </section>
      )}

      {problem && (
        <section>
          <p style={{ color: "#666", fontSize: 14 }}>
            {problem.domain} · {problem.skill} · difficulty {problem.difficulty_target}
            {regen != null && ` · verified after ${regen} regeneration${regen === 1 ? "" : "s"}`}
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
        </section>
      )}

      <p>
        <button onClick={() => loadNext(studentId)} disabled={busy}>
          Next problem →
        </button>
      </p>
    </main>
  );
}
