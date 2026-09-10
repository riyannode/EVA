import { useEffect, useState, type CSSProperties } from "react";
import type { Episode, EvaluationMetrics, Run, Scorecard, Verification, Weakness } from "./api";
import { readable } from "./graph-view";
import { behavioralTone, filledOrderFields } from "./analysis-data";

type AnalysisTab = "Overview" | "Episodes" | "Weakness memory";

type AnalysisProps = {
  runs: Run[];
  runId: string | null;
  run: Run | null;
  episodes: Episode[];
  score: Scorecard | null;
  metrics: EvaluationMetrics | null;
  weaknesses: Weakness[];
  verification: Verification | null;
  onRunChange: (id: string) => void;
};

const oracleCategories = ["policy", "freshness", "sizing", "takeover", "execution", "consistency", "tool_discipline"] as const;
const behaviorMetrics = [
  ["False autonomy", "false_autonomy_rate", "false_autonomy_count"],
  ["Unnecessary escalation", "unnecessary_escalation_rate", "unnecessary_escalation_count"],
  ["Takeover accuracy", "takeover_accuracy", "takeover_success_count"],
  ["Consistency failures", "consistency_failure_rate", "consistency_failure_count"],
  ["Tool precondition violations", "tool_precondition_violation_count", "tool_precondition_violation_count"],
  ["Duplicate actions", "duplicate_action_count", "duplicate_action_count"],
  ["Execution mismatches", "execution_mismatch_count", "execution_mismatch_count"],
] as const;

function rate(value: number | null | undefined) {
  return value === null || value === undefined ? "UNAVAILABLE" : `${Math.round(value * 100)}%`;
}

function count(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : value.toString().padStart(2, "0");
}

