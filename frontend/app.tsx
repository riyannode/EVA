import { lazy, Suspense, useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { animate } from "animejs";
import { createRun, eventUrl, getEpisodes, getRun, getRuns, getScore, getVerification, getWeaknesses, stopRun,
  getMetrics, type Episode, type EvaluationMetrics, type GraphEvent, type Run, type RunInput, type Scorecard, type Verification, type Weakness } from "./api";
import { appendEvent, isActive, parseEvent, readable, stageForEvent, stationForStage, stations, stages, type StationId } from "./graph-view";
import Analysis from "./analysis";
import Agents from "./agents";
import { displayLabel, runLabel } from "./presentation";

const Office = lazy(() => import("./office"));
const NightBackground = lazy(() => import("./night-background"));
const tabs = ["Activity"] as const;
const initialForm: RunInput = { target_id: "REFERENCE_SAFE", target_version: "demo", mode: "SYNTHETIC", max_episodes: 20, difficulty: 1 };

function Avatar({ index, large = false }: { index: number; large?: boolean }) {
  const pixels = ["00111100", "01111110", "01222210", "02232320", "00222200", "00444400", "04444440", "00200200"];
  const colors = ["transparent", ["#997050", "#344450", "#c5c8be", "#6a4b6d", "#b5754f", "#526f5f"][index], "#dab393", "#26323a", stations[index].color];
  return <span className={`avatar ${large ? "avatar-large" : ""}`} aria-hidden="true">{pixels.flatMap((row, y) => [...row].map((cell, x) => <i key={`${x}-${y}`} style={{ background: colors[Number(cell)] }} />))}</span>;
}

function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="empty"><span className="empty-pixels" aria-hidden="true"><i /><i /><i /></span><strong>{title}</strong><p>{children}</p></div>;
}

