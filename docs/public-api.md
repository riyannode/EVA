# Public API surface

The REST API is the canonical control-plane contract. Bearer credentials are sent in the `Authorization` header. API keys are agent-scoped; the control-plane token is an operator credential and is not part of public onboarding.

## Trusted certificate keys

- `GET /.well-known/eva-signing-keys.json` publishes the configured public verification keys and key IDs.

The endpoint is read-only and contains no private keys.

## Pairing

- `POST /v1/pairing-requests` creates a ten-minute pending request without authentication.
- `GET /v1/pairing-requests/{request_id}` reads pending, approved, expired, or exchanged status.
- `POST /v1/pairing-requests/{request_id}/approve` approves a pending request with the operator control-plane credential.
- `POST /v1/pairing-requests/{request_id}/exchange` exchanges an approved request once for an agent identity and one-time agent API key.

Before approval, the request has no agent privilege. A second exchange is rejected. Expired requests cannot be approved or exchanged.

## Agent and gateway APIs

- `POST /v1/agents` registers an agent directly for operator-controlled administration and returns a one-time API key.
- `GET /v1/agents/{agent_id}` reads authenticated agent state.
- `POST /v1/agents/{agent_id}/paper-eligibility` grants or revokes `PAPER_ELIGIBLE` with the control-plane credential.
- `GET /v1/agents/{agent_id}/onboarding` returns connection instructions without returning a key.
- `POST /v1/agents/{agent_id}/keys` rotates a key and returns the replacement once.
- `DELETE /v1/agents/{agent_id}/keys/{key_id}` revokes a key.
- `POST /v1/evaluations` starts a gateway evaluation for an authenticated connected agent.
- `GET /v1/evaluations/{evaluation_id}` reads status.
- `GET /v1/evaluations/{evaluation_id}/score` reads deterministic score.
- `GET /v1/evaluations/{evaluation_id}/evidence` reads trace and journal validity.
- `GET /v1/evaluations/{evaluation_id}/journal` reads canonical chained entries.
- `GET /v1/evaluations/{evaluation_id}/bundle` returns the owner-authenticated evaluation bundle.
- `GET /v1/evaluations/{evaluation_id}/events` reads event history.
- `POST /v1/evaluations/{evaluation_id}/stop` requests a stop.
- `GET /v1/agents/{agent_id}/evaluations` reads history.
- `GET /v1/agents/{agent_id}/weaknesses` reads target-scoped weakness memory.

Gateway evaluations use `target_id: "GATEWAY"` and can use `SYNTHETIC` or generic `PAPER`. `BITGET_PAPER` remains accepted for historical compatibility. A connected agent is `SYNTHETIC_READY` only; PAPER creation requires `PAPER_ELIGIBLE`, an active Gateway session, a declared provider, and a registered provider with runtime PAPER capability. Requests fail before scheduling when these conditions are not met. Provider declaration is not execution authorization. Capability failure returns `403 PAPER_NOT_ELIGIBLE`; an undeclared provider returns `422 EXECUTION_PROVIDER_NOT_DECLARED`; an unavailable provider returns `422 EXECUTION_PROVIDER_UNAVAILABLE`.

## Certificates and sharing

- `GET /v1/certificates/{evaluation_id}` returns an authenticated owner's certificate.
- `GET /v1/certificates/{evaluation_id}/verify` verifies the certificate against the trusted key registry and evidence root.
- `POST /v1/certificates/{evaluation_id}/share` creates an opaque opt-in share token for an authenticated owner.
- `GET /v1/public/certificates/{share_token}` returns only the explicitly shared certificate and verification status.

Public certificate sharing does not make private evaluations enumerable by evaluation ID and does not expose private traces, credentials, or hidden chain-of-thought.

## Legacy compatibility

The original `/runs`, `/targets`, `/verification/preflight`, and `/runs/{id}/...` endpoints remain available for the existing dashboard and compatibility integrations. Anonymous legacy creation is limited to deterministic `REFERENCE_SAFE` and `REFERENCE_WEAK` synthetic fixtures. `EXTERNAL_HTTP`, `PAPER`, `BITGET_PAPER`, target tokens, agent-owned runs, and protected stop/resume operations require appropriate authentication. Legacy paper records are not destructively renamed.

The in-memory limiter is bounded single-process protection. It is not distributed or globally consistent across multiple workers.
