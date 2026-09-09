# EVA Architecture

## Graph

The backend has one LangGraph `StateGraph`:

`LOAD_RUN -> CHOOSE_SCENARIO -> RUN_TARGET -> RUN_ORACLES -> CRITIC -> SAVE_MEMORY -> ROUTE`

`ROUTE` deterministically chooses `MUTATE`, `HARDER`, or `FINISH`. Failed episodes can mutate the current scenario twice. Three consecutive passes in the same category raise difficulty up to level 5. The episode budget and stop flag always terminate the run.

## Target protocol

External targets receive a POST body containing `run_id`, `episode_id`, the typed scenario, the standardized tool list, `max_steps`, and accumulated tool results. They return either a validated tool call or a validated final decision. Responses have a timeout and byte cap; the tool loop is capped at eight steps.

Reference targets are deliberately small demo fixtures. They demonstrate how EVA detects different behavior and are not trading products.

## Oracles

`oracle.py` owns policy, freshness, sizing, takeover, tool, execution, and consistency checks. Results are `PASS`, `FAIL`, or `NOT_APPLICABLE` and carry machine-readable failure codes. The LLM critic can explain a result but cannot override it.

## Memory

`db.py` stores runs, episodes, events, and target/version-scoped weaknesses in SQLite. Episode JSON includes scenario labels, observable target trace, final decision, oracle results, critic summary, difficulty, model, prompt version, and timestamps. Hidden chain-of-thought is not stored.

## Qwen

`qwen.py` is the only model transport. Scenario output receives Pydantic and semantic validation with one repair retry, then an explicit deterministic fallback. Critique and mutation output are also validated. Qwen is never given Bitget credentials and never calculates readiness.

## Bitget

`bitget.py` invokes a fixed executable with argument arrays and `shell=False`. It exposes discovery, market ticker, candles, account overview, and paper order. Paper execution is the only Bitget write path; an order is verified only when the CLI response contains an order reference. The evaluation graph exposes only standardized paper tools to external targets.

## Frontend

The flat React dashboard calls the FastAPI endpoints, opens `/runs/{id}/events` through `EventSource`, and polls once per second as a fallback. It renders text as text and never inserts raw HTML.
