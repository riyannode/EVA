const base = import.meta.env?.VITE_API_URL || "http://localhost:8000";

export type Run = {
  id: string;
  agent_id: string | null;
  execution_provider: string | null;
  evidence_root: string | null;
  target_id: string;
  target_name: string | null;
  target_model: string | null;
  target_version: string;
  mode: "SYNTHETIC" | "PAPER" | "BITGET_PAPER";
  status: "CREATED" | "RUNNING" | "COMPLETED" | "STOPPED" | "FAILED";
  difficulty: number;
  max_episodes: number;
  episode: number;
  current_category: string | null;
  current_stage: string;
  last_failure: string | null;
};

export type RunInput = Pick<Run, "target_id" | "target_version" | "mode" | "max_episodes" | "difficulty"> & {
  agent_id?: string;
  execution_provider?: string;
  target_url?: string;
  target_name?: string;
  target_model?: string;
  target_token?: string;
};

export type EvidenceRecord = {
  evidence_id: string;
  kind: string;
  summary: string;
  observed_at: string;
  source_labels: string[];
  authoritative: boolean;
};

export type TraceRecord = {
  sequence: number;
  tool: string;
  arguments: Record<string, unknown>;
  timestamp: string;
  result_status: string;
  result: Record<string, unknown>;
  latency_ms: number;
  verification_labels: string[];
};

export type DecisionRecord = {
  action: string;
  symbol?: string;
  notional?: string;
  confidence: number;
  reason: string;
  evidence_used: string[];
};

export type OracleRecord = { name: string; category: string; status: string; code: string; details: string; labels: string[] };

export type CriticRecord = {
  diagnosis: string;
  failure_class: string;
  trigger: string;
  mutation_direction: string;
  model: string;
  prompt_name: string;
  prompt_version: string;
  labels: string[];
};

export type Episode = {
  id: string;
  number: number;
  category: string;
  difficulty: number;
  scenario: { scenario_id: string; title: string; description: string; category: string; difficulty: number; source_labels: string[]; evidence: EvidenceRecord[]; mutation_reason?: string | null };
  target_trace: TraceRecord[];
  decision: DecisionRecord | null;
  oracle_results: OracleRecord[];
  critic: CriticRecord;
  failure_type: string | null;
  result: string;
};

export type Scorecard = {
  score: number;
  label: string;
  breakdown: Record<string, number>;
  measured: Record<string, { pass: number; total: number }>;
  coverage_pct: number;
  measured_weight: number;
  possible_weight: number;
  primary_weakness: string | null;
};

export type EvaluationMetrics = {
  total_scenarios: number;
  total_episodes: number;
  pass_rate: number;
  failure_rate: number;
  risk_violation_count: number;
  risk_violation_rate: number;
  false_autonomy_count: number;
  false_autonomy_rate: number;
  unnecessary_escalation_count: number;
  unnecessary_escalation_rate: number;
  takeover_required_count: number;
  takeover_success_count: number;
  takeover_accuracy: number | null;
  consistency_failure_count: number;
  consistency_failure_rate: number;
  tool_precondition_violation_count: number;
  duplicate_action_count: number;
  execution_mismatch_count: number;
  primary_recurring_weakness: string | null;
  difficulty_reached: number;
  targeted_mutations: number;
  mutation_retest_passes: number;
  mutation_retest_failures: number;
  paper_trade_count: number;
  paper_metrics_status: "UNAVAILABLE" | "UNVERIFIED";
  win_rate: number | null;
  pnl: number | null;
  return_pct: number | null;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown: number | null;
  turnover: number | null;
  fees: number | null;
  slippage: number | null;
};

export type Weakness = {
  failure_type: string;
  category: string;
  attempts: number;
  fails: number;
  passes: number;
  failure_rate: number;
};

export type GraphEvent = {
  id: number;
  run_id: string;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type Verification = {
  status: "NOT_APPLICABLE" | "UNVERIFIED" | "READY";
  official_track2_ready: boolean;
  blocking_reasons: string[];
  evidence?: Record<string, boolean>;
  target_identity?: Record<string, string | null>;
};

export type Agent = {
  agent_id: string;
  owner_id: string;
  name: string;
  version: string;
  declared_model: string;
  framework: string | null;
  created_at: string;
  last_seen_at: string | null;
  status: "OFFLINE" | "CONNECTING" | "ONLINE" | "EVALUATING" | "DEGRADED" | "DISABLED";
  capability_state: "REGISTERED" | "SYNTHETIC_READY" | "PAPER_ELIGIBLE";
  protocol_version: string;
  capabilities: string[];
  execution_providers: string[];
  provider_capabilities: Record<string, string[]>;
  evaluation_count: number;
  latest_readiness: string | null;
  latest_evaluation_id: string | null;
};

export type AgentRegistration = { agent: Agent; key: { key_id: string; agent_id: string; created_at: string; revoked_at: string | null; last_used_at: string | null }; api_key: string };
export type Onboarding = { agent_id: string; protocol: string; gateway_path: string; evaluation: { synthetic: string; paper: string; execution_provider: string; provider_capabilities: string[] }; methods: { id: string; name: string; command: string }[]; prompt: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(15000),
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw new Error(`HTTP_${response.status}`);
  return response.json() as Promise<T>;
}

export const createRun = (input: RunInput) => request<Run>("/runs", { method: "POST", body: JSON.stringify(input) });
export const getRuns = () => request<Run[]>("/runs");
export const getRun = (id: string) => request<Run>(`/runs/${encodeURIComponent(id)}`);
export const getEpisodes = (id: string) => request<Episode[]>(`/runs/${encodeURIComponent(id)}/episodes`);
export const getScore = (id: string) => request<Scorecard>(`/runs/${encodeURIComponent(id)}/score`);
export const getMetrics = (id: string) => request<EvaluationMetrics>(`/runs/${encodeURIComponent(id)}/metrics`);
export const getWeaknesses = (id: string) => request<Weakness[]>(`/runs/${encodeURIComponent(id)}/weaknesses`);
export const getVerification = (id: string) => request<Verification>(`/runs/${encodeURIComponent(id)}/verification`);
export const stopRun = (id: string) => request<Run>(`/runs/${encodeURIComponent(id)}/stop`, { method: "POST" });
export const eventUrl = (id: string) => `${base}/runs/${encodeURIComponent(id)}/events`;
export const registerAgent = (input: { name: string; version: string; declared_model: string; framework?: string; execution_providers?: string[] }, controlToken: string) => request<AgentRegistration>("/v1/agents", { method: "POST", headers: { Authorization: `Bearer ${controlToken}` }, body: JSON.stringify(input) });
export const getAgent = (id: string, apiKey: string) => request<Agent>(`/v1/agents/${encodeURIComponent(id)}`, { headers: { Authorization: `Bearer ${apiKey}` } });
export const getOnboarding = (id: string, apiKey: string) => request<Onboarding>(`/v1/agents/${encodeURIComponent(id)}/onboarding`, { headers: { Authorization: `Bearer ${apiKey}` } });
export const createEvaluation = (input: { agent_id: string; target_id: "GATEWAY"; mode: "SYNTHETIC" | "PAPER" | "BITGET_PAPER"; execution_provider?: string; max_episodes: number; difficulty: number }, apiKey: string) => request<Run>("/v1/evaluations", { method: "POST", headers: { Authorization: `Bearer ${apiKey}` }, body: JSON.stringify(input) });
