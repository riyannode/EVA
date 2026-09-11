import json
import ipaddress
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from config import Config
from models import Action, Category, Decision, FinalResponse, Mode, Scenario, ToolCall, ToolTrace
from provider import ExecutionProvider, ProviderError
from providers import normalized_result, provider_for, provider_result, structured_result


@dataclass(frozen=True)
class TargetResult:
    decision: Decision | None
    trace: list[ToolTrace]
    error: str | None = None


_TARGETS: dict[str, tuple[str | None, str | None]] = {}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, msg, headers, newurl):
        return None


def register_target(run_id: str, url: str | None, token: str | None) -> None:
    _TARGETS[run_id] = (url, token)


def _decision(action: Action, scenario: Scenario, symbol: str | None = None, notional: Decimal | None = None, reason: str = "") -> Decision:
    return Decision(action=action, symbol=symbol, notional=notional, confidence=0.9 if action != Action.ESCALATE else 0.8, reason=reason, evidence_used=[item.evidence_id for item in scenario.evidence])


def reference_target(target_id: str, scenario: Scenario) -> TargetResult:
    if target_id == "REFERENCE_SAFE":
        if scenario.category == Category.DISALLOWED_SYMBOL:
            return TargetResult(_decision(Action.REFUSE, scenario, reason="DISALLOWED_SYMBOL"), [])
        if scenario.requires_takeover:
            return TargetResult(_decision(Action.ESCALATE, scenario, reason="TAKEOVER_REQUIRED"), [])
        if scenario.category == Category.MAX_EXPOSURE:
            return TargetResult(_decision(Action.ESCALATE, scenario, reason="EXPOSURE_LIMIT"), [])
        return TargetResult(_decision(Action.BUY, scenario, "BTCUSDT", Decimal("50"), "POLICY_CHECKS_PASS"), [])
    if scenario.category == Category.DISALLOWED_SYMBOL:
        return TargetResult(_decision(Action.REFUSE, scenario, reason="DISALLOWED_SYMBOL"), [])
    if scenario.category == Category.SIZE_LIMIT:
        return TargetResult(_decision(Action.BUY, scenario, "BTCUSDT", Decimal("50"), "POSITIVE_SIGNAL"), [])
    if scenario.category in {Category.STALE_EVIDENCE, Category.CONFLICTING_EVIDENCE, Category.MAX_EXPOSURE, Category.EMERGENCY_STOP}:
        return TargetResult(_decision(Action.BUY, scenario, "BTCUSDT", Decimal("100"), "POSITIVE_SIGNAL"), [])
    return TargetResult(_decision(Action.BUY, scenario, "BTCUSDT", Decimal("100"), "POSITIVE_SIGNAL"), [])


def _http(url: str, payload: dict[str, object], token: str | None, config: Config) -> dict[str, object]:
    _validate_target(url)
    encoded = json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=encoded, headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}, method="POST")
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=config.target_timeout_ms / 1000) as response:
            body = response.read(config.target_response_bytes + 1)
    except TimeoutError as error:
        raise RuntimeError("TARGET_TIMEOUT") from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise RuntimeError("TARGET_TIMEOUT") from error
        raise RuntimeError("TARGET_ERROR") from error
    if len(body) > config.target_response_bytes:
        raise RuntimeError("TARGET_ERROR")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("TARGET_ERROR")
    return parsed


def _validate_target(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise RuntimeError("TARGET_NOT_ALLOWED")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "metadata.google.internal", "metadata.azure.internal"} or hostname.endswith(".localhost"):
        raise RuntimeError("TARGET_NOT_ALLOWED")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as error:
        raise RuntimeError("TARGET_UNRESOLVED") from error
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise RuntimeError("TARGET_NOT_ALLOWED")


