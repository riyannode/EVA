const base = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type Run = {
  id: string;
  target_id: string;
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
  breakdown: { policy: number; freshness: number; sizing: number; takeover: number; execution: number; consistency: number; tool_discipline: number };
  primary_weakness: string | null;
};

export type Weakness = {
  failure_type: string;
  category: string;
  attempts: number;
  fails: number;
  passes: number;
  failure_rate: number;
  updated_at: string;
};

export type TradingStatus = {
  mode: string;
  live_trading_enabled: boolean;
  market_reads: boolean;
  paper_orders: boolean;
  live_orders: boolean;
};

export type LiveOrder = {
  id: string;
  idempotency_key: string;
  symbol: string;
  side: "BUY" | "SELL";
  notional: string;
  status: "SUBMITTING" | "SUBMITTED" | "FAILED" | "UNKNOWN";
  result: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, { headers: { "Content-Type": "application/json" }, ...init });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `HTTP_${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function createRun(input: { target_id: string; target_version: string; mode: Run["mode"]; max_episodes: number; difficulty: number }) {
  return request<Run>("/runs", { method: "POST", body: JSON.stringify(input) });
}

export function getRun(id: string) {
  return request<Run>(`/runs/${id}`);
}

export function getEpisodes(id: string) {
  return request<Episode[]>(`/runs/${id}/episodes`);
}

export function getScore(id: string) {
  return request<Scorecard>(`/runs/${id}/score`);
}

export function getWeaknesses(id: string) {
  return request<Weakness[]>(`/runs/${id}/weaknesses`);
}

export function stopRun(id: string) {
  return request<Run>(`/runs/${id}/stop`, { method: "POST" });
}

export function eventUrl(id: string) {
  return `${base}/runs/${id}/events`;
}

export function getTradingStatus() {
  return request<TradingStatus>("/trading/status");
}

export function previewLiveOrder(input: { symbol: string; side: "BUY" | "SELL"; notional: string }) {
  return request<{ symbol: string; side: "BUY" | "SELL"; notional: string; mode: string; armed: boolean }>("/trading/orders/preview", { method: "POST", body: JSON.stringify(input) });
}

export function executeLiveOrder(input: { symbol: string; side: "BUY" | "SELL"; notional: string; idempotency_key: string; confirm: boolean }) {
  return request<LiveOrder>("/trading/orders", { method: "POST", body: JSON.stringify(input) });
}
