# EVA

EVA is an autonomous evaluation and red-team agent for trading agents.

## 1. Why EVA

Trading tools can expose market, account, and paper-execution capabilities. EVA evaluates whether a target agent uses those capabilities safely before it receives more autonomy.

## 2. How it works

EVA generates a structured scenario, runs the target, applies deterministic oracles, asks Qwen for a qualitative diagnosis, stores weakness memory, mutates failed scenarios, raises difficulty after repeated passes, and calculates a reproducible readiness score.

## 3. Demo

Run `REFERENCE_WEAK` and `REFERENCE_SAFE` in `SYNTHETIC` mode as local deterministic fixtures. The official Track 2 demo uses `EXTERNAL_HTTP` with `BITGET_PAPER`; the target URL and declared identity, Bitget market/instrument/account evidence, target trace, filled paper-order detail, oracle reconciliation, and persisted episode evidence are required.

## 4. Architecture

FastAPI schedules one in-process LangGraph state graph. SQLite stores runs, episodes, weakness memory, and events. See [docs/architecture.md](docs/architecture.md).

## 5. Qwen role

Qwen is used for structured scenario generation, qualitative critique, and targeted mutation when `BITGET_QWEN_API_KEY` is configured. Pydantic validation and deterministic fallback protect the run. Qwen never scores readiness or changes policy.

## 6. Bitget role

`BITGET_PAPER` is the only Bitget write mode in V1 and is restricted to the official benchmark target flow. `BITGET_MODE` accepts only `read-only` and `paper`. Paper success requires a documented order reference followed by a filled order-detail response; an empty, pending, cancelled, or ambiguous CLI response remains `UNVERIFIED`.

## 7. Benchmark metrics

Readiness is weighted across policy, freshness, sizing, takeover, execution, consistency, and tool discipline. Evaluation metrics are available at `/runs/{id}/metrics`; paper performance fields remain unavailable or unverified unless stored execution data is sufficient.

## 8. Quickstart

Backend:

```powershell
cd backend
uv sync
uv run pytest test_eva.py -q
uv run fastapi dev app.py
```

Frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`, select a target, choose `SYNTHETIC` or `BITGET_PAPER`, and start an evaluation. For Track 2, install/configure the official `bgc`, use `EXTERNAL_HTTP`, provide the target URL, declared target name, and declared target model, configure `BITGET_MODE=paper`, run `GET /verification/preflight?target_url=...&target_name=...&target_model=...`, then inspect `/runs/{id}/verification`, `/runs/{id}/metrics`, and `/runs/{id}/events`.

## 9. Verification

See [docs/verification.md](docs/verification.md) for the current evidence matrix.

## 10. Limitations

V1 is single-process and intended for a bounded demo. Real-money execution is not part of the backend. Missing Qwen, Bitget CLI, or Bitget paper credentials leave the implementation `RUNTIME UNVERIFIED`; deterministic fallback output remains explicitly labeled.

## 11. Hackathon

EVA targets Bitget AI Base Camp Hackathon S2, Track 2 — Agentic Trading, Open Theme. EVA autonomously red-teams trading agents before capital does.

## 12. License

MIT. See [LICENSE](LICENSE).
