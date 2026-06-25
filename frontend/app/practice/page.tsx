"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api, Problem } from "../../lib/api";

const SESSION_KEY = "stemgen.sessionId";

type View = "loading" | "onboarding" | "welcome" | "settings" | "practice";

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

interface Ctx { id: string; noun: string; narrative: string; interest_tags: string[] }
interface Skill { id: string; domain: string; method: string; difficulties: number[] }

export default function Practice() {
  const [view, setView] = useState<View>("loading");
  const [sessionId, setSessionId] = useState<string | null>(null);

  const [contexts, setContexts] = useState<Ctx[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);

  // chosen / saved settings
  const [ctx, setCtx] = useState("generic");
  const [skill, setSkill] = useState("kinematics");
  const [difficulty, setDifficulty] = useState(1);
  const [model, setModel] = useState("mock");

  // practice state
  const [problem, setProblem] = useState<Problem | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [regen, setRegen] = useState<number | null>(null);
  const [source, setSource] = useState<"pre_stored" | "llm" | null>(null);
  const [requestedDiff, setRequestedDiff] = useState<number | null>(null);

  // ---- bootstrap: load catalogs + detect returning session ----
  useEffect(() => {
    Promise.all([api.contexts().catch(() => []), api.skills().catch(() => [])]).then(
      ([cs, sk]) => {
        setContexts(cs);
        setSkills(sk);
      }
    );
    const id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      setView("onboarding");
      return;
    }
    api
      .getSession(id)
      .then((s) => {
        setSessionId(id);
        setCtx(s.current_context_id || "generic");
        setSkill(s.current_skill || "kinematics");
        setDifficulty(s.current_difficulty || 1);
        setModel(s.current_model || "mock");
        setView("welcome");
      })
      .catch(() => {
        localStorage.removeItem(SESSION_KEY);
        setView("onboarding");
      });
  }, []);

  // Difficulties available for the currently selected skill (from the bank).
  const availDiffs = skills.find((s) => s.id === skill)?.difficulties ?? [1, 2, 3, 4, 5];

  // Clamp the chosen difficulty to what the selected skill actually offers.
  useEffect(() => {
    if (skills.length && !availDiffs.includes(difficulty)) setDifficulty(availDiffs[0]);
  }, [skills, skill]); // eslint-disable-line react-hooks/exhaustive-deps

  function resetProblemState() {
    setProblem(null);
    setAttempts([]);
    setAnswer("");
    setFeedback(null);
    setRegen(null);
  }

  // ---- onboarding -> create session -> instant pre-stored problem ----
  async function beginSession() {
    setBusy(true);
    try {
      const s = await api.createSession({ context_id: ctx, skill, difficulty, model });
      localStorage.setItem(SESSION_KEY, s.id);
      setSessionId(s.id);
      await fetchPreStored(s.id);
    } finally {
      setBusy(false);
    }
  }

  // ---- adjust settings -> instant pre-stored problem ----
  async function applySettings() {
    if (!sessionId) return;
    setBusy(true);
    try {
      await api.adjustSettings(sessionId, { context_id: ctx, skill, difficulty, model });
      await fetchPreStored(sessionId);
    } finally {
      setBusy(false);
    }
  }

  // ---- pre-stored: instant, already verified ----
  async function fetchPreStored(id: string) {
    resetProblemState();
    setSource("pre_stored");
    setRequestedDiff(difficulty);
    setView("practice");
    setBusy(true);
    try {
      const res = await api.preStored(id, { skill, difficulty, context: ctx });
      if (res.accepted) setProblem(res.problem as Problem);
      setRegen(0);
    } finally {
      setBusy(false);
    }
  }

  // ---- "Next problem": keep settings. Mock = instant bank; real model = generate live. ----
  function nextSameSettings() {
    if (!sessionId) return;
    if (model === "mock") fetchPreStored(sessionId);
    else streamProblem({ skill, difficulty });
  }

  // ---- stream the live LLM loop with the session's model ----
  // opts.skill/difficulty -> keep the user's settings; empty -> Planner (adaptive).
  function streamProblem(opts: { skill?: string; difficulty?: number } = {}) {
    if (!sessionId) return;
    resetProblemState();
    setSource("llm");
    setRequestedDiff(opts.difficulty ?? null);
    setView("practice");
    setBusy(true);
    const es = new EventSource(api.sessionStreamUrl(sessionId, opts));
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.type === "progress") setAttempts((a) => [...a, ev as Attempt]);
      else if (ev.type === "result") {
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
    if (!sessionId || !problem) return;
    setBusy(true);
    try {
      const res = await api.sessionAttempt(sessionId, problem.id, answer);
      setFeedback(
        res.correct ? "✅ Correct!" : `❌ ${res.detail} (new mastery: ${res.new_mastery})`
      );
    } finally {
      setBusy(false);
    }
  }

  function resetSession() {
    localStorage.removeItem(SESSION_KEY);
    setSessionId(null);
    resetProblemState();
    setView("onboarding");
  }

  // ---------- shared UI bits ----------
  const sel = { padding: 6, marginLeft: 6 } as const;
  const domains = Array.from(new Set(skills.map((s) => s.domain)));

  function settingsForm(submitLabel: string, onSubmit: () => void) {
    return (
      <section style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center",
        padding: "12px 14px", background: "#eef2ff", border: "1px solid #c7d2fe",
        borderRadius: 10, marginBottom: 16 }}>
        <label>Context
          <select value={ctx} onChange={(e) => setCtx(e.target.value)} style={sel}>
            {contexts.map((c) => <option key={c.id} value={c.id}>{c.id}</option>)}
          </select>
        </label>
        <label>Skill
          <select value={skill} onChange={(e) => setSkill(e.target.value)} style={sel}>
            {domains.map((d) => (
              <optgroup key={d} label={d}>
                {skills.filter((s) => s.domain === d).map((s) => (
                  <option key={s.id} value={s.id}>{s.id}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label>Difficulty
          <select value={difficulty} onChange={(e) => setDifficulty(Number(e.target.value))} style={sel}>
            {availDiffs.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          {availDiffs.length < 5 && (
            <span style={{ color: "#6b7280", fontSize: 12, marginLeft: 6 }}>
              (only {availDiffs.join(", ")} available)
            </span>
          )}
        </label>
        <label>Model
          <select value={model} onChange={(e) => setModel(e.target.value)} style={sel}>
            <option value="mock">Mock (instant)</option>
            <option value="openai">Llama (local)</option>
            <option value="anthropic">Claude (needs key)</option>
          </select>
        </label>
        <button onClick={onSubmit} disabled={busy}>{submitLabel}</button>
      </section>
    );
  }

  function row(key: number, accent: string, children: ReactNode) {
    return (
      <div key={key} style={{ borderLeft: `3px solid ${accent}`, padding: "6px 10px",
        margin: "4px 0", background: "#fff", borderRadius: 4 }}>{children}</div>
    );
  }
  function renderAttempt(a: Attempt, i: number) {
    const t = (n?: number) => <span style={{ color: "#6b7280" }}>attempt {n}</span>;
    if (a.status === "plan")
      return row(i, "#9ca3af", <span>🧭 Planner selected <b>{a.skill}</b> · difficulty {a.difficulty_target}</span>);
    if (a.status === "generating")
      return row(i, "#f59e0b", <span style={{ color: "#92400e" }}>{t(a.attempt)} · generating… <span className="pulse">⏳</span></span>);
    if (a.status === "accepted")
      return row(i, "#16a34a", <span style={{ color: "#166534", fontWeight: 600 }}>{t(a.attempt)} · ✓ accepted</span>);
    if (a.status === "rejected")
      return row(i, "#dc2626",
        <div>
          <span style={{ color: "#991b1b", fontWeight: 600 }}>{t(a.attempt)} · ✗ rejected</span>
          {a.statement && <div style={{ color: "#6b7280", fontSize: 13 }}>“{a.statement.slice(0, 90)}…” → claimed <b>{a.answer}</b></div>}
          {(a.details || []).map((d, j) => (
            <div key={j} style={{ fontSize: 13, color: "#b91c1c" }}>• <b>{d.code}</b>{d.detail ? ` — ${d.detail}` : ` — ${d.label}`}</div>
          ))}
        </div>);
    if (a.status === "exhausted")
      return row(i, "#dc2626", <span style={{ color: "#991b1b" }}>⚠ Budget exhausted — click “Continue” to retry.</span>);
    return null;
  }

  const pulseStyle = (
    <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}} .pulse{display:inline-block;animation:pulse 1s ease-in-out infinite}`}</style>
  );

  // ---------- screens ----------
  if (view === "loading") return <main><h1>Practice</h1><p>Loading…</p></main>;

  if (view === "onboarding")
    return (
      <main>
        <h1>Welcome 👋</h1>
        <p>Pick your starting context, skill, and difficulty. Your first problem is served instantly from a pre-verified bank.</p>
        {settingsForm(busy ? "Starting…" : "Start practicing →", beginSession)}
      </main>
    );

  if (view === "welcome")
    return (
      <main>
        <h1>Welcome back 👋</h1>
        <p>Saved settings: <b>{skill}</b> · difficulty {difficulty} · context {ctx} · model {model}.</p>
        <p>Change settings before your next problem?</p>
        <button onClick={() => setView("settings")}>Yes, change settings</button>{" "}
        <button onClick={nextSameSettings} disabled={busy}>No, continue →</button>
        <p><button onClick={resetSession} style={{ fontSize: 12 }}>Reset session</button></p>
      </main>
    );

  if (view === "settings")
    return (
      <main>
        <h1>Adjust settings</h1>
        {settingsForm(busy ? "Loading…" : "Apply & get a problem →", applySettings)}
        <button onClick={() => setView("practice")} disabled={!problem}>Cancel</button>
      </main>
    );

  // practice
  return (
    <main>
      <h1>Practice</h1>
      {pulseStyle}

      {(busy || attempts.length > 0) && !problem && (
        <section style={{ background: "#f3f4f6", border: "1px solid #e5e7eb", padding: 14,
          borderRadius: 10, marginBottom: 16, fontFamily: "ui-monospace, Menlo, monospace", fontSize: 14 }}>
          <p style={{ margin: "0 0 8px", fontWeight: 700, fontFamily: "system-ui" }}>
            {attempts.length > 0
              ? <><span className="pulse">⏳</span> Regenerate-until-valid loop (verifier checking each candidate)</>
              : <><span className="pulse">⏳</span> Fetching a verified problem…</>}
          </p>
          {attempts.map(renderAttempt)}
        </section>
      )}

      {problem && (
        <section>
          <p style={{ color: "#666", fontSize: 14 }}>
            {problem.domain} · {problem.skill} · difficulty {problem.difficulty_target}
            {source === "pre_stored" ? " · pre-stored (instant)"
              : regen != null ? ` · verified after ${regen} regeneration${regen === 1 ? "" : "s"}` : ""}
            {source === "pre_stored" && requestedDiff != null && problem.difficulty_target !== requestedDiff && (
              <span style={{ color: "#b45309" }}> · closest available (you picked {requestedDiff})</span>
            )}
          </p>
          <p style={{ fontSize: 18 }}>{problem.statement}</p>
          <input value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Your answer"
            style={{ padding: 8, width: "60%" }} />{" "}
          <button onClick={submit} disabled={busy || !answer}>Submit</button>
          {feedback && <p>{feedback}</p>}
          {feedback && <details><summary>Show solution</summary><p>{problem.solution}</p></details>}
        </section>
      )}

      <p style={{ marginTop: 20 }}>
        <button onClick={nextSameSettings} disabled={busy}
          title={model === "mock" ? "Instant from the verified bank" : `Generate with ${model} at your skill/difficulty`}>
          Next problem →
        </button>{" "}
        <button onClick={() => streamProblem({})} disabled={busy}
          title="The Planner picks what to practice next (changes skill/difficulty)">
          Adaptive next (Planner) →
        </button>{" "}
        <button onClick={() => setView("settings")} disabled={busy}>Change settings</button>{" "}
        <button onClick={resetSession} style={{ fontSize: 12 }}>Reset session</button>
      </p>
    </main>
  );
}