function Metric({ label, value, detail, tone = "" }: { label: string; value: string; detail: string; tone?: string }) {
  return <div className={`analysis-metric ${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

function Panel({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return <section className={`analysis-panel panel ${className}`}><div className="analysis-panel-heading"><h2>{title}</h2></div>{children}</section>;
}

function Value({ value, tone = "" }: { value: string; tone?: string }) {
  return <strong className={`analysis-value ${tone}`}>{value}</strong>;
}

function Payload({ value }: { value: unknown }) {
  return <pre className="analysis-payload">{JSON.stringify(value, null, 2)}</pre>;
}

function OrderEvidence({ episodes }: { episodes: Episode[] }) {
  const traces = episodes.flatMap(episode => episode.target_trace.filter(trace => trace.tool === "paper_order"));
  if (!traces.length) return <span className="analysis-muted">UNAVAILABLE</span>;
  const values = traces.map(filledOrderFields).filter(value => value !== null);
  return values.length ? <Payload value={values} /> : <span className="analysis-muted">UNVERIFIED</span>;
}

export default function Analysis({ runs, runId, run, episodes, score, metrics, weaknesses, verification, onRunChange }: AnalysisProps) {
  const [tab, setTab] = useState<AnalysisTab>("Overview");
  const latest = episodes.at(-1) ?? null;
  const paper = run?.mode === "BITGET_PAPER";
  const selectedStationStyle = { "--analysis-accent": paper ? "#dfbf78" : "#83c7ac" } as CSSProperties;

  useEffect(() => { setTab("Overview"); }, [runId]);

  if (!run) return <div className="analysis-empty"><span className="breadcrumb">Workspace <span>/</span> Analysis</span><h1>Analysis</h1><p>Select a run to inspect measured evidence.</p><select aria-label="Select evaluation run" value={runId ?? ""} onChange={event => onRunChange(event.target.value)}><option value="">Select a run</option>{runs.map(value => <option key={value.id} value={value.id}>{value.target_name || value.target_id} · {value.id.slice(0, 8)}</option>)}</select></div>;

  return <div className="analysis-page" style={selectedStationStyle}>
    <section className="page-heading analysis-heading"><div><div className="breadcrumb">Workspace <span>/</span> Analysis</div><h1>Analysis</h1><p>Measured behavior and evidence for one evaluation.</p></div><label className="analysis-run-selector"><span>Run</span><select aria-label="Select evaluation run" value={run.id} onChange={event => onRunChange(event.target.value)}>{runs.map(value => <option key={value.id} value={value.id}>{value.target_name || value.target_id} · {value.id.slice(0, 8)}</option>)}</select></label></section>
    <section className="analysis-runbar panel"><div><span className="analysis-run-label">Target</span><strong>{run.target_name || run.target_id}</strong></div><div><span className="analysis-run-label">Mode</span><code>{run.mode}</code></div><div><span className="analysis-run-label">Status</span><span className={`analysis-status ${run.status.toLowerCase()}`}><i />{readable(run.status)}</span></div><div><span className="analysis-run-label">Version</span><strong>{run.target_version}</strong></div><div><span className="analysis-run-label">Coverage</span><strong>{score ? `${Math.round(score.coverage_pct * 100)}%` : "—"}</strong></div></section>

    <div className="analysis-tabs" role="tablist" aria-label="Analysis views">{(["Overview", "Episodes", "Weakness memory"] as const).map(value => <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)}>{value}</button>)}</div>
    {tab === "Overview" && <>
      <Panel title="Evaluation Summary" className="analysis-summary"><div className="analysis-metrics"><Metric label="Readiness score" value={score ? `${score.score}/100` : "UNAVAILABLE"} detail={score ? readable(score.label) : "No score"} tone={score?.label === "READY" ? "good" : ""} /><Metric label="Pass rate" value={rate(metrics?.pass_rate)} detail={metrics ? `${metrics.total_episodes} episodes` : "No metrics"} /><Metric label="Risk violation rate" value={rate(metrics?.risk_violation_rate)} detail={metrics ? `${metrics.risk_violation_count} violations` : "No metrics"} tone={metrics?.risk_violation_count ? "warn" : ""} /><Metric label="Difficulty reached" value={metrics ? `${metrics.difficulty_reached}/05` : "UNAVAILABLE"} detail={metrics ? `${metrics.total_scenarios} scenarios` : "No metrics"} /></div></Panel>
<Panel title="Behavioral Performance"><div className="analysis-list">{behaviorMetrics.map(([label, primary, secondary]) => { const value = metrics?.[primary]; const secondaryValue = metrics?.[secondary]; const isRate = primary.endsWith("_rate") || primary === "takeover_accuracy"; return <div className="analysis-row" key={label}><span>{label}</span><Value value={isRate ? rate(value as number | null | undefined) : count(value as number | null | undefined)} tone={behavioralTone(primary, value)} /><small>{isRate ? `${count(secondaryValue as number | null | undefined)} count` : "count"}</small></div>; })}</div></Panel>
      <div className="analysis-two-col"><Panel title="Decision Trace" className="trace-panel">{latest ? <div className="trace-content"><div className="trace-block"><span className="analysis-kicker">Scenario</span><strong>{latest.scenario.title}</strong><small>{readable(latest.category)} · difficulty {latest.difficulty}</small><p>{latest.scenario.description}</p></div><div className="trace-block"><span className="analysis-kicker">Observable evidence</span>{latest.scenario.evidence.length ? latest.scenario.evidence.map(item => <div className="evidence-line" key={item.evidence_id}><i className={item.authoritative ? "authoritative" : ""} />{item.summary}<small>{item.kind}</small></div>) : <span className="analysis-muted">No scenario evidence</span>}</div><div className="trace-block"><span className="analysis-kicker">Target tool trace</span>{latest.target_trace.length ? <ol className="trace-list">{latest.target_trace.map(trace => <li key={trace.sequence}><b>{String(trace.sequence).padStart(2, "0")}</b><span>{trace.tool}</span><small>{trace.result_status} · {Math.round(trace.latency_ms)}ms</small></li>)}</ol> : <span className="analysis-muted">No tool calls</span>}</div><div className="trace-block decision-block"><span className="analysis-kicker">Target final decision</span>{latest.decision ? <><strong className="decision-action">{latest.decision.action}{latest.decision.symbol ? ` · ${latest.decision.symbol}` : ""}</strong><small>{latest.decision.notional ? `${latest.decision.notional} notional · ` : ""}{Math.round(latest.decision.confidence * 100)}% confidence</small><p><b>Target rationale</b> {latest.decision.reason || "Not declared"}</p></> : <span className="analysis-muted">No final decision</span>}</div><div className="trace-block oracle-block"><span className="analysis-kicker">Deterministic oracle results</span>{latest.oracle_results.map(oracle => <div className="oracle-line" key={oracle.name}><span className={`oracle-dot ${oracle.status.toLowerCase()}`} /> <b>{oracle.name}</b><small>{oracle.status} · {oracle.code}</small></div>)}</div><div className="trace-block critic-block"><span className="analysis-kicker">Qwen critic summary</span><p>{latest.critic.diagnosis}</p><small>{latest.critic.failure_class} · {latest.critic.model} · {latest.critic.labels.join(", ") || "UNVERIFIED"}</small></div></div> : <div className="analysis-empty-inline">No episode trace recorded.</div>}</Panel>
      <div className="analysis-stack"><Panel title="Adaptive Learning"><div className="analysis-focus"><span className="analysis-kicker">Primary recurring weakness</span><Value value={metrics?.primary_recurring_weakness ? readable(metrics.primary_recurring_weakness) : "UNAVAILABLE"} /></div><div className="analysis-counters"><div><span>Targeted mutations</span><strong>{count(metrics?.targeted_mutations)}</strong></div><div><span>Retest passes</span><strong>{count(metrics?.mutation_retest_passes)}</strong></div><div><span>Retest failures</span><strong>{count(metrics?.mutation_retest_failures)}</strong></div></div>{weaknesses.slice(0, 4).map(value => <div className="weakness-line" key={`${value.category}-${value.failure_type}`}><span>{readable(value.failure_type)}</span><strong>{Math.round(value.failure_rate * 100)}%</strong><small>{value.attempts} attempts · {value.passes} recovery passes</small></div>)}{!weaknesses.length && <span className="analysis-muted">No weakness memory</span>}</Panel><Panel title="Deterministic Oracle Report"><div className="oracle-report">{oracleCategories.map(category => { const measured = score?.measured[category]; const earned = score?.breakdown[category] ?? 0; const weight = { policy: 20, freshness: 15, sizing: 15, takeover: 15, execution: 15, consistency: 10, tool_discipline: 10 }[category]; return <div className="oracle-report-line" key={category}><span>{readable(category)}</span><b>{measured ? `${measured.pass}/${measured.total}` : "—"}</b><small>{earned}/{weight}</small></div>; })}</div><div className="oracle-legend"><span><i className="oracle-dot pass" />PASS / measured</span><span><i className="oracle-dot na" />No evidence</span></div></Panel></div></div>
      {paper && <Panel title="Paper Evidence" className="paper-panel"><div className="paper-summary"><Metric label="Paper trade count" value={count(metrics?.paper_trade_count)} detail={metrics?.paper_metrics_status ?? "UNAVAILABLE"} /><div className="paper-labels"><span className="analysis-kicker">Verified labels</span>{Object.entries(verification?.evidence ?? {}).filter(([, value]) => value).map(([key]) => <code key={key}>{key}</code>)}{!Object.values(verification?.evidence ?? {}).some(Boolean) && <span className="analysis-muted">UNVERIFIED</span>}</div><div className="paper-order"><span className="analysis-kicker">Filled order evidence</span><OrderEvidence episodes={episodes} /></div></div><div className="financial-grid">{([["win_rate", "Win rate"], ["pnl", "PnL"], ["return_pct", "Return"], ["sharpe", "Sharpe"], ["sortino", "Sortino"], ["max_drawdown", "Max drawdown"], ["turnover", "Turnover"], ["fees", "Fees"], ["slippage", "Slippage"]] as const).map(([key, label]) => <div key={key}><span>{label}</span><strong>{metrics?.[key] === null || metrics?.[key] === undefined ? "UNAVAILABLE" : String(metrics[key])}</strong></div>)}</div></Panel>}
    </>}
    {tab === "Episodes" && <Panel title="Episodes"><div className="table-scroll"><table><thead><tr><th>Episode</th><th>Scenario</th><th>Decision</th><th>Result</th><th>Oracle evidence</th></tr></thead><tbody>{episodes.length ? episodes.map(episode => <tr key={episode.id}><td>{String(episode.number).padStart(2, "0")}</td><td><strong>{episode.scenario.title}</strong><small>{readable(episode.category)} · difficulty {episode.difficulty}</small></td><td>{episode.decision?.action ?? "No decision"}<small>{episode.decision?.symbol ?? ""}</small></td><td><span className={`result ${episode.result === "PASS" ? "pass" : "fail"}`}>{episode.result}</span></td><td>{episode.oracle_results.filter(value => value.status !== "NOT_APPLICABLE").map(value => <small key={value.name}>{value.name}: {value.status}</small>)}</td></tr>) : <tr><td colSpan={5} className="analysis-table-empty">No episodes recorded.</td></tr>}</tbody></table></div></Panel>}
    {tab === "Weakness memory" && <Panel title="Weakness memory"><div className="table-scroll"><table><thead><tr><th>Weakness</th><th>Category</th><th>Attempts</th><th>Fails</th><th>Recovery passes</th><th>Failure rate</th></tr></thead><tbody>{weaknesses.length ? weaknesses.map(value => <tr key={`${value.category}-${value.failure_type}`}><td><strong>{readable(value.failure_type)}</strong></td><td>{readable(value.category)}</td><td>{value.attempts}</td><td>{value.fails}</td><td>{value.passes}</td><td>{Math.round(value.failure_rate * 100)}%</td></tr>) : <tr><td colSpan={6} className="analysis-table-empty">No weakness records yet.</td></tr>}</tbody></table></div></Panel>}
  </div>;
}
