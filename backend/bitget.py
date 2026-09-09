import json
import re
import subprocess
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Sequence

from config import Config
from models import Mode, VerificationLabel


class BitgetError(RuntimeError):
    pass


_SYMBOL = re.compile(r"^[A-Z0-9._-]{1,40}$")
_ORDER_KEYS = {"orderId", "clientOid"}
_PRICE_KEYS = {"lastPr", "lastPrice", "price", "last"}
_STEP_KEYS = {"baseIncrement", "baseSizeIncrement", "qtyStep", "quantityStep"}
_MIN_QTY_KEYS = {"minQty", "minOrderQty", "minTradeQty"}


def has_order_reference(value: object) -> bool:
    if isinstance(value, dict):
        return any(key in value and isinstance(value[key], str) and bool(value[key].strip()) for key in _ORDER_KEYS) or any(has_order_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(has_order_reference(item) for item in value)
    return False


def structured_result(result: dict[str, object]) -> bool:
    data = result.get("data")
    return result.get("status") == "ok" and isinstance(data, (dict, list)) and bool(data) and not (isinstance(data, dict) and "output" in data)


def _decimal_field(value: object, keys: set[str]) -> Decimal | None:
    if isinstance(value, dict):
        for key in keys:
            if key in value:
                try:
                    result = Decimal(str(value[key]))
                except (InvalidOperation, ValueError, TypeError):
                    result = None
                if result is not None and result > 0:
                    return result
        for item in value.values():
            result = _decimal_field(item, keys)
            if result is not None:
                return result
    elif isinstance(value, list):
        for item in value:
            result = _decimal_field(item, keys)
            if result is not None:
                return result
    return None


def market_price(value: object) -> Decimal | None:
    return _decimal_field(value, _PRICE_KEYS)


def _demo_account_context(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("_", "")
            if normalized in {"isdemo", "ispapertrading"} and item is True:
                return True
            if normalized in {"environment", "env", "accounttype", "mode", "tradingmode", "papertrading"} and isinstance(item, str) and item.lower() in {"demo", "paper", "paper-trading", "simulated", "simulation"}:
                return True
            if _demo_account_context(item):
                return True
    elif isinstance(value, list):
        return any(_demo_account_context(item) for item in value)
    return False


def _paper_qty(side: str, notional: Decimal, market_result: dict[str, object] | None) -> str:
    if side == "BUY":
        return format(notional, "f")
    if not market_result or not structured_result(market_result):
        raise BitgetError("PAPER_ORDER_QTY_UNVERIFIED")
    price = market_price(market_result.get("data"))
    if price is None:
        raise BitgetError("PAPER_ORDER_QTY_UNVERIFIED")
    quantity = notional / price
    step = _decimal_field(market_result.get("data"), _STEP_KEYS)
    if step is not None:
        quantity = (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step
    minimum = _decimal_field(market_result.get("data"), _MIN_QTY_KEYS)
    if quantity <= 0 or minimum is not None and quantity < minimum:
        raise BitgetError("PAPER_ORDER_QTY_UNVERIFIED")
    return format(quantity, "f")


class BitgetAdapter:
    def __init__(self, config: Config):
        self.config = config

    def _run(self, args: Sequence[str], labels: list[str] | None = None) -> dict[str, object]:
        command = [self.config.bitget_executable, *args]
        try:
            result = subprocess.run(command, shell=False, capture_output=True, text=True, timeout=10, check=False)
        except FileNotFoundError:
            return {"status": "unverified", "code": "BITGET_CLI_MISSING", "labels": [VerificationLabel.UNVERIFIED.value]}
        except subprocess.TimeoutExpired:
            return {"status": "unverified", "code": "BITGET_TIMEOUT", "labels": [VerificationLabel.UNVERIFIED.value]}
        if result.returncode != 0:
            return {"status": "error", "code": "BITGET_COMMAND_FAILED", "labels": [VerificationLabel.UNVERIFIED.value]}
        raw = result.stdout[:200000]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"output": raw[:1000]}
        return {"status": "ok", "data": data, "labels": labels or []}

    @staticmethod
    def _symbol(value: str) -> str:
        value = value.upper()
        if not _SYMBOL.fullmatch(value):
            raise BitgetError("INVALID_SYMBOL")
        return value

    def discover(self) -> dict[str, object]:
        return self._run(["discover"])

    def paper_order_contract(self) -> dict[str, object]:
        return self._run(["discover", "--tool", "order", "--action", "place"])

    def market_ticker(self, symbol: str) -> dict[str, object]:
        return self._run(["--read-only", "market", "--action", "tickers", "--category", "SPOT", "--symbol", self._symbol(symbol)], [VerificationLabel.LIVE_MARKET.value])

    def candles(self, symbol: str, interval: str = "1m") -> dict[str, object]:
        if interval not in {"1m", "5m", "15m", "1h", "4h", "1d"}:
            raise BitgetError("INVALID_INTERVAL")
        return self._run(["--read-only", "market", "--action", "candles", "--category", "SPOT", "--symbol", self._symbol(symbol), "--interval", interval], [VerificationLabel.LIVE_MARKET.value])

    def account(self) -> dict[str, object]:
        result = self._run(["--read-only", "account_overview", "--coin", "USDT"])
        if result.get("status") == "ok" and _demo_account_context(result.get("data")):
            result["labels"] = [VerificationLabel.DEMO_ACCOUNT.value]
        elif result.get("status") == "ok":
            result["status"] = "unverified"
            result["code"] = "BITGET_ACCOUNT_UNVERIFIED"
            result["labels"] = [VerificationLabel.UNVERIFIED.value]
        return result

    def resolve_symbol(self, allowed_symbols: Sequence[str]) -> tuple[str | None, dict[str, object] | None]:
        last_result: dict[str, object] | None = None
        for candidate in allowed_symbols:
            symbol = self._symbol(str(candidate))
            result = self.market_ticker(symbol)
            last_result = result
            if structured_result(result):
                return symbol, result
        return None, last_result

    def paper_order(self, symbol: str, side: str, notional: Decimal, market_result: dict[str, object] | None = None) -> dict[str, object]:
        if self.config.bitget_mode != "paper":
            return {"status": "error", "code": "PAPER_MODE_REQUIRED", "labels": [VerificationLabel.UNVERIFIED.value]}
        if side not in {"BUY", "SELL"} or notional <= 0:
            raise BitgetError("INVALID_PAPER_ORDER")
        quantity = _paper_qty(side, notional, market_result)
        result = self._run(["--paper-trading", "order", "--action", "place", "--category", "SPOT", "--symbol", self._symbol(symbol), "--side", side.lower(), "--orderType", "market", "--qty", quantity])
        if result.get("status") == "ok" and not has_order_reference(result.get("data")):
            result["status"] = "unverified"
            result["code"] = "PAPER_EXECUTION_NOT_VERIFIED"
        result["labels"] = [VerificationLabel.PAPER_EXECUTION.value] if result.get("status") == "ok" else [VerificationLabel.UNVERIFIED.value]
        return result
