import { useEffect, useState } from "react";
import type { Episode, EvaluationMetrics, Run, Scorecard, Verification, Weakness } from "./api";
import { displayLabel as readable, runLabel, textParagraphs } from "./presentation";
import { behavioralTone, filledOrderFields } from "./analysis-data";
import Select from "./select";

type View = "Summary" | "Test details" | "Learning" | "Paper evidence";
type AnalysisProps = {
  runs: Run[]; runId: string | null; run: Run | null; episodes: Episode[];
  score: Scorecard | null; metrics: EvaluationMetrics | null; weaknesses: Weakness[];
  verification: Verification | null; onRunChange: (id: string) => void;
};
const categories = ["policy", "freshness", "sizing", "takeover", "execution", "consistency", "tool_discipline"] as const;
const weights = { policy: 20, freshness: 15, sizing: 15, takeover: 15, execution: 15, consistency: 10, tool_discipline: 10 };
const behaviors = [
  ["Acted without approval", "false_autonomy_rate"],
  ["Unnecessary escalation", "unnecessary_escalation_rate"],
  ["Correct human handovers", "takeover_accuracy"],
  ["Inconsistent decisions", "consistency_failure_rate"],
  ["Skipped tool checks", "tool_precondition_violation_count"],
  ["Duplicate actions", "duplicate_action_count"],
  ["Execution mismatches", "execution_mismatch_count"],
] as const;
function rate(value: number | null | undefined) { return value == null ? "Not measured" : `${Math.round(value * 100)}%`; }
function count(value: number | null | undefined) { return value == null ? "—" : String(value); }
function Payload({ value }: { value: unknown }) { return <pre className="analysis-payload">{JSON.stringify(value, null, 2)}</pre>; }
function Panel({ title, children }: { title: string; children: React.ReactNode }) { return <section className="analysis-panel panel"><div className="analysis-panel-heading"><h2>{title}</h2></div>{children}</section>; }
function Disclosure({ title, children }: { title: string; children: React.ReactNode }) { return <details className="report-disclosure"><summary>{title}</summary><div>{children}</div></details>; }

function TestDetail({ episode }: { episode: Episode }) {
  const critic = episode.critic;
  return <div className="test-detail" key={episode.id}>
    <div className="test-title"><span className={`result ${episode.result === "PASS" ? "pass" : "fail"}`}>{readable(episode.result)}</span><span>Test {episode.number} · difficulty {episode.difficulty}/5</span></div>
    <h2>{episode.scenario.title}</h2>
    <p className="test-description">{episode.scenario.description}</p>
    <div className="decision-snapshot"><span>Final decision</span><strong>{episode.decision?.action ?? "No decision"}{episode.decision?.symbol ? ` · ${episode.decision.symbol}` : ""}</strong>{episode.decision && <small>{episode.decision.notional ? `${episode.decision.notional} notional · ` : ""}{rate(episode.decision.confidence)} confidence</small>}</div>
    <Disclosure title="Target rationale"><p>{episode.decision?.reason || "Not declared"}</p></Disclosure>
    <Disclosure title={`Evidence available · ${episode.scenario.evidence.length}`}>
      {episode.scenario.evidence.map(item => <div className="report-evidence" key={item.evidence_id}><strong>{readable(item.kind)}</strong><p>{item.summary}</p><small>{item.observed_at} · {item.source_labels.join(", ")}</small></div>)}
      {!episode.scenario.evidence.length && <p>No evidence recorded.</p>}
    </Disclosure>
    <Disclosure title={`Tool trace · ${episode.target_trace.length} calls`}>
      {episode.target_trace.map(trace => <details className="report-disclosure" key={trace.sequence}><summary>{trace.sequence}. {trace.tool} · {trace.result_status} · {Math.round(trace.latency_ms)}ms</summary><Payload value={{ arguments: trace.arguments, result: trace.result, labels: trace.verification_labels }} /></details>)}
      {!episode.target_trace.length && <p>No tool calls recorded.</p>}
    </Disclosure>
    <section className="test-oracles"><h3>Deterministic oracle report</h3>{episode.oracle_results.map(oracle => <details key={oracle.name}><summary><span className={`oracle-dot ${oracle.status.toLowerCase()}`} /><span>{readable(oracle.category)}</span><strong>{readable(oracle.status)}</strong></summary><p>{readable(oracle.code)}</p><Payload value={oracle.details} /></details>)}</section>
    <section className="report-critic" aria-label="Qwen critic summary"><div className="critic-heading"><h3>Qwen critic summary</h3><span className="critic-source">{critic.labels.includes("LLM_CRITIQUE") ? "Qwen analysis" : "Fallback · Qwen unverified"}</span></div>
      <p className="critic-excerpt">{critic.diagnosis || "No summary recorded."}</p>
      <Disclosure title="Read full assessment"><div className="critic-reading"><h4>What happened</h4>{textParagraphs(critic.diagnosis).map((text, index) => <p key={index}>{text}</p>)}</div>{critic.trigger && <div className="critic-reading"><h4>Trigger</h4><p>{critic.trigger}</p></div>}{critic.mutation_direction && <div className="critic-reading"><h4>Suggested retest</h4><p>{critic.mutation_direction}</p></div>}<small>Qualitative analysis. Oracle verdicts remain authoritative.</small><dl><dt>Model</dt><dd>{critic.model}</dd><dt>Prompt</dt><dd>{critic.prompt_name}:{critic.prompt_version}</dd><dt>Finding</dt><dd>{readable(critic.failure_class)}</dd></dl></Disclosure>
    </section>
  </div>;
}

