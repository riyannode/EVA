import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("Agents page exposes pairing without a control-plane form", async () => {
  const source = await readFile(new URL("../agents.tsx", import.meta.url), "utf8");
  assert.match(source, /Create pairing request/);
  assert.match(source, /Waiting for approval/);
  assert.match(source, /Copy AI Agent Prompt/);
  assert.match(source, /Refresh Status/);
  assert.match(source, /Start Synthetic Evaluation/);
  assert.match(source, /getOnboarding/);
  assert.match(source, /onboarding\.methods/);
  assert.doesNotMatch(source, /control-plane token/i);
  assert.doesNotMatch(source, /EVA_CONTROL_PLANE_TOKEN/);
});

test("Agents defaults to a public catalog with resilient state transitions", async () => {
  const source = await readFile(new URL("../agents.tsx", import.meta.url), "utf8");
  assert.match(source, /useState<AgentMode>\("catalog"\)/);
  assert.match(source, /getAgentCatalog/);
  assert.match(source, /setTimeout\(load, 5000\)/);
  assert.match(source, /aria-busy="true"/);
  assert.match(source, /NO PUBLISHED AGENTS/);
  assert.match(source, /Agent catalog unavailable\./);
  assert.match(source, /Retry/);
  assert.match(source, /Connect agent/);
  assert.match(source, /Back to agents/);
  assert.match(source, /OFFLINE/);
  assert.match(source, /Readiness/);
  assert.match(source, /entry\.capability_state/);
  assert.match(source, /entry\.evaluation_count/);
  assert.match(source, /entry\.capabilities/);
});

test("catalog cards are collapsed native disclosures with high-signal summaries", async () => {
  const source = await readFile(new URL("../agents.tsx", import.meta.url), "utf8");
  const styles = await readFile(new URL("../styles.css", import.meta.url), "utf8");
  const card = source.split("function CatalogAgentCard")[1]?.split("function CatalogSkeleton")[0] ?? "";
  const summary = card.split('<summary className="catalog-agent-header">')[1]?.split("</summary>")[0] ?? "";
  assert.match(card, /<details className="catalog-agent-card">/);
  assert.match(card, /<summary className="catalog-agent-header">/);
  assert.match(summary, /entry\.name/);
  assert.match(summary, /ConnectionStatus/);
  assert.doesNotMatch(summary, /declared_model|framework|capability_state|evaluation_count|capabilities/);
  assert.match(card, /className="catalog-agent-details"/);
  assert.doesNotMatch(card, /<details className="catalog-agent-card" open/);
  assert.match(styles, /catalog-agent-card\[open\]/);
});

test("catalog renders each entry in the responsive product grid", async () => {
  const source = await readFile(new URL("../agents.tsx", import.meta.url), "utf8");
  const styles = await readFile(new URL("../styles.css", import.meta.url), "utf8");
  assert.match(source, /className="catalog-surface"/);
  assert.match(source, /agents\.map\(entry => <CatalogAgentCard/);
  assert.match(styles, /\.catalog-surface \{[^}]*width: 100%/s);
  assert.match(styles, /\.catalog-grid \{[^}]*grid-template-columns: repeat\(3, minmax\(0, 420px\)\)/s);
  assert.match(styles, /@media \(max-width: 1100px\)[\s\S]*\.catalog-grid \{ grid-template-columns: repeat\(2/);
  assert.match(styles, /@media \(max-width: 767px\)[\s\S]*\.catalog-grid \{ grid-template-columns: 1fr/);
});

test("public catalog card never renders private agent fields", async () => {
  const source = await readFile(new URL("../agents.tsx", import.meta.url), "utf8");
  const card = source.split("function CatalogAgentCard")[1]?.split("function CatalogSkeleton")[0] ?? "";
  assert.doesNotMatch(card, /owner_id|api_key|key_id|key_hash|key_salt|credentials|latest_evaluation_id/);
});
