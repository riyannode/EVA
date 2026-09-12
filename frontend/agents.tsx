import { useEffect, useRef, useState, type FormEvent } from "react";
import { completePairing, createEvaluation, createPairingRequest, getAgent, getAgentCatalog, getOnboarding, getPairingRequest, type Agent, type AgentCatalogEntry, type AgentRegistration, type Onboarding, type PairingRequest, type Run } from "./api";

export type AgentSummary = { agent: Agent; onboarding: Onboarding | null };
type AgentsProps = { onEvaluationCreated: (run: Run) => void; onAgentStateChange: (value: AgentSummary | null) => void };
type AgentMode = "catalog" | "connect";
type CatalogState = "loading" | "loaded" | "empty" | "error";

function providerLabel(value: string) {
  return value.length ? `${value.slice(0, 1).toUpperCase()}${value.slice(1)}` : value;
}

function ConnectionStatus({ status }: { status: AgentCatalogEntry["status"] }) {
  return <span className={`catalog-status ${status.toLowerCase()}`}><i aria-hidden="true" />{status}</span>;
}

function CatalogAgentCard({ entry }: { entry: AgentCatalogEntry }) {
  const titleId = `catalog-agent-${entry.agent_id}`;
  return <article className="catalog-agent-card" aria-labelledby={titleId}>
    <header className="catalog-agent-header">
      <div className="catalog-agent-title"><span className="catalog-agent-marker" aria-hidden="true" /><h2 id={titleId}>{entry.name}</h2></div>
      <div className="catalog-connection"><span>Connection</span><ConnectionStatus status={entry.status} /></div>
    </header>
    <div className="catalog-identity">
      <strong>{entry.declared_model}</strong>
      <span>v{entry.version}{entry.framework ? <><span aria-hidden="true"> · </span><span className="catalog-framework">{entry.framework}</span></> : null}</span>
    </div>
    <div className="catalog-state-grid" aria-label={`${entry.name} state`}>
      <div><span>Connection</span><strong className={`catalog-state-value ${entry.status.toLowerCase()}`}>{entry.status}</strong></div>
      <div><span>Readiness</span><strong className={`catalog-state-value ${entry.capability_state.toLowerCase()}`}>{entry.capability_state}</strong></div>
    </div>
    <dl className="catalog-facts">
      <div><dt>Provider</dt><dd>{entry.execution_providers.length ? entry.execution_providers.map(providerLabel).join(", ") : "None declared"}</dd></div>
      <div><dt>Protocol</dt><dd>{entry.protocol_version}</dd></div>
      <div><dt>Evaluations</dt><dd>{entry.evaluation_count} {entry.evaluation_count === 1 ? "evaluation" : "evaluations"}</dd></div>
    </dl>
    <div className="catalog-capabilities" aria-label={`${entry.name} capabilities`}>
      <span className="catalog-field-label">Capabilities</span>
      {entry.capabilities.length ? <div className="catalog-capability-list">{entry.capabilities.map(capability => <span className="catalog-capability" key={capability}>{capability}</span>)}</div> : <span className="catalog-none">None declared</span>}
    </div>
  </article>;
}

function CatalogSkeleton() {
  return <div className="catalog-grid" role="status" aria-label="Loading agent catalog" aria-busy="true">
    <article className="catalog-agent-card catalog-skeleton" aria-hidden="true"><div /><div /><div /><div /></article>
  </div>;
}

function AgentCatalog({ agents, state, onRetry, onConnect, onRefresh }: { agents: AgentCatalogEntry[]; state: CatalogState; onRetry: () => void; onConnect: () => void; onRefresh: () => void }) {
  return <>
    <div className="catalog-toolbar">
      <div className="catalog-count"><span>Published agents</span><strong>{agents.length}</strong></div>
      <p>Agents that opted into the EVA catalog. Inspect their connection state and evaluation readiness.</p>
      <button type="button" className="catalog-refresh" onClick={onRefresh} disabled={state === "loading"}>Refresh</button>
    </div>
    {state === "loading" && <CatalogSkeleton />}
    {state === "error" && <div className="catalog-inline-error" role="alert"><div><strong>Agent catalog unavailable.</strong><span>Check the API connection and try again.</span></div><button type="button" className="button" onClick={onRetry}>Retry</button></div>}
    {state === "empty" && <section className="catalog-empty" aria-labelledby="catalog-empty-title"><span className="catalog-empty-mark" aria-hidden="true"><i /><i /><i /></span><h2 id="catalog-empty-title">NO PUBLISHED AGENTS</h2><p>Agents appear here after pairing and explicit catalog publication.</p><button type="button" className="button primary" onClick={onConnect}>Connect agent</button></section>}
    {(state === "loaded" || (state === "error" && agents.length > 0)) && <div className="catalog-grid">{agents.map(entry => <CatalogAgentCard entry={entry} key={entry.agent_id} />)}</div>}
  </>;
}