export default function Analysis({ runs, runId, run, episodes, score, metrics, weaknesses, verification, onRunChange }: AnalysisProps) {
  const [view, setView] = useState<View>("Summary");
  const [episodeId, setEpisodeId] = useState("");
  const selected = episodes.find(episode => episode.id === episodeId) ?? episodes.find(episode => episode.result === "FAIL") ?? episodes.at(-1);
  const views: View[] = ["Summary", "Test details", "Learning", ...(run?.mode === "BITGET_PAPER" ? ["Paper evidence" as const] : [])];
  useEffect(() => { setView("Summary"); setEpisodeId(""); }, [runId]);
  function inspect(episode: Episode) { setEpisodeId(episode.id); setView("Test details"); }
  return <div className="analysis-page analysis-report">
    <section className="page-heading analysis-heading"><div><h1>Analysis</h1><p>How your agent performed across safety tests.</p></div><label className="analysis-run-selector"><span>Evaluation</span><Select ariaLabel="Select evaluation run" value={runId ?? ""} onChange={onRunChange} options={[{ value: "", label: "Select evaluation", disabled: true }, ...runs.map(item => ({ value: item.id, label: runLabel(item) }))]} /></label></section>
    {!run ? <div className="analysis-empty-inline">Select an evaluation to see its results.</div> : <>
      <div className="report-context"><strong>{run.target_name || readable(run.target_id)}</strong><span>{readable(run.mode)}</span><span className={`analysis-status ${run.status.toLowerCase()}`}><i />{readable(run.status)}</span><span>v{run.target_version}</span></div>
      <nav className="analysis-tabs" aria-label="Analysis views">{views.map(tab => <button key={tab} aria-current={view === tab ? "page" : undefined} onClick={() => setView(tab)}>{tab}</button>)}</nav>
      {view === "Summary" && <div className="report-summary">
        <section className="report-outcome panel" aria-label="Evaluation summary"><div className="readiness-result"><span>Readiness</span><strong>{score ? score.score : "—"}<small>/100</small></strong><span>{score ? readable(score.label) : "Awaiting results"}</span><small>{score ? `${rate(score.coverage_pct)} of check weight measured` : "No measured checks"}</small></div><div className="report-results"><div className="report-numbers"><div><span>Tests passed</span><strong>{rate(metrics?.pass_rate)}</strong></div><div><span>Risk violations</span><strong className={metrics?.risk_violation_count ? "warn" : ""}>{count(metrics?.risk_violation_count)}</strong><small>{rate(metrics?.risk_violation_rate)} of tests</small></div><div><span>Difficulty</span><strong>{count(metrics?.difficulty_reached)}<small>/5</small></strong></div></div><div className="episode-map-heading"><h2>Test results</h2><span>{episodes.length} recorded</span></div><div className="episode-map">{episodes.map(episode => <button key={episode.id} className={episode.result === "PASS" ? "passed" : episode.result === "FAIL" ? "failed" : "unknown"} onClick={() => inspect(episode)} aria-label={`Open test ${episode.number}: ${episode.scenario.title}, ${readable(episode.result)}`} title={episode.scenario.title}><strong>{String(episode.number).padStart(2, "0")}</strong><span>{readable(episode.result)}</span></button>)}{!episodes.length && <span>No completed tests yet.</span>}</div></div></section>
        <div className="report-columns"><Panel title="Safety checks"><div className="check-chart"><div className="chart-caption"><span>Deterministic oracles</span><span>Passed / tested</span></div>{categories.map(category => { const measured = score?.measured[category]; const percentage = measured?.total ? Math.round(measured.pass / measured.total * 100) : 0; return <div className="check-row" key={category}><span>{readable(category)}</span><div className="check-track" role="progressbar" aria-label={readable(category)} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percentage} aria-valuetext={measured?.total ? `${measured.pass} of ${measured.total} passed` : "Not tested"}><i style={{ width: `${percentage}%` }} /></div><strong>{measured?.total ? `${measured.pass}/${measured.total}` : "Not tested"}</strong></div>; })}<Disclosure title="Score breakdown"><div className="score-breakdown">{categories.map(category => <div key={category}><span>{readable(category)}</span><strong>{score?.breakdown[category] ?? 0}/{weights[category]} points</strong></div>)}</div></Disclosure></div></Panel>
        <Panel title="Behavioral performance"><div className="behavior-report">{behaviors.map(([label, key]) => <div key={key}><span>{label}</span><strong className={behavioralTone(key, metrics?.[key])}>{key.endsWith("_rate") || key === "takeover_accuracy" ? rate(metrics?.[key]) : count(metrics?.[key])}</strong></div>)}</div></Panel></div>
        <section className="report-next panel"><div><span>Recurring weakness</span><strong>{metrics?.primary_recurring_weakness ? readable(metrics.primary_recurring_weakness) : metrics ? "None recorded" : "Awaiting results"}</strong></div><button onClick={() => setView("Learning")}>Review retests <span aria-hidden="true">→</span></button></section>
      </div>}
      {view === "Test details" && <section className="test-workspace panel"><aside className="test-index"><h2>Decision trace</h2><div>{episodes.map(episode => <button key={episode.id} aria-pressed={selected?.id === episode.id} onClick={() => setEpisodeId(episode.id)}><span className={`oracle-dot ${episode.result.toLowerCase()}`} /><span><strong>Test {episode.number}</strong><small>{readable(episode.category)}</small></span><span>{readable(episode.result)}</span></button>)}</div></aside>{selected ? <TestDetail episode={selected} /> : <p className="analysis-empty-inline">No test results recorded.</p>}</section>}
      {view === "Learning" && <Panel title="Adaptive learning"><div className="learning-summary"><div><span>Targeted mutations</span><strong>{count(metrics?.targeted_mutations)}</strong></div><div><span>Retests passed</span><strong>{count(metrics?.mutation_retest_passes)}</strong></div><div><span>Retests failed</span><strong>{count(metrics?.mutation_retest_failures)}</strong></div></div><div className="table-scroll"><table><thead><tr><th>Weakness memory</th><th>Test category</th><th>Attempts</th><th>Failures</th><th>Recovery passes</th><th>Failure rate</th></tr></thead><tbody>{weaknesses.map(item => <tr key={`${item.category}-${item.failure_type}`}><td>{readable(item.failure_type)}</td><td>{readable(item.category)}</td><td>{item.attempts}</td><td>{item.fails}</td><td>{item.passes}</td><td>{rate(item.failure_rate)}</td></tr>)}{!weaknesses.length && <tr><td colSpan={6}>No weaknesses recorded.</td></tr>}</tbody></table></div><div className="mutation-retests"><h3>Targeted retests</h3>{episodes.filter(episode => episode.scenario.mutation_reason).map(episode => <button key={episode.id} onClick={() => inspect(episode)}><span>Test {episode.number} · {readable(episode.scenario.mutation_reason!)}</span><strong>{readable(episode.result)}</strong></button>)}{!episodes.some(episode => episode.scenario.mutation_reason) && <p>No targeted retests recorded.</p>}</div></Panel>}
      {view === "Paper evidence" && run.mode === "BITGET_PAPER" && <Panel title="Bitget paper evidence"><div className="learning-summary"><div><span>Paper trades</span><strong>{count(metrics?.paper_trade_count)}</strong></div><div><span>Acceptance</span><strong>{verification?.status ?? "UNVERIFIED"}</strong></div><div><span>Financial metrics</span><strong>{metrics?.paper_metrics_status ?? "UNAVAILABLE"}</strong></div></div><div className="paper-report"><Disclosure title="Verification checks">{Object.entries(verification?.evidence ?? {}).map(([key, value]) => <div className="score-breakdown" key={key}><span>{readable(key)} · {value ? "Verified" : "Unverified"}</span></div>)}{verification?.blocking_reasons.map(reason => <p key={reason}>{readable(reason)}</p>)}</Disclosure><Disclosure title="Filled order evidence">{episodes.flatMap(episode => episode.target_trace.filter(trace => trace.tool === "paper_order")).length ? episodes.flatMap(episode => episode.target_trace.filter(trace => trace.tool === "paper_order")).map((trace, index) => { const fields = filledOrderFields(trace); return fields ? <Payload key={index} value={fields} /> : <p key={index}>UNVERIFIED</p>; }) : <p>UNAVAILABLE</p>}</Disclosure><Disclosure title="Financial performance"><div className="financial-grid">{(["win_rate", "pnl", "return_pct", "sharpe", "sortino", "max_drawdown", "turnover", "fees", "slippage"] as const).map(key => <div key={key}><span>{readable(key)}</span><strong>{metrics?.[key] == null ? "UNAVAILABLE" : String(metrics[key])}</strong></div>)}</div></Disclosure></div></Panel>}
    </>}
  </div>;
}
