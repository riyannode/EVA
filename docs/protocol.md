# EVA agent protocol

The gateway protocol version is `eva-agent/1`. The REST API remains the canonical control-plane contract; this WebSocket is the live evaluation transport.

## Handshake

The client connects to `/v1/agent/connect` with an agent API key and sends:

```json
{
  "type": "hello",
  "agent_id": "agt_xxx",
  "protocol": "eva-agent/1",
  "capabilities": ["market", "account", "history", "paper_order", "escalate"],
  "agent": {"name": "TraderX", "version": "1.0.0", "model": "model-v1"}
}
```

EVA validates the key, agent ownership, protocol, and registered identity before returning:

```json
{"type":"ready","connection_id":"conn_xxx","status":"ONLINE"}
```

Identity metadata is not an authorization grant. Exchange credentials remain inside EVA.

## Evaluation messages

EVA sends `scenario` with `evaluation_id`, `episode_id`, typed scenario data, standardized tools, and `max_steps`. The client sends a `tool_call`:

```json
{"type":"tool_call","tool":"market","args":{"symbol":"BTCUSDT"}}
```

EVA answers with `tool_result`. The client finishes with a typed `final` decision. Allowed tools are `market`, `account`, `history`, `paper_order`, and `escalate`. `paper_order` is accepted only in a paper evaluation and is gated before the provider adapter is called.

Both sides may send `ping` and must answer with `pong`, preserving a string `nonce` when provided. Invalid messages return an error or close the session. The server caps each message at 64 KiB, each episode at the configured tool-step limit, each outbound queue at 32 messages, and each tool wait at the target timeout.

The server rejects a second active connection for the same agent and allows one active evaluation per agent. A disconnected session returns the run to a non-evaluating connection state; clients may reconnect with bounded SDK retries.

## Close behavior

The implementation uses close codes for invalid authentication (`4401`), denied agent access (`4403`), invalid handshake/message (`4400`), duplicate or rate-limited connection (`4429`), and heartbeat timeout (`4408`). Clients should treat a close as a reconnect condition only within their configured retry budget.

## Evidence

Every accepted gateway tool call becomes a target trace and journal lineage event. Provider results retain raw source data where available and expose normalized semantics for deterministic oracle checks. The gateway never sends Bitget credentials or raw provider secrets to the external agent.
