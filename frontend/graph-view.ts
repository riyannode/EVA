import type { GraphEvent, Run } from "./api";

export const stations = [
  { id: "scenario", name: "Scenario", role: "Qwen · test author", color: "#dfbf78", description: "Creates the next evaluation scenario.", stages: ["CHOOSE_SCENARIO"] },
  { id: "target", name: "Target", role: "Trading decision-maker", color: "#83c7ac", description: "Reads evidence and makes the trading decision.", stages: ["RUN_TARGET"] },
  { id: "oracles", name: "Oracles", role: "Deterministic judges", color: "#88b7dc", description: "Checks policy, tools, safety and execution.", stages: ["RUN_ORACLES"] },
  { id: "critic", name: "Critic", role: "Qwen · behavioral analyst", color: "#c0a1df", description: "Explains results without changing the verdict.", stages: ["CRITIC"] },
  { id: "memory", name: "Memory", role: "SQLite · failure history", color: "#e79a85", description: "Stores episodes and tracks weakness recovery.", stages: ["SAVE_MEMORY"] },
  { id: "mutation", name: "Mutation", role: "Qwen · targeted retests", color: "#c4cb80", description: "Changes scenario content to retest a weakness.", stages: ["MUTATE"] },
] as const;

export type StationId = typeof stations[number]["id"];
export const stages = ["LOAD_RUN", "CHOOSE_SCENARIO", "RUN_TARGET", "RUN_ORACLES", "CRITIC", "SAVE_MEMORY", "ROUTE", "MUTATE", "HARDER", "FINISH"];
const eventStages: Record<string, string> = {
  SCENARIO_SELECTED: "CHOOSE_SCENARIO", BITGET_SYMBOL_RESOLVED: "RUN_TARGET", TARGET_COMPLETED: "RUN_TARGET",
  ORACLES_COMPLETED: "RUN_ORACLES", CRITIC_COMPLETED: "CRITIC", MEMORY_SAVED: "SAVE_MEMORY",
  ROUTE_SELECTED: "ROUTE", SCENARIO_MUTATED: "MUTATE", CURRICULUM_ADVANCED: "HARDER", RUN_FINISHED: "FINISH",
};

export function stageForEvent(type: string): string | null {
  return stages.includes(type) ? type : eventStages[type] ?? null;
}

export function stationForStage(stage: string | null): StationId | null {
  return stations.find(station => station.stages.some(item => item === stage))?.id ?? null;
}

export function eventStops(events: GraphEvent[], afterId: number): { id: number; station: StationId }[] {
  const unique = new Map(events.filter(event => event.id > afterId).map(event => [event.id, event]));
  return [...unique.values()].sort((a, b) => a.id - b.id).flatMap(event => {
    const station = stationForStage(stageForEvent(event.type));
    return station ? [{ id: event.id, station }] : [];
  });
}

export function parseEvent(raw: string, runId: string): GraphEvent | null {
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    if (!("id" in value) || !Number.isSafeInteger(value.id) || typeof value.id !== "number") return null;
    if (!("run_id" in value) || value.run_id !== runId) return null;
    if (!("type" in value) || typeof value.type !== "string") return null;
    if (!("created_at" in value) || typeof value.created_at !== "string") return null;
    if (!("payload" in value) || !value.payload || typeof value.payload !== "object" || Array.isArray(value.payload)) return null;
    return value as GraphEvent;
  } catch { return null; }
}

export function appendEvent(events: GraphEvent[], event: GraphEvent): GraphEvent[] {
  if (events.some(item => item.id === event.id)) return events;
  return [...events, event].sort((a, b) => a.id - b.id).slice(-200);
}

export const isActive = (run: Run | null) => run?.status === "RUNNING" || run?.status === "CREATED";
export const readable = (value: string) => value.replaceAll("_", " ").toLowerCase();
