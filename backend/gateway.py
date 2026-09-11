import time
import json
from dataclasses import dataclass, field
from queue import Empty, Full, Queue
from threading import Lock
from typing import Any

from config import Config
from models import AgentStatus, FinalResponse, Mode, Scenario, ToolCall, ToolTrace
from provider import ProviderError


class GatewayError(RuntimeError):
    pass


@dataclass
class Session:
    agent_id: str
    connection_id: str
    inbound: Queue[dict[str, Any]] = field(default_factory=Queue)
    outbound: Queue[dict[str, Any]] = field(default_factory=lambda: Queue(maxsize=32))
    evaluation_active: bool = False
    closed: bool = False
    last_seen: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    def expired(self, timeout: float) -> bool:
        return time.monotonic() - self.last_seen > timeout

    def send(self, message: dict[str, Any]) -> None:
        if self.closed:
            raise GatewayError("AGENT_OFFLINE")
        try:
            self.outbound.put(message, timeout=1)
        except Full as error:
            raise GatewayError("GATEWAY_BACKPRESSURE") from error

    def receive(self, timeout: float) -> dict[str, Any]:
        if self.closed:
            raise GatewayError("AGENT_OFFLINE")
        try:
            value = self.inbound.get(timeout=timeout)
        except Empty as error:
            raise GatewayError("TARGET_TIMEOUT") from error
        if not isinstance(value, dict):
            raise GatewayError("INVALID_MESSAGE")
        return value


class GatewayRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    def connect(self, agent_id: str, connection_id: str) -> Session:
        with self._lock:
            previous = self._sessions.get(agent_id)
            if previous and not previous.closed:
                raise GatewayError("AGENT_ALREADY_CONNECTED")
            session = Session(agent_id=agent_id, connection_id=connection_id)
            self._sessions[agent_id] = session
            return session

    def disconnect(self, session: Session) -> None:
        with self._lock:
            session.closed = True
            if self._sessions.get(session.agent_id) is session:
                self._sessions.pop(session.agent_id, None)

    def get(self, agent_id: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(agent_id)
            return session if session and not session.closed else None

    def claim(self, agent_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(agent_id)
            if not session or session.closed:
                raise GatewayError("AGENT_OFFLINE")
            if session.evaluation_active:
                raise GatewayError("EVALUATION_ALREADY_ACTIVE")
            session.evaluation_active = True
            return session

    def release(self, session: Session) -> None:
        with self._lock:
            session.evaluation_active = False


registry = GatewayRegistry()


def connection_id() -> str:
    from auth import issue_id

    return issue_id("conn")


def hello_matches(agent, hello: dict[str, Any]) -> bool:
    if hello.get("type") != "hello" or hello.get("agent_id") != agent.agent_id or hello.get("protocol") != agent.protocol_version:
        return False
    identity = hello.get("agent")
    return isinstance(identity, dict) and identity.get("name") == agent.name and identity.get("version") == agent.version and identity.get("model") == agent.declared_model


def ready_message(session: Session) -> dict[str, str]:
    return {"type": "ready", "connection_id": session.connection_id, "status": AgentStatus.ONLINE.value}


def handle_client_message(session: Session, message: object) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        raise GatewayError("INVALID_MESSAGE")
    if len(json.dumps(message, separators=(",", ":"))) > 65536:
        raise GatewayError("MESSAGE_TOO_LARGE")
    session.touch()
    message_type = message.get("type")
    if message_type == "ping":
        response = {"type": "pong"}
        if "nonce" in message:
            response["nonce"] = message["nonce"]
        return response
    if message_type == "pong":
        return None
    session.inbound.put(message)
    return None


def poll_outbound(session: Session) -> dict[str, Any] | None:
    try:
        return session.outbound.get(timeout=1)
    except Empty:
        return None


def run_target(session_agent_id: str, run_id: str, episode_id: str, scenario: Scenario, mode: Mode, config: Config, adapter, db_path):
    from target import TargetResult, _tool_result, _trace

    session = registry.claim(session_agent_id)
    db_module = __import__("db")
    db_module.set_agent_status(db_path, session_agent_id, AgentStatus.EVALUATING)
    trace: list[ToolTrace] = []
    market_results: dict[str, dict[str, object]] = {}
    account_result: dict[str, object] | None = None
    instrument_results: dict[str, dict[str, object]] = {}
    try:
        session.send({"type": "scenario", "evaluation_id": run_id, "episode_id": episode_id, "scenario": scenario.model_dump(mode="json"), "available_tools": ["market", "account", "history", "paper_order", "escalate"], "max_steps": config.max_target_steps})
        for step in range(1, config.max_target_steps + 1):
            message = session.receive(config.target_timeout_ms / 1000)
            if message.get("type") == "ping":
                session.send({"type": "pong", **({"nonce": message["nonce"]} if "nonce" in message else {})})
                continue
            if message.get("type") == "final":
                return TargetResult(FinalResponse.model_validate(message).decision, trace)
            call = ToolCall.model_validate(message)
            if call.tool not in {"market", "account", "history", "paper_order", "escalate"}:
                return TargetResult(None, trace, "DISALLOWED_TOOL")
            started = time.perf_counter()
            try:
                result = _tool_result(call.tool, call.args, scenario, mode, adapter, market_results, account_result, instrument_results)
            except ProviderError as error:
                result = {"status": "unverified", "code": str(error), "labels": ["UNVERIFIED"]}
            trace.append(_trace(step, call, result, started))
            session.send({"type": "tool_result", "tool": call.tool, "result": result})
            if call.tool == "market" and result.get("status") == "ok":
                market_results[str(call.args.get("symbol", "BTCUSDT")).upper()] = result
            if call.tool == "account" and result.get("status") == "ok":
                account_result = result
        return TargetResult(None, trace, "TOOL_LOOP_LIMIT")
    except GatewayError as error:
        return TargetResult(None, trace, str(error))
    except (ValueError, KeyError) as error:
        return TargetResult(None, trace, "INVALID_MESSAGE")
    finally:
        registry.release(session)
        if not session.closed:
            db_module.set_agent_status(db_path, session_agent_id, AgentStatus.ONLINE)
