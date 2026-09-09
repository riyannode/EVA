import json
import re
import subprocess
from decimal import Decimal
from typing import Sequence

from config import Config
from models import Mode, VerificationLabel


class BitgetError(RuntimeError):
    pass


_SYMBOL = re.compile(r"^[A-Z0-9._-]{1,40}$")
_ORDER_KEYS = {"id", "orderId", "order_id", "clientOid", "client_order_id"}


def has_order_reference(value: object) -> bool:
    if isinstance(value, dict):
        return any(key in value and value[key] for key in _ORDER_KEYS) or any(has_order_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(has_order_reference(item) for item in value)
    return False


def discovered_symbols(value: object) -> list[str]:
    symbols: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for key in {"symbol", "symbolName", "instId", "instrument"}:
                candidate = item.get(key)
                if isinstance(candidate, str):
                    symbol = candidate.upper()
                    if _SYMBOL.fullmatch(symbol) and symbol not in symbols:
                        symbols.append(symbol)
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return symbols


class BitgetAdapter:
    def __init__(self, config: Config):
        self.config = config

    def _run(self, args: Sequence[str]) -> dict[str, object]:
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
        return {"status": "ok", "data": data, "labels": [VerificationLabel.LIVE_MARKET.value]}

    @staticmethod
    def _symbol(value: str) -> str:
        if not _SYMBOL.fullmatch(value):
            raise BitgetError("INVALID_SYMBOL")
        return value

    def discover(self) -> dict[str, object]:
        return self._run(["--read-only", "market", "--action", "instruments"])

    def market_ticker(self, symbol: str) -> dict[str, object]:
        return self._run(["--read-only", "market", "--action", "tickers", "--symbol", self._symbol(symbol)])

    def candles(self, symbol: str, interval: str = "1m") -> dict[str, object]:
        if interval not in {"1m", "5m", "15m", "1h", "4h", "1d"}:
            raise BitgetError("INVALID_INTERVAL")
        return self._run(["--read-only", "market", "--action", "candles", "--symbol", self._symbol(symbol), "--interval", interval])

    def account(self) -> dict[str, object]:
        result = self._run(["--read-only", "account", "--action", "overview"])
        if result.get("status") == "ok":
            result["labels"] = [VerificationLabel.DEMO_ACCOUNT.value]
        return result

    def paper_order(self, symbol: str, side: str, notional: Decimal) -> dict[str, object]:
        if self.config.bitget_mode != "paper":
            return {"status": "error", "code": "PAPER_MODE_REQUIRED", "labels": [VerificationLabel.UNVERIFIED.value]}
        if side not in {"BUY", "SELL"} or notional <= 0:
            raise BitgetError("INVALID_PAPER_ORDER")
        result = self._run(["--paper-trading", "order", "--action", "place", "--symbol", self._symbol(symbol), "--side", side, "--notional", format(notional, "f")])
        if result.get("status") == "ok" and not has_order_reference(result.get("data")):
            result["status"] = "unverified"
            result["code"] = "PAPER_EXECUTION_NOT_VERIFIED"
        result["labels"] = [VerificationLabel.PAPER_EXECUTION.value] if result.get("status") == "ok" else [VerificationLabel.UNVERIFIED.value]
        return result
