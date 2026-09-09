# Hackathon Submission Draft

## Thesis

EVA autonomously red-teams trading agents before capital does. It tests whether an agent respects policy, uses fresh evidence, sizes actions safely, avoids duplicate execution, and hands control back to a human when uncertainty requires it.

## Target user

Trading-agent developers, financial-AI deployment teams, exchanges and agent platforms, and operators deciding whether an agent is ready for more autonomy.

## Validation

The reference weak and safe targets run through the same adaptive benchmark. Deterministic oracles expose objective failures; SQLite memory persists them per target version; mutations retest the observed weakness; and the fixed weighted score produces a reproducible readiness label.

## Progress

V1 includes the typed backend contracts, SQLite records, LangGraph loop, Qwen transport and fallback, HTTP target contract, reference targets, paper and gated live Bitget adapters, FastAPI API, live event stream, and React console. Qwen and Bitget execution evidence are conditional on configured credentials/tools and are not claimed without runtime evidence.

## Deliverables

- Standalone EVA repository.
- Synthetic weak-versus-safe demo.
- `SYNTHETIC` and `BITGET_PAPER` mode switch.
- Deterministic oracle and readiness evidence.
- Flat dashboard for runs, episodes, score, and weaknesses.

## LLM role

Qwen powers structured scenario generation, qualitative failure diagnosis, and targeted adversarial mutation. Pydantic validation, policy checks, freshness, sizing, tool-use, takeover, execution, consistency, and readiness scoring remain deterministic.
