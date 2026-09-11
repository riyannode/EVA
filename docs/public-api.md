# Public API surface

## Control plane

- `POST /v1/agents` registers an agent and returns a one-time API key.
- `GET /v1/agents/{agent_id}` reads authenticated agent state.
- `GET /v1/agents/{agent_id}/onboarding` returns connection instructions without returning a key.
- `POST /v1/agents/{agent_id}/keys` rotates a key and returns the replacement once.
- `DELETE /v1/agents/{agent_id}/keys/{key_id}` revokes a key.

Registration requires the configured control-plane bearer token. Agent reads and key operations require the agent key or the authorized control-plane token.

## Gateway evaluations

- `POST /v1/evaluations` starts a gateway evaluation for an authenticated connected agent.
- `GET /v1/evaluations/{evaluation_id}` reads status.
- `GET /v1/evaluations/{evaluation_id}/score` reads deterministic score.
- `GET /v1/evaluations/{evaluation_id}/evidence` reads trace and journal validity.
- `GET /v1/evaluations/{evaluation_id}/journal` reads canonical chained entries.
- `GET /v1/evaluations/{evaluation_id}/events` reads event history.
- `POST /v1/evaluations/{evaluation_id}/stop` requests a stop.
- `GET /v1/agents/{agent_id}/evaluations` reads history.
- `GET /v1/agents/{agent_id}/weaknesses` reads target-scoped weakness memory.

Gateway evaluations use `target_id: "GATEWAY"` and can use `SYNTHETIC` or generic `PAPER`. `BITGET_PAPER` remains accepted for historical compatibility. Paper creation validates that the selected provider is registered; only configured capabilities can execute.

## Legacy compatibility

The original `/runs`, `/targets`, `/verification/preflight`, and `/runs/{id}/...` endpoints remain available for the existing dashboard and `EXTERNAL_HTTP` integrations. New public integrations should use the registry and gateway routes. Legacy paper records are not destructively renamed.
