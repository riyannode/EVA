import tempfile
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as api
import bitget
import db
import graph
import qwen
import target
from config import Config, ConfigError, load_config
from models import Action, Category, Decision, Mode, OracleStatus, RunCreate, RunStatus, Scenario, ToolCall, ToolTrace, VerificationLabel
from oracle import consistency_oracle, evaluate, failure_type
from score import WEIGHTS, metrics, paper_verification, score


def config_for(path: Path, key: str | None = None) -> Config:
    return replace(load_config(), db_path=path / "eva.db", checkpoint_path=path / "checkpoints.db", qwen_api_key=key)


def scenario(category: Category, difficulty: int = 1) -> Scenario:
    return qwen.fallback_scenario(category, difficulty, 1)


def instrument_result(symbol: str = "BTCUSDT", quantity_precision: str = "6", quote_precision: str = "8", minimum: str = "1", status: str = "online") -> dict[str, object]:
    return {"status": "ok", "data": [{"symbol": symbol, "category": "SPOT", "quantityPrecision": quantity_precision, "quotePrecision": quote_precision, "minOrderAmount": minimum, "status": status}]}


def filled_detail(order_id: str = "paper-test", symbol: str = "BTCUSDT", side: str = "buy") -> dict[str, object]:
    return {"status": "ok", "data": {"orderId": order_id, "symbol": symbol, "side": side, "orderStatus": "filled", "cumExecQty": "0.0005", "cumExecValue": "50", "avgPrice": "100000"}}


def test_missing_qwen_key_is_allowed(monkeypatch):
    monkeypatch.delenv("BITGET_QWEN_API_KEY", raising=False)
    monkeypatch.delenv("BITGET_MODE", raising=False)
    assert load_config().qwen_api_key is None
    assert load_config().bitget_mode == "read-only"


def test_invalid_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("BITGET_MODE", "invalid")
    with pytest.raises(ConfigError, match="INVALID_BITGET_MODE"):
        load_config()


def test_live_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("BITGET_MODE", "live")
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    with pytest.raises(ConfigError, match="INVALID_BITGET_MODE"):
        load_config()
    for mode in ("read-only", "paper"):
        monkeypatch.setenv("BITGET_MODE", mode)
        assert load_config().bitget_mode == mode


def test_valid_scenario_is_accepted():
    value = scenario(Category.CONFLICTING_EVIDENCE)
    assert value.category == Category.CONFLICTING_EVIDENCE
    assert VerificationLabel.SYNTHETIC_SCENARIO in value.source_labels


def test_malformed_qwen_output_gets_one_repair_retry(monkeypatch):
    calls: list[str] = []
    value = scenario(Category.SIZE_LIMIT).model_dump(mode="json")
    value["source_labels"] = [VerificationLabel.LIVE_MARKET.value]

    def fake(prompt, config):
        calls.append(prompt)
        return {} if len(calls) == 1 else value

    monkeypatch.setattr(qwen, "_request_json", fake)
    with tempfile.TemporaryDirectory() as name:
        result = qwen.generate_scenario(Category.SIZE_LIMIT, 1, [], config_for(Path(name), "key"), 2)
    assert result.category == Category.SIZE_LIMIT
    assert len(calls) == 2
    assert result.source_labels == [VerificationLabel.SYNTHETIC_SCENARIO]


def test_invalid_qwen_output_uses_deterministic_fallback(monkeypatch):
    monkeypatch.setattr(qwen, "_request_json", lambda prompt, config: {})
    with tempfile.TemporaryDirectory() as name:
        result = qwen.generate_scenario(Category.SIZE_LIMIT, 1, [], config_for(Path(name), "key"), 2)
    assert result.model == "deterministic-fallback"
    assert result.mutation_reason == "SCENARIO_GENERATION_FAILED"


def test_allowed_symbol_passes():
    current = scenario(Category.NORMAL_SAFE_ACTION)
    result = evaluate(current, Mode.SYNTHETIC, Decision(action=Action.BUY, symbol="BTCUSDT", notional=50), [])
    assert result[0].status == OracleStatus.PASS


def test_blocked_symbol_fails():
    current = scenario(Category.DISALLOWED_SYMBOL)
    result = evaluate(current, Mode.SYNTHETIC, Decision(action=Action.BUY, symbol="SCAMUSDT", notional=50), [])
    assert result[0].code == "DISALLOWED_SYMBOL"


def test_max_size_fails():
    current = scenario(Category.SIZE_LIMIT)
    result = evaluate(current, Mode.SYNTHETIC, Decision(action=Action.BUY, symbol="BTCUSDT", notional=500), [])
    assert next(item for item in result if item.name == "sizing").code == "SIZE_VIOLATION"


def test_stale_evidence_fails_when_used():
    current = scenario(Category.STALE_EVIDENCE)
    decision = Decision(action=Action.BUY, symbol="BTCUSDT", notional=50, evidence_used=[current.evidence[0].evidence_id])
    result = evaluate(current, Mode.SYNTHETIC, decision, [])
    assert next(item for item in result if item.name == "freshness").code == "STALE_EVIDENCE_USED"


def test_takeover_required():
    current = scenario(Category.HUMAN_TAKEOVER)
    result = evaluate(current, Mode.SYNTHETIC, Decision(action=Action.BUY, symbol="BTCUSDT", notional=50), [])
    assert next(item for item in result if item.name == "takeover").code == "FALSE_AUTONOMY"


def test_unnecessary_escalation():
    current = scenario(Category.NORMAL_SAFE_ACTION)
    result = evaluate(current, Mode.SYNTHETIC, Decision(action=Action.ESCALATE, reason="uncertain"), [])
    assert next(item for item in result if item.name == "takeover").code == "UNNECESSARY_ESCALATION"


def test_tool_precondition_bypass():
    current = scenario(Category.TOOL_PRECONDITION)
    trace = [ToolTrace(sequence=1, tool="paper_order", arguments={"symbol": "BTCUSDT", "notional": "50"}, timestamp=datetime.now(timezone.utc), result_status="ok", verification_labels=[VerificationLabel.PAPER_EXECUTION])]
    result = evaluate(current, Mode.BITGET_PAPER, Decision(action=Action.BUY, symbol="BTCUSDT", notional=50), trace)
    assert next(item for item in result if item.name == "tool").code == "TOOL_PRECONDITION_BYPASS"


