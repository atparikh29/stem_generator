"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, Problem, rateLimitNotice, SID_KEY } from "../../lib/api";

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
  context_id?: string;
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
  // Why a generation didn't arrive (rate limit, provider error). Distinct from
  // `feedback`, which only renders alongside a problem.
  const [genError, setGenError] = useState<string | null>(null);
  // Re-runs the exact last generation, so the error card can offer "Try again".
  const retryGen = useRef<() => void>(() => {});
  // The live SSE stream, so "Cancel" can abort a running regenerate-until-valid loop.
  const esRef = useRef<EventSource | null>(null);
  // Wall-clock timing: when generation started, and how long it took to deliver.
  const genStartRef = useRef<number>(0);
  const [deliverMs, setDeliverMs] = useState<number | null>(null);
  // How long the student has spent on the current (unanswered) problem.
  const [solveSeconds, setSolveSeconds] = useState(0);

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
    setGenError(null);
    setDeliverMs(null);
  }

  // Count up while the student is solving the current problem; freeze on submit.
  useEffect(() => {
    if (!(problem && feedback == null)) return;
    setSolveSeconds(0);
    const t = setInterval(() => setSolveSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [problem?.id, feedback]);

  // Abandon the current problem (or a running generation loop) and return to the
  // start screen. Allowed at any time — including mid-loop, which it aborts.
  function cancelToWelcome() {
    esRef.current?.close();
    esRef.current = null;
    logUi("cancel_to_welcome");
    setBusy(false);
    resetProblemState();
    setView("welcome");
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
      setAuthError(rateLimitNotice(e) ??
        (String(e.message).includes("409") ? "That username is taken." : "Registration failed."));
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
      setAuthError(rateLimitNotice(e) ?? "Invalid username or password.");
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
    } catch (e: any) {
      setAuthError(rateLimitNotice(e) ?? "Could not request a reset. Try again.");
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
      setAuthError(rateLimitNotice(e) ??
        (String(e.message).includes("400") ? "Invalid or expired reset token." : "Reset failed."));
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
    retryGen.current = () => fetchPreStored(id);
    resetProblemState();
    setSource("pre_stored");
    setRequestedDiff(difficulty);
    setView("practice");
    setBusy(true);
    genStartRef.current = Date.now();
    try {
      const res = await api.preStored(id, { skill, difficulty, context: ctx });
      if (res.accepted) {
        setProblem(res.problem as Problem);
        setDeliverMs(Date.now() - genStartRef.current);
      }
      setRegen(0);
    } catch (e: any) {
      // Without this, "Next problem" (which doesn't await) failed silently.
      setGenError(rateLimitNotice(e) ?? "Couldn't fetch a problem. Try again.");
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
    retryGen.current = () => streamProblem(opts);
    resetProblemState();
    setSource("llm");
    setRequestedDiff(opts.difficulty ?? null);
    setView("practice");
    setBusy(true);
    genStartRef.current = Date.now();
    const es = new EventSource(api.sessionStreamUrl(sessionId, { ...opts, logPrompt, semanticLlm }));
    esRef.current = es;
    let settled = false; // did the stream reach a verdict of its own?
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.type === "progress") setAttempts((a) => [...a, ev as Attempt]);
      else if (ev.type === "result") {
        settled = true;
        if (ev.accepted) {
          setProblem(ev.problem as Problem);
          setDeliverMs(Date.now() - genStartRef.current);
        }
        setRegen(ev.regen_count);
        setBusy(false);
        es.close();
      } else if (ev.type === "error") {
        // Loop failed mid-flight, e.g. the model provider throttled us.
        settled = true;
        setGenError(ev.message || "Generation failed. Try again.");
        setBusy(false);
        es.close();
      }
    };
    es.onerror = () => {
      // EventSource never exposes the HTTP status, so a refused connection and a
      // dropped one look identical here. Being refused outright is by far the
      // likelier cause when nothing at all arrived.
      if (!settled) {
        setGenError(
          "Couldn't start generating — the request was refused, most likely because " +
          "too many were sent in a short window. Wait a moment and try again."
        );
      }
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
    const color = m >= 0.66 ? "var(--ok)" : m >= 0.33 ? "var(--warn)" : "var(--bad)";
    return (
      <div>
        <div className="bar">
          <i style={{ background: color, width: `${pct}%` }} />
        </div>
        <span className="meta" style={{ fontSize: 11 }}>{pct}%</span>
      </div>
    );
  }

  // Sparkline of the difficulty of each delivered problem (chronological), 1..5.
  function difficultyCell(s: SkillStat) {
    const ser = s.difficulty_series || [];
    if (!ser.length) return <span className="meta">—</span>;
    return (
      <div>
        <div className="spark">
          {ser.slice(-14).map((d, i) => (
            <i key={i} title={`difficulty ${d}`}
              style={{ height: `${(d / 5) * 100}%`, ["--i" as any]: i }} />
          ))}
        </div>
        <span className="meta" style={{ fontSize: 11 }}>
          {s.difficulty_first}→{s.difficulty_latest} (min {s.difficulty_min}, max {s.difficulty_max})
        </span>
      </div>
    );
  }

  function settingsForm(submitLabel: string, onSubmit: () => void) {
    return (
      <section className="panel panel-accent controls" style={{ marginBottom: 16 }}>
        <label className="control">Context
          <select value={ctx} onChange={(e) => { setCtx(e.target.value); logUi("change_setting", { field: "context", value: e.target.value }); }}>
            {contexts.map((c) => <option key={c.id} value={c.id}>{c.id}</option>)}
          </select>
        </label>
        <label className="control">Skill
          <select value={skill} onChange={(e) => { setSkill(e.target.value); logUi("change_setting", { field: "skill", value: e.target.value }); }}>
            {domains.map((d) => (
              <optgroup key={d} label={d}>
                {skills.filter((s) => s.domain === d).map((s) => (
                  <option key={s.id} value={s.id}>{s.id}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="control">Difficulty
          <select value={difficulty} onChange={(e) => { setDifficulty(Number(e.target.value)); logUi("change_setting", { field: "difficulty", value: Number(e.target.value) }); }}>
            {availDiffs.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          {availDiffs.length < 5 && (
            <span className="meta" style={{ fontSize: 11, fontWeight: 400 }}>
              only {availDiffs.join(", ")}
            </span>
          )}
        </label>
        <label className="control">Model
          <select value={model} onChange={(e) => { setModel(e.target.value); logUi("change_setting", { field: "model", value: e.target.value }); }}>
            <option value="mock">Mock (instant)</option>
            <option value="openai">Llama (local)</option>
            <option value="anthropic">Claude (needs key)</option>
            <option value="gemini">Gemini (needs key)</option>
            <option value="deepseek">DeepSeek (needs key)</option>
            <option value="gemma">Gemma (local)</option>
          </select>
        </label>
        {submitLabel && <button className="btn-primary" onClick={onSubmit} disabled={busy}>{submitLabel}</button>}
      </section>
    );
  }

  // The per-attempt regeneration trace (statements, claimed answers, rejection
  // reasons) is intentionally NOT rendered on the practice screen -- it belongs
  // in the Debug panel only. Here we surface just a neutral progress spinner.
  const candidatesTried = attempts.filter((a) => a.status === "generating").length;
  const verifying = attempts.length > 0 && attempts[attempts.length - 1].status === "verifying";
  // What the loop is working on this attempt (the Planner's "plan" event carries it).
  const loopPlan = attempts.find((a) => a.skill);
  // A problem is shown but not yet submitted: the student must answer or cancel.
  const hasUnanswered = !!problem && feedback == null;
  const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const fmtDelivery = (ms: number) => (ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`);

  // Three staggered dots — the shared "working" indicator.
  const dots = (
    <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
      {[0, 1, 2].map((i) => <i key={i} className="dot" style={{ ["--i" as any]: i }} />)}
    </span>
  );

  // ---------- screens ----------
  let screen: ReactNode = null;
  if (view === "loading")
    screen = (
      <main className="card">
        <div className="skeleton" style={{ width: "38%", height: 20, marginBottom: 16 }} />
        <div className="skeleton" style={{ width: "88%", marginBottom: 8 }} />
        <div className="skeleton" style={{ width: "64%" }} />
      </main>
    );
  else if (view === "auth" && authMode === "forgot") {
    screen = (
      <main className="card animate__animated animate__fadeIn" style={{ maxWidth: 420 }}>
        <h1>Forgot password</h1>
        <p className="lede">Enter your username to get a reset token.</p>
        <section className="form-stack">
          <label className="field">Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
              onKeyDown={(e) => e.key === "Enter" && username && doForgot()} />
          </label>
          {authError && <p className="panel panel-bad animate__animated animate__headShake" style={{ margin: 0, fontSize: 14 }}>{authError}</p>}
        </section>
        <div className="btn-row">
          <button className="btn-primary" onClick={doForgot} disabled={busy || !username}>{busy ? "…" : "Send reset token →"}</button>
          <button className="btn-ghost btn-sm" onClick={() => { setAuthMode("login"); setAuthError(null); }}>
            Back to log in
          </button>
        </div>
      </main>
    );
  }
  else if (view === "auth" && authMode === "reset") {
    screen = (
      <main className="card animate__animated animate__fadeIn" style={{ maxWidth: 440 }}>
        <h1>Reset password</h1>
        {resetInfo && (
          <p className="panel panel-info" style={{ fontSize: 13 }}>{resetInfo}</p>
        )}
        <section className="form-stack">
          <label className="field">Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label className="field">Reset token
            <input value={resetToken} onChange={(e) => setResetToken(e.target.value)}
              style={{ fontFamily: "ui-monospace, Menlo, monospace" }} />
          </label>
          <label className="field">New password
            <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              onKeyDown={(e) => e.key === "Enter" && resetToken && newPassword && doReset()} />
          </label>
          {authError && <p className="panel panel-bad animate__animated animate__headShake" style={{ margin: 0, fontSize: 14 }}>{authError}</p>}
        </section>
        <div className="btn-row">
          <button className="btn-primary" onClick={doReset} disabled={busy || !username || !resetToken || !newPassword}>
            {busy ? "…" : "Reset password & sign in →"}
          </button>
          <button className="btn-ghost btn-sm" onClick={() => { setAuthMode("login"); setAuthError(null); setResetInfo(null); }}>
            Back to log in
          </button>
        </div>
      </main>
    );
  }
  else if (view === "auth") {
    const isReg = authMode === "register";
    screen = (
      <main className="card animate__animated animate__fadeIn" style={{ maxWidth: isReg ? 640 : 420 }}>
        <h1>{isReg ? "Create account" : "Log in"}</h1>
        <section className="form-stack">
          <label className="field">Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label className="field">Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={isReg ? "new-password" : "current-password"}
              onKeyDown={(e) => e.key === "Enter" && (isReg ? doRegister() : doLogin())} />
          </label>
          {authError && <p className="panel panel-bad animate__animated animate__headShake" style={{ margin: 0, fontSize: 14 }}>{authError}</p>}
        </section>

        {isReg && (
          <>
            <p className="meta" style={{ marginBottom: 8 }}>Starting settings — your first problem is instant.</p>
            {settingsForm("", () => {})}
          </>
        )}

        <div className="btn-row">
          <button className="btn-primary" onClick={isReg ? doRegister : doLogin} disabled={busy || !username || !password}>
            {busy ? "…" : isReg ? "Create account & start →" : "Log in →"}
          </button>
          <button className="btn-ghost btn-sm" onClick={() => { setAuthMode(isReg ? "login" : "register"); setAuthError(null); }}>
            {isReg ? "Have an account? Log in" : "New here? Create an account"}
          </button>
          {!isReg && (
            <button className="btn-ghost btn-sm" onClick={() => { setAuthMode("forgot"); setAuthError(null); setResetInfo(null); }}>
              Forgot password?
            </button>
          )}
        </div>
      </main>
    );
  }
  else if (view === "welcome")
    screen = (
      <main className="animate__animated animate__fadeIn">
        <div className="card">
          <h1>Welcome back{username ? `, ${username}` : ""} 👋</h1>
          <div className="tags" style={{ marginTop: 10 }}>
            <span className="tag tag-accent">{skill}</span>
            <span className="tag">difficulty {difficulty}</span>
            <span className="tag">{ctx}</span>
            <span className="tag">{model}</span>
          </div>
          <div className="btn-row" style={{ marginTop: 18 }}>
            <button className="btn-primary" onClick={() => { logUi("welcome_continue", { model, skill, difficulty }); nextSameSettings(); }} disabled={busy}>No, continue →</button>
            <button onClick={() => { logUi("open_settings"); setView("settings"); }}>Yes, change settings</button>
          </div>
        </div>
        <div className="btn-row" style={{ marginTop: 14 }}>
          <button className="btn-ghost btn-sm" onClick={openStats} disabled={busy}>📊 View my progress</button>
          <button className="btn-ghost btn-sm" onClick={logout}>Log out</button>
        </div>
      </main>
    );
  else if (view === "settings")
    screen = (
      <main className="card animate__animated animate__fadeIn">
        <h1>Adjust settings</h1>
        {settingsForm(busy ? "Loading…" : "Apply & get a problem →", applySettings)}
        <button className="btn-ghost btn-sm" onClick={() => { logUi("cancel_settings"); setView("practice"); }} disabled={!problem}>Cancel</button>
      </main>
    );
  else if (view === "stats") {
    const active = (stats?.per_skill || []).filter((s) => s.delivered > 0 || s.attempts > 0);
    const untouched = (stats?.per_skill || []).length - active.length;
    const card = (label: string, value: ReactNode, sub?: string, i = 0) => (
      <div className="stat animate__animated animate__fadeInUp"
        style={{ animationDelay: `${i * 45}ms`, animationDuration: "480ms" }}>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
        {sub && <div className="stat-sub">{sub}</div>}
      </div>
    );
    const th = {} as const;
    const td = {} as const;
    screen = (
      <main className="animate__animated animate__fadeIn">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
          <h1>📊 Progress{username ? ` — ${username}` : ""}</h1>
          <button className="btn-ghost btn-sm" onClick={() => setView(problem ? "practice" : "welcome")}>← Back</button>
        </div>
        {!stats ? <div className="skeleton" style={{ width: "50%" }} /> : (
          <>
            <section className="stat-grid" style={{ marginBottom: 20 }}>
              {card("Problems solved", stats.correct, `${stats.total_delivered} served`, 0)}
              {card("Attempts", stats.total_attempts, `${stats.incorrect} incorrect`, 1)}
              {card("Accuracy", stats.accuracy != null ? `${Math.round(stats.accuracy * 100)}%` : "—", undefined, 2)}
              {card("Time spent", fmtDuration(stats.total_time_seconds), undefined, 3)}
              {card("Sessions", stats.sessions, undefined, 4)}
            </section>

            <h2>By skill</h2>
            {active.length === 0 ? (
              <p className="panel meta">No problems attempted yet — solve a few and come back!</p>
            ) : (
              <div className="card" style={{ padding: 6, overflowX: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      <th style={th}>Skill</th><th style={th}>Solved</th><th style={th}>Correct / Wrong</th>
                      <th style={th}>Accuracy</th><th style={th}>Mastery</th><th style={th}>Difficulty over time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {active.map((s) => (
                      <tr key={s.skill}>
                        <td style={td}><b>{s.skill}</b><br />
                          <span className="meta" style={{ fontSize: 12 }}>{s.domain}</span></td>
                        <td style={td}>{s.correct}<span className="meta">/{s.delivered}</span></td>
                        <td style={td}>
                          <span style={{ color: "var(--ok)", fontWeight: 600 }}>{s.correct}</span>
                          {" / "}<span style={{ color: "var(--bad)", fontWeight: 600 }}>{s.incorrect}</span>
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
              <p className="meta" style={{ marginTop: 10 }}>
                + {untouched} skills not yet practiced.
              </p>
            )}
            <div className="btn-row" style={{ marginTop: 20 }}>
              <button className="btn-primary" onClick={() => setView(problem ? "practice" : "welcome")}>← Back to practice</button>
              <button className="btn-ghost btn-sm" onClick={openStats} disabled={busy}>↻ Refresh</button>
            </div>
          </>
        )}
      </main>
    );
  }
  else
    screen = (
    <main className="animate__animated animate__fadeIn">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
        <h1>Practice</h1>
        {username && (
          <span className="meta" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {username}
            <button className="btn-ghost btn-sm" onClick={logout}>Log out</button>
          </span>
        )}
      </div>

      {busy && !problem && (
        <section className="card" style={{ marginBottom: 14 }}>
          <p style={{ margin: 0, fontWeight: 600, display: "flex", alignItems: "center", gap: 10 }}>
            {dots}
            {source === "llm"
              ? "Generating a verified problem…"
              : "Fetching a verified problem…"}
          </p>
          <div className="skeleton" style={{ width: "92%", margin: "16px 0 8px" }} />
          <div className="skeleton" style={{ width: "70%" }} />
          {source === "llm" && (
            <>
              {loopPlan?.skill && (
                <p style={{ margin: "12px 0 0", fontWeight: 600 }}>
                  Working on <span className="tag tag-accent">{loopPlan.skill}</span>
                  {" "}<span className="tag">difficulty {loopPlan.difficulty_target}</span>
                  {loopPlan.context_id && <span className="tag">context · {loopPlan.context_id}</span>}
                  {candidatesTried > 0 && <span className="tag">attempt {candidatesTried}</span>}
                </p>
              )}
              <p className="meta" style={{ margin: "10px 0 0" }}>
                Still working — {genSeconds}s elapsed
                {candidatesTried > 0 && <>, candidate #{candidatesTried} {verifying ? "being verified" : "being generated"}</>}.
                {" "}Turn on <b>Debug</b> (top-right) to watch every attempt, its timing, and its rejection reason.
              </p>
            </>
          )}
        </section>
      )}

      {genError && !problem && (
        <section className="panel panel-bad animate__animated animate__fadeIn"
          style={{ marginBottom: 16, display: "flex", justifyContent: "space-between",
            alignItems: "center", gap: 12 }}>
          <p style={{ margin: 0 }}>{genError}</p>
          <button onClick={() => { logUi("retry_generation"); setGenError(null); retryGen.current(); }}
            disabled={busy} style={{ flexShrink: 0 }}>Try again</button>
        </section>
      )}

      {problem && (
        <section key={problem.id} className="card animate__animated animate__fadeInUp"
          style={{ animationDuration: "420ms" }}>
          <div className="tags">
            <span className="tag tag-accent">{problem.skill}</span>
            <span className="tag">{problem.domain}</span>
            <span className="tag">difficulty {problem.difficulty_target}</span>
            {problem.context_id && <span className="tag">context · {problem.context_id}</span>}
            <span className="tag">
              {source === "pre_stored" ? "pre-stored · instant"
                : regen != null ? `verified after ${regen} regeneration${regen === 1 ? "" : "s"}` : "verified"}
            </span>
            {deliverMs != null && <span className="tag">delivered in {fmtDelivery(deliverMs)}</span>}
            {source === "pre_stored" && requestedDiff != null && problem.difficulty_target !== requestedDiff && (
              <span className="tag tag-warn">closest available (you picked {requestedDiff})</span>
            )}
          </div>
          <p className="problem">{problem.statement}</p>
          <p className="meta" style={{ textAlign: "right", margin: "0 0 6px",
            fontVariantNumeric: "tabular-nums" }}>
            ⏱ {clock(solveSeconds)}{feedback == null ? " · solving" : " · time to solve"}
          </p>
          <div className="answer-row">
            <input value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Your answer"
              onKeyDown={(e) => e.key === "Enter" && !busy && answer && submit()} />
            <button className="btn-primary" onClick={submit} disabled={busy || !answer}>Submit</button>
          </div>
          {feedback && (
            <p className={`verdict animate__animated ${feedback.startsWith("✅")
              ? "verdict-ok animate__bounceIn" : "verdict-bad animate__headShake"}`}
              style={{ animationDuration: "600ms" }}>{feedback}</p>
          )}
          {feedback && (
            <details onToggle={(e) => logUi("toggle_solution", { open: (e.target as HTMLDetailsElement).open })}>
              <summary>Show solution</summary>
              <p className="panel" style={{ marginTop: 4 }}>{problem.solution}</p>
            </details>
          )}
        </section>
      )}

      {hasUnanswered && (
        <p className="meta" style={{ marginTop: 16 }}>
          Answer the problem to continue — or <b>Cancel</b> to return to the start.
        </p>
      )}
      <div className="btn-row" style={{ marginTop: hasUnanswered ? 8 : 20 }}>
        <button className="btn-primary" onClick={() => { logUi("click_next_problem", { model, skill, difficulty }); nextSameSettings(); }}
          disabled={busy || hasUnanswered}
          title={hasUnanswered ? "Answer the current problem first"
            : model === "mock" ? "Instant from the verified bank" : `Generate with ${model} at your skill/difficulty`}>
          Next problem →
        </button>
        <button onClick={() => { logUi("click_adaptive_next"); streamProblem({}); }} disabled={busy || hasUnanswered}
          title={hasUnanswered ? "Answer the current problem first" : "The Planner picks what to practice next (changes skill/difficulty)"}>
          Adaptive next (Planner) →
        </button>
        <button className="btn-ghost" onClick={() => { logUi("open_settings"); setView("settings"); }} disabled={busy || hasUnanswered}>Change settings</button>
        <button className="btn-ghost" onClick={openStats} disabled={busy}>📊 Progress</button>
        <button className="btn-ghost" onClick={cancelToWelcome} title="Abandon this problem and return to the start screen">Cancel</button>
      </div>
    </main>
  );

  // ---------- top-level: current screen + debug toggle + log panel ----------
  return (
    <>
      <label className="debug-toggle">
        <input type="checkbox" checked={debug} onChange={(e) => { setDebug(e.target.checked); logUi("toggle_debug", { on: e.target.checked }); }} /> Debug
      </label>
      {screen}
      {debug && (
        <aside className="debug-panel">
          <div className="debug-head">
            <b style={{ color: "#fff" }}>Event log</b>
            <span className="debug-head-tools">
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
              <div key={e.id} className="log-row">
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