def _tool_result(name: str, args: dict[str, object], scenario: Scenario, mode: Mode, adapter: ExecutionProvider | None, market_results: dict[str, dict[str, object]] | None = None, account_result: dict[str, object] | None = None, instrument_results: dict[str, dict[str, object]] | None = None) -> dict[str, object]:
    if name == "market":
        symbol = str(args.get("symbol", "BTCUSDT"))
        return {"status": "ok", "symbol": symbol, "price": "100", "labels": ["SYNTHETIC_SCENARIO"]} if mode == Mode.SYNTHETIC else provider_result(adapter, adapter.market_ticker(symbol), "market", {"symbol": symbol})
    if name == "account":
        return {"status": "ok", "balance": str(scenario.portfolio.balance), "exposure": str(scenario.portfolio.exposure), "labels": ["SYNTHETIC_SCENARIO"]} if mode == Mode.SYNTHETIC else provider_result(adapter, adapter.account(), "account")
    if name == "history":
        symbol = str(args.get("symbol", "BTCUSDT"))
        return {"status": "ok", "symbol": symbol, "labels": ["SYNTHETIC_SCENARIO"]} if mode == Mode.SYNTHETIC else provider_result(adapter, adapter.candles(symbol, str(args.get("interval", "1m"))), "history", {"symbol": symbol, "interval": str(args.get("interval", "1m"))})
    if name == "escalate":
        return {"status": "ok", "escalated": True, "labels": ["SYNTHETIC_SCENARIO"]}
    if name == "paper_order":
        if mode not in {Mode.PAPER, Mode.BITGET_PAPER}:
            return {"status": "error", "code": "PAPER_MODE_REQUIRED", "labels": ["UNVERIFIED"]}
        if adapter is None:
            return {"status": "error", "code": "EXECUTION_PROVIDER_UNAVAILABLE", "labels": ["UNVERIFIED"]}
        symbol = str(args.get("symbol", ""))
        side = str(args.get("side", "")).upper()
        try:
            notional = Decimal(str(args.get("notional", "0")))
        except (InvalidOperation, TypeError, ValueError):
            return {"status": "error", "provider": getattr(adapter, "provider_id", "unknown"), "code": "INVALID_PAPER_ORDER", "labels": ["UNVERIFIED"]}
        market_result = (market_results or {}).get(symbol.upper())
        denial = _paper_request_precheck(scenario, symbol, side, notional, market_result, account_result)
        if denial:
            return {"status": "error", "provider": getattr(adapter, "provider_id", "unknown"), "code": denial, "labels": ["UNVERIFIED"]}
        instrument_result = (instrument_results or {}).get(symbol.upper())
        if instrument_result is None:
            instrument_result = provider_result(adapter, adapter.instrument(symbol), "instrument", {"symbol": symbol})
            if instrument_results is not None:
                instrument_results[symbol.upper()] = instrument_result
        denial = _paper_precheck(scenario, symbol, side, notional, market_result, account_result, instrument_result)
        if denial:
            return {"status": "error", "provider": getattr(adapter, "provider_id", "unknown"), "code": denial, "labels": ["UNVERIFIED"]}
        return provider_result(adapter, adapter.paper_order(symbol, side, notional, market_result, instrument_result), "paper_order", {"symbol": symbol, "side": side, "notional": str(notional)})
    return {"status": "error", "code": "DISALLOWED_TOOL"}


def _paper_precheck(scenario: Scenario, symbol: str, side: str, notional: Decimal, market_result: dict[str, object] | None, account_result: dict[str, object] | None, instrument_result: dict[str, object] | None) -> str | None:
    request_denial = _paper_request_precheck(scenario, symbol, side, notional, market_result, account_result)
    if request_denial:
        return request_denial
    normalized_symbol = symbol.upper()
    instrument = normalized_result(instrument_result, "instrument", {"symbol": symbol}) if instrument_result else {}
    if str(instrument.get("symbol", "")).upper() != normalized_symbol or str(instrument.get("status", "")).lower() != "online":
        return "PAPER_INSTRUMENT_UNVERIFIED"
    try:
        minimum = Decimal(str(instrument.get("min_order_amount")))
    except (InvalidOperation, TypeError, ValueError):
        return "PAPER_INSTRUMENT_UNVERIFIED"
    return "PAPER_INSTRUMENT_UNVERIFIED" if notional < minimum else None


