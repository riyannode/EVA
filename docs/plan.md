# EVA Implementation Plan

> **For agentic workers:** Execute this plan inline in the current repository. Do not commit unless the user explicitly requests it.

**Goal:** Build the complete EVA V1 benchmark loop, safe Bitget paper adapter, dashboard, demo targets, and verification docs.

**Architecture:** Keep one flat Python file per responsibility and one flat React entry surface. A typed LangGraph state drives scenario selection, target execution, deterministic oracles, qualitative Qwen critique, SQLite memory, deterministic curriculum routing, and scoring.

**Tech Stack:** Python, FastAPI, LangGraph, SQLite, Pydantic, OpenAI-compatible Responses API, Vite, React, TypeScript, native CSS, npm, uv.

## Global Constraints

- Only `backend/`, `frontend/`, `docs/`, `sdk/`, and `cli/` are repository root product directories.
- No helpers, utils, services, repositories, controllers, components, hooks, lib, common, or shared folders.
- `SYNTHETIC`, generic `PAPER`, and compatibility `BITGET_PAPER` are the benchmark modes.
- Execution-backed logic depends on the provider contract; Bitget is the first registered provider.
- Qwen may generate scenarios, critiques, and mutations; deterministic code owns pass/fail and readiness.
- Bitget writes are paper-trading only and use an explicit allowlist with `shell=False`.
- SQLite uses parameterized SQL and no ORM; `eva.db` and `checkpoints.db` are ignored.
- No secrets, withdrawals, transfers, margin, real-money execution, or arbitrary shell commands.

## File Map

- `backend/config.py`: environment parsing and bounded runtime configuration.
- `backend/models.py`: Pydantic contracts and enums.
- `backend/db.py`: SQLite schema, queries, memory, events, and score readback.
- `backend/oracle.py`: deterministic policy, freshness, sizing, takeover, tool, execution, and consistency checks.
- `backend/score.py`: fixed weighted readiness score and labels.
- `backend/qwen.py`: optional OpenAI-compatible scenario, critic, and mutation calls with validation and one scenario repair retry.
- `backend/target.py`: HTTP protocol, reference weak/safe targets, tool loop, caps, and target errors.
- `backend/bitget.py`: fixed Bitget CLI invocation with paper-only write support.
- `backend/provider.py`, `backend/providers.py`: exchange-neutral execution contract, normalization seam, and provider registry.
- `backend/graph.py`: one LangGraph state machine and deterministic curriculum.
- `backend/app.py`: FastAPI endpoints and in-process run scheduling.
- `backend/auth.py`, `backend/gateway.py`, `backend/journal.py`, `backend/certificate.py`: registry auth, outbound agent gateway, evidence lineage, and signed certificates.
- `backend/test_eva.py`: focused backend regression tests.
- `frontend/index.html`, `main.tsx`, `app.tsx`, `api.ts`, `styles.css`, `package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`: flat dashboard.
- `sdk/typescript`, `sdk/python`, `cli`: framework-neutral gateway clients and onboarding/verification commands.
- `README.md`, `LICENSE`, `docs/architecture.md`, `docs/demo.md`, `docs/submission.md`, `docs/verification.md`: user-facing product and evidence documentation.

## Execution Tasks

### Task 1: Repository baseline

Create the allowed root structure, ignore local state and secrets, initialize git metadata, and record the baseline branch, HEAD availability, files, and runtime versions. Do not claim product capability from this task.

### Task 2: Backend contracts and persistence

Define typed request, scenario, decision, trace, oracle, run, episode, weakness, and score contracts. Create SQLite tables and parameterized queries. Add `/health`, target listing, run creation/read endpoints, and tests for configuration, validation, and memory version isolation.

### Task 3: Deterministic evaluation

Implement all required oracle statuses and machine-readable failures, reference scenario seeds including earnings conflict, market-closed evidence uncertainty, and max exposure, plus fixed score weights. Add regression tests for every hard oracle case and score determinism.

### Task 4: Qwen transport

Implement one OpenAI-compatible client in `qwen.py`. Keep prompt name/version in every call, validate JSON through Pydantic, perform one repair retry for invalid scenarios, then use a deterministic labeled fallback. Ensure Qwen cannot emit scores, policy changes, or Bitget commands. Test missing credentials, malformed output, retry count, and fallback.

### Task 5: Target protocol and Bitget safety

Implement the stateless HTTP target contract with timeout, body-size, response-shape, and step caps. Implement reference weak/safe targets and standardized tools. Implement Bitget discovery/read/paper order calls with fixed arrays, disallowed operation rejection, paper flag enforcement, and order-reference verification. Test timeout, malformed responses, step limits, allowlists, and absence of real-money write commands.

### Task 6: Adaptive LangGraph run

Build one graph with the required state fields and nodes. Persist stage events and episodes, update failure memory, route hard failures to targeted mutations, raise difficulty after three category passes, stop at budget or stop flag, and checkpoint with SQLite. Add API run/stop/resume/event/episode/score endpoints and tests for routing, stop, max budget, weak-vs-safe behavior, and memory readback.

### Task 7: Dashboard

Build the flat Vite React console with target/version/mode/episode/difficulty controls, start/stop actions, SSE plus polling fallback, live stage data, episode table, score breakdown, readiness badge, weakness table, and API error state. Run `npm ci` and `npm run build`.

### Task 8: Evidence and acceptance

Run bounded synthetic weak and safe demos, inspect persisted SQLite records, validate `BITGET_PAPER` behavior without credentials, run backend tests, `git diff --check`, and a source scan for secrets, forbidden directories, comments, and real-money order paths. Write docs that distinguish verified, unverified, synthetic, paper, and LLM evidence. Leave all task-started processes stopped and leave the final commit step to the user.
