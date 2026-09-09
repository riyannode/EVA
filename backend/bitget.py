import json
import re
import subprocess
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Sequence

from config import Config
from models import Mode, VerificationLabel


class BitgetError(RuntimeError):
    pass


_SYMBOL = re.compile(r"^[A-Z0-9._-]{1,40}$")
_ORDER_KEYS = ("orderId", "clientOid")
_PRICE_KEYS = {"lastPr", "lastPrice", "price", "last"}
_PAPER_ORDER_PARAMS = {"category", "symbol", "side", "orderType", "qty"}
_INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1H", "4H", "6H", "12H", "1D"}
_INTERVAL_ALIASES = {"1h": "1H", "4h": "4H", "1d": "1D"}
MAX_ORDER_DETAIL_ATTEMPTS = 3
ORDER_DETAIL_POLL_SECONDS = 0.2
_PENDING_ORDER_STATUSES = {"live", "new", "partially_filled"}


def has_order_reference(value: object) -> bool:
    return order_reference(value) is not None


def order_reference(value: object) -> tuple[str, str] | None:
    if isinstance(value, dict):
        for key in _ORDER_KEYS:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return key, item.strip()
        for key in ("data", "placement", "order_detail"):
            if key in value:
                reference = order_reference(value[key])
                if reference is not None:
                    return reference
    if isinstance(value, list):
        for item in value:
            reference = order_reference(item)
            if reference is not None:
                return reference
    return None


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


def instrument_record(value: object, symbol: str) -> dict[str, object] | None:
    data = value.get("data") if isinstance(value, dict) and "data" in value else value
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    records = data if isinstance(data, list) else [data]
    normalized = symbol.upper()
    for item in records:
        if isinstance(item, dict) and str(item.get("symbol", "")).upper() == normalized and str(item.get("category", "")).upper() == "SPOT":
            return item
    return None


