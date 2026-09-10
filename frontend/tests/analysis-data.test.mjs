import test from "node:test";
import assert from "node:assert/strict";
import { filledOrderFields, behavioralTone } from "../analysis-data.ts";

const detail = { orderId: "test-order", clientOid: "test-client", orderStatus: "filled", executedQty: "0.0005", avgPrice: "100000", fee: 0, feeCurrency: "USDT" };
const trace = order_detail => ({ tool: "paper_order", result_status: "ok", verification_labels: ["PAPER_EXECUTION"], result: { data: { placement: { orderId: "ack-only" }, order_detail, instrument: { symbol: "BTCUSDT" } } } });

test("filled order reads nested CLI data and preserves only available fields", () => {
  for (const value of [detail, { data: detail }, { data: [detail] }, { order_detail: { data: detail } }]) assert.deepEqual(filledOrderFields(trace(value)), detail);
  assert.deepEqual(filledOrderFields(trace({ orderId: "test-order", orderStatus: "filled", fee: null })), { orderId: "test-order", orderStatus: "filled" });
});

test("ACK, malformed, pending, failed and unverified details cannot become filled evidence", () => {
  for (const value of [null, {}, "invalid", { id: "random", orderStatus: "filled" }, { ...detail, orderStatus: "new" }, { ...detail, orderStatus: "cancelled" }]) assert.equal(filledOrderFields(trace(value)), null);
  assert.equal(filledOrderFields({ ...trace(detail), verification_labels: ["UNVERIFIED"] }), null);
  assert.equal(filledOrderFields({ ...trace(detail), result_status: "error" }), null);
  assert.equal(filledOrderFields({ ...trace(detail), tool: "market" }), null);
});

test("takeover accuracy is positive while violation metrics warn", () => {
  assert.equal(behavioralTone("takeover_accuracy", 1), "good");
  assert.equal(behavioralTone("takeover_accuracy", null), "");
  assert.equal(behavioralTone("takeover_accuracy", undefined), "");
  for (const metric of ["risk_violation_rate", "false_autonomy_rate", "unnecessary_escalation_rate", "consistency_failure_rate", "tool_precondition_violation_count", "duplicate_action_count", "execution_mismatch_count"]) {
    assert.equal(behavioralTone(metric, 1), "warn");
    assert.equal(behavioralTone(metric, 0), "");
  }
});
