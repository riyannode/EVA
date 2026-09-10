import type { TraceRecord } from "./api";

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function orderDetail(value: unknown): Record<string, unknown> | null {
  if (Array.isArray(value)) {
    for (const item of value) {
      const detail = orderDetail(item);
      if (detail) return detail;
    }
  } else if (record(value)) {
    if ("orderStatus" in value) return value;
    for (const key of ["data", "order_detail"]) {
      const detail = orderDetail(value[key]);
      if (detail) return detail;
    }
  }
  return null;
}

export function filledOrderFields(trace: TraceRecord): Record<string, string | number> | null {
  if (trace.tool !== "paper_order" || trace.result_status !== "ok" || !trace.verification_labels.includes("PAPER_EXECUTION")) return null;
  if (!record(trace.result.data)) return null;
  const detail = orderDetail(trace.result.data.order_detail);
  if (!detail || String(detail.orderStatus).toLowerCase() !== "filled") return null;
  if (![detail.orderId, detail.clientOid].some(value => typeof value === "string" && value.trim())) return null;
  const fields: Record<string, string | number> = {};
  for (const key of ["orderId", "clientOid", "orderStatus", "executedQty", "avgPrice", "fee", "feeCurrency"]) {
    const value = detail[key];
    if ((typeof value === "string" && value.trim()) || (typeof value === "number" && Number.isFinite(value))) fields[key] = value;
  }
  return fields;
}

export function behavioralTone(metric: string, value: number | null | undefined): string {
  if (value === null || value === undefined || value <= 0) return "";
  return metric === "takeover_accuracy" ? "good" : "warn";
}
