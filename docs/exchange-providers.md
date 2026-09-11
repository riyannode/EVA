# Exchange provider boundary

EVA treats an exchange as an execution provider, not as part of an agent's identity. The evaluator, gateway, scoring, weakness memory, journal, certificates, SDK protocol, and dashboard consume provider-neutral fields.

## Current contract

`backend/provider.py` defines the narrow `ExecutionProvider` contract:

- `provider_id()` metadata through `provider_id`
- `capabilities()`
- `discover()`
- `market_ticker(symbol)`
- `candles(symbol, interval)`
- `instrument(symbol)`
- `account()`
- `paper_order(...)`
- `paper_order_detail(reference_key, reference)`
- `resolve_symbol(allowed_symbols)`

`backend/providers.py` owns the provider registry. `BitgetAdapter` is registered as `bitget`; no evaluator node imports or constructs it directly.

Provider adapters own raw response parsing. A result carries `provider` and `normalized` evidence when available. The normalized fields used by EVA include `symbol`, `market_price`, `observed_at`, `account_mode`, `balance`, `available_balance`, `status`, `quantity_precision`, `min_order_amount`, `reference`, `order_status`, `executed_quantity`, `executed_value`, `average_price`, and `fee`.

## Compatibility

`BITGET_PAPER` remains a readable historical mode. New paper evaluations can use the generic `PAPER` mode and persist `execution_provider`, while old records are not renamed or rewritten. Synthetic evaluations do not require an execution provider.

Agent registration accepts optional `execution_providers` and `provider_capabilities`. These fields describe the agent's declared support; they do not grant credentials or execution access. An agent may declare one provider, several providers, or none.

## Adding a future provider

The intended change is bounded to:

1. implement an adapter for the contract;
2. normalize its raw responses inside that adapter;
3. register its factory in `backend/providers.py`;
4. add adapter and capability tests;
5. enable it through `EVA_EXECUTION_PROVIDER` or an evaluation's `execution_provider`.

The LangGraph flow, deterministic oracles, prompts, scoring, journal, certificates, gateway messages, SDKs, registry, and dashboard do not need an exchange-specific rewrite. The current test suite includes a fake provider registry selection test as an architecture seam; it does not connect to a real second exchange.

## Safety boundary

Only Bitget's configured paper adapter currently implements execution-backed placement. The pre-execution gate runs before `paper_order`, requires normalized market/account/instrument evidence, and returns a structured denial without invoking the adapter when policy or evidence checks fail. Live orders, withdrawals, transfers, and real-money execution are outside the contract.