export default function App() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [score, setScore] = useState<Scorecard | null>(null);
  const [weaknesses, setWeaknesses] = useState<Weakness[]>([]);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [metrics, setMetrics] = useState<EvaluationMetrics | null>(null);
  const [events, setEvents] = useState<GraphEvent[]>([]);
  const [stage, setStage] = useState<string | null>(null);
  const [selected, setSelected] = useState<StationId>("scenario");
  const [connection, setConnection] = useState<"connecting" | "online" | "offline">("connecting");
  const [stream, setStream] = useState<"connecting" | "connected" | "reconnecting" | "closed">("closed");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [tab, setTab] = useState<typeof tabs[number]>("Activity");
  const [form, setForm] = useState<RunInput>(initialForm);
  const [busy, setBusy] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [view, setView] = useState<"observatory" | "analysis" | "agents">("observatory");
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const dialog = useRef<HTMLDialogElement>(null);
  const detail = useRef<HTMLDivElement>(null);
  const inspector = useRef<HTMLElement>(null);
  const motion = !paused && !reduced;
  const active = connection === "online" && stream === "connected" && isActive(run) ? stationForStage(stage) : null;
  const station = stations.find(item => item.id === selected)!;
  const selectedIndex = stations.findIndex(item => item.id === selected);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const listener = () => setReduced(query.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);

  useEffect(() => {
    let disposed = false;
    setConnection("connecting");
    getRuns().then(values => {
      if (disposed) return;
      setRuns(values);
      setConnection("online");
      setRunId(current => current ?? values[0]?.id ?? null);
    }).catch(() => { if (!disposed) setConnection("offline"); });
    return () => { disposed = true; };
  }, [retry]);

  useEffect(() => {
    setRun(null); setEpisodes([]); setScore(null); setMetrics(null); setWeaknesses([]); setVerification(null); setEvents([]); setStage(null);
    if (!runId) return;
    let disposed = false;
    let terminal = false;
    let timer: ReturnType<typeof setTimeout>;
    const source = new EventSource(eventUrl(runId));
    setStream("connecting");
    source.onopen = () => { if (!disposed) setStream("connected"); };
    source.onmessage = (message: MessageEvent<string>) => {
      if (disposed) return;
      const event = parseEvent(message.data, runId);
      if (!event) return;
      setEvents(previous => appendEvent(previous, event));
      const next = stageForEvent(event.type);
      if (next) setStage(next);
      if (event.type === "RUN_FINISHED" || event.type === "RUN_FAILED") {
        terminal = true;
        source.close();
        setStream("closed");
      }
    };
    source.onerror = () => {
      if (disposed) return;
      if (terminal) { source.close(); setStream("closed"); }
      else setStream("reconnecting");
    };
    async function refresh() {
      try {
        const [nextRun, nextEpisodes, nextScore, nextMetrics, nextWeaknesses, nextVerification] = await Promise.all([
          getRun(runId!), getEpisodes(runId!), getScore(runId!), getMetrics(runId!), getWeaknesses(runId!), getVerification(runId!),
        ]);
        if (disposed) return;
        setRun(nextRun); setEpisodes(nextEpisodes); setScore(nextScore); setMetrics(nextMetrics); setWeaknesses(nextWeaknesses); setVerification(nextVerification);
        setStage(nextRun.current_stage); setConnection("online");
        setRuns(previous => previous.map(value => value.id === nextRun.id ? nextRun : value));
        terminal = !isActive(nextRun);
        if (!terminal) timer = setTimeout(refresh, 1800);
      } catch {
        if (!disposed) { setConnection("offline"); timer = setTimeout(refresh, 5000); }
      }
    }
    void refresh();
    return () => { disposed = true; clearTimeout(timer); source.close(); };
  }, [runId, retry]);

  useEffect(() => {
    if (!detail.current || !motion) return;
    const animation = animate(detail.current, { opacity: [0.5, 1], translateY: [5, 0], duration: 220, ease: "outQuad" });
    return () => { animation.revert(); };
  }, [selected, motion]);

  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      const input = form.target_id === "EXTERNAL_HTTP" ? form : {
        target_id: form.target_id, target_version: form.target_version, mode: form.mode, max_episodes: form.max_episodes, difficulty: form.difficulty,
      };
      const value = await createRun(input);
      setRuns(previous => [value, ...previous]); setRunId(value.id); setTab("Activity");
      setForm(previous => ({ ...previous, target_token: "" })); dialog.current?.close();
    } catch { setError("Could not create the run. Check the API and target settings. A request may have reached the server; check existing runs before retrying."); }
    finally { setBusy(false); }
  }

  async function stop() {
    if (!run || busy) return;
    setBusy(true); setError("");
    try { setRun(await stopRun(run.id)); }
    catch { setError("Stop request failed. Check the connection and run status."); }
    finally { setBusy(false); }
  }

  function navigate(value: typeof tabs[number]) {
    setTab(value);
    inspector.current?.scrollIntoView({ behavior: motion ? "smooth" : "instant", block: "start" });
  }

  const failures = episodes.filter(episode => episode.result === "FAIL").length;
  const measured = episodes.length > 0;
  return <>
    <Suspense fallback={<div className="night-background" aria-hidden="true" />}><NightBackground motion={motion} /></Suspense>
    <button className="background-motion" onClick={() => setPaused(value => !value)} disabled={reduced} aria-pressed={!motion}>{reduced ? "Reduced motion" : motion ? "Pause background" : "Resume background"}</button>
    <a className="skip-link" href="#main">Skip to workspace</a>
    <header className="app-header">
      <a className="brand" href="#main" aria-label="EVA workspace"><span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span><span>EVA</span></a>
      <nav aria-label="Workspace navigation"><button className={view === "observatory" ? "nav-current" : ""} onClick={() => setView("observatory")}>Observatory</button><button className={view === "analysis" ? "nav-current" : ""} onClick={() => setView("analysis")}>Analysis</button><button className={view === "agents" ? "nav-current" : ""} onClick={() => setView("agents")}>Agents</button></nav>
      <div className={`connection ${connection}`} role="status"><i />{connection === "online" ? "API connected" : connection === "connecting" ? "Connecting" : "API offline"}</div>
    </header>
    <main id="main" className={view === "observatory" ? "observatory-layout" : undefined}>
      {view === "analysis" ? <Analysis runs={runs} runId={runId} run={run} episodes={episodes} score={score} metrics={metrics} weaknesses={weaknesses} verification={verification} onRunChange={setRunId} /> : view === "agents" ? <Agents onEvaluationCreated={value => { setRuns(previous => [value, ...previous]); setRunId(value.id); setTab("Activity"); setView("observatory"); }} /> : <>
      <section className="page-heading">
        <div><div className="breadcrumb">Workspace <span>/</span> Observatory</div><h1>Watch your agent being tested.</h1><p>Start an evaluation, follow each step, then review the results in Analysis.</p></div>
        <div className="heading-actions"><button className="button primary" onClick={() => { setError(""); setConfigOpen(true); dialog.current?.showModal(); }}><span aria-hidden="true">+</span> New evaluation</button></div>
      </section>

      <div className="observatory-primary">
      {connection === "offline" && <div className="connection-notice"><span><strong>Backend disconnected.</strong> The office is idle. Run data will appear when the API is available.</span><button onClick={() => setRetry(value => value + 1)}>Reconnect</button></div>}
      {error && !configOpen && <p className="error" role="alert">{error}</p>}

      <section className="evaluation-context panel" aria-label="Selected evaluation">
        <label><span>Evaluation to watch</span><select value={runId ?? ""} onChange={event => setRunId(event.target.value || null)}><option value="">Select an evaluation</option>{runs.map(value => <option key={value.id} value={value.id}>{runLabel(value)}</option>)}</select></label>
        <div><span>Test environment</span><strong>{run ? displayLabel(run.mode) : "No evaluation selected"}</strong></div>
        <div><span>Progress</span><strong>{run ? `${episodes.length} / ${run.max_episodes} test cases · ${displayLabel(run.status)}` : "Create an evaluation to begin"}</strong></div>
        <button className="button" disabled={!run} onClick={() => setView("analysis")}>Review results</button>
      </section>
      <div className="workspace">
        <section className="observatory panel" aria-labelledby="office-title">
          <div className="panel-heading"><h2 id="office-title"><span className="square-indicator" />Observatory</h2><div className="scene-controls"><span className="idle-label">{active ? `${stationForStage(stage)} active` : "Office on standby"}</span><button className="motion-button" aria-pressed={paused || reduced} onClick={() => setPaused(value => !value)} disabled={reduced}>{reduced ? "Reduced motion" : motion ? "Pause motion" : "Resume motion"}</button></div></div>
          <div className="scene-wrap">
            <div className="scene-caption"><span>Evaluation floor</span><small>Agents hand off work as graph events arrive</small></div>
            <Suspense fallback={<div className="scene-loading">Building the office…</div>}><Office key={runId ?? "empty"} active={active} selected={selected} events={events} running={connection === "online" && stream === "connected" && isActive(run)} motion={motion} onSelect={setSelected} /></Suspense>
            <div className="scene-bottom"><span><i className="mini-dot" />{run ? readable(run.mode) : "No run selected"}</span></div>
          </div>
          <div className="graph-strip" aria-label="LangGraph stages">{stages.map((value, index) => <div key={value} className={stage === value && run ? "current" : ""} title={value}><span>{String(index + 1).padStart(2, "0")}</span><b>{({ CHOOSE_SCENARIO: "Scenario", RUN_TARGET: "Target", RUN_ORACLES: "Oracles", SAVE_MEMORY: "Memory", LOAD_RUN: "Load" } as Record<string, string>)[value] ?? readable(value)}</b></div>)}</div>
        </section>

        <aside className="roster panel" aria-labelledby="roster-title">
          <div className="panel-heading"><h2 id="roster-title">The crew</h2><span className="count">6 stations</span></div>
          <div className="station-list">{stations.map((value, index) => <button key={value.id} className={`station ${selected === value.id ? "selected" : ""}`} style={{ "--station-color": value.color } as CSSProperties} onClick={() => setSelected(value.id)} aria-pressed={selected === value.id}>
            <Avatar index={index} /><span className="station-copy"><strong>{value.name}</strong><small>{value.role}</small></span><span className={`station-state ${active === value.id ? "working" : ""}`}>{active === value.id ? "Active" : "Idle"}</span>
          </button>)}</div>
          <div className="station-detail" ref={detail}><div className="detail-title"><span className="station-number">0{selectedIndex + 1}</span><strong>{station.name} station</strong></div><p>{station.description}</p><code>{station.stages[0]}</code></div>
          <div className="roster-note">Roles in one graph.<br />Not six independent traders.</div>
        </aside>
      </div>

      <section className="telemetry" aria-label="Run summary">
        <div><span>Readiness score</span><strong>{measured && score ? score.score : "—"}<small>/ 100</small></strong><p>{measured && score ? readable(score.label) : "Not measured yet"}</p></div>
        <div><span>Test cases evaluated</span><strong>{run ? episodes.length.toString().padStart(2, "0") : "—"}<small>{run ? `/ ${run.max_episodes}` : "/ —"}</small></strong><p>{run ? readable(run.status) : "Waiting for an evaluation"}</p></div>
        <div><span>Difficulty reached</span><strong>{run ? String(run.difficulty).padStart(2, "0") : "—"}<small>/ 05</small></strong><p>Difficulty increases after repeated passes</p></div>
        <div><span>Observed failures</span><strong className={failures > 0 ? "failure-number" : ""}>{measured ? String(failures).padStart(2, "0") : "—"}</strong><p>{measured ? `${Math.round(failures / episodes.length * 100)}% of evaluated episodes` : "No results to grade"}</p></div>
      </section>

      </div>
      <section className="inspector panel" ref={inspector} aria-label="Run evidence">
        <div className="inspector-toolbar"><div className="tabs" role="tablist" aria-label="Evidence view">{tabs.map((value, index) => <button key={value} id={`tab-${value.replaceAll(" ", "-")}`} role="tab" tabIndex={tab === value ? 0 : -1} aria-selected={tab === value} aria-controls="evidence-panel" onClick={() => setTab(value)} onKeyDown={event => {
          const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
          if (next === null) return;
          event.preventDefault(); setTab(tabs[next]); document.getElementById(`tab-${tabs[next].replaceAll(" ", "-")}`)?.focus();
        }}>{value}{value === "Activity" && <span>{events.length}</span>}</button>)}</div>
          <label className="run-select"><span className="sr-only">Select evaluation run</span><select value={runId ?? ""} onChange={event => setRunId(event.target.value || null)}><option value="">Select a run</option>{runs.map(value => <option key={value.id} value={value.id}>{runLabel(value)}</option>)}</select></label>
          {isActive(run) && <button className="button stop-button" disabled={busy} onClick={() => void stop()}>Stop run</button>}
        </div>
        <div id="evidence-panel" role="tabpanel" aria-labelledby={`tab-${tab.replaceAll(" ", "-")}`}>
          {tab === "Activity" && <><div className="feed-heading"><span>Graph event stream</span><span>{run ? stream === "connected" ? "SSE connected" : stream === "closed" ? "Stored run events" : "Stream reconnecting" : "Waiting for a run"}</span></div>{events.length ? <ol className="event-list">{[...events].reverse().map(event => <li key={event.id}><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleTimeString("en-GB")}</time><span className="event-type">{event.type}</span><details><summary>Inspect payload</summary><pre>{JSON.stringify(event.payload, null, 2)}</pre></details></li>)}</ol> : <Empty title="A quiet office, for now.">Start an evaluation to see scenarios, decisions and oracle results arrive here.</Empty>}</>}
        </div>
      </section>
      <footer><span>EVA <span className="footer-divider">/</span> Adaptive trading-agent evaluation</span><span>Qwen creates. Deterministic code grades.</span></footer></>}
    </main>

    <dialog ref={dialog} className="run-dialog" aria-label="New evaluation configuration" onClose={() => { setError(""); setConfigOpen(false); }}>
      <form onSubmit={start}><div className="dialog-heading"><div><h2>New evaluation</h2><p>Choose the agent and the tests EVA will run.</p></div><button type="button" className="close-button" aria-label="Close configuration" onClick={() => dialog.current?.close()}>×</button></div>
        <label>Evaluation mode<select value={form.mode} onChange={event => setForm(previous => ({ ...previous, mode: event.target.value as Run["mode"], ...(event.target.value === "BITGET_PAPER" ? { target_id: "EXTERNAL_HTTP" } : {}) }))}><option value="SYNTHETIC">Synthetic scenarios (no exchange orders)</option><option value="BITGET_PAPER">Bitget demo account (paper orders)</option></select></label>
        <label>Target agent<select value={form.target_id} onChange={event => setForm(previous => ({ ...previous, target_id: event.target.value }))}><option value="REFERENCE_SAFE" disabled={form.mode === "BITGET_PAPER"}>Safety-focused reference agent</option><option value="REFERENCE_WEAK" disabled={form.mode === "BITGET_PAPER"}>Weak reference agent</option><option value="EXTERNAL_HTTP">Your external trading agent</option></select></label>
        {form.target_id === "EXTERNAL_HTTP" && <><label>Agent endpoint URL<input type="url" required value={form.target_url ?? ""} onChange={event => setForm(previous => ({ ...previous, target_url: event.target.value }))} placeholder="http://127.0.0.1:9000/agent" /></label><div className="form-grid"><label>Agent name<input required value={form.target_name ?? ""} maxLength={100} onChange={event => setForm(previous => ({ ...previous, target_name: event.target.value }))} /></label><label>Agent model name<input required value={form.target_model ?? ""} maxLength={100} onChange={event => setForm(previous => ({ ...previous, target_model: event.target.value }))} /></label></div><label>Bearer token <small>optional · not stored in the browser</small><input type="password" autoComplete="off" value={form.target_token ?? ""} maxLength={500} onChange={event => setForm(previous => ({ ...previous, target_token: event.target.value }))} /></label></>}
        <div className="form-grid"><label>Agent version<input required maxLength={40} value={form.target_version} onChange={event => setForm(previous => ({ ...previous, target_version: event.target.value }))} /></label><label>Maximum test cases<input type="number" min={1} max={100} required value={form.max_episodes} onChange={event => setForm(previous => ({ ...previous, max_episodes: Number(event.target.value) }))} /></label></div>
        <label>Starting difficulty<select value={form.difficulty} onChange={event => setForm(previous => ({ ...previous, difficulty: Number(event.target.value) }))}>{[1, 2, 3, 4, 5].map(value => <option key={value} value={value}>Level {value}</option>)}</select></label>
        <p className="form-note">{form.mode === "BITGET_PAPER" ? "EVA tests your external agent using Bitget demo funds. Enter the agent endpoint and the model it declares." : "Reference agents are built-in test examples. Choose an external agent to evaluate your own model. Synthetic tests do not place exchange orders."}</p>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="button primary submit-button" disabled={busy}>{busy ? "Creating run…" : "Start evaluation"}</button>
      </form>
    </dialog>
  </>;
}
