# EVA Design

## Goal

EVA is a standalone benchmark console that runs adaptive safety evaluations against trading agents. The first repository lives under `outputs/eva` so the repository root can keep the PRD's allowed directories while preserving the Codex workspace folders.

## Architecture

FastAPI owns the small HTTP surface and schedules one in-process benchmark task. `graph.py` owns one LangGraph `StateGraph`; its nodes call the scenario, target, oracle, critic, memory, curriculum, and scoring modules through typed models. `db.py` owns parameterized SQLite queries for run records, episode evidence, weakness memory, and events.

Qwen is an optional OpenAI-compatible transport used only by scenario generation, qualitative critique, and mutation. Missing or invalid model output has an explicit fallback and never changes deterministic oracle results. The reference targets make the demo runnable without an external target. External targets use the stateless HTTP contract from the PRD.

The frontend is one flat React view. It switches between `SYNTHETIC` and the legacy-compatible `BITGET_PAPER` flow, starts and stops runs, subscribes to SSE events with polling fallback, and renders run evidence. The Connect External Agent dialog registers a venue-neutral identity, shows the one-time key, presents SDK/CLI/manual methods, reports `ONLINE` and `SYNTHETIC_READY`, and starts a gateway synthetic evaluation after the agent connects.

## Safety decisions

- Provider calls use a narrow execution-provider boundary. Bitget calls use a fixed executable, fixed argument allowlist, and `shell=False`. The only Bitget write path is paper execution requested by an external benchmark target.
- Deterministic oracles are authoritative for readiness and failure codes.
- External target responses, tool traces, critic summaries, and model output are size-capped and schema-validated before persistence or rendering.
- No credentials, generated databases, or build output are committed.

## Verification boundary

Python 3.14.7 and Node 24.x are the PRD targets. The host currently exposes Node 22.23.1, while `uv` resolved CPython 3.14.7 for the backend. The PRD's TypeScript 6.0 pin does not exist in the active npm registry; the frontend uses the available stable TypeScript 7.0.2. The repository will not claim Bitget paper or external-agent runtime verification without runtime evidence.