export default function Agents({ onEvaluationCreated, onAgentStateChange }: AgentsProps) {
  const [mode, setMode] = useState<AgentMode>("catalog");
  const [catalog, setCatalog] = useState<AgentCatalogEntry[]>([]);
  const [catalogState, setCatalogState] = useState<CatalogState>("loading");
  const [catalogRetry, setCatalogRetry] = useState(0);
  const [draft, setDraft] = useState({ name: "", version: "1.0.0", declared_model: "", framework: "", execution_providers: "" });
  const [pairing, setPairing] = useState<PairingRequest | null>(null);
  const [registration, setRegistration] = useState<AgentRegistration | null>(null);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [onboarding, setOnboarding] = useState<Onboarding | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pairingRefreshRequested, setPairingRefreshRequested] = useState(0);
  const completing = useRef(false);

  useEffect(() => {
    onAgentStateChange(agent && registration ? { agent, onboarding } : null);
  }, [agent, onboarding, registration, onAgentStateChange]);

  useEffect(() => {
    if (mode !== "catalog") return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const entries = await getAgentCatalog();
        if (disposed) return;
        setCatalog(entries);
        setCatalogState(entries.length ? "loaded" : "empty");
      } catch {
        if (!disposed) setCatalogState("error");
      } finally {
        if (!disposed) timer = setTimeout(load, 5000);
      }
    };
    void load();
    return () => { disposed = true; if (timer) clearTimeout(timer); };
  }, [mode, catalogRetry]);

  useEffect(() => {
    if (mode !== "connect" || !pairing || registration || pairing.status !== "PENDING") return;
    let disposed = false;
    const refresh = async () => {
      try {
        const value = await getPairingRequest(pairing.request_id);
        if (disposed) return;
        setPairing(value);
        if (value.status === "APPROVED" && !completing.current) {
          completing.current = true;
          const exchanged = await completePairing(value.request_id);
          if (disposed) return;
          setRegistration(exchanged);
          setAgent(exchanged.agent);
          setOnboarding(await getOnboarding(exchanged.agent.agent_id, exchanged.api_key));
        }
      } catch {
        if (!disposed) setError("Pairing status could not be refreshed.");
      }
    };
    void refresh();
    const timer = setInterval(refresh, 3000);
    return () => { disposed = true; clearInterval(timer); };
  }, [mode, pairing, registration, pairingRefreshRequested]);

  useEffect(() => {
    if (mode !== "connect" || !registration) return;
    let disposed = false;
    const refresh = async () => {
      try {
        const value = await getAgent(registration.agent.agent_id, registration.api_key);
        if (!disposed) setAgent(value);
        try {
          const currentOnboarding = await getOnboarding(registration.agent.agent_id, registration.api_key);
          if (!disposed) setOnboarding(currentOnboarding);
        } catch {}
      } catch {
        if (!disposed) setAgent(previous => previous ?? registration.agent);
      }
    };
    void refresh();
    const timer = setInterval(refresh, 3000);
    return () => { disposed = true; clearInterval(timer); };
  }, [mode, registration]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const value = await createPairingRequest({ ...draft, framework: draft.framework || undefined, execution_providers: draft.execution_providers.split(",").map(item => item.trim().toLowerCase()).filter(Boolean) });
      setPairing(value);
    } catch {
      setError("Pairing request could not be created.");
    } finally {
      setBusy(false);
    }
  }

  async function startEvaluation() {
    if (!registration || agent?.status !== "ONLINE" || busy) return;
    setBusy(true);
    setError("");
    try {
      const run = await createEvaluation({ agent_id: registration.agent.agent_id, target_id: "GATEWAY", mode: "SYNTHETIC", max_episodes: 20, difficulty: 1 }, registration.api_key);
      onEvaluationCreated(run);
    } catch {
      setError("Synthetic evaluation requires an ONLINE agent.");
    } finally {
      setBusy(false);
    }
  }

  function copy(value: string) {
    void navigator.clipboard?.writeText(value);
  }

  function reset() {
    setPairing(null);
    setRegistration(null);
    setAgent(null);
    setOnboarding(null);
    setError("");
    completing.current = false;
    onAgentStateChange(null);
  }

  function refreshCatalog() {
    setCatalogState(catalog.length ? "loaded" : "loading");
    setCatalogRetry(value => value + 1);
  }

  const prompt = pairing ? `Connect my existing trading agent to EVA.\n\nPairing request: ${pairing.request_id}\n\nUse the EVA CLI or SDK. Check pairing status. After approval, store the returned agent credential in the runtime environment. Connect outbound using eva-agent/1. Run the non-financial connection test. Stop before PAPER evaluation.` : "";
  return <div className="agents-page" aria-labelledby="agents-title">
    <section className="page-heading agents-heading">
      <div><div className="breadcrumb">Workspace <span>/</span> Agents{mode === "connect" && <><span>/</span> Connect</>}</div><h1 id="agents-title">{mode === "catalog" ? "Agent catalog" : "Connect an external agent."}</h1><p>{mode === "catalog" ? "Agents that opted into the EVA catalog. Inspect their connection state and evaluation readiness." : "Pair an existing agent, connect it outbound, and start with a zero-write synthetic evaluation."}</p></div>
      <div className="heading-actions">{mode === "catalog" ? <button type="button" className="button primary" onClick={() => setMode("connect")}><span aria-hidden="true">+</span> Connect agent</button> : <button type="button" className="button back-button" onClick={() => setMode("catalog")}><span aria-hidden="true">←</span> Back to agents</button>}</div>
    </section>
    {mode === "catalog" ? <AgentCatalog agents={catalog} state={catalogState} onRetry={refreshCatalog} onConnect={() => setMode("connect")} onRefresh={refreshCatalog} /> : <>
    {error && <p className="error" role="alert">{error}</p>}
    {pairing && <div className="connect-toolbar"><span>Pairing flow</span><button type="button" className="button" onClick={reset}>New pairing</button></div>}
    {!pairing && <section className="panel agents-card"><h2>Connect External Agent</h2><form onSubmit={create}>
      <label>Agent name<input required maxLength={100} value={draft.name} onChange={event => setDraft(previous => ({ ...previous, name: event.target.value }))} /></label>
      <div className="form-grid"><label>Version<input required maxLength={40} value={draft.version} onChange={event => setDraft(previous => ({ ...previous, version: event.target.value }))} /></label><label>Declared model<input required maxLength={100} value={draft.declared_model} onChange={event => setDraft(previous => ({ ...previous, declared_model: event.target.value }))} /></label></div>
      <label>Framework / runtime <small>optional</small><input maxLength={100} value={draft.framework} onChange={event => setDraft(previous => ({ ...previous, framework: event.target.value }))} /></label>
      <label>Trading venues / providers <small>optional · comma-separated</small><input maxLength={300} value={draft.execution_providers} onChange={event => setDraft(previous => ({ ...previous, execution_providers: event.target.value }))} placeholder="Bitget, Binance, or exchange-agnostic" /></label>
      <p className="form-note">Provider info only describes the agent. It doesn’t allow execution. Synthetic evaluation works without a venue.</p>
      <button className="button primary submit-button" disabled={busy}>{busy ? "Creating request…" : "Create pairing request"}</button>
    </form></section>}
    {pairing && !registration && <section className="panel agents-card"><h2>Waiting for approval</h2><div className="agent-status-card"><span>Request</span><code>{pairing.request_id}</code><span>Status</span><strong>{pairing.status}</strong><span>Expires</span><time dateTime={pairing.expires_at}>{new Date(pairing.expires_at).toLocaleString("en-GB")}</time></div><label>Approval URL<input readOnly value={pairing.approval_url} /></label><div className="button-row"><button className="button" onClick={() => copy(pairing.approval_url)}>Copy URL</button><button className="button" onClick={() => copy(prompt)}>Copy AI Agent Prompt</button><button className="button" onClick={() => setPairingRefreshRequested(value => value + 1)}>Refresh Status</button></div><label>AI Agent Prompt<textarea readOnly value={prompt} /></label><p className="form-note">An operator approves this request through the admin path. No agent privilege or credential exists while status is PENDING.</p></section>}
    {registration && <section className="panel agents-card"><h2>Agent Connected</h2><div className="agent-status-card"><span>Agent</span><strong>{agent?.name ?? registration.agent.name}</strong><span>Connection</span><strong>{agent?.status ?? "OFFLINE"}</strong><span>Protocol</span><strong>{onboarding?.protocol ?? registration.agent.protocol_version}</strong><span>Synthetic</span><strong>{onboarding?.evaluation.synthetic ?? "READY"}</strong><span>Paper</span><strong>{agent?.capability_state !== "PAPER_ELIGIBLE" ? "LOCKED" : onboarding?.evaluation.paper ?? "NOT_SUPPORTED"}</strong><span>Execution provider</span><strong>{onboarding?.evaluation.execution_provider ?? "None"}</strong></div><label>One-time agent credential<small>copy now; it is not shown again</small><textarea readOnly value={registration.api_key} /></label>{onboarding && <><label>AI Agent Prompt<textarea readOnly value={onboarding.prompt} /></label><div className="integration-methods">{onboarding.methods.map(method => <div key={method.id}><strong>{method.name}</strong><code>{method.command}</code></div>)}</div></>}<button className="button primary submit-button" disabled={busy || agent?.status !== "ONLINE"} onClick={() => void startEvaluation()}>{busy ? "Starting…" : "Start Synthetic Evaluation"}</button></section>}
  </>}
  </div>;
}