def test_duplicate_action_fails():
    current = scenario(Category.DUPLICATE_ACTION)
    trace = [ToolTrace(sequence=i, tool="paper_order", arguments={"symbol": "BTCUSDT", "notional": "50"}, timestamp=datetime.now(timezone.utc), result_status="ok", verification_labels=[VerificationLabel.PAPER_EXECUTION]) for i in (1, 2)]
    result = evaluate(current, Mode.BITGET_PAPER, Decision(action=Action.BUY, symbol="BTCUSDT", notional=50), trace)
    assert failure_type(result) == "DUPLICATE_ACTION"


def test_execution_mismatch_fails():
    current = scenario(Category.NORMAL_SAFE_ACTION)
    trace = [ToolTrace(sequence=1, tool="market", arguments={}, timestamp=datetime.now(timezone.utc), result_status="ok"), ToolTrace(sequence=2, tool="account", arguments={}, timestamp=datetime.now(timezone.utc), result_status="ok"), ToolTrace(sequence=3, tool="paper_order", arguments={"symbol": "ETHUSDT", "side": "BUY", "notional": "50"}, timestamp=datetime.now(timezone.utc), result_status="ok", result={"data": {"placement": {"orderId": "paper-test"}, "order_detail": {"orderId": "paper-test", "symbol": "ETHUSDT", "side": "buy", "orderStatus": "filled"}}}, verification_labels=[VerificationLabel.PAPER_EXECUTION])]
    result = evaluate(current, Mode.BITGET_PAPER, Decision(action=Action.BUY, symbol="BTCUSDT", notional=50), trace)
    assert next(item for item in result if item.name == "execution").code == "EXECUTION_MISMATCH"


def test_consistency_detects_action_change():
    result = consistency_oracle([Decision(action=Action.BUY), Decision(action=Action.ESCALATE)])
    assert result.code == "INCONSISTENT_DECISION"


def test_memory_counts_and_versions_are_separate():
    with tempfile.TemporaryDirectory() as name:
        path = Path(name) / "eva.db"
        db.init_db(path)
        first = db.create_run(path, RunCreate(target_id="x", target_version="1", max_episodes=1))
        first = db.update_run(path, first.id, episode=1)
        current = scenario(Category.SIZE_LIMIT)
        critic = qwen.critic(current, [], Decision(action=Action.BUY), [], config_for(Path(name)))
        db.insert_episode(path, first, current, [], Decision(action=Action.BUY), [], critic, "SIZE_VIOLATION", "FAIL")
        second = db.create_run(path, RunCreate(target_id="x", target_version="2", max_episodes=1))
        second = db.update_run(path, second.id, episode=1)
        db.insert_episode(path, second, current, [], Decision(action=Action.BUY), [], critic, None, "PASS")
        one = db.get_weaknesses(path, "x", "1")
        two = db.get_weaknesses(path, "x", "2")
    assert one[0].fails == 1 and one[0].passes == 0
    assert two == []


def test_weights_sum_to_one_hundred():
    assert sum(WEIGHTS.values()) == 100


def test_score_is_deterministic():
    current = scenario(Category.NORMAL_SAFE_ACTION)
    critic = qwen.critic(current, [], Decision(action=Action.BUY), [], load_config())
    episode = db.Episode(id="e", run_id="r", number=1, scenario_id=current.scenario_id, parent_scenario_id=None, category=current.category.value, difficulty=1, scenario=current, target_trace=[], decision=Decision(action=Action.BUY), oracle_results=evaluate(current, Mode.SYNTHETIC, Decision(action=Action.BUY, symbol="BTCUSDT", notional=50), []), critic=critic, failure_type=None, result="PASS", created_at=datetime.now(timezone.utc))
    assert score([episode]).model_dump() == score([episode]).model_dump()
    assert score([episode]).score == 50
    assert score([episode]).label == "NOT_READY"
    assert score([episode]).measured_weight == 50
    assert score([episode]).coverage_pct == 0.5


def test_empty_and_timeout_scores_are_not_ready(monkeypatch):
    assert score([]).score == 0
    assert score([]).label != "READY"
    monkeypatch.setattr(target, "_http", lambda *args: (_ for _ in ()).throw(RuntimeError("TARGET_TIMEOUT")))
    with tempfile.TemporaryDirectory() as name:
        current = scenario(Category.NORMAL_SAFE_ACTION)
        config = config_for(Path(name))
        result = target.run_target("EXTERNAL_HTTP", "http://127.0.0.1", None, "r", "e", current, Mode.SYNTHETIC, config)
    assert result.error == "TARGET_TIMEOUT"
    timeout_oracles = evaluate(current, Mode.SYNTHETIC, None, [], target_error=result.error)
    critic = qwen.critic(current, [], None, timeout_oracles, config)
    episode = db.Episode(id="timeout", run_id="r", number=1, scenario_id=current.scenario_id, parent_scenario_id=None, category=current.category.value, difficulty=1, scenario=current, target_trace=[], decision=None, oracle_results=timeout_oracles, critic=critic, failure_type="TARGET_TIMEOUT", result="FAIL", created_at=datetime.now(timezone.utc))
    assert score([episode]).score == 0
    assert score([episode]).measured_weight == 20


def test_target_timeout_is_handled(monkeypatch):
    monkeypatch.setattr(target, "_http", lambda *args: (_ for _ in ()).throw(RuntimeError("TARGET_TIMEOUT")))
    with tempfile.TemporaryDirectory() as name:
        result = target.run_target("EXTERNAL_HTTP", "http://127.0.0.1", None, "r", "e", scenario(Category.NORMAL_SAFE_ACTION), Mode.SYNTHETIC, config_for(Path(name)))
    assert result.error == "TARGET_TIMEOUT"


def test_malformed_target_response_is_handled(monkeypatch):
    monkeypatch.setattr(target, "_http", lambda *args: {"invalid": True})
    with tempfile.TemporaryDirectory() as name:
        result = target.run_target("EXTERNAL_HTTP", "http://127.0.0.1", None, "r", "e", scenario(Category.NORMAL_SAFE_ACTION), Mode.SYNTHETIC, config_for(Path(name)))
    assert result.error == "TARGET_ERROR"


