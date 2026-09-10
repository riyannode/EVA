const base = import.meta.env?.VITE_API_URL || "http://localhost:8000";

export type Run = {
  id: string;
  target_id: string;
  target_name: string | null;
  target_model: string | null;
  target_version: string;
  mode: "SYNTHETIC" | "BITGET_PAPER";
  status: "CREATED" | "RUNNING" | "COMPLETED" | "STOPPED" | "FAILED";
  difficulty: number;
  max_episodes: number;
  episode: number;
  current_category: string | null;
  current_stage: string;
  last_failure: string | null;
};

export type RunInput = Pick<Run, "target_id" | "target_version" | "mode" | "max_episodes" | "difficulty"> & {
  target_url?: string;
  target_name?: string;
  target_model?: string;
  target_token?: string;
};

export type Episode = {
  id: string;
  number: number;
  category: string;
  difficulty: number;
  scenario: { title: string; source_labels: string[] };
  decision: { action: string; symbol?: string; notional?: string } | null;
  oracle_results: { name: string; category: string; status: string; code: string }[];
  failure_type: string | null;
  result: string;
};

export type Scorecard = {
  score: number;
  label: string;
  breakdown: Record<string, number>;
  coverage_pct: number;
  measured_weight: number;
  possible_weight: number;
  primary_weakness: string | null;
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
};

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
export const getWeaknesses = (id: string) => request<Weakness[]>(`/runs/${encodeURIComponent(id)}/weaknesses`);
export const getVerification = (id: string) => request<Verification>(`/runs/${encodeURIComponent(id)}/verification`);
export const stopRun = (id: string) => request<Run>(`/runs/${encodeURIComponent(id)}/stop`, { method: "POST" });
export const eventUrl = (id: string) => `${base}/runs/${encodeURIComponent(id)}/events`;
