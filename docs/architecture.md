# EVA Architecture

## Graph

The backend has one LangGraph `StateGraph`:

`LOAD_RUN -> CHOOSE_SCENARIO -> RUN_TARGET -> RUN_ORACLES -> CRITIC -> SAVE_MEMORY -> ROUTE`

`ROUTE` deterministically chooses `MUTATE`, `HARDER`, or `FINISH`. Failed episodes can mutate the current scenario twice. Three consecutive passes in the same category raise difficulty up to level 5. The episode budget and stop flag always terminate the run.

## Target protocol

External targets receive a POST body containing `run_id`, `episode_id`, the typed scenario, the standardized tool list, `max_steps`, and accumulated tool results. They return either a validated tool call or a validated final decision. Responses have a timeout and byte cap; the tool loop is capped at eight steps. Official paper runs persist declared target name, version, model, and URL; these declarations identify the run but do not prove which model executed remotely.

Reference targets are deliberately small demo fixtures. They demonstrate how EVA detects different behavior and are not trading products.

## Oracles

`oracle.py` owns policy, freshness, sizing, takeover, tool, execution, and consistency checks. Results are `PASS`, `FAIL`, or `NOT_APPLICABLE` and carry machine-readable failure codes. The LLM critic can explain a result but cannot override it.

## Memory

`db.py` stores runs, episodes, events, and target/version-scoped weaknesses in SQLite. Episode JSON includes scenario labels, observable target trace, final decision, oracle results, critic summary, difficulty, model, prompt version, and timestamps. Hidden chain-of-thought is not stored.

## Qwen

`qwen.py` is the only model transport. Scenario output receives Pydantic and semantic validation with one repair retry, then an explicit deterministic fallback. Critique and mutation output are also validated. Qwen is never given Bitget credentials and never calculates readiness.

## Bitget

`bitget.py` invokes a fixed executable with argument arrays and `shell=False`. It exposes `bgc discover`, `market --action tickers|candles|instruments --category SPOT`, `account_overview --coin USDT`, and paper order. Read-only account reads use `--read-only`; paper benchmark account reads and order reads/writes use `--paper-trading`. Instrument metadata is the source of quantity precision, quote precision, minimum quote amount, and online status. A paper BUY maps EVA quote notional to Bitget `qty`; a SELL converts quote notional using same-symbol verified market evidence and instrument quantity precision, failing closed when conversion is unverified. Paper execution is the only Bitget write path; an order is verified only when the CLI response contains `orderId` or `clientOid`, the detail lookup returns the same reference with `orderStatus=filled`, and the deterministic oracle reconciles the target decision. Pending detail states are polled at most three times with a fixed short delay; placement is never retried. The evaluation graph exposes only standardized paper tools to external targets.

## Frontend

The flat React dashboard calls the FastAPI endpoints, opens `/runs/{id}/events` through `EventSource`, and polls once per second as a fallback. It renders text as text and never inserts raw HTML.