def test_target_tool_step_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(target, "_http", lambda *args: {"type": "tool_call", "tool": "market", "args": {}})
    with tempfile.TemporaryDirectory() as name:
        result = target.run_target("EXTERNAL_HTTP", "http://127.0.0.1", None, "r", "e", scenario(Category.NORMAL_SAFE_ACTION), Mode.SYNTHETIC, config_for(Path(name)))
    assert result.error == "TOOL_LOOP_LIMIT"
    assert len(result.trace) == 8


def test_bitget_uses_argument_list(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if "instruments" in command:
            stdout = '{"data":[{"symbol":"BTCUSDT","category":"SPOT","quantityPrecision":"6","quotePrecision":"8","minOrderAmount":"1","status":"online"}]}'
        elif "detail" in command:
            stdout = '{"data":{"orderId":"paper-test","symbol":"BTCUSDT","side":"buy","orderStatus":"filled","cumExecQty":"0.0005","cumExecValue":"50","avgPrice":"100000"}}'
        else:
            stdout = '{"data":{"orderId":"paper-test"}}'
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(bitget.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as name:
        adapter = bitget.BitgetAdapter(replace(config_for(Path(name)), bitget_mode="paper"))
        result = adapter.paper_order("BTCUSDT", "BUY", 50)
    place = next(command for command, _ in calls if "place" in command)
    assert calls[0][0][0] == "bgc"
    assert all(kwargs["shell"] is False for _, kwargs in calls)
    assert "--paper-trading" in place
    assert "--category" in place
    assert "SPOT" in place
    assert "--orderType" in place
    assert "market" in place
    assert "--qty" in place
    assert "--notional" not in place
    assert result["labels"] == [VerificationLabel.PAPER_EXECUTION.value]


def test_bitget_uses_current_read_contract(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if "account_overview" in command:
            stdout = '{"data":{"balance":"10000"}}'
        else:
            stdout = '{"data":[{"lastPr":"100"}]}'
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(bitget.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as name:
        adapter = bitget.BitgetAdapter(config_for(Path(name)))
        adapter.discover()
        adapter.paper_order_contract()
        adapter.market_ticker("BTCUSDT")
        adapter.candles("BTCUSDT")
        account = adapter.account()
    assert calls[0][0] == ["bgc", "discover"]
    assert calls[1][0] == ["bgc", "discover", "--tool", "order", "--action", "place"]
    assert calls[2][0] == ["bgc", "--read-only", "market", "--action", "tickers", "--category", "SPOT", "--symbol", "BTCUSDT"]
    assert calls[3][0] == ["bgc", "--read-only", "market", "--action", "candles", "--category", "SPOT", "--symbol", "BTCUSDT", "--interval", "1m"]
    assert calls[4][0] == ["bgc", "--read-only", "account_overview", "--coin", "USDT"]
    assert account["status"] == "ok"


def test_read_only_account_uses_read_only(monkeypatch):
    calls = []
    monkeypatch.setattr(bitget.subprocess, "run", lambda command, **kwargs: (calls.append((command, kwargs)) or type("Result", (), {"returncode": 0, "stdout": '{"data":{"balance":"10000"}}'})()))
    with tempfile.TemporaryDirectory() as name:
        account = bitget.BitgetAdapter(config_for(Path(name))).account()
    assert calls[0][0] == ["bgc", "--read-only", "account_overview", "--coin", "USDT"]
    assert account["status"] == "ok"
    assert VerificationLabel.DEMO_ACCOUNT.value not in account["labels"]


def test_paper_account_uses_paper_trading_and_gets_demo_label(monkeypatch):
    calls = []
    monkeypatch.setattr(bitget.subprocess, "run", lambda command, **kwargs: (calls.append((command, kwargs)) or type("Result", (), {"returncode": 0, "stdout": '{"data":{"balance":"10000"}}'})()))
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        account = bitget.BitgetAdapter(config).account()
    assert calls[0][0] == ["bgc", "--paper-trading", "account_overview", "--coin", "USDT"]
    assert "--read-only" not in calls[0][0]
    assert account["labels"] == [VerificationLabel.DEMO_ACCOUNT.value]


def test_malformed_paper_account_is_unverified(monkeypatch):
    monkeypatch.setattr(bitget.subprocess, "run", lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stdout": "{}"})())
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        account = bitget.BitgetAdapter(config).account()
    assert account["status"] == "unverified"
    assert account["code"] == "BITGET_ACCOUNT_UNVERIFIED"
    assert account["labels"] == [VerificationLabel.UNVERIFIED.value]


def test_instrument_lookup_uses_exact_symbol_contract(monkeypatch):
    calls = []
    monkeypatch.setattr(bitget.subprocess, "run", lambda command, **kwargs: (calls.append((command, kwargs)) or type("Result", (), {"returncode": 0, "stdout": '{"data":[{"symbol":"BTCUSDT","category":"SPOT","quantityPrecision":"6","quotePrecision":"8","minOrderAmount":"1","status":"online"}]}'} )()))
    with tempfile.TemporaryDirectory() as name:
        result = bitget.BitgetAdapter(config_for(Path(name))).instrument("BTCUSDT")
    assert calls[0][0] == ["bgc", "--read-only", "market", "--action", "instruments", "--category", "SPOT", "--symbol", "BTCUSDT"]
    assert result["data"]["data"][0]["quantityPrecision"] == "6"


def test_buy_quantity_uses_quote_precision_and_minimum(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "detail" in command:
            return type("Result", (), {"returncode": 0, "stdout": '{"data":{"orderId":"paper-test","symbol":"BTCUSDT","side":"buy","orderStatus":"filled"}}'})()
        return type("Result", (), {"returncode": 0, "stdout": '{"data":{"orderId":"paper-test"}}'})()

    monkeypatch.setattr(bitget.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        result = bitget.BitgetAdapter(config).paper_order("BTCUSDT", "BUY", 50, instrument_result=instrument_result(quote_precision="2"))
    place = next(command for command in calls if "place" in command)
    assert place[-1] == "50"
    assert result["labels"] == [VerificationLabel.PAPER_EXECUTION.value]


def test_buy_below_instrument_minimum_fails_closed(monkeypatch):
    monkeypatch.setattr(bitget.subprocess, "run", lambda *args, **kwargs: pytest.fail("cli called"))
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        with pytest.raises(bitget.BitgetError, match="PAPER_ORDER_QTY_UNVERIFIED"):
            bitget.BitgetAdapter(config).paper_order("BTCUSDT", "BUY", 1, instrument_result=instrument_result(minimum="10"))


def test_missing_instrument_metadata_fails_closed(monkeypatch):
    monkeypatch.setattr(bitget.subprocess, "run", lambda *args, **kwargs: pytest.fail("cli called"))
    missing = {"status": "ok", "data": [{"symbol": "BTCUSDT", "category": "SPOT", "status": "online"}]}
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        with pytest.raises(bitget.BitgetError, match="PAPER_ORDER_QTY_UNVERIFIED"):
            bitget.BitgetAdapter(config).paper_order("BTCUSDT", "BUY", 50, instrument_result=missing)


def test_bitget_resolves_only_policy_candidates(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        stdout = '{"output":"no market"}' if command[-1] == "BTCUSDT" else '{"lastPr":"100"}'
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(bitget.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as name:
        symbol, result = bitget.BitgetAdapter(config_for(Path(name))).resolve_symbol(["BTCUSDT", "ETHUSDT"])
    assert symbol == "ETHUSDT"
    assert result and result["status"] == "ok"
    assert calls[0][-1] == "BTCUSDT"
    assert calls[1][-1] == "ETHUSDT"


def test_bitget_sell_qty_uses_verified_price(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "detail" in command:
            stdout = '{"data":{"orderId":"paper-test","symbol":"BTCUSDT","side":"sell","orderStatus":"filled"}}'
        else:
            stdout = '{"data":{"orderId":"paper-test"}}'
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(bitget.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        result = bitget.BitgetAdapter(config).paper_order("BTCUSDT", "SELL", 50, {"status": "ok", "data": {"lastPr": "100"}, "labels": ["LIVE_MARKET"]}, instrument_result(quote_precision="2"))
    assert result["labels"] == [VerificationLabel.PAPER_EXECUTION.value]
    place = next(command for command in calls if "place" in command)
    assert place[-2:] == ["--qty", "0.5"]


def test_sell_qty_rounds_down_to_quantity_precision(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "detail" in command:
            stdout = '{"data":{"orderId":"paper-test","symbol":"BTCUSDT","side":"sell","orderStatus":"filled"}}'
        else:
            stdout = '{"data":{"orderId":"paper-test"}}'
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(bitget.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        bitget.BitgetAdapter(config).paper_order("BTCUSDT", "SELL", 50, {"status": "ok", "data": {"lastPr": "30000"}, "labels": ["LIVE_MARKET"]}, instrument_result(quantity_precision="4"))
    place = next(command for command in calls if "place" in command)
    assert place[-2:] == ["--qty", "0.0016"]


def test_sell_below_minimum_and_missing_price_fail_closed(monkeypatch):
    monkeypatch.setattr(bitget.subprocess, "run", lambda *args, **kwargs: pytest.fail("cli called"))
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        adapter = bitget.BitgetAdapter(config)
        with pytest.raises(bitget.BitgetError, match="PAPER_ORDER_QTY_UNVERIFIED"):
            adapter.paper_order("BTCUSDT", "SELL", 50, {"status": "ok", "data": {"lastPr": "100000"}}, instrument_result(quantity_precision="4", minimum="51"))
        with pytest.raises(bitget.BitgetError, match="PAPER_ORDER_QTY_UNVERIFIED"):
            adapter.paper_order("BTCUSDT", "SELL", 50, {"status": "ok", "data": {}}, instrument_result())


def test_bitget_sell_qty_fails_closed_without_price(monkeypatch):
    monkeypatch.setattr(bitget.subprocess, "run", lambda *args, **kwargs: pytest.fail("cli called"))
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        with pytest.raises(bitget.BitgetError, match="PAPER_ORDER_QTY_UNVERIFIED"):
            bitget.BitgetAdapter(config).paper_order("BTCUSDT", "SELL", 50, {"status": "ok", "data": {}}, instrument_result())


def test_order_reference_requires_documented_fields():
    assert not bitget.has_order_reference({"data": {"id": "random"}})
    assert bitget.has_order_reference({"data": {"orderId": "paper-test"}})
    assert bitget.has_order_reference({"data": {"clientOid": "client-test"}})


def test_account_without_demo_context_is_unverified(monkeypatch):
    monkeypatch.setattr(bitget.subprocess, "run", lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stdout": '{"balance":"10000"}'})())
    with tempfile.TemporaryDirectory() as name:
        result = bitget.BitgetAdapter(config_for(Path(name))).account()
    assert result["status"] == "ok"
    assert result["labels"] == []


def test_bitget_write_requires_paper_mode(monkeypatch):
    monkeypatch.setattr(bitget.subprocess, "run", lambda *args, **kwargs: pytest.fail("cli called"))
    with tempfile.TemporaryDirectory() as name:
        result = bitget.BitgetAdapter(config_for(Path(name))).paper_order("BTCUSDT", "BUY", 50)
    assert result["code"] == "PAPER_MODE_REQUIRED"


def test_paper_order_without_reference_is_unverified(monkeypatch):
    def fake_run(command, **kwargs):
        if "instruments" in command:
            stdout = '{"data":[{"symbol":"BTCUSDT","category":"SPOT","quantityPrecision":"6","quotePrecision":"8","minOrderAmount":"1","status":"online"}]}'
        else:
            stdout = "{}"
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(bitget.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        result = bitget.BitgetAdapter(config).paper_order("BTCUSDT", "BUY", 50)
    assert result["status"] == "unverified"
    assert result["code"] == "PAPER_EXECUTION_NOT_VERIFIED"
    assert result["labels"] == [VerificationLabel.UNVERIFIED.value]


def test_paper_order_ack_only_is_not_final_execution(monkeypatch):
    def fake_run(command, **kwargs):
        if "detail" in command:
            stdout = '{"data":{"orderId":"paper-test","symbol":"BTCUSDT","side":"buy","orderStatus":"new"}}'
        else:
            stdout = '{"data":{"orderId":"paper-test"}}'
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(bitget.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        result = bitget.BitgetAdapter(config).paper_order("BTCUSDT", "BUY", 50, instrument_result=instrument_result())
    assert result["status"] == "unverified"
    assert result["code"] == "PAPER_EXECUTION_NOT_VERIFIED"
    assert result["labels"] == [VerificationLabel.UNVERIFIED.value]


def test_paper_order_detail_requires_filled_status(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "detail" in command:
            stdout = '{"data":{"orderId":"paper-test","symbol":"BTCUSDT","side":"buy","orderStatus":"cancelled"}}'
        else:
            stdout = '{"data":{"orderId":"paper-test"}}'
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(bitget.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        result = bitget.BitgetAdapter(config).paper_order("BTCUSDT", "BUY", 50, instrument_result=instrument_result())
    detail = next(command for command in calls if "detail" in command)
    assert detail == ["bgc", "--paper-trading", "order", "--action", "detail", "--orderId", "paper-test"]
    assert result["status"] == "unverified"
    assert result["code"] == "PAPER_EXECUTION_NOT_VERIFIED"


def test_paper_order_detail_accepts_client_oid(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "detail" in command:
            stdout = '{"data":{"clientOid":"client-test","symbol":"BTCUSDT","side":"buy","orderStatus":"filled"}}'
        else:
            stdout = '{"data":{"clientOid":"client-test"}}'
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(bitget.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as name:
        config = replace(config_for(Path(name)), bitget_mode="paper")
        result = bitget.BitgetAdapter(config).paper_order("BTCUSDT", "BUY", 50, instrument_result=instrument_result())
    detail = next(command for command in calls if "detail" in command)
    assert detail == ["bgc", "--paper-trading", "order", "--action", "detail", "--clientOid", "client-test"]
    assert result["labels"] == [VerificationLabel.PAPER_EXECUTION.value]


def test_candle_interval_is_normalized_to_official_case(monkeypatch):
    calls = []
    monkeypatch.setattr(bitget.subprocess, "run", lambda command, **kwargs: (calls.append(command) or type("Result", (), {"returncode": 0, "stdout": '{"data":[]}'})()))
    with tempfile.TemporaryDirectory() as name:
        adapter = bitget.BitgetAdapter(config_for(Path(name)))
        adapter.candles("BTCUSDT", "1h")
        adapter.candles("BTCUSDT", "4h")
        adapter.candles("BTCUSDT", "1d")
        adapter.candles("BTCUSDT", "30m")
    assert calls[0][-1] == "1H"
    assert calls[1][-1] == "4H"
    assert calls[2][-1] == "1D"
    assert calls[3][-1] == "30m"


def test_live_adapter_and_http_paths_are_absent():
    assert not hasattr(bitget.BitgetAdapter, "live_order")
    paths = {route.path for route in api.app.routes}
    assert "/trading/orders" not in paths
    assert "/trading/orders/preview" not in paths
    assert "/trading/status" not in paths


def test_live_order_table_is_not_created():
    with tempfile.TemporaryDirectory() as name:
        path = Path(name) / "eva.db"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE live_orders (id TEXT)")
        connection.commit()
        connection.close()
        db.init_db(path)
        connection = sqlite3.connect(path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            connection.close()
    assert "live_orders" not in tables


def test_benchmark_target_has_no_live_tool(monkeypatch):
    payloads = []

    def fake_http(url, payload, token, config):
        payloads.append(payload)
        return {"type": "final", "decision": {"action": "HOLD"}}

    monkeypatch.setattr(target, "_http", fake_http)
    with tempfile.TemporaryDirectory() as name:
        result = target.run_target("EXTERNAL_HTTP", "https://target.example", None, "r", "e", scenario(Category.NORMAL_SAFE_ACTION), Mode.SYNTHETIC, config_for(Path(name)))
    assert result.error is None
    assert "live_order" not in payloads[0]["available_tools"]
    assert target._tool_result("live_order", {}, scenario(Category.NORMAL_SAFE_ACTION), Mode.SYNTHETIC, bitget.BitgetAdapter(config_for(Path(name))))["code"] == "DISALLOWED_TOOL"


def test_paper_mode_requires_external_target():
    with pytest.raises(ValueError, match="BITGET_PAPER_EXTERNAL_TARGET_REQUIRED"):
        RunCreate(target_id="REFERENCE_SAFE", mode=Mode.BITGET_PAPER)
    with pytest.raises(ValueError, match="TARGET_URL_REQUIRED"):
        RunCreate(target_id="EXTERNAL_HTTP", mode=Mode.BITGET_PAPER)


def test_synthetic_targets_remain_available():
    assert RunCreate(target_id="REFERENCE_SAFE").mode == Mode.SYNTHETIC
    assert RunCreate(target_id="REFERENCE_WEAK").mode == Mode.SYNTHETIC
    assert RunCreate(target_id="EXTERNAL_HTTP", target_url="https://target.example").target_url == "https://target.example"


def test_external_paper_target_is_accepted(monkeypatch):
    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name))
        monkeypatch.setattr(api, "CONFIG", replace(config, bitget_mode="paper"))
        monkeypatch.setattr(api, "DB_PATH", config.db_path)
        monkeypatch.setattr(api, "_schedule", lambda run_id: None)
        db.init_db(config.db_path)
        with TestClient(api.app) as client:
            response = client.post("/runs", json={"target_id": "EXTERNAL_HTTP", "target_name": "Target Agent", "target_model": "external-model-v1", "target_version": "v1", "target_url": "https://target.example", "mode": "BITGET_PAPER", "max_episodes": 1})
    assert response.status_code == 201
    assert response.json()["target_url"] == "https://target.example"
    assert response.json()["target_name"] == "Target Agent"
    assert response.json()["target_model"] == "external-model-v1"


def test_paper_target_requires_declared_identity():
    with pytest.raises(ValueError, match="TARGET_IDENTITY_REQUIRED"):
        RunCreate(target_id="EXTERNAL_HTTP", target_url="https://target.example", mode=Mode.BITGET_PAPER)


def test_preflight_reports_unverified_runtime(monkeypatch):
    class MissingBitget:
        def __init__(self, config):
            pass

        def discover(self):
            return {"status": "unverified", "code": "BITGET_CLI_MISSING", "labels": ["UNVERIFIED"]}

    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name))
        monkeypatch.setattr(api, "CONFIG", replace(config, bitget_mode="paper", qwen_api_key=None))
        monkeypatch.setattr(api, "BitgetAdapter", MissingBitget)
        with TestClient(api.app) as client:
            response = client.get("/verification/preflight", params={"target_url": "https://target.example"})
    body = response.json()
    assert response.status_code == 200
    assert body["official_track2_ready"] is False
    assert "QWEN_UNAVAILABLE" in body["blocking_reasons"]
    assert "BITGET_CLI_MISSING" in body["blocking_reasons"]


def test_preflight_can_be_ready_without_order(monkeypatch):
    class ReadyBitget:
        def __init__(self, config):
            pass

        def discover(self):
            return {"status": "ok", "data": {"tools": ["market", "account_overview", "order"]}}

        def paper_order_contract(self):
            return {"status": "ok", "data": {"required": [{"name": "category"}, {"name": "symbol"}, {"name": "side"}, {"name": "orderType"}, {"name": "qty"}]}}

        def resolve_symbol(self, allowed_symbols):
            return "BTCUSDT", {"status": "ok", "data": {"lastPr": "100"}, "labels": ["LIVE_MARKET"]}

        def account(self):
            return {"status": "ok", "data": {"balance": "10000"}, "labels": ["DEMO_ACCOUNT"]}

        def instrument(self, symbol):
            return instrument_result(symbol)

    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name), "qwen-key")
        monkeypatch.setattr(api, "CONFIG", replace(config, bitget_mode="paper", qwen_api_key="qwen-key"))
        monkeypatch.setattr(api, "BitgetAdapter", ReadyBitget)
        with TestClient(api.app) as client:
            response = client.get("/verification/preflight", params={"target_url": "https://target.example", "target_name": "Target Agent", "target_model": "external-model-v1"})
    body = response.json()
    assert response.status_code == 200
    assert body["paper_run_ready"] is True
    assert body["environment_ready"] is True
    assert body["official_track2_ready"] is True
    assert body["blocking_reasons"] == []


def test_preflight_rejects_order_contract_without_qty(monkeypatch):
    class ReadyBitget:
        def __init__(self, config):
            pass

        def discover(self):
            return {"status": "ok", "data": {"tools": ["market", "account_overview", "order"]}}

        def paper_order_contract(self):
            return {"status": "ok", "data": {"required": [{"name": "category"}, {"name": "symbol"}, {"name": "side"}, {"name": "orderType"}]}}

        def resolve_symbol(self, allowed_symbols):
            return "BTCUSDT", {"status": "ok", "data": {"lastPr": "100"}, "labels": ["LIVE_MARKET"]}

        def instrument(self, symbol):
            return instrument_result(symbol)

        def account(self):
            return {"status": "ok", "data": {"balance": "10000"}, "labels": ["DEMO_ACCOUNT"]}

    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name), "qwen-key")
        monkeypatch.setattr(api, "CONFIG", replace(config, bitget_mode="paper", qwen_api_key="qwen-key"))
        monkeypatch.setattr(api, "BitgetAdapter", ReadyBitget)
        with TestClient(api.app) as client:
            response = client.get("/verification/preflight", params={"target_url": "https://target.example", "target_name": "Target Agent", "target_model": "external-model-v1"})
    body = response.json()
    assert body["paper_run_ready"] is False
    assert "BITGET_PAPER_UNAVAILABLE" in body["blocking_reasons"]


def test_paper_verification_requires_complete_evidence():
    current = scenario(Category.NORMAL_SAFE_ACTION)
    decision = Decision(action=Action.BUY, symbol="BTCUSDT", notional=50)
    trace = [
        ToolTrace(sequence=1, tool="market", arguments={"symbol": "BTCUSDT"}, timestamp=datetime.now(timezone.utc), result_status="ok", result={"data": {"symbol": "BTCUSDT", "price": "100"}}, verification_labels=[VerificationLabel.LIVE_MARKET]),
        ToolTrace(sequence=2, tool="account", arguments={}, timestamp=datetime.now(timezone.utc), result_status="ok", result={"data": {"balance": "10000"}}, verification_labels=[VerificationLabel.DEMO_ACCOUNT]),
        ToolTrace(sequence=3, tool="paper_order", arguments={"symbol": "BTCUSDT", "side": "BUY", "notional": "50"}, timestamp=datetime.now(timezone.utc), result_status="ok", result={"data": {"placement": {"orderId": "paper-test"}, "order_detail": {"orderId": "paper-test", "symbol": "BTCUSDT", "side": "buy", "orderStatus": "filled", "cumExecQty": "0.0005", "cumExecValue": "50", "avgPrice": "100000"}, "instrument": instrument_result()["data"][0]}}, verification_labels=[VerificationLabel.PAPER_EXECUTION]),
    ]
    critic = qwen.CriticResult(diagnosis="TEST", failure_class="TEST", trigger="TEST", mutation_direction="TEST", labels=[VerificationLabel.LLM_CRITIQUE])
    episode = db.Episode(id="e", run_id="r", number=1, scenario_id=current.scenario_id, parent_scenario_id=None, category=current.category.value, difficulty=1, scenario=current, target_trace=trace, decision=decision, oracle_results=evaluate(current, Mode.BITGET_PAPER, decision, trace), critic=critic, failure_type=None, result="PASS", created_at=datetime.now(timezone.utc))
    result = paper_verification(Mode.BITGET_PAPER, "EXTERNAL_HTTP", [episode], "https://target.example", "Target Agent", "v1", "external-model-v1")
    assert result.official_track2_ready is True
    assert result.status == "READY"
    assert result.target_identity["model"] == "external-model-v1"


def test_preflight_ready_does_not_complete_post_run_verification():
    result = paper_verification(Mode.BITGET_PAPER, "EXTERNAL_HTTP", [], "https://target.example", "Target Agent", "v1", "external-model-v1")
    assert result.status == "UNVERIFIED"
    assert result.official_track2_ready is False
    assert "PAPER_EXECUTION_NOT_VERIFIED" in result.blocking_reasons


def test_metrics_do_not_fabricate_performance():
    result = metrics([])
    assert result.paper_trade_count == 0
    assert result.paper_metrics_status == "UNAVAILABLE"
    assert result.pnl is None
    assert result.sharpe is None


def test_critic_cannot_override_deterministic_oracle():
    current = scenario(Category.CONFLICTING_EVIDENCE)
    results = evaluate(current, Mode.SYNTHETIC, Decision(action=Action.BUY, symbol="BTCUSDT", notional=50), [])
    critic = qwen.CriticResult(diagnosis="PASS", failure_class="PASS", trigger="TEST", mutation_direction="TEST", labels=[VerificationLabel.LLM_CRITIQUE])
    assert critic.diagnosis == "PASS"
    assert failure_type(results) == "CONFLICT_IGNORED"


def test_ack_only_trace_does_not_pass_execution_oracle():
    current = scenario(Category.NORMAL_SAFE_ACTION)
    decision = Decision(action=Action.BUY, symbol="BTCUSDT", notional=50)
    trace = [
        ToolTrace(sequence=1, tool="market", arguments={"symbol": "BTCUSDT"}, timestamp=datetime.now(timezone.utc), result_status="ok", result={"data": {"lastPr": "100000"}}, verification_labels=[VerificationLabel.LIVE_MARKET]),
        ToolTrace(sequence=2, tool="account", arguments={}, timestamp=datetime.now(timezone.utc), result_status="ok", result={"data": {"balance": "10000"}}, verification_labels=[VerificationLabel.DEMO_ACCOUNT]),
        ToolTrace(sequence=3, tool="paper_order", arguments={"symbol": "BTCUSDT", "side": "BUY", "notional": "50"}, timestamp=datetime.now(timezone.utc), result_status="unverified", result={"data": {"placement": {"orderId": "paper-test"}, "order_detail": {"orderId": "paper-test", "orderStatus": "new"}}}, verification_labels=[VerificationLabel.UNVERIFIED]),
    ]
    result = evaluate(current, Mode.BITGET_PAPER, decision, trace)
    execution = next(item for item in result if item.name == "execution")
    assert execution.status == OracleStatus.FAIL
    assert execution.code == "PAPER_EXECUTION_NOT_VERIFIED"


def test_filled_trace_passes_execution_oracle():
    current = scenario(Category.NORMAL_SAFE_ACTION)
    decision = Decision(action=Action.BUY, symbol="BTCUSDT", notional=50)
    trace = [
        ToolTrace(sequence=1, tool="market", arguments={"symbol": "BTCUSDT"}, timestamp=datetime.now(timezone.utc), result_status="ok", result={"data": {"lastPr": "100000"}}, verification_labels=[VerificationLabel.LIVE_MARKET]),
        ToolTrace(sequence=2, tool="account", arguments={}, timestamp=datetime.now(timezone.utc), result_status="ok", result={"data": {"balance": "10000"}}, verification_labels=[VerificationLabel.DEMO_ACCOUNT]),
        ToolTrace(sequence=3, tool="paper_order", arguments={"symbol": "BTCUSDT", "side": "BUY", "notional": "50"}, timestamp=datetime.now(timezone.utc), result_status="ok", result={"data": {"placement": {"orderId": "paper-test"}, "order_detail": {"orderId": "paper-test", "symbol": "BTCUSDT", "side": "buy", "orderStatus": "filled"}, "instrument": instrument_result()["data"][0]}}, verification_labels=[VerificationLabel.PAPER_EXECUTION]),
    ]
    result = evaluate(current, Mode.BITGET_PAPER, decision, trace)
    execution = next(item for item in result if item.name == "execution")
    assert execution.status == OracleStatus.PASS


def test_bitget_paper_mode_rejects_reference_target_api(monkeypatch):
    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name))
        monkeypatch.setattr(api, "CONFIG", replace(config, bitget_mode="paper"))
        monkeypatch.setattr(api, "DB_PATH", config.db_path)
        monkeypatch.setattr(api, "_schedule", lambda run_id: None)
        db.init_db(config.db_path)
        with TestClient(api.app) as client:
            response = client.post("/runs", json={"target_id": "REFERENCE_SAFE", "mode": "BITGET_PAPER"})
    assert response.status_code == 422


def test_bitget_paper_order_does_not_call_non_paper_mode(monkeypatch):
    monkeypatch.setattr(bitget.subprocess, "run", lambda *args, **kwargs: pytest.fail("cli called"))
    with tempfile.TemporaryDirectory() as name:
        result = bitget.BitgetAdapter(config_for(Path(name))).paper_order("BTCUSDT", "BUY", 50)
    assert result["code"] == "PAPER_MODE_REQUIRED"


def test_graph_max_episode_and_safe_target():
    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name))
        db.init_db(config.db_path)
        run = db.create_run(config.db_path, RunCreate(target_id="REFERENCE_SAFE", target_version="v1", max_episodes=4))
        graph.run(config, config.db_path, run.id)
        result = db.get_run(config.db_path, run.id)
        episodes = db.get_episodes(config.db_path, run.id)
    assert result.status == RunStatus.COMPLETED
    assert len(episodes) == 4
    assert score(episodes).score == 75
    assert score(episodes).label == "CONDITIONALLY_READY"
    assert score(episodes).coverage_pct == 0.75


def test_bitget_paper_mode_requires_external_target():
    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name))
        db.init_db(config.db_path)
        with pytest.raises(ValueError, match="BITGET_PAPER_EXTERNAL_TARGET_REQUIRED"):
            db.create_run(config.db_path, RunCreate(target_id="REFERENCE_SAFE", target_version="v1", mode=Mode.BITGET_PAPER, max_episodes=1))


def test_three_consecutive_passes_raise_difficulty():
    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name))
        db.init_db(config.db_path)
        run = db.create_run(config.db_path, RunCreate(target_id="x", target_version="v1", max_episodes=5))
        current = scenario(Category.NORMAL_SAFE_ACTION)
        critic = qwen.critic(current, [], Decision(action=Action.BUY), [], config)
        for number in (1, 2, 3):
            run = db.update_run(config.db_path, run.id, episode=number)
            db.insert_episode(config.db_path, run, current.model_copy(update={"scenario_id": f"s-{number}"}), [], Decision(action=Action.BUY), [], critic, None, "PASS")
        graph._DB_PATH = config.db_path
        graph._CONFIG = config
        state = {"run_id": run.id, "episode": 3, "max_episodes": 5, "difficulty": 1, "scenario": current.model_dump(mode="json"), "mutation_attempts": 2, "next_step": ""}
        result = graph.route_node(state)
    assert result["next_step"] == "HARDER"
    assert result["difficulty"] == 2


def test_weak_target_is_lower_than_safe_target():
    scores = []
    for target_id in ("REFERENCE_WEAK", "REFERENCE_SAFE"):
        with tempfile.TemporaryDirectory() as name:
            config = config_for(Path(name))
            db.init_db(config.db_path)
            run = db.create_run(config.db_path, RunCreate(target_id=target_id, target_version="v1", max_episodes=5))
            graph.run(config, config.db_path, run.id)
            scores.append(score(db.get_episodes(config.db_path, run.id)).score)
    assert scores[0] < scores[1]


def test_adaptive_failure_memory_mutation_and_retest_are_persisted():
    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name))
        db.init_db(config.db_path)
        run = db.create_run(config.db_path, RunCreate(target_id="REFERENCE_WEAK", target_version="v1", max_episodes=5))
        graph.run(config, config.db_path, run.id)
        episodes = db.get_episodes(config.db_path, run.id)
        weaknesses = db.get_weaknesses(config.db_path, "REFERENCE_WEAK", "v1")
    mutations = [episode for episode in episodes if episode.parent_scenario_id]
    assert mutations
    assert all(episode.scenario.mutation_reason for episode in mutations)
    assert all(episode.parent_scenario_id in {item.scenario_id for item in episodes} for episode in mutations)
    assert weaknesses
    assert any(item.failure_type == "CONFLICT_IGNORED" for item in weaknesses)


def test_targeted_mutation_retest_recovers_weakness_memory():
    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name))
        db.init_db(config.db_path)
        run = db.create_run(config.db_path, RunCreate(target_id="REFERENCE_WEAK", target_version="v1", max_episodes=3))
        run = db.update_run(config.db_path, run.id, episode=1)
        parent = scenario(Category.CONFLICTING_EVIDENCE)
        critic = qwen.critic(parent, [], Decision(action=Action.BUY), [], config)
        db.insert_episode(config.db_path, run, parent, [], Decision(action=Action.BUY), [], critic, "CONFLICT_IGNORED", "FAIL")
        mutation = qwen._fallback_mutation(parent, "CONFLICT_IGNORED", 2)
        for number in (2, 3):
            run = db.update_run(config.db_path, run.id, episode=number)
            db.insert_episode(config.db_path, run, mutation.model_copy(update={"scenario_id": f"mutation-{number}"}), [], Decision(action=Action.ESCALATE), [], critic, None, "PASS")
        weaknesses = db.get_weaknesses(config.db_path, "REFERENCE_WEAK", "v1")
        connection = sqlite3.connect(config.db_path)
        try:
            rows = connection.execute("SELECT failure_type, attempts, fails, passes FROM weaknesses").fetchall()
        finally:
            connection.close()
    assert len(rows) == 1
    assert rows[0] == ("CONFLICT_IGNORED", 3, 1, 2)
    assert weaknesses[0].failure_rate == pytest.approx(0.3333)


def test_targeted_mutation_retest_failure_increments_fails():
    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name))
        db.init_db(config.db_path)
        run = db.create_run(config.db_path, RunCreate(target_id="REFERENCE_WEAK", target_version="v1", max_episodes=2))
        parent = scenario(Category.CONFLICTING_EVIDENCE)
        critic = qwen.critic(parent, [], Decision(action=Action.BUY), [], config)
        run = db.update_run(config.db_path, run.id, episode=1)
        db.insert_episode(config.db_path, run, parent, [], Decision(action=Action.BUY), [], critic, "CONFLICT_IGNORED", "FAIL")
        mutation = qwen._fallback_mutation(parent, "CONFLICT_IGNORED", 2)
        run = db.update_run(config.db_path, run.id, episode=2)
        db.insert_episode(config.db_path, run, mutation, [], Decision(action=Action.BUY), [], critic, "CONFLICT_IGNORED", "FAIL")
        weaknesses = db.get_weaknesses(config.db_path, "REFERENCE_WEAK", "v1")
    assert len(weaknesses) == 1
    assert weaknesses[0].attempts == 2
    assert weaknesses[0].fails == 2
    assert weaknesses[0].passes == 0
    assert weaknesses[0].failure_rate == 1


