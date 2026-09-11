import type { Run } from "./api";

const labels: Record<string, string> = {
  REFERENCE_SAFE: "Safety-focused reference agent",
  REFERENCE_WEAK: "Weak reference agent",
  EXTERNAL_HTTP: "External trading agent",
  SYNTHETIC: "Synthetic test",
  BITGET_PAPER: "Bitget paper test",
  PAPER: "Execution-backed paper test",
  policy: "Policy compliance",
  freshness: "Evidence freshness",
  sizing: "Order size limits",
  takeover: "Human handover",
  execution: "Order execution",
  consistency: "Decision consistency",
  tool_discipline: "Required tool use",
  PASS: "Passed",
  FAIL: "Failed",
  NOT_APPLICABLE: "Not tested",
  UNVERIFIED: "Not verified",
  READY: "Ready",
  STALE_EVIDENCE_USED: "Used outdated evidence",
  CONFLICT_IGNORED: "Ignored conflicting evidence",
  FALSE_AUTONOMY: "Acted without required approval",
  SIZE_VIOLATION: "Exceeded order size limits",
  TOOL_PRECONDITION_BYPASS: "Skipped required checks",
  PAPER_EXECUTION_NOT_VERIFIED: "Paper execution not verified",
};

export function displayLabel(value: string) {
  return labels[value] ?? value.replaceAll("_", " ").toLowerCase().replace(/^./, char => char.toUpperCase());
}

export function runLabel(run: Run) {
  return `${run.target_name || displayLabel(run.target_id)} · ${displayLabel(run.status)} · ${run.id.slice(0, 8)}`;
}

export function textParagraphs(value: string) {
  return value.split(/\n\s*\n/).map(part => part.trim()).filter(Boolean);
}
