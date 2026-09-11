from datetime import datetime, timezone
from typing import Callable

from bitget import BitgetAdapter, structured_result as bitget_structured_result
from config import Config
from models import ToolTrace
from provider import ExecutionProvider, ProviderError


ProviderFactory = Callable[[Config], ExecutionProvider]
_FACTORIES: dict[str, ProviderFactory] = {"bitget": BitgetAdapter}


def provider_for(config: Config, provider_id: str | None = None) -> ExecutionProvider:
    name = provider_id or config.execution_provider
    factory = _FACTORIES.get(name)
    if factory is None:
        raise ProviderError("UNSUPPORTED_EXECUTION_PROVIDER")
    return factory(config)


def provider_ids() -> list[str]:
    return sorted(_FACTORIES)


def provider_result(provider: ExecutionProvider, value: dict[str, object], tool: str, arguments: dict[str, object] | None = None) -> dict[str, object]:
    result = dict(value)
    provider_id = str(getattr(provider, "provider_id", "unknown"))
    existing = result.get("normalized")
    normalizer = getattr(provider, "normalize_result", None)
    if isinstance(existing, dict) and existing:
        normalized = existing
    elif callable(normalizer):
        normalized = normalizer(result, tool, arguments)
    else:
        normalized = normalized_result(result, tool, arguments)
    result.setdefault("provider", provider_id)
    if isinstance(normalized, dict) and normalized:
        normalized = {**normalized, "provider": normalized.get("provider", provider_id), "tool": normalized.get("tool", tool), "observed_at": normalized.get("observed_at", datetime.now(timezone.utc).isoformat())}
        result["normalized"] = normalized
    return result


def structured_result(value: dict[str, object] | None) -> bool:
    if not isinstance(value, dict):
        return False
    provider = str(value.get("provider", "bitget"))
    if provider == "bitget":
        return bitget_structured_result(value)
    return value.get("status") == "ok" and isinstance(value.get("data"), (dict, list)) and bool(value.get("data"))


def paper_order_contract_ready(value: dict[str, object] | None) -> bool:
    if not structured_result(value):
        return False
    envelope = value.get("data")
    if not isinstance(envelope, dict):
        return False
    contract = envelope.get("data")
    if not isinstance(contract, dict) or contract.get("tool") != "order" or contract.get("action") != "place":
        return False
    required = contract.get("required")
    if not isinstance(required, list):
        return False
    names = {item.get("name") for item in required if isinstance(item, dict)}
    return {"category", "symbol", "side", "orderType", "qty"} <= names


def instrument_ready(value: dict[str, object] | None, symbol: str) -> bool:
    evidence = normalized_result(value, "instrument", {"symbol": symbol})
    return str(evidence.get("symbol", "")).upper() == symbol.upper() and str(evidence.get("status", "")).lower() == "online"


def normalized_evidence(trace: ToolTrace) -> dict[str, object]:
    value = trace.result.get("normalized")
    if isinstance(value, dict):
        return value
    provider = str(trace.result.get("provider", "bitget"))
    if provider == "bitget":
        from bitget import normalize_response

        return normalize_response(trace.result, trace.tool, trace.arguments, trace.timestamp.isoformat())
    return {}


def normalized_result(value: dict[str, object] | None, tool: str, arguments: dict[str, object] | None = None) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    normalized = value.get("normalized")
    if isinstance(normalized, dict):
        return normalized
    provider = str(value.get("provider", "bitget"))
    if provider == "bitget":
        from bitget import normalize_response

        return normalize_response(value, tool, arguments)
    return {}
