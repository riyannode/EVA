# EVA Design

## Goal

EVA is a standalone benchmark console that runs adaptive safety evaluations against trading agents. The first repository lives under `outputs/eva` so the repository root can keep the PRD's allowed directories while preserving the Codex workspace folders.

## Architecture

FastAPI owns the small HTTP surface and schedules one in-process benchmark task. `graph.py` owns one LangGraph `StateGraph`; its nodes call the scenario, target, oracle, critic, memory, curriculum, and scoring modules through typed models. `db.py` owns parameterized SQLite queries for run records, episode evidence, weakness memory, and events.

Qwen is an optional OpenAI-compatible transport used only by scenario generation, qualitative critique, and mutation. Missing or invalid model output has an explicit fallback and never changes deterministic oracle results. The reference targets make the demo runnable without an external target. External targets use the stateless HTTP contract from the PRD.

The frontend is one flat React view. It switches between `SYNTHETIC` and `BITGET_PAPER` for evaluation, starts and stops runs, subscribes to SSE events with polling fallback, renders run evidence, and exposes a separate live order preview/confirmation surface.

## Safety decisions

- Live benchmark evidence and live financial execution are separate concerns.
- Bitget calls use a fixed executable, fixed argument allowlist, and `shell=False`. Live execution is locked by default, requires two environment gates and user confirmation, and is idempotent at the API ledger boundary.
- Deterministic oracles are authoritative for readiness and failure codes.
- External target responses, tool traces, critic summaries, and model output are size-capped and schema-validated before persistence or rendering.
- No credentials, generated databases, or build output are committed.

## Verification boundary

Python 3.14.7 and Node 24.x are the PRD targets. The host currently exposes Node 22.23.1, while `uv` resolved CPython 3.14.7 for the backend. The PRD's TypeScript 6.0 pin does not exist in the active npm registry; the frontend uses the available stable TypeScript 7.0.2. The repository will not claim live Bitget or external-agent verification without runtime evidence.
