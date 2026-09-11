import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import websockets


@dataclass(frozen=True)
class AgentIdentity:
    name: str
    version: str
    model: str


class EvaluationContext:
    def __init__(self, scenario: dict[str, Any], request_tool: Callable[[str, dict[str, Any]], Awaitable[Any]]) -> None:
        self.scenario = scenario
        self._request_tool = request_tool

    async def request(self, tool: str, args: dict[str, Any] | None = None) -> Any:
        return await self._request_tool(tool, args or {})


class EvaAgent:
    def __init__(self, api_key: str, agent_id: str, gateway_url: str, reconnect_attempts: int = 3, reconnect_delay: float = 0.5, heartbeat_seconds: float = 15) -> None:
        self.api_key = api_key
        self.agent_id = agent_id
        self.gateway_url = gateway_url
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.heartbeat_seconds = heartbeat_seconds
        self._socket = None
        self._pending: tuple[str, asyncio.Future[Any]] | None = None
        self._closed = False

    async def connect(self, identity: AgentIdentity, decide: Callable[[EvaluationContext], Any]) -> None:
        attempts = 0
        while not self._closed:
            try:
                async with websockets.connect(self.gateway_url, additional_headers={"Authorization": f"Bearer {self.api_key}"}, max_size=65536) as socket:
                    self._socket = socket
                    await self._send({"type": "hello", "agent_id": self.agent_id, "protocol": "eva-agent/1", "capabilities": ["market", "account", "history", "paper_order", "escalate"], "agent": {"name": identity.name, "version": identity.version, "model": identity.model}})
                    ready = await socket.recv()
                    message = self._parse(ready)
                    if message.get("type") != "ready" or message.get("status") != "ONLINE":
                        raise RuntimeError("HANDSHAKE_FAILED")
                    attempts = 0
                    await self._serve(socket, decide)
            except Exception:
                if self._closed or attempts >= self.reconnect_attempts:
                    raise
                await asyncio.sleep(self.reconnect_delay * 2**attempts)
                attempts += 1

    async def close(self) -> None:
        self._closed = True
        if self._socket:
            await self._socket.close()

    async def _serve(self, socket, decide: Callable[[EvaluationContext], Any]) -> None:
        heartbeat = asyncio.create_task(self._heartbeat())
        try:
            async for raw in socket:
                message = self._parse(raw)
                message_type = message.get("type")
                if message_type == "ping":
                    await self._send({"type": "pong", **({"nonce": message["nonce"]} if isinstance(message.get("nonce"), str) else {})})
                elif message_type == "tool_result":
                    self._resolve_tool(message)
                elif message_type == "scenario":
                    scenario = message.get("scenario")
                    if not isinstance(scenario, dict):
                        await self._send({"type": "error", "code": "INVALID_MESSAGE"})
                    else:
                        await self._finalize(decide, scenario)
                else:
                    raise RuntimeError("INVALID_MESSAGE")
        finally:
            heartbeat.cancel()

    async def _finalize(self, decide: Callable[[EvaluationContext], Any], scenario: dict[str, Any]) -> None:
        try:
            value = decide(EvaluationContext(scenario, self._request_tool))
            decision = await value if asyncio.iscoroutine(value) else value
            if not isinstance(decision, dict) or not isinstance(decision.get("action"), str):
                raise ValueError("INVALID_DECISION")
            await self._send({"type": "final", "decision": decision})
        except Exception:
            await self._send({"type": "error", "code": "DECISION_FAILED"})

    async def _request_tool(self, tool: str, args: dict[str, Any]) -> Any:
        if self._pending:
            raise RuntimeError("TOOL_REQUEST_ACTIVE")
        future = asyncio.get_running_loop().create_future()
        self._pending = (tool, future)
        await self._send({"type": "tool_call", "tool": tool, "args": args})
        try:
            return await asyncio.wait_for(future, 30)
        finally:
            self._pending = None

    def _resolve_tool(self, message: dict[str, Any]) -> None:
        if not self._pending or message.get("tool") != self._pending[0]:
            raise RuntimeError("TOOL_RESULT_MISMATCH")
        future = self._pending[1]
        if not future.done():
            future.set_result(message.get("result"))

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            await self._send({"type": "ping"})

    async def _send(self, value: dict[str, Any]) -> None:
        if not self._socket:
            raise RuntimeError("AGENT_OFFLINE")
        await self._socket.send(json.dumps(value, separators=(",", ":")))

    @staticmethod
    def _parse(raw: Any) -> dict[str, Any]:
        value = json.loads(raw if isinstance(raw, str) else raw.decode())
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise RuntimeError("INVALID_MESSAGE")
        return value
