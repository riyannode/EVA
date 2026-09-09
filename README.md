# EVA

EVA is an autonomous evaluation and red-team agent for trading agents.

## 1. Why EVA

Trading tools can expose market, account, and paper-execution capabilities. EVA evaluates whether a target agent uses those capabilities safely before it receives more autonomy.

## 2. How it works

EVA generates a structured scenario, runs the target, applies deterministic oracles, asks Qwen for a qualitative diagnosis, stores weakness memory, mutates failed scenarios, raises difficulty after repeated passes, and calculates a reproducible readiness score.

## 3. Demo

Run `REFERENCE_WEAK` and `REFERENCE_SAFE` in `SYNTHETIC` mode. The weak target violates selected constraints; the safe target follows the reference policy. The dashboard shows the difference and the mutations.

## 4. Architecture

FastAPI schedules one in-process LangGraph state graph. SQLite stores runs, episodes, weakness memory, and events. See [docs/architecture.md](docs/architecture.md).

## 5. Qwen role

Qwen is used for structured scenario generation, qualitative critique, and targeted mutation when `BITGET_QWEN_API_KEY` is configured. Pydantic validation and deterministic fallback protect the run. Qwen never scores readiness or changes policy.

## 6. Bitget role

`BITGET_PAPER` remains the benchmark execution mode. The separate live execution surface uses the same fixed CLI adapter and is locked unless `BITGET_MODE=live` and `ENABLE_LIVE_TRADING=true` are configured. A live order requires a preview, an explicit confirmation, and a UUID idempotency key. The evaluation graph never submits live orders automatically.

## 7. Benchmark metrics

Readiness is weighted across policy, freshness, sizing, takeover, execution, consistency, and tool discipline. Paper PnL metrics are intentionally separate from readiness.

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

Open `http://localhost:5173`, select a target, choose `SYNTHETIC` or `BITGET_PAPER`, and start an evaluation.

## 9. Verification

See [docs/verification.md](docs/verification.md) for the current evidence matrix.

## 10. Limitations

V1 is single-process and intended for a bounded demo. The live execution surface has no user authentication and relies on the configured Bitget CLI and credentials. A timeout is recorded as `UNKNOWN` and must be reconciled before another request. Missing Qwen credentials use an explicitly labeled deterministic fallback.

## 11. Hackathon

EVA targets Bitget AI Base Camp Hackathon S2, Track 2 — Agentic Trading, Open Theme. EVA autonomously red-teams trading agents before capital does.

## 12. License

MIT. See [LICENSE](LICENSE).
