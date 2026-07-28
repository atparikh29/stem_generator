"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api, Problem, SID_KEY } from "../../lib/api";

const SESSION_KEY = "stemgen.sessionId";
const USER_KEY = "stemgen.username";

type View = "loading" | "auth" | "welcome" | "settings" | "practice" | "stats";

interface SkillStat {
  skill: string; domain: string; delivered: number; attempts: number;
  correct: number; incorrect: number; accuracy: number | null; mastery: number;
  difficulty_first: number | null; difficulty_latest: number | null;
  difficulty_min: number | null; difficulty_max: number | null; difficulty_series: number[];
}
interface Stats {
  sessions: number; total_delivered: number; total_attempts: number;
  correct: number; incorrect: number; accuracy: number | null;
  total_time_seconds: number; first_seen: string | null; last_seen: string | null;
  per_skill: SkillStat[];
}

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

  // auth
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authMode, setAuthMode] = useState<"login" | "register" | "forgot" | "reset">("login");
  const [authError, setAuthError] = useState<string | null>(null);
  // password reset
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [resetInfo, setResetInfo] = useState<string | null>(null);

  // debug log panel
  const [debug, setDebug] = useState(false);
  const [logEvents, setLogEvents] = useState<any[]>([]);
  const [logScope, setLogScope] = useState<"session" | "user">("session");
  const [logPrompt, setLogPrompt] = useState(false); // log/show the full LLM prompt
  const [semanticLlm, setSemanticLlm] = useState(true); // advanced: LLM clarity check on/off
  const [genSeconds, setGenSeconds] = useState(0); // live "still working" counter

  // progress / stats dashboard
  const [stats, setStats] = useState<Stats | null>(null);

  // ---- bootstrap: load catalogs + detect returning session ----
  useEffect(() => {
    Promise.all([api.contexts().catch(() => []), api.skills().catch(() => [])]).then(
      ([cs, sk]) => {
        setContexts(cs);
        setSkills(sk);
      }
    );
    const id = localStorage.getItem(SESSION_KEY);
    setUsername(localStorage.getItem(USER_KEY) || "");
    if (!id) {
      setView("auth");
      return;
    }
    api
      .getSession(id)
      .then((s) => {
        applySavedState(id, s);
        setView("welcome");
      })
      .catch(() => {
        localStorage.removeItem(SESSION_KEY);
        setView("auth");
      });
  }, []);

  function applySavedState(id: string, s: any) {
    setSessionId(id);
    localStorage.setItem(SESSION_KEY, id);
    if (s.session_id) localStorage.setItem(SID_KEY, s.session_id); // login-session id
    if (s.username) {
      setUsername(s.username);
      localStorage.setItem(USER_KEY, s.username);
    }
    setCtx(s.current_context_id || "generic");
    setSkill(s.current_skill || "kinematics");
    setDifficulty(s.current_difficulty || 1);
    setModel(s.current_model || "mock");
  }

  // ---- debug log ----
  async function refreshLog() {
    if (!sessionId) return;
    try {
      const sid = logScope === "session" ? localStorage.getItem(SID_KEY) || undefined : undefined;
      setLogEvents(await api.events(sessionId, sid));
    } catch {
      /* ignore */
    }
  }

  // Refresh the log when the panel is open, on scope change, and every 3s.
  useEffect(() => {
    if (!debug) return;
    refreshLog();
    const t = setInterval(refreshLog, 3000);
    return () => clearInterval(t);
  }, [debug, logScope, sessionId, problem, feedback]); // eslint-disable-line react-hooks/exhaustive-deps

  // Shift page content left so the fixed debug panel doesn't overlap it.
  useEffect(() => {
    document.body.style.paddingRight = debug ? "46vw" : "";
    return () => {
      document.body.style.paddingRight = "";
    };
  }, [debug]);

  // Difficulties available for the currently selected skill (from the bank).
  const availDiffs = skills.find((s) => s.id === skill)?.difficulties ?? [1, 2, 3, 4, 5];

  // Clamp the chosen difficulty to what the selected skill actually offers.
  useEffect(() => {
    if (skills.length && !availDiffs.includes(difficulty)) setDifficulty(availDiffs[0]);
  }, [skills, skill]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fire-and-forget GUI-action logging (records button clicks / settings changes).
  function logUi(action: string, detail: Record<string, any> = {}) {
    const uid = sessionId || localStorage.getItem(SESSION_KEY);
    if (uid) api.logUi(uid, action, detail);
  }

  // Tick an elapsed-seconds counter while the LLM loop runs, so a slow model
  // reads as "still working (12s)" rather than a frozen screen.
  useEffect(() => {
    if (!(busy && source === "llm" && !problem)) {
      setGenSeconds(0);
      return;
    }
    const t = setInterval(() => setGenSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [busy, source, problem]);

  function resetProblemState() {
    setProblem(null);
    setAttempts([]);
    setAnswer("");
    setFeedback(null);
    setRegen(null);
  }

  // ---- register: create account + session -> instant pre-stored problem ----
  async function doRegister() {
    setAuthError(null);
    setBusy(true);
    try {
      const s = await api.register({ username, password, context_id: ctx, skill, difficulty, model });
      applySavedState(s.id, s);
      setPassword("");
      await fetchPreStored(s.id);
    } catch (e: any) {
      setAuthError(String(e.message).includes("409") ? "That username is taken." : "Registration failed.");
      setBusy(false);
    }
  }

  // ---- login: verify -> resume saved session ----
  async function doLogin() {
    setAuthError(null);
    setBusy(true);
    try {
      const s = await api.login(username, password);
      applySavedState(s.id, s);
      setPassword("");
      api.logUi(s.id, "ui_login"); // s.id known now; header sid set by applySavedState
      setView("welcome");
    } catch (e: any) {
      setAuthError("Invalid username or password.");
    } finally {
      setBusy(false);
    }
  }

  // ---- forgot password: request a reset token (dev delivery, no email) ----
  async function doForgot() {
    setAuthError(null);
    setResetInfo(null);
    setBusy(true);
    try {
      const res = await api.forgotPassword(username);
      if (res.reset_token) {
        // No mail server: prefill the token and move straight to the reset step.
        setResetToken(res.reset_token);
        setResetInfo(`Reset token issued (expires in ${res.expires_in_minutes} min). Normally this would be emailed; here it's pre-filled below.`);
      } else {
        setResetInfo(res.message || "If that account exists, a reset token has been issued.");
      }
      setAuthMode("reset");
    } catch {
      setAuthError("Could not request a reset. Try again.");
    } finally {
      setBusy(false);
    }
  }

  // ---- reset password: consume the token, set a new password, sign in ----
  async function doReset() {
    setAuthError(null);
    setBusy(true);
    try {
      const s = await api.resetPassword(username, resetToken, newPassword);
      applySavedState(s.id, s);
      setPassword("");
      setNewPassword("");
      setResetToken("");
      setResetInfo(null);
      api.logUi(s.id, "password_reset");
      setView("welcome");
    } catch (e: any) {
      setAuthError(String(e.message).includes("400") ? "Invalid or expired reset token." : "Reset failed.");
    } finally {
      setBusy(false);
    }
  }

  // ---- progress dashboard ----
  async function openStats() {
    if (!sessionId) return;
    logUi("open_stats");
    setBusy(true);
    try {
      setStats(await api.stats(sessionId));
      setView("stats");
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    logUi("logout");
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(SID_KEY);
    setSessionId(null);
    setUsername("");
    setPassword("");
    resetProblemState();
    setView("auth");
  }

  // ---- adjust settings -> instant pre-stored problem ----
  async function applySettings() {
    if (!sessionId) return;
    logUi("apply_settings", { context_id: ctx, skill, difficulty, model });
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
    const es = new EventSource(api.sessionStreamUrl(sessionId, { ...opts, logPrompt, semanticLlm }));
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
    logUi("submit_answer", { problem_id: problem.id, answer });
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

  // ---------- shared UI bits ----------
  // Color-code event types in the debug log: green=accepted/delivered,
  // red=rejected/exhausted, amber=everything else.
  // The backend stores UTC but serializes without a timezone marker, so mark it
  // UTC before converting to the viewer's local date + time.
  function fmtTs(ts?: string): string {
    if (!ts) return "—";
    const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(ts);
    const d = new Date(hasTz ? ts : ts.replace(" ", "T") + "Z");
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  }

  function logTypeColor(type: string): string {
    if (["accept", "deliver"].includes(type)) return "#4ade80";
    if (["reject", "exhausted"].includes(type)) return "#f87171";
    if (type === "ui") return "#38bdf8"; // GUI actions — cyan
    if (["verify_start", "verify_step"].includes(type)) return "#a78bfa"; // verify phase — purple
    return "#fbbf24";
  }
  const sel = { padding: 6, marginLeft: 6 } as const;
  const domains = Array.from(new Set(skills.map((s) => s.domain)));

  function fmtDuration(sec: number): string {
    if (!sec || sec < 1) return "under 1m";
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
    if (h) return `${h}h ${m}m`;
    if (m) return `${m}m`;
    return `${Math.floor(sec)}s`;
  }

  function masteryBar(m: number) {
    const pct = Math.round(m * 100);
    const color = m >= 0.66 ? "#16a34a" : m >= 0.33 ? "#f59e0b" : "#ef4444";
    return (
      <div>
        <div style={{ background: "#e5e7eb", borderRadius: 6, height: 8, width: 100, overflow: "hidden" }}>
          <div style={{ background: color, width: `${pct}%`, height: "100%" }} />
        </div>
        <span style={{ fontSize: 11, color: "#64748b" }}>{pct}%</span>
      </div>
    );
  }

  // Sparkline of the difficulty of each delivered problem (chronological), 1..5.
  function difficultyCell(s: SkillStat) {
    const ser = s.difficulty_series || [];
    if (!ser.length) return <span style={{ color: "#cbd5e1" }}>—</span>;
    return (
      <div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 24 }}>
          {ser.slice(-14).map((d, i) => (
            <div key={i} title={`difficulty ${d}`} style={{ width: 5, height: `${(d / 5) * 100}%`,
              background: "#6366f1", borderRadius: 1 }} />
          ))}
        </div>
        <span style={{ fontSize: 11, color: "#64748b" }}>
          {s.difficulty_first}→{s.difficulty_latest} (min {s.difficulty_min}, max {s.difficulty_max})
        </span>
      </div>
    );
  }

  function settingsForm(submitLabel: string, onSubmit: () => void) {
    return (
      <section style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center",
        padding: "12px 14px", background: "#eef2ff", border: "1px solid #c7d2fe",
        borderRadius: 10, marginBottom: 16 }}>
        <label>Context
          <select value={ctx} onChange={(e) => { setCtx(e.target.value); logUi("change_setting", { field: "context", value: e.target.value }); }} style={sel}>
            {contexts.map((c) => <option key={c.id} value={c.id}>{c.id}</option>)}
          </select>
        </label>
        <label>Skill
          <select value={skill} onChange={(e) => { setSkill(e.target.value); logUi("change_setting", { field: "skill", value: e.target.value }); }} style={sel}>
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
          <select value={difficulty} onChange={(e) => { setDifficulty(Number(e.target.value)); logUi("change_setting", { field: "difficulty", value: Number(e.target.value) }); }} style={sel}>
            {availDiffs.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          {availDiffs.length < 5 && (
            <span style={{ color: "#6b7280", fontSize: 12, marginLeft: 6 }}>
              (only {availDiffs.join(", ")} available)
            </span>
          )}
        </label>
        <label>Model
          <select value={model} onChange={(e) => { setModel(e.target.value); logUi("change_setting", { field: "model", value: e.target.value }); }} style={sel}>
            <option value="mock">Mock (instant)</option>
            <option value="openai">Llama (local)</option>
            <option value="anthropic">Claude (needs key)</option>
            <option value="gemini">Gemini (needs key)</option>
          </select>
        </label>
        {submitLabel && <button onClick={onSubmit} disabled={busy}>{submitLabel}</button>}
      </section>
    );
  }

  // The per-attempt regeneration trace (statements, claimed answers, rejection
  // reasons) is intentionally NOT rendered on the practice screen -- it belongs
  // in the Debug panel only. Here we surface just a neutral progress spinner.
  const candidatesTried = attempts.filter((a) => a.status === "generating").length;
  const verifying = attempts.length > 0 && attempts[attempts.length - 1].status === "verifying";

  const pulseStyle = (
    <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}} .pulse{display:inline-block;animation:pulse 1s ease-in-out infinite}`}</style>
  );

  // ---------- screens ----------
  let screen: ReactNode = null;
  if (view === "loading") screen = <main><h1>Practice</h1><p>Loading…</p></main>;
  else if (view === "auth" && authMode === "forgot") {
    screen = (
      <main>
        <h1>Forgot password</h1>
        <p style={{ maxWidth: 380, color: "#374151" }}>Enter your username to get a reset token.</p>
        <section style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 320 }}>
          <label>Username<br />
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
              onKeyDown={(e) => e.key === "Enter" && username && doForgot()}
              style={{ padding: 8, width: "100%" }} />
          </label>
          {authError && <p style={{ color: "#b91c1c", margin: 0 }}>{authError}</p>}
        </section>
        <button onClick={doForgot} disabled={busy || !username}>{busy ? "…" : "Send reset token →"}</button>{" "}
        <button onClick={() => { setAuthMode("login"); setAuthError(null); }} style={{ fontSize: 13 }}>
          Back to log in
        </button>
      </main>
    );
  }
  else if (view === "auth" && authMode === "reset") {
    screen = (
      <main>
        <h1>Reset password</h1>
        {resetInfo && (
          <p style={{ maxWidth: 420, background: "#ecfeff", border: "1px solid #a5f3fc",
            borderRadius: 8, padding: "8px 10px", color: "#155e75", fontSize: 13 }}>{resetInfo}</p>
        )}
        <section style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 380 }}>
          <label>Username<br />
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
              style={{ padding: 8, width: "100%" }} />
          </label>
          <label>Reset token<br />
            <input value={resetToken} onChange={(e) => setResetToken(e.target.value)}
              style={{ padding: 8, width: "100%", fontFamily: "ui-monospace, Menlo, monospace" }} />
          </label>
          <label>New password<br />
            <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              onKeyDown={(e) => e.key === "Enter" && resetToken && newPassword && doReset()}
              style={{ padding: 8, width: "100%" }} />
          </label>
          {authError && <p style={{ color: "#b91c1c", margin: 0 }}>{authError}</p>}
        </section>
        <button onClick={doReset} disabled={busy || !username || !resetToken || !newPassword}>
          {busy ? "…" : "Reset password & sign in →"}
        </button>{" "}
        <button onClick={() => { setAuthMode("login"); setAuthError(null); setResetInfo(null); }} style={{ fontSize: 13 }}>
          Back to log in
        </button>
      </main>
    );
  }
  else if (view === "auth") {
    const isReg = authMode === "register";
    screen = (
      <main>
        <h1>{isReg ? "Create account" : "Log in"}</h1>
        <section style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 320 }}>
          <label>Username<br />
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
              style={{ padding: 8, width: "100%" }} />
          </label>
          <label>Password<br />
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={isReg ? "new-password" : "current-password"}
              onKeyDown={(e) => e.key === "Enter" && (isReg ? doRegister() : doLogin())}
              style={{ padding: 8, width: "100%" }} />
          </label>
          {authError && <p style={{ color: "#b91c1c", margin: 0 }}>{authError}</p>}
        </section>

        {isReg && (
          <>
            <p style={{ marginBottom: 4 }}>Starting settings (your first problem is instant from the verified bank):</p>
            {settingsForm("", () => {})}
          </>
        )}

        <button onClick={isReg ? doRegister : doLogin} disabled={busy || !username || !password}>
          {busy ? "…" : isReg ? "Create account & start →" : "Log in →"}
        </button>{" "}
        <button onClick={() => { setAuthMode(isReg ? "login" : "register"); setAuthError(null); }} style={{ fontSize: 13 }}>
          {isReg ? "Have an account? Log in" : "New here? Create an account"}
        </button>
        {!isReg && (
          <>{" "}
            <button onClick={() => { setAuthMode("forgot"); setAuthError(null); setResetInfo(null); }} style={{ fontSize: 13 }}>
              Forgot password?
            </button>
          </>
        )}
      </main>
    );
  }
  else if (view === "welcome")
    screen = (
      <main>
        <h1>Welcome back{username ? `, ${username}` : ""} 👋</h1>
        <p>Saved settings: <b>{skill}</b> · difficulty {difficulty} · context {ctx} · model {model}.</p>
        <p>Change settings before your next problem?</p>
        <button onClick={() => { logUi("open_settings"); setView("settings"); }}>Yes, change settings</button>{" "}
        <button onClick={() => { logUi("welcome_continue", { model, skill, difficulty }); nextSameSettings(); }} disabled={busy}>No, continue →</button>
        <p>
          <button onClick={openStats} disabled={busy} style={{ fontSize: 13 }}>📊 View my progress</button>{" "}
          <button onClick={logout} style={{ fontSize: 12 }}>Log out</button>
        </p>
      </main>
    );
  else if (view === "settings")
    screen = (
      <main>
        <h1>Adjust settings</h1>
        {settingsForm(busy ? "Loading…" : "Apply & get a problem →", applySettings)}
        <button onClick={() => { logUi("cancel_settings"); setView("practice"); }} disabled={!problem}>Cancel</button>
      </main>
    );
  else if (view === "stats") {
    const active = (stats?.per_skill || []).filter((s) => s.delivered > 0 || s.attempts > 0);
    const untouched = (stats?.per_skill || []).length - active.length;
    const card = (label: string, value: ReactNode, sub?: string) => (
      <div style={{ flex: "1 1 120px", background: "#f8fafc", border: "1px solid #e2e8f0",
        borderRadius: 10, padding: "12px 14px" }}>
        <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
        <div style={{ fontSize: 12, color: "#64748b" }}>{label}</div>
        {sub && <div style={{ fontSize: 11, color: "#94a3b8" }}>{sub}</div>}
      </div>
    );
    const th = { padding: "6px 10px" } as const;
    const td = { padding: "8px 10px" } as const;
    screen = (
      <main>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h1>📊 Progress{username ? ` — ${username}` : ""}</h1>
          <button onClick={() => setView(problem ? "practice" : "welcome")} style={{ fontSize: 13 }}>← Back</button>
        </div>
        {!stats ? <p>Loading…</p> : (
          <>
            <section style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
              {card("Problems solved", stats.correct, `${stats.total_delivered} served`)}
              {card("Attempts", stats.total_attempts, `${stats.incorrect} incorrect`)}
              {card("Accuracy", stats.accuracy != null ? `${Math.round(stats.accuracy * 100)}%` : "—")}
              {card("Time spent", fmtDuration(stats.total_time_seconds))}
              {card("Sessions", stats.sessions)}
            </section>

            <h2 style={{ fontSize: 18 }}>By skill</h2>
            {active.length === 0 ? (
              <p style={{ color: "#64748b" }}>No problems attempted yet — solve a few and come back!</p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 14 }}>
                  <thead>
                    <tr style={{ textAlign: "left", color: "#64748b", borderBottom: "2px solid #e2e8f0" }}>
                      <th style={th}>Skill</th><th style={th}>Solved</th><th style={th}>Correct / Wrong</th>
                      <th style={th}>Accuracy</th><th style={th}>Mastery</th><th style={th}>Difficulty over time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {active.map((s) => (
                      <tr key={s.skill} style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={td}><b>{s.skill}</b><br />
                          <span style={{ color: "#94a3b8", fontSize: 12 }}>{s.domain}</span></td>
                        <td style={td}>{s.correct}<span style={{ color: "#cbd5e1" }}>/{s.delivered}</span></td>
                        <td style={td}>
                          <span style={{ color: "#16a34a" }}>{s.correct}</span>
                          {" / "}<span style={{ color: "#dc2626" }}>{s.incorrect}</span>
                        </td>
                        <td style={td}>{s.accuracy != null ? `${Math.round(s.accuracy * 100)}%` : "—"}</td>
                        <td style={{ ...td, minWidth: 120 }}>{masteryBar(s.mastery)}</td>
                        <td style={td}>{difficultyCell(s)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {untouched > 0 && (
              <p style={{ color: "#94a3b8", fontSize: 13, marginTop: 10 }}>
                + {untouched} skills not yet practiced.
              </p>
            )}
            <p style={{ marginTop: 20 }}>
              <button onClick={() => setView(problem ? "practice" : "welcome")}>← Back to practice</button>{" "}
              <button onClick={openStats} disabled={busy} style={{ fontSize: 13 }}>↻ Refresh</button>
            </p>
          </>
        )}
      </main>
    );
  }
  else
    screen = (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1>Practice</h1>
        {username && (
          <span style={{ fontSize: 13, color: "#6b7280" }}>
            {username} · <button onClick={logout} style={{ fontSize: 13 }}>Log out</button>
          </span>
        )}
      </div>
      {pulseStyle}

      {busy && !problem && (
        <section style={{ background: "#f3f4f6", border: "1px solid #e5e7eb", padding: 14,
          borderRadius: 10, marginBottom: 16 }}>
          <p style={{ margin: 0, fontWeight: 600 }}>
            <span className="pulse">⏳</span>{" "}
            {source === "llm"
              ? "Generating a verified problem… running the regenerate-until-valid loop."
              : "Fetching a verified problem…"}
          </p>
          {source === "llm" && (
            <p style={{ margin: "6px 0 0", color: "#6b7280", fontSize: 13 }}>
              Still working — {genSeconds}s elapsed
              {candidatesTried > 0 && <>, candidate #{candidatesTried} {verifying ? "being verified" : "being generated"}</>}.
              {" "}Turn on <b>Debug</b> (top-right) to watch every attempt, its timing, and its rejection reason.
            </p>
          )}
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
          {feedback && (
            <details onToggle={(e) => logUi("toggle_solution", { open: (e.target as HTMLDetailsElement).open })}>
              <summary>Show solution</summary><p>{problem.solution}</p>
            </details>
          )}
        </section>
      )}

      <p style={{ marginTop: 20 }}>
        <button onClick={() => { logUi("click_next_problem", { model, skill, difficulty }); nextSameSettings(); }} disabled={busy}
          title={model === "mock" ? "Instant from the verified bank" : `Generate with ${model} at your skill/difficulty`}>
          Next problem →
        </button>{" "}
        <button onClick={() => { logUi("click_adaptive_next"); streamProblem({}); }} disabled={busy}
          title="The Planner picks what to practice next (changes skill/difficulty)">
          Adaptive next (Planner) →
        </button>{" "}
        <button onClick={() => { logUi("open_settings"); setView("settings"); }} disabled={busy}>Change settings</button>{" "}
        <button onClick={openStats} disabled={busy}>📊 Progress</button>
      </p>
    </main>
  );

  // ---------- top-level: current screen + debug toggle + log panel ----------
  return (
    <>
      <label style={{ position: "fixed", top: 8, right: 8, zIndex: 30, fontSize: 12,
        background: "#fff", padding: "3px 8px", border: "1px solid #ddd", borderRadius: 6 }}>
        <input type="checkbox" checked={debug} onChange={(e) => { setDebug(e.target.checked); logUi("toggle_debug", { on: e.target.checked }); }} /> Debug
      </label>
      {screen}
      {debug && (
        <aside style={{ position: "fixed", top: 0, right: 0, width: "46vw", height: "100vh",
          overflow: "auto", background: "#0b1020", color: "#d1d5db", borderLeft: "1px solid #1f2937",
          padding: 14, fontFamily: "ui-monospace, Menlo, monospace", fontSize: 12, zIndex: 25 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <b style={{ color: "#fff" }}>Event log</b>
            <span>
              <label style={{ fontSize: 12, marginRight: 8 }}>
                <input type="checkbox" checked={logPrompt}
                  onChange={(e) => { setLogPrompt(e.target.checked); logUi("toggle_log_prompt", { on: e.target.checked }); }} />
                {" "}log prompt
              </label>
              <select value={logScope} onChange={(e) => setLogScope(e.target.value as any)}
                style={{ fontSize: 12 }}>
                <option value="session">this session</option>
                <option value="user">all sessions (user)</option>
              </select>{" "}
              <button onClick={refreshLog} style={{ fontSize: 12 }}>↻</button>
            </span>
          </div>
          {logPrompt && (
            <div style={{ color: "#38bdf8", marginBottom: 6, fontSize: 11 }}>
              Full prompt will be logged on your next generation (LLM models only).
            </div>
          )}
          <details style={{ marginBottom: 8, background: "#111827", borderRadius: 6, padding: "4px 8px" }}>
            <summary style={{ cursor: "pointer", color: "#93c5fd", fontSize: 12 }}>⚙ Advanced</summary>
            <label style={{ display: "block", marginTop: 6, fontSize: 12 }}>
              <input type="checkbox" checked={semanticLlm}
                onChange={(e) => { setSemanticLlm(e.target.checked); logUi("toggle_semantic_llm", { on: e.target.checked }); }} />
              {" "}LLM clarity check (2nd model call per problem)
            </label>
            <div style={{ color: "#6b7280", fontSize: 11, marginTop: 2 }}>
              Off = offline heuristic only; avoids doubling {model} calls and the rate-limit
              stall you can hit on the verify step. Applies to LLM models on the next generation.
            </div>
          </details>
          <div style={{ color: "#6b7280", marginBottom: 6 }}>
            user {sessionId?.slice(0, 8)} · {logEvents.length} events
          </div>
          {logEvents.map((e) => {
            const { prompt, ...rest } = (e.payload || {}) as any;
            return (
              <div key={e.id} style={{ borderBottom: "1px solid #1f2937", padding: "5px 0" }}>
                <div>
                  <span style={{ color: "#93c5fd" }}>#{e.id}</span>{" "}
                  <b style={{ color: logTypeColor(e.type) }}>{e.type}</b>{" "}
                  <span style={{ color: "#6b7280" }}>{fmtTs(e.ts)}</span>{" "}
                  <span style={{ color: "#4b5563" }}>sid:{(e.session_id || "—").slice(0, 8)}</span>
                </div>
                <pre style={{ margin: "2px 0 0", whiteSpace: "pre-wrap", color: "#9ca3af" }}>
                  {JSON.stringify(rest, null, 1)}
                </pre>
                {prompt && (
                  <details style={{ marginTop: 2 }}>
                    <summary style={{ cursor: "pointer", color: "#38bdf8" }}>
                      prompt ({String(prompt).length} chars)
                    </summary>
                    <pre style={{ margin: "2px 0 0", whiteSpace: "pre-wrap", color: "#cbd5e1",
                      background: "#111827", padding: 6, borderRadius: 4 }}>{prompt}</pre>
                  </details>
                )}
              </div>
            );
          })}
        </aside>
      )}
    </>
  );
}
