# Verification Matrix

| Capability | Implemented | Tested | Evidence | Status |
|---|---:|---:|---|---|
| LangGraph adaptive loop | yes | yes | `uv run pytest test_eva.py -q`, runtime smoke | VERIFIED |
| Qwen scenario generation | yes | yes | schema/retry tests; configured runtime required | CONDITIONAL |
| Qwen critic | yes | yes | fallback and graph tests; configured runtime required | CONDITIONAL |
| Qwen mutation | yes | yes | mutation path in graph tests; configured runtime required | CONDITIONAL |
| Pydantic scenario validation | yes | yes | malformed output and semantic validation tests | VERIFIED |
| Policy oracle | yes | yes | blocked, emergency, exposure tests | VERIFIED |
| Freshness oracle | yes | yes | stale evidence test | VERIFIED |
| Sizing oracle | yes | yes | size and balance tests | VERIFIED |
| Takeover metric | yes | yes | required and unnecessary escalation tests | VERIFIED |
| Tool discipline | yes | yes | precondition, duplicate, step-cap tests | VERIFIED |
| Execution safety | yes | yes | mismatch and paper-gate tests | VERIFIED |
| Consistency metric | yes | yes | equivalent action comparison test | VERIFIED |
| Failure memory | yes | yes | SQLite readback and version isolation test | VERIFIED |
| Deterministic curriculum | yes | yes | graph budget, stop, mutation, difficulty routing | VERIFIED |
| Deterministic score | yes | yes | fixed weights and repeatability tests | VERIFIED |
| Reference weak target | yes | yes | weak-versus-safe graph test | VERIFIED |
| Reference safe target | yes | yes | safe graph score test | VERIFIED |
| Synthetic S2 scenarios | yes | yes | earnings conflict, market-closed, max-exposure seeds | VERIFIED |
| FastAPI run API | yes | yes | create/read/stop/score TestClient test | VERIFIED |
| SSE events | yes | no live server test | endpoint and generator implementation | UNVERIFIED |
| Frontend mode switch | yes | yes | `npm run build` | VERIFIED |
| Frontend live status | yes | no browser session | EventSource and polling implementation | UNVERIFIED |
| Bitget argument allowlist | yes | yes | subprocess array and shell flag tests | VERIFIED |
| Bitget market/account reads | yes | no configured CLI | adapter path only | UNVERIFIED |
| Bitget paper order | yes | yes | paper flag required test | CONDITIONAL |
| Bitget live financial write | gated | no real order sent | adapter argument path, live env gate, confirmation and idempotency tests | NOT_RUN |
| External target integration | yes | yes | timeout, malformed response, step cap tests | CONTRACT_VERIFIED |

## Labels

`LIVE_MARKET`, `DEMO_ACCOUNT`, `PAPER_EXECUTION`, `SYNTHETIC_SCENARIO`, `SYNTHETIC_MUTATION`, `DETERMINISTIC_ORACLE`, `LLM_CRITIQUE`, and `UNVERIFIED` are kept separate in stored evidence.

## Commands

```powershell
cd backend
uv sync
uv run pytest test_eva.py -q
cd ..\frontend
npm ci
npm run build
```

The current host resolves Python 3.14.7 through `uv`. The active npm registry has no TypeScript 6.0.0, so the build uses stable TypeScript 7.0.2. The host Node runtime is 22.23.1; the PRD target is Node 24.x.