def order_detail_record(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        if "orderStatus" in value:
            return value
        for key in ("data", "order_detail"):
            if key in value:
                record = order_detail_record(value[key])
                if record is not None:
                    return record
    elif isinstance(value, list):
        for item in value:
            record = order_detail_record(item)
            if record is not None:
                return record
    return None


def paper_order_contract_ready(value: dict[str, object] | None) -> bool:
    if not value or not structured_result(value):
        return False
    envelope = value.get("data")
    if not isinstance(envelope, dict):
        return False
    data = envelope.get("data")
    if not isinstance(data, dict) or data.get("tool") != "order" or data.get("action") != "place":
        return False
    required = data.get("required")
    if not isinstance(required, list):
        return False
    names = {item.get("name") for item in required if isinstance(item, dict)}
    return _PAPER_ORDER_PARAMS <= names


def _precision(record: dict[str, object], key: str) -> int | None:
    try:
        value = Decimal(str(record[key]))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return None
    if value < 0 or value != value.to_integral_value():
        return None
    return int(value)


def _amount(record: dict[str, object], key: str) -> Decimal | None:
    try:
        value = Decimal(str(record[key]))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _instrument_constraints(result: dict[str, object] | None, symbol: str) -> tuple[dict[str, object], int, int, Decimal]:
    if result and result.get("status") != "ok" and result.get("code"):
        raise BitgetError(str(result["code"]))
    record = instrument_record(result, symbol) if result and structured_result(result) else None
    quantity_precision = _precision(record, "quantityPrecision") if record else None
    quote_precision = _precision(record, "quotePrecision") if record else None
    minimum = _amount(record, "minOrderAmount") if record else None
    if not record or str(record.get("status", "")).lower() != "online" or quantity_precision is None or quote_precision is None or minimum is None:
        raise BitgetError("PAPER_ORDER_QTY_UNVERIFIED")
    return record, quantity_precision, quote_precision, minimum


def _paper_qty(side: str, notional: Decimal, market_result: dict[str, object] | None, instrument_result: dict[str, object] | None, symbol: str) -> tuple[str, dict[str, object]]:
    record, quantity_precision, quote_precision, minimum = _instrument_constraints(instrument_result, symbol)
    if side == "BUY":
        quantum = Decimal(1).scaleb(-quote_precision)
        quantity = notional.quantize(quantum, rounding=ROUND_DOWN)
        if quantity <= 0 or quantity < minimum:
            raise BitgetError("PAPER_ORDER_QTY_UNVERIFIED")
        return _decimal_text(notional if quantity == notional else quantity), record
    if not market_result or not structured_result(market_result):
        raise BitgetError("PAPER_ORDER_QTY_UNVERIFIED")
    price = market_price(market_result.get("data"))
    if price is None:
        raise BitgetError("PAPER_ORDER_QTY_UNVERIFIED")
    quantity = (notional / price).quantize(Decimal(1).scaleb(-quantity_precision), rounding=ROUND_DOWN)
    if quantity <= 0 or quantity * price < minimum:
        raise BitgetError("PAPER_ORDER_QTY_UNVERIFIED")
    return _decimal_text(quantity), record


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
        interval = _INTERVAL_ALIASES.get(interval, interval)
        if interval not in _INTERVALS:
            raise BitgetError("INVALID_INTERVAL")
        return self._run(["--read-only", "market", "--action", "candles", "--category", "SPOT", "--symbol", self._symbol(symbol), "--interval", interval], [VerificationLabel.LIVE_MARKET.value])

    def instrument(self, symbol: str) -> dict[str, object]:
        return self._run(["--read-only", "market", "--action", "instruments", "--category", "SPOT", "--symbol", self._symbol(symbol)])

    def account(self) -> dict[str, object]:
        mode = "--paper-trading" if self.config.bitget_mode == "paper" else "--read-only"
        result = self._run([mode, "account_overview", "--coin", "USDT"])
        if result.get("status") == "ok" and structured_result(result):
            result["labels"] = [VerificationLabel.DEMO_ACCOUNT.value] if mode == "--paper-trading" else []
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

    def paper_order_detail(self, reference_key: str, reference: str) -> dict[str, object]:
        if reference_key not in _ORDER_KEYS:
            raise BitgetError("PAPER_EXECUTION_NOT_VERIFIED")
        return self._run(["--paper-trading", "order", "--action", "detail", f"--{reference_key}", reference])

    def paper_order(self, symbol: str, side: str, notional: Decimal, market_result: dict[str, object] | None = None, instrument_result: dict[str, object] | None = None) -> dict[str, object]:
        if self.config.bitget_mode != "paper":
            return {"status": "error", "code": "PAPER_MODE_REQUIRED", "labels": [VerificationLabel.UNVERIFIED.value]}
        try:
            notional = Decimal(str(notional))
        except (InvalidOperation, TypeError, ValueError):
            raise BitgetError("INVALID_PAPER_ORDER") from None
        if side not in {"BUY", "SELL"} or notional <= 0:
            raise BitgetError("INVALID_PAPER_ORDER")
        symbol = self._symbol(symbol)
        if instrument_result is None:
            instrument_result = self.instrument(symbol)
        quantity, instrument = _paper_qty(side, notional, market_result, instrument_result, symbol)
        placement = self._run(["--paper-trading", "order", "--action", "place", "--category", "SPOT", "--symbol", symbol, "--side", side.lower(), "--orderType", "market", "--qty", quantity])
        if placement.get("status") != "ok" or not has_order_reference(placement.get("data")):
            placement["status"] = "unverified" if placement.get("status") == "ok" else placement.get("status")
            placement["code"] = placement.get("code") or "PAPER_EXECUTION_NOT_VERIFIED"
            placement["labels"] = [VerificationLabel.UNVERIFIED.value]
            return placement
        reference_pair = order_reference(placement.get("data"))
        reference_key, reference = reference_pair if reference_pair else (None, None)
        if not reference or not reference_key:
            placement["status"] = "unverified"
            placement["code"] = "PAPER_EXECUTION_NOT_VERIFIED"
            placement["labels"] = [VerificationLabel.UNVERIFIED.value]
            return placement
        data = {"placement": placement.get("data"), "order_detail": None, "instrument": instrument}
        for attempt in range(MAX_ORDER_DETAIL_ATTEMPTS):
            detail = self.paper_order_detail(reference_key, reference)
            data["order_detail"] = detail.get("data")
            order = order_detail_record(detail.get("data")) if detail.get("status") == "ok" and structured_result(detail) else None
            if not order:
                break
            status = str(order.get("orderStatus", "")).lower()
            if status == "filled":
                if has_order_reference(order) and order.get(reference_key) == reference:
                    return {"status": "ok", "data": data, "labels": [VerificationLabel.PAPER_EXECUTION.value]}
                break
            if status not in _PENDING_ORDER_STATUSES:
                break
            if attempt + 1 < MAX_ORDER_DETAIL_ATTEMPTS:
                time.sleep(ORDER_DETAIL_POLL_SECONDS)
        return {"status": "unverified", "code": "PAPER_EXECUTION_NOT_VERIFIED", "data": data, "labels": [VerificationLabel.UNVERIFIED.value]}
