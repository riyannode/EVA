import { useEffect, useRef, useState, type FormEvent } from "react";
import { completePairing, createEvaluation, createPairingRequest, getAgent, getOnboarding, getPairingRequest, type Agent, type AgentRegistration, type Onboarding, type PairingRequest, type Run } from "./api";

type AgentsProps = { onEvaluationCreated: (run: Run) => void };

export default function Agents({ onEvaluationCreated }: AgentsProps) {
  const [draft, setDraft] = useState({ name: "", version: "1.0.0", declared_model: "", framework: "", execution_providers: "" });
  const [pairing, setPairing] = useState<PairingRequest | null>(null);
  const [registration, setRegistration] = useState<AgentRegistration | null>(null);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [onboarding, setOnboarding] = useState<Onboarding | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refreshRequested, setRefreshRequested] = useState(0);
  const completing = useRef(false);

  useEffect(() => {
    if (!pairing || registration || pairing.status !== "PENDING") return;
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
  }, [pairing, registration, refreshRequested]);

  useEffect(() => {
    if (!registration) return;
    let disposed = false;
    const refresh = async () => {
      try {
        const value = await getAgent(registration.agent.agent_id, registration.api_key);
        if (!disposed) setAgent(value);
      } catch {
        if (!disposed) setAgent(previous => previous ?? registration.agent);
      }
    };
    void refresh();
    const timer = setInterval(refresh, 3000);
    return () => { disposed = true; clearInterval(timer); };
  }, [registration]);

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
  }

  const prompt = pairing ? `Connect my existing trading agent to EVA.\n\nPairing request: ${pairing.request_id}\n\nUse the EVA CLI or SDK. Check pairing status. After approval, store the returned agent credential in the runtime environment. Connect outbound using eva-agent/1. Run the non-financial connection test. Stop before PAPER evaluation.` : "";
  return <div className="agents-page" aria-labelledby="agents-title">
    <section className="page-heading">
      <div><div className="breadcrumb">Workspace <span>/</span> Agents</div><h1 id="agents-title">Connect an external agent.</h1><p>Pair an existing agent, connect it outbound, and start with a zero-write synthetic evaluation.</p></div>
      {pairing && <button className="button" onClick={reset}>New pairing</button>}
    </section>
    {error && <p className="error" role="alert">{error}</p>}
    {!pairing && <section className="panel agents-card"><h2>Connect External Agent</h2><form onSubmit={create}>
      <label>Agent name<input required maxLength={100} value={draft.name} onChange={event => setDraft(previous => ({ ...previous, name: event.target.value }))} /></label>
      <div className="form-grid"><label>Version<input required maxLength={40} value={draft.version} onChange={event => setDraft(previous => ({ ...previous, version: event.target.value }))} /></label><label>Declared model<input required maxLength={100} value={draft.declared_model} onChange={event => setDraft(previous => ({ ...previous, declared_model: event.target.value }))} /></label></div>
      <label>Framework / runtime <small>optional</small><input maxLength={100} value={draft.framework} onChange={event => setDraft(previous => ({ ...previous, framework: event.target.value }))} /></label>
      <label>Trading venues / providers <small>optional · comma-separated</small><input maxLength={300} value={draft.execution_providers} onChange={event => setDraft(previous => ({ ...previous, execution_providers: event.target.value }))} placeholder="Bitget, Binance, or exchange-agnostic" /></label>
      <p className="form-note">Provider metadata describes the agent only. It does not grant execution access. Synthetic evaluation is available without a venue.</p>
      <button className="button primary submit-button" disabled={busy}>{busy ? "Creating request…" : "Create pairing request"}</button>
    </form></section>}
    {pairing && !registration && <section className="panel agents-card"><h2>Waiting for approval</h2><div className="agent-status-card"><span>Request</span><code>{pairing.request_id}</code><span>Status</span><strong>{pairing.status}</strong><span>Expires</span><time dateTime={pairing.expires_at}>{new Date(pairing.expires_at).toLocaleString("en-GB")}</time></div><label>Approval URL<input readOnly value={pairing.approval_url} /></label><div className="button-row"><button className="button" onClick={() => copy(pairing.approval_url)}>Copy URL</button><button className="button" onClick={() => copy(prompt)}>Copy AI Agent Prompt</button><button className="button" onClick={() => setRefreshRequested(value => value + 1)}>Refresh Status</button></div><label>AI Agent Prompt<textarea readOnly value={prompt} /></label><p className="form-note">An operator approves this request through the admin path. No agent privilege or credential exists while status is PENDING.</p></section>}
    {registration && <section className="panel agents-card"><h2>Agent Connected</h2><div className="agent-status-card"><span>Agent</span><strong>{agent?.name ?? registration.agent.name}</strong><span>Connection</span><strong>{agent?.status ?? "OFFLINE"}</strong><span>Protocol</span><strong>{onboarding?.protocol ?? registration.agent.protocol_version}</strong><span>Synthetic</span><strong>{onboarding?.evaluation.synthetic ?? "READY"}</strong><span>Paper</span><strong>{onboarding?.evaluation.paper ?? "NOT_SUPPORTED"}</strong><span>Execution provider</span><strong>{onboarding?.evaluation.execution_provider ?? "None"}</strong></div><label>One-time agent credential<small>copy now; it is not shown again</small><textarea readOnly value={registration.api_key} /></label>{onboarding && <><label>AI Agent Prompt<textarea readOnly value={onboarding.prompt} /></label><div className="integration-methods">{onboarding.methods.map(method => <div key={method.id}><strong>{method.name}</strong><code>{method.command}</code></div>)}</div></>}<button className="button primary submit-button" disabled={busy || agent?.status !== "ONLINE"} onClick={() => void startEvaluation()}>{busy ? "Starting…" : "Start Synthetic Evaluation"}</button></section>}
  </div>;
}