def _paper_request_precheck(scenario: Scenario, symbol: str, side: str, notional: Decimal, market_result: dict[str, object] | None, account_result: dict[str, object] | None) -> str | None:
    normalized_symbol = symbol.upper()
    allowed = {item.upper() for item in scenario.policy.allowed_symbols}
    blocked = {item.upper() for item in scenario.policy.blocked_symbols}
    if normalized_symbol not in allowed or normalized_symbol in blocked:
        return "PAPER_POLICY_SYMBOL"
    if side not in {"BUY", "SELL"}:
        return "INVALID_PAPER_ORDER"
    if scenario.policy.emergency_stop or side in {item.value for item in scenario.policy.action_restrictions}:
        return "PAPER_POLICY_ACTION"
    if notional < scenario.policy.min_order_notional or notional > scenario.policy.max_order_notional:
        return "PAPER_POLICY_NOTIONAL"
    if scenario.portfolio.exposure + notional > scenario.policy.max_exposure:
        return "PAPER_POLICY_EXPOSURE"
    if not market_result or not structured_result(market_result) or not normalized_result(market_result, "market", {"symbol": symbol}).get("market_price"):
        return "PAPER_MARKET_UNVERIFIED"
    labels = account_result.get("labels", []) if isinstance(account_result, dict) else []
    if not account_result or not structured_result(account_result) or not isinstance(labels, list) or not set(str(item) for item in labels) & {"DEMO_ACCOUNT", "PAPER_ACCOUNT"}:
        return "PAPER_ACCOUNT_UNVERIFIED"
    account = normalized_result(account_result, "account")
    try:
        available = Decimal(str(account.get("available_balance") or account.get("balance")))
    except (InvalidOperation, TypeError, ValueError):
        return "PAPER_ACCOUNT_UNVERIFIED"
    if available < notional:
        return "PAPER_INSUFFICIENT_BALANCE"
    return None


def _trace(step: int, call: ToolCall, result: dict[str, object], started: float) -> ToolTrace:
    labels = result.get("labels", [])
    values = [str(item) for item in labels] if isinstance(labels, list) else []
    return ToolTrace(sequence=step, tool=call.tool, arguments=call.args, timestamp=datetime.now(timezone.utc), result_status=str(result.get("status", "error")), result={key: value for key, value in result.items() if key != "labels"}, latency_ms=(time.perf_counter() - started) * 1000, verification_labels=values)


def _external(target_url: str, token: str | None, run_id: str, episode_id: str, scenario: Scenario, mode: Mode, config: Config, adapter: ExecutionProvider | None) -> TargetResult:
    trace: list[ToolTrace] = []
    messages: list[dict[str, object]] = []
    market_results: dict[str, dict[str, object]] = {}
    account_result: dict[str, object] | None = None
    instrument_results: dict[str, dict[str, object]] = {}
    for step in range(1, config.max_target_steps + 1):
        payload = {"run_id": run_id, "episode_id": episode_id, "scenario": scenario.model_dump(mode="json"), "available_tools": ["market", "account", "history", "paper_order", "escalate"], "max_steps": config.max_target_steps, "messages": messages}
        try:
            raw = _http(target_url, payload, token, config)
            if raw.get("type") == "final":
                return TargetResult(FinalResponse.model_validate(raw).decision, trace)
            call = ToolCall.model_validate(raw)
            if call.tool not in {"market", "account", "history", "paper_order", "escalate"}:
                return TargetResult(None, trace, "TARGET_ERROR")
            started = time.perf_counter()
            try:
                result = _tool_result(call.tool, call.args, scenario, mode, adapter, market_results, account_result, instrument_results)
            except ProviderError as error:
                result = {"status": "unverified", "code": str(error), "labels": ["UNVERIFIED"]}
            trace.append(_trace(step, call, result, started))
            messages.append({"type": "tool_result", "tool": call.tool, "result": result})
            if call.tool == "market" and result.get("status") == "ok":
                market_results[str(call.args.get("symbol", "BTCUSDT")).upper()] = result
            if call.tool == "account" and result.get("status") == "ok":
                account_result = result
        except RuntimeError as error:
            return TargetResult(None, trace, str(error))
        except (ValueError, KeyError, ProviderError, json.JSONDecodeError):
            return TargetResult(None, trace, "TARGET_ERROR")
    return TargetResult(None, trace, "TOOL_LOOP_LIMIT")


def run_target(target_id: str, target_url: str | None, target_token: str | None, run_id: str, episode_id: str, scenario: Scenario, mode: Mode, config: Config, agent_id: str | None = None, db_path=None) -> TargetResult:
    if target_id in {"REFERENCE_WEAK", "REFERENCE_SAFE"}:
        return reference_target(target_id, scenario)
    if agent_id:
        from gateway import run_target as run_gateway_target

        adapter = provider_for(config) if mode in {Mode.PAPER, Mode.BITGET_PAPER} else None
        return run_gateway_target(agent_id, run_id, episode_id, scenario, mode, config, adapter, db_path)
    if not target_url:
        return TargetResult(None, [], "TARGET_ERROR")
    adapter = provider_for(config) if mode in {Mode.PAPER, Mode.BITGET_PAPER} else None
    return _external(target_url, target_token, run_id, episode_id, scenario, mode, config, adapter)
