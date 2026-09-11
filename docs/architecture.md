# EVA Architecture

## Graph

The backend has one LangGraph `StateGraph`:

`LOAD_RUN -> CHOOSE_SCENARIO -> RUN_TARGET -> RUN_ORACLES -> CRITIC -> SAVE_MEMORY -> ROUTE`

`ROUTE` deterministically chooses `MUTATE`, `HARDER`, or `FINISH`. Failed episodes can mutate the current scenario twice. Three consecutive passes in the same category raise difficulty up to level 5. The episode budget and stop flag always terminate the run.

## Target protocol

External targets receive a POST body containing `run_id`, `episode_id`, the typed scenario, the standardized tool list, `max_steps`, and accumulated tool results. They return either a validated tool call or a validated final decision. Responses have a timeout and byte cap; the tool loop is capped at eight steps. Official paper runs persist declared target name, version, model, and URL; these declarations identify the run but do not prove which model executed remotely.

Reference targets are deliberately small demo fixtures. They demonstrate how EVA detects different behavior and are not trading products.

## Agent gateway

The preferred external-agent path is an authenticated outbound WebSocket at `/v1/agent/connect`. `gateway.py` owns connection sessions, bounded queues, heartbeat handling, message validation, and one-active-evaluation claims. `app.py` owns the HTTP authentication and lifecycle route. Gateway tool requests are routed through the existing target tool path, so deterministic oracles, scoring, Qwen critique, weakness memory, and curriculum are not duplicated for connected agents.

The gateway protocol is documented in [protocol.md](protocol.md). Public deployment requires HTTPS/WSS; local HTTP/WS is only for private development.

## Oracles

`oracle.py` owns policy, freshness, sizing, takeover, tool, execution, and consistency checks. Results are `PASS`, `FAIL`, or `NOT_APPLICABLE` and carry machine-readable failure codes. The LLM critic can explain a result but cannot override it.

## Memory

`db.py` stores runs, episodes, events, and target/version-scoped weaknesses in SQLite. Episode JSON includes scenario labels, observable target trace, final decision, oracle results, critic summary, difficulty, model, prompt version, and timestamps. Hidden chain-of-thought is not stored.

## Qwen

`qwen.py` is the only model transport. Scenario output receives Pydantic and semantic validation with one repair retry, then an explicit deterministic fallback. Critique and mutation output are also validated. Qwen is never given Bitget credentials and never calculates readiness.

Local `prompts.py` constructs `eva-scenario:v2`, `eva-critic:v2`, and `eva-mutation:v2` with `langchain_core.prompts.ChatPromptTemplate`. Rendered system/user messages go directly to the existing OpenAI-compatible Responses client. Pydantic validates JSON; LangGraph owns curriculum and SQLite retains memory/checkpoints. Qwen creates, explains, and mutates tests. Deterministic code grades them. The external target remains the trader.

Runtime inputs use sorted compact JSON in user messages and are explicitly untrusted. The critic explains observed traces and cannot replace deterministic failure codes. Mutation must retain its parent category and supplied difficulty; code assigns provenance and identifiers. Repair receives invalid output and its error type, with exactly one repair attempt before fallback.

Prompt builders receive evaluation data only, never configuration objects or bearer tokens. Weakness input is projected to failure type, category, attempts, fails, passes and failure rate. Offline tests cover deterministic rendering, injection placement, secret exclusion, semantic rejection and fallback. These tests do not establish prompt-injection immunity or real model quality. QWEN PROMPT RUNTIME: UNVERIFIED until real Qwen calls are evaluated.

LangSmith is not used by EVA V1. No remote prompts, tracing, Prompt Hub or LangSmith configuration is used. `langchain-core` was already a LangGraph transitive dependency and is now explicitly pinned for prompt construction; its transitive packages do not constitute an EVA integration.

## Exchange providers

EVA's evaluator depends on the `ExecutionProvider` contract and the provider registry rather than a concrete exchange adapter. Bitget is registered as the first provider. Raw provider responses can remain in source evidence, while normalized fields are consumed by pre-execution gates, execution checks, and scoring. Agent identity accepts optional provider metadata and is not coupled to one venue. See [exchange-providers.md](exchange-providers.md).

## Bitget

`bitget.py` invokes a fixed executable with argument arrays and `shell=False`. It exposes `bgc discover`, `market --action tickers|candles|instruments --category SPOT`, `account_overview --coin USDT`, and paper order. Read-only account reads use `--read-only`; paper benchmark account reads and order reads/writes use `--paper-trading`. Instrument metadata is the source of quantity precision, quote precision, minimum quote amount, and online status. A paper BUY maps EVA quote notional to Bitget `qty`; a SELL converts quote notional using same-symbol verified market evidence and instrument quantity precision, failing closed when conversion is unverified. Paper execution is the only Bitget write path; an order is verified only when the CLI response contains `orderId` or `clientOid`, the detail lookup returns the same reference with `orderStatus=filled`, and the deterministic oracle reconciles the target decision. Pending detail states are polled at most three times with a fixed short delay; placement is never retried. The evaluation graph exposes only standardized paper tools to external targets.

## Frontend

The flat React dashboard calls the FastAPI endpoints, opens `/runs/{id}/events` through `EventSource`, and polls once per second as a fallback. It renders text as text and never inserts raw HTML.
