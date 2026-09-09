import { FormEvent, useEffect, useMemo, useState } from "react";
import { createRun, eventUrl, Episode, executeLiveOrder, getEpisodes, getRun, getScore, getTradingStatus, getWeaknesses, LiveOrder, previewLiveOrder, Run, Scorecard, stopRun, TradingStatus, Weakness } from "./api";

const initialScore: Scorecard = { score: 0, label: "NOT_READY", breakdown: { policy: 0, freshness: 0, sizing: 0, takeover: 0, execution: 0, consistency: 0, tool_discipline: 0 }, primary_weakness: null };

function Badge({ value }: { value: string }) {
  return <span className={`badge badge-${value.toLowerCase().replaceAll("_", "-")}`}>{value}</span>;
}

function App() {
  const [target, setTarget] = useState("REFERENCE_WEAK");
  const [version, setVersion] = useState("v1");
  const [mode, setMode] = useState<Run["mode"]>("SYNTHETIC");
  const [maxEpisodes, setMaxEpisodes] = useState(12);
  const [difficulty, setDifficulty] = useState(1);
  const [run, setRun] = useState<Run | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [score, setScore] = useState<Scorecard>(initialScore);
  const [weaknesses, setWeaknesses] = useState<Weakness[]>([]);
  const [error, setError] = useState("");
  const [tradingStatus, setTradingStatus] = useState<TradingStatus | null>(null);
  const [liveSymbol, setLiveSymbol] = useState("BTCUSDT");
  const [liveSide, setLiveSide] = useState<"BUY" | "SELL">("BUY");
  const [liveNotional, setLiveNotional] = useState("50");
  const [livePreview, setLivePreview] = useState<{ symbol: string; side: "BUY" | "SELL"; notional: string; mode: string; armed: boolean; idempotency_key: string } | null>(null);
  const [liveOrder, setLiveOrder] = useState<LiveOrder | null>(null);
  const [liveConfirm, setLiveConfirm] = useState(false);
  const [liveError, setLiveError] = useState("");

  useEffect(() => {
    void getTradingStatus().then(setTradingStatus).catch((caught) => setLiveError(caught instanceof Error ? caught.message : "API_ERROR"));
  }, []);

  const refresh = async (id: string) => {
    try {
      const current = await getRun(id);
      const [history, currentScore, memory] = await Promise.all([getEpisodes(id), getScore(id), getWeaknesses(id)]);
      setRun(current);
      setEpisodes(history);
      setScore(currentScore);
      setWeaknesses(memory);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "API_ERROR");
    }
  };

  useEffect(() => {
    if (!run) return;
    if (["COMPLETED", "STOPPED", "FAILED"].includes(run.status)) return;
    const source = new EventSource(eventUrl(run.id));
    const poll = window.setInterval(() => void refresh(run.id), 1000);
    source.onmessage = () => void refresh(run.id);
    source.onerror = () => source.close();
    return () => {
      source.close();
      window.clearInterval(poll);
    };
  }, [run?.id]);

  const canStop = run?.status === "RUNNING" || run?.status === "CREATED";
  const lastEpisode = episodes[episodes.length - 1];
  const progress = useMemo(() => Math.min(100, ((run?.episode || 0) / (run?.max_episodes || maxEpisodes)) * 100), [run, maxEpisodes]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const created = await createRun({ target_id: target, target_version: version, mode, max_episodes: maxEpisodes, difficulty });
      setRun(created);
      setEpisodes([]);
      setScore(initialScore);
      setWeaknesses([]);
      await refresh(created.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "API_ERROR");
    }
  };

  const stop = async () => {
    if (!run) return;
    try {
      setRun(await stopRun(run.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "API_ERROR");
    }
  };

  const preview = async () => {
    setLiveError("");
    setLiveOrder(null);
    try {
      const value = await previewLiveOrder({ symbol: liveSymbol, side: liveSide, notional: liveNotional });
      setLivePreview({ ...value, idempotency_key: crypto.randomUUID() });
      setLiveConfirm(false);
    } catch (caught) {
      setLiveError(caught instanceof Error ? caught.message : "API_ERROR");
    }
  };

  const execute = async () => {
    if (!livePreview || !liveConfirm) return;
    setLiveError("");
    try {
      setLiveOrder(await executeLiveOrder({ ...livePreview, confirm: true }));
    } catch (caught) {
      setLiveError(caught instanceof Error ? caught.message : "API_ERROR");
    }
  };

  return (
    <main className="shell">
      <header className="topbar">
        <div><span className="eyebrow">EVALUATION & VERIFICATION AGENT</span><h1>EVA console</h1></div>
        <div className="header-note"><span className="pulse" />adaptive benchmark loop</div>
      </header>
      <section className="grid start-grid">
        <form className="panel start-panel" onSubmit={submit}>
          <div className="panel-heading"><div><span className="eyebrow">01 / CONFIGURE</span><h2>Start run</h2></div><Badge value={mode} /></div>
          <div className="fields">
            <label>Target<select value={target} onChange={(event) => setTarget(event.target.value)}><option>REFERENCE_WEAK</option><option>REFERENCE_SAFE</option><option>EXTERNAL_HTTP</option></select></label>
            <label>Target version<input value={version} onChange={(event) => setVersion(event.target.value)} /></label>
            <label>Mode<select value={mode} onChange={(event) => setMode(event.target.value as Run["mode"])}><option value="SYNTHETIC">SYNTHETIC</option><option value="BITGET_PAPER">BITGET_PAPER · live benchmark</option></select></label>
            <label>Max episodes<input type="number" min="1" max="100" value={maxEpisodes} onChange={(event) => setMaxEpisodes(Number(event.target.value))} /></label>
            <label>Starting difficulty<input type="number" min="1" max="5" value={difficulty} onChange={(event) => setDifficulty(Number(event.target.value))} /></label>
          </div>
          <div className="button-row"><button type="submit">Start evaluation <span>→</span></button><button type="button" className="ghost" onClick={stop} disabled={!canStop}>Stop</button></div>
          {error && <div className="error">{error}</div>}
        </form>
        <section className="panel signal-panel"><span className="eyebrow">THESIS</span><p className="thesis">EVA tests the agents that trade.</p><div className="signal-list"><div><span>Generate</span><b>→</b></div><div><span>Verify</span><b>→</b></div><div><span>Remember</span><b>→</b></div><div><span>Mutate</span><b>→</b></div><div><span>Score</span></div></div></section>
      </section>
      <section className="panel trade-panel"><div className="panel-heading"><div><span className="eyebrow">06 / EXECUTE</span><h2>Live trading</h2></div><Badge value={tradingStatus?.live_orders ? "LIVE ARMED" : "LOCKED"} /></div><p className="trade-note">Live execution is separate from the benchmark loop and requires an explicit confirmation.</p><div className="trade-fields"><label>Symbol<input value={liveSymbol} onChange={(event) => setLiveSymbol(event.target.value.toUpperCase())} /></label><label>Side<select value={liveSide} onChange={(event) => setLiveSide(event.target.value as "BUY" | "SELL")}><option value="BUY">BUY</option><option value="SELL">SELL</option></select></label><label>Notional<input inputMode="decimal" value={liveNotional} onChange={(event) => setLiveNotional(event.target.value)} /></label></div><div className="button-row"><button type="button" className="ghost" onClick={preview}>Preview order</button>{livePreview && <label className="confirm"><input type="checkbox" checked={liveConfirm} onChange={(event) => setLiveConfirm(event.target.checked)} /> Confirm live order</label>}<button type="button" onClick={execute} disabled={!livePreview || !liveConfirm}>Submit live order</button></div>{livePreview && <div className="order-preview"><span>{livePreview.side} {livePreview.symbol} · {livePreview.notional}</span><small>idempotency {livePreview.idempotency_key}</small></div>}{liveOrder && <div className="order-result"><Badge value={liveOrder.status} /><span>{liveOrder.id}</span></div>}{liveError && <div className="error">{liveError}</div>}</section>
      <section className="grid live-grid">
        <section className="panel live-panel"><div className="panel-heading"><div><span className="eyebrow">02 / OBSERVE</span><h2>Live run</h2></div>{run && <Badge value={run.status} />}</div><div className="run-id">{run ? run.id : "No run selected"}</div><div className="progress"><span style={{ width: `${progress}%` }} /></div><div className="telemetry"><div><span>Episode</span><strong>{run?.episode || 0}<small> / {run?.max_episodes || maxEpisodes}</small></strong></div><div><span>Difficulty</span><strong>{run?.difficulty || difficulty}</strong></div><div><span>Category</span><strong>{run?.current_category || "—"}</strong></div><div><span>Graph stage</span><strong>{run?.current_stage || "IDLE"}</strong></div><div><span>Target action</span><strong>{lastEpisode?.decision?.action || "—"}</strong></div><div><span>Oracle result</span><strong className={lastEpisode?.result === "FAIL" ? "danger-text" : "safe-text"}>{lastEpisode?.result || "—"}</strong></div></div></section>
        <section className="panel score-panel"><div className="panel-heading"><div><span className="eyebrow">03 / READINESS</span><h2>Scorecard</h2></div><Badge value={score.label} /></div><div className="score-value">{score.score}<small>/100</small></div><div className="breakdown">{Object.entries(score.breakdown).map(([name, value]) => <div key={name}><span>{name.replaceAll("_", " ")}</span><b>{value}</b></div>)}</div><div className="weak-callout"><span>Primary weakness</span><strong>{score.primary_weakness || "None detected"}</strong></div></section>
      </section>
      <section className="grid tables-grid"><section className="panel"><div className="panel-heading"><div><span className="eyebrow">04 / EPISODES</span><h2>Evidence history</h2></div><span className="count">{episodes.length} records</span></div><div className="table-wrap"><table><thead><tr><th>#</th><th>Scenario</th><th>Difficulty</th><th>Decision</th><th>Result</th><th>Failure</th></tr></thead><tbody>{episodes.length ? episodes.map((episode) => <tr key={episode.id}><td>{String(episode.number).padStart(2, "0")}</td><td><strong>{episode.scenario.title}</strong><small>{episode.category}</small></td><td>{episode.difficulty}</td><td>{episode.decision?.action || "—"}</td><td><Badge value={episode.result} /></td><td className="failure-cell">{episode.failure_type || "—"}</td></tr>) : <tr><td colSpan={6} className="empty">Start a run to collect benchmark evidence.</td></tr>}</tbody></table></div></section><section className="panel"><div className="panel-heading"><div><span className="eyebrow">05 / MEMORY</span><h2>Weaknesses</h2></div><span className="count">target-scoped</span></div><div className="table-wrap"><table><thead><tr><th>Failure</th><th>Attempts</th><th>Fails</th><th>Rate</th></tr></thead><tbody>{weaknesses.length ? weaknesses.map((weakness) => <tr key={`${weakness.failure_type}-${weakness.category}`}><td><strong>{weakness.failure_type}</strong><small>{weakness.category}</small></td><td>{weakness.attempts}</td><td className="danger-text">{weakness.fails}</td><td>{Math.round(weakness.failure_rate * 100)}%</td></tr>) : <tr><td colSpan={4} className="empty">No recurring weakness yet.</td></tr>}</tbody></table></div></section></section>
      <footer><span>EVA / V1</span><span>Objective oracles remain authoritative · Live execution is user-confirmed</span></footer>
    </main>
  );
}

export default App;
