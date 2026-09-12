import test from "node:test";
import assert from "node:assert/strict";
import * as api from "../api.ts";

test("frontend calls only existing read, create and stop contracts", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url, init }); return new Response(JSON.stringify({ id: "run" }), { status: 200 }); };
  try {
    await api.getRuns();
    await api.getRun("run");
    await api.getEpisodes("run");
    await api.getScore("run");
    await api.getMetrics("run");
    await api.getWeaknesses("run");
    await api.getVerification("run");
    await api.stopRun("run");
    assert.deepEqual(calls.map(call => new URL(call.url).pathname), ["/runs", "/runs/run", "/runs/run/episodes", "/runs/run/score", "/runs/run/metrics", "/runs/run/weaknesses", "/runs/run/verification", "/runs/run/stop"]);
    assert.equal(calls.at(-1).init.method, "POST");
    assert.equal(new URL(api.eventUrl("run")).pathname, "/runs/run/events");
  } finally { globalThis.fetch = original; }
});

test("paper target identity is submitted unchanged", async () => {
  const original = globalThis.fetch;
  const input = { target_id: "EXTERNAL_HTTP", target_version: "v1", target_name: "test-only", target_model: "declared", target_url: "http://127.0.0.1:9000/agent", mode: "BITGET_PAPER", max_episodes: 2, difficulty: 1 };
  globalThis.fetch = async (_url, init) => {
    assert.deepEqual(JSON.parse(init.body), input);
    assert.ok(init.signal instanceof AbortSignal);
    return new Response(JSON.stringify({ id: "test" }));
  };
  try { assert.deepEqual(await api.createRun(input), { id: "test" }); }
  finally { globalThis.fetch = original; }
});

test("failed writes are not retried or presented as success", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response("private diagnostic", { status: 422 }); };
  try {
    await assert.rejects(api.createRun({}), { message: "HTTP_422" });
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

test("no obsolete financial-write API exports remain", () => {
  assert.equal("executeLiveOrder" in api, false);
  assert.equal("previewLiveOrder" in api, false);
  assert.equal("getTradingStatus" in api, false);
});

test("pairing API uses public request and one-time exchange routes", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({ request_id: "pair_test", status: "PENDING", expires_at: "2026-01-01T00:00:00Z", approval_url: "https://eva.test/pair" }));
  };
  try {
    await api.createPairingRequest({ name: "TraderX", version: "1.0.0", declared_model: "model-v1" });
    await api.getPairingRequest("pair_test");
    await api.completePairing("pair_test");
    assert.deepEqual(calls.map(call => new URL(call.url).pathname), ["/v1/pairing-requests", "/v1/pairing-requests/pair_test", "/v1/pairing-requests/pair_test/exchange"]);
    assert.equal(calls[0].init.headers.Authorization, undefined);
    assert.equal(calls[2].init.method, "POST");
  } finally { globalThis.fetch = original; }
});

test("public agent catalog parses safe fields without an agent credential", async () => {
  const original = globalThis.fetch;
  const entry = {
    agent_id: "agt_public",
    name: "darwin-bitget",
    version: "0.2.0",
    declared_model: "qwen3.8-max",
    framework: "cloudflare-workers-durable-objects",
    status: "OFFLINE",
    capability_state: "SYNTHETIC_READY",
    protocol_version: "eva-agent/1",
    capabilities: ["market", "account", "history", "escalate"],
    execution_providers: ["bitget"],
    evaluation_count: 0,
    latest_readiness: null,
  };
  globalThis.fetch = async (url, init) => {
    assert.equal(new URL(url).pathname, "/v1/catalog/agents");
    assert.equal(init.method, undefined);
    assert.equal(init.headers.Authorization, undefined);
    return new Response(JSON.stringify([entry]), { status: 200 });
  };
  try { assert.deepEqual(await api.getAgentCatalog(), [entry]); }
  finally { globalThis.fetch = original; }
});

test("public catalog type excludes private agent identity and credential fields", async () => {
  const source = await (await import("node:fs/promises")).readFile(new URL("../api.ts", import.meta.url), "utf8");
  const publicType = source.match(/export type AgentCatalogEntry = \{[\s\S]*?\n\};/)?.[0] ?? "";
  assert.match(publicType, /agent_id/);
  assert.doesNotMatch(publicType, /owner_id|api_key|key_id|key_hash|key_salt|credentials|latest_evaluation_id/);
});
