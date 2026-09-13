import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function appSource() {
  return readFile(new URL("../app.tsx", import.meta.url), "utf8");
}

async function summarySource() {
  const source = await appSource();
  return source.split("function AgentCatalogSummary")[1]?.split("export default function App")[0] ?? "";
}

test("Observatory summary uses the public catalog instead of pairing state", async () => {
  const source = await appSource();
  const summary = await summarySource();
  assert.match(source, /getAgentCatalog/);
  assert.match(source, /useState<AgentCatalogEntry\[\]>\(\[\]\)/);
  assert.match(source, /<AgentCatalogSummary agents=\{catalog\} state=\{catalogState\}/);
  assert.match(source, /<Agents onEvaluationCreated=/);
  assert.doesNotMatch(source, /AgentSummary|onAgentStateChange|activeAgent|ActiveAgentCard/);
  assert.doesNotMatch(summary, /registration|onboarding|api[_-]?key|Authorization|credential/i);
});

test("Observatory catalog refreshes only while visible and cleans up its timer", async () => {
  const source = await appSource();
  const start = source.indexOf('if (view !== "observatory") return;');
  const end = source.indexOf("}, [view]);", start);
  const refreshEffect = source.slice(start, end);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  assert.match(refreshEffect, /getAgentCatalog\(\)/);
  assert.match(refreshEffect, /void load\(\)/);
  assert.match(refreshEffect, /setTimeout\(load, 5000\)/);
  assert.match(refreshEffect, /disposed = true; if \(timer\) clearTimeout\(timer\)/);
  assert.doesNotMatch(refreshEffect, /api[_-]?key|Authorization|credential/i);
});

test("single catalog agent shows name, connection and separate readiness", async () => {
  const summary = await summarySource();
  assert.match(summary, /agents\.length === 1/);
  assert.match(summary, /entry\.name/);
  assert.match(summary, /entry\.status/);
  assert.match(summary, /Connection: \$\{entry\.status\}/);
  assert.match(summary, /Readiness/);
  assert.match(summary, /entry\.capability_state/);
  assert.doesNotMatch(summary, /NO AGENT CONNECTED|ACTIVE AGENT/);
});

test("multiple catalog agents use aggregate semantics", async () => {
  const summary = await summarySource();
  assert.match(summary, /const onlineCount = agents\.filter\(entry => entry\.status === "ONLINE"\)\.length/);
  assert.match(summary, /published agents/);
  assert.match(summary, /\{onlineCount\} online/);
  assert.doesNotMatch(summary, /ACTIVE AGENT|active agent/i);
});

test("empty catalog and navigation actions remain explicit", async () => {
  const source = await appSource();
  const summary = await summarySource();
  assert.match(summary, /NO AGENTS PUBLISHED/);
  assert.match(summary, /Connect an external agent to add it to EVA\./);
  assert.match(summary, /View agents/);
  assert.match(summary, /Connect agent/);
  assert.match(source, /onOpen=\{\(\) => setView\("agents"\)\}/);
});