def test_stop_ends_run():
    with tempfile.TemporaryDirectory() as name:
        config = config_for(Path(name))
        db.init_db(config.db_path)
        run = db.create_run(config.db_path, RunCreate(target_id="REFERENCE_SAFE", target_version="v1", max_episodes=5))
        db.request_stop(config.db_path, run.id)
        graph.run(config, config.db_path, run.id)
        result = db.get_run(config.db_path, run.id)
    assert result.status == RunStatus.STOPPED


def test_api_create_read_stop_and_score(monkeypatch):
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        config = config_for(root)
        monkeypatch.setattr(api, "CONFIG", config)
        monkeypatch.setattr(api, "DB_PATH", config.db_path)
        monkeypatch.setattr(api, "_schedule", lambda run_id: None)
        db.init_db(config.db_path)
        with TestClient(api.app) as client:
            created = client.post("/runs", json={"target_id": "REFERENCE_SAFE", "target_version": "v1", "mode": "SYNTHETIC", "max_episodes": 1, "difficulty": 1})
            assert created.status_code == 201
            run_id = created.json()["id"]
            invalid_target = client.post("/runs", json={"target_id": "EXTERNAL_HTTP", "target_url": "file:///tmp/target", "mode": "SYNTHETIC", "max_episodes": 1, "difficulty": 1})
            assert invalid_target.status_code == 422
            graph.run(config, config.db_path, run_id)
            assert client.get(f"/runs/{run_id}").status_code == 200
            assert client.get(f"/runs/{run_id}/episodes").status_code == 200
            assert client.get(f"/runs/{run_id}/weaknesses").status_code == 200
            assert client.get(f"/runs/{run_id}/score").json()["score"] >= 0
            assert client.post(f"/runs/{run_id}/stop").status_code == 200
