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
| Deterministic score | yes | yes | fixed weights, coverage, empty-score, timeout, and repeatability tests | VERIFIED |
| Reference weak target | yes | yes | weak-versus-safe graph test | VERIFIED |
| Reference safe target | yes | yes | safe graph score test | VERIFIED |
| Synthetic S2 scenarios | yes | yes | earnings conflict, market-closed, max-exposure seeds | VERIFIED |
| FastAPI run API | yes | yes | create/read/stop/score TestClient test | VERIFIED |
| SSE events | yes | no running-server test | endpoint and generator implementation | UNVERIFIED |
| Frontend mode switch | yes | yes | `npm run build` | VERIFIED |
| Bitget argument allowlist | yes | yes | subprocess array and shell flag tests | VERIFIED |
| Bitget market/account reads | yes | no configured CLI | adapter path only | UNVERIFIED |
| Bitget paper order evidence | yes | yes | paper flag and order-reference tests | CONDITIONAL |
| Track 2 paper acceptance gate | yes | yes | external target, evidence, reconciliation, and persisted verification tests | CONDITIONAL |
| Track 2 preflight | yes | yes | missing-runtime and all-ready-without-order tests | CONDITIONAL |
| Declared external target identity | yes | yes | API and SQLite readback tests | CONDITIONAL |
| Evaluation metrics | yes | yes | empty-data and stored-episode metric tests | VERIFIED |
| External target integration | yes | yes | timeout, malformed response, step cap tests | CONTRACT_VERIFIED |

## Labels

`LIVE_MARKET`, `DEMO_ACCOUNT`, `PAPER_EXECUTION`, `SYNTHETIC_SCENARIO`, `SYNTHETIC_MUTATION`, `DETERMINISTIC_ORACLE`, `LLM_CRITIQUE`, and `UNVERIFIED` are kept separate in stored evidence.

## Commands

```powershell
cd backend
uv sync
uv run pytest test_eva.py -q
```

The current host resolves Python 3.14.7 through `uv`. Bitget and Qwen runtime evidence remains conditional on credentials and the configured `bgc` executable.

Preflight is a pre-run environment check. Its `paper_run_ready` and compatibility `official_track2_ready` fields do not certify an order. `/runs/{id}/verification` is the post-run acceptance gate and requires persisted market/account evidence, a verified paper order, deterministic reconciliation, and runtime Qwen critic evidence.
