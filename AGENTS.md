# EVA Repository Instructions

- Read `docs/PRODUCT_PRD.md` before planning or implementing product changes. It is the product source of truth.
- Inspect the current implementation before making changes.
- Treat the PRD roadmap as separate from implemented state. Never claim a roadmap feature is implemented without code and runtime evidence.
- Preserve these permanent boundaries:
  - EVA = evaluator, adversarial scenario engine, deterministic oracle, weakness memory, execution verifier, and evidence/certificate authority.
  - External Trader = autonomous decision-maker and target under evaluation.
  - Qwen = scenario generation, qualitative diagnosis, and targeted mutation only.
  - Qwen must never own PASS/FAIL, readiness score, execution authority, or policy authority.
  - LangGraph = orchestration/state-machine layer.
  - Agent Gateway = transport layer.
  - MCP = adapter layer.
  - x402 = payment/access layer.
- Do not turn EVA into a trading strategy, portfolio manager, alpha marketplace, generic backtester, autonomous execution bot, or BitgetBench clone.
- Follow minimal targeted changes, inspect before modification, verify actual execution where relevant, and do not implement adjacent roadmap phases without explicit scope.
