# EVA

EVA is an autonomous evaluation and red-team agent for trading agents.

For the authoritative EVA product definition and production roadmap, see [docs/PRODUCT_PRD.md](docs/PRODUCT_PRD.md).

## 1. Why EVA

Trading tools can expose market, account, and paper-execution capabilities. EVA evaluates whether a target agent uses those capabilities safely before it receives more autonomy.

## 2. How it works

EVA generates a structured scenario, runs the target, applies deterministic oracles, asks Qwen for a qualitative diagnosis, stores weakness memory, mutates failed scenarios, raises difficulty after repeated passes, and calculates a reproducible readiness score.

## 3. Demo

Run `REFERENCE_WEAK` and `REFERENCE_SAFE` in `SYNTHETIC` mode as local deterministic fixtures. External agents can pair through the Agents page or CLI and connect outbound through `eva-agent/1`; onboarding and gateway evaluations are exchange-neutral. The official Track 2 demo uses `EXTERNAL_HTTP` with `BITGET_PAPER`; the target URL and declared identity, Bitget market/instrument/account evidence, target trace, filled paper-order detail, oracle reconciliation, and persisted episode evidence are required.

## 4. Architecture

FastAPI schedules one in-process LangGraph state graph. SQLite stores runs, episodes, weakness memory, chained events, agents, and certificates. The gateway and SDKs are the preferred external-agent transport. Exchange-specific parsing stays behind the `ExecutionProvider` registry; Bitget is the first provider and `PAPER` is the generic paper mode. See [docs/architecture.md](docs/architecture.md) and [docs/exchange-providers.md](docs/exchange-providers.md).

## 5. External-agent onboarding

Use the dashboard's `Agents` page or `eva auth start`, wait for operator approval, complete the one-time pairing exchange, then connect an SDK or raw client to `/v1/agent/connect`. Registration accepts optional provider metadata; it is not an exchange credential grant. Synthetic evaluation is available without a venue. See [docs/onboarding.md](docs/onboarding.md), [docs/protocol.md](docs/protocol.md), and [docs/public-api.md](docs/public-api.md).

## 6. Qwen role

Qwen is used for structured scenario generation, qualitative critique, and targeted mutation when `BITGET_QWEN_API_KEY` is configured. Pydantic validation and deterministic fallback protect the run. Qwen never scores readiness or changes policy.

## 7. Bitget role

`BITGET_PAPER` is the only Bitget write mode in V1 and is restricted to the official benchmark target flow. `BITGET_MODE` accepts only `read-only` and `paper`. Paper success requires a documented order reference followed by a filled order-detail response; an empty, pending, cancelled, or ambiguous CLI response remains `UNVERIFIED`.

## 8. Benchmark metrics

Readiness is weighted across policy, freshness, sizing, takeover, execution, consistency, and tool discipline. Evaluation metrics are available at `/runs/{id}/metrics`; paper performance fields remain unavailable or unverified unless stored execution data is sufficient.

## 9. Quickstart

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

Open `http://localhost:5173`, select a target, choose `SYNTHETIC` or `BITGET_PAPER`, and start an evaluation. To connect an external agent, open `Agents`, create a pairing request, and have an operator approve it through the admin path. For Track 2, install/configure the official `bgc`, use `EXTERNAL_HTTP`, provide the target URL, declared target name, and declared target model, configure `BITGET_MODE=paper`, run `GET /verification/preflight?target_url=...&target_name=...&target_model=...`, then inspect `/runs/{id}/verification`, `/runs/{id}/metrics`, and `/runs/{id}/events`.

## 10. Verification

See [docs/verification.md](docs/verification.md) for the current evidence matrix.

## 11. Limitations

V1 is single-process and intended for a bounded demo. Real-money execution is not part of the backend. Missing Qwen, Bitget CLI, or Bitget paper credentials leave the implementation `RUNTIME UNVERIFIED`; deterministic fallback output remains explicitly labeled.

## 12. Hackathon

EVA targets Bitget AI Base Camp Hackathon S2, Track 2 — Agentic Trading, Open Theme. EVA autonomously red-teams trading agents before capital does.

## 13. License

MIT. See [LICENSE](LICENSE).
