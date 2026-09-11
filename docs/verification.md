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
| Bitget paper order evidence | yes | yes | paper flag, instrument constraints, order-reference, and filled-detail tests | CONDITIONAL |
| Track 2 paper acceptance gate | yes | yes | external target, instrument/account evidence, filled order detail, reconciliation, and persisted verification tests | CONDITIONAL |
| Track 2 preflight | yes | yes | missing-runtime, contract validation, instrument/account, and all-ready-without-order tests | CONDITIONAL |
| Declared external target identity | yes | yes | API and SQLite readback tests | CONDITIONAL |
| Evaluation metrics | yes | yes | empty-data and stored-episode metric tests | VERIFIED |
| External target integration | yes | yes | timeout, malformed response, step cap tests | CONTRACT_VERIFIED |
| Agent registry and hashed keys | yes | yes | authenticated registration, rotation, revocation, isolation tests | VERIFIED |
| Agent gateway `eva-agent/1` | yes | yes | TestClient handshake, heartbeat, identity, and synthetic evaluation tests | CONTRACT_VERIFIED |
| Exchange provider boundary | yes | yes | registry seam, normalized provider evidence, and paper-gate tests | CONTRACT_VERIFIED |
| Tamper-evident journal | yes | yes | chain mutation, deletion, reorder, and append tests | VERIFIED |
| Signed certificates | yes | yes | Ed25519 issue, trusted-key verification, attacker-key substitution, root binding, rotation, and revocation tests | TRUST_MODEL_TEST_VERIFIED |
| Pairing bootstrap | yes | yes | pending request, expiry, authorized approval, one-time exchange, and duplicate exchange tests | CONTRACT_VERIFIED |
| Legacy mutation authorization | yes | yes | anonymous fixture policy and protected external, paper, stop, and resume tests | SECURITY_TEST_VERIFIED |
| External HTTP boundary | yes | yes | HTTPS-only validation, destination policy, redirect denial, bounded body, timeout, and DNS pinning tests | SECURITY_TEST_VERIFIED |
| Gateway resource bounds | yes | yes | bounded queues, message size, duplicate session, heartbeat, timeout, and cleanup tests | SECURITY_TEST_VERIFIED |
| Evidence bundle and sharing | yes | yes | owner bundle, opaque share token, explicit public certificate access, and secret exclusion tests | CONTRACT_VERIFIED |
| TypeScript dashboard | yes | yes | `npm test`, `npm run typecheck`, `npm run build` | VERIFIED |
| TypeScript SDK | yes | yes | strict TypeScript compiler check | CONTRACT_VERIFIED |
| Python SDK syntax | yes | yes | targeted `py_compile` | CONTRACT_VERIFIED |
| CLI syntax | yes | yes | `node --check cli/index.mjs` | CONTRACT_VERIFIED |

## Labels

`LIVE_MARKET`, `DEMO_ACCOUNT`, `PAPER_EXECUTION`, `SYNTHETIC_SCENARIO`, `SYNTHETIC_MUTATION`, `DETERMINISTIC_ORACLE`, `LLM_CRITIQUE`, and `UNVERIFIED` are kept separate in stored evidence.

## Commands

```powershell
cd backend
uv sync
uv run pytest test_eva.py -q
cd ..\frontend
npm ci
npm test
npm run typecheck
npm run build
```

The current host resolves Python 3.14.7 through `uv`. The official CLI is installed separately with `npm install -g @bitget-ai/bitget-agent-cli`; Bitget and Qwen runtime evidence remains conditional on credentials and the configured `bgc` executable.

Preflight is a pre-run environment check. Its `paper_run_ready` and compatibility `official_track2_ready` fields do not certify an order. `/runs/{id}/verification` is the post-run acceptance gate and requires persisted market/account evidence, a verified paper order, deterministic reconciliation, and runtime Qwen critic evidence.

The gateway, SDKs, registry, journal, and certificate checks are contract-level evidence. Public production smoke, WSS termination, configured Qwen calls, configured `bgc` calls, and a complete external-agent Bitget PAPER run remain unverified until run in their target environment.

## Phase status

- Phase 2: implemented / test-verified.
- Phase 3: implemented / contract-E2E-verified / external-E2E-pending.
- Phase 4: implemented / onboarding-contract-verified / external-E2E-pending.
- Phase 5: implemented / security-test-verified / production HTTPS and WSS pending.
- Phase 6: implemented / integrity-verified.
- Phase 7: implemented / trust-model-test-verified.
- Phase 8: implemented / local-platform-smoke-verified / final external acceptance pending.
- Phase 1: intentionally deferred to a separate reference-trader service.
- Phase 9 MCP: not implemented.
- Phase 10 x402: not implemented.
