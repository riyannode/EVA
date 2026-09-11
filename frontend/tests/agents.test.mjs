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
