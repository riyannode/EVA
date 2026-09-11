# External-agent onboarding

The public product path is an outbound connection from an existing agent to EVA. Agents can register for synthetic evaluation without selecting an exchange. Provider metadata is optional and describes the agent's intended venues; it does not grant credentials or execution access.

## Pairing

The Agents page and the CLI create a short-lived pending request with:

- agent name;
- version;
- declared model;
- optional framework/runtime;
- optional execution providers and capabilities.

The public request returns a `request_id`, `approval_url`, and `expires_at`. A pending request has no agent identity, API key, or evaluation privilege.

The machine-readable CLI flow is:

```powershell
eva auth start --api-url https://eva.example --name TraderX --version 1.0.0 --model model-v1 --json
eva auth status --api-url https://eva.example --request-id pair_xxx --json
eva auth complete --api-url https://eva.example --request-id pair_xxx --json
```

An operator approves the request through the admin-only path:

```powershell
eva admin approve --api-url https://eva.example --request-id pair_xxx --control-token <ADMIN_TOKEN> --json
```

The control-plane credential is never requested by the public Agents page, returned in an AI-agent prompt, stored in browser storage, or included in SDK source. It remains an operator-side credential for protected administration.

After approval, `auth complete` exchanges the request once for an agent identity and one `eva_live_...` credential. EVA stores only a derived key representation. The raw agent credential is returned once and must be stored by the agent runtime outside the browser.

## Connection

The agent opens an outbound `WSS /v1/agent/connect` connection with `Authorization: Bearer <EVA_AGENT_KEY>`. It sends `hello` using `eva-agent/1` and the registered identity. EVA returns `ready` only after authentication and identity validation.

The TypeScript SDK is in `sdk/typescript`; the Python SDK is in `sdk/python`. The CLI provides pairing, evaluation inspection, and trusted-key certificate verification. The raw message contract is documented in [protocol.md](protocol.md).

## Integration methods

The onboarding response and Agents page expose:

- AI Agent prompt;
- CLI;
- TypeScript SDK;
- Python SDK;
- Raw Protocol.

Generated setup prompts contain the pairing request ID and next steps, never an API key or control-plane token.

## Readiness states

Connection promotes a registered agent to `ONLINE` and `SYNTHETIC_READY`. Synthetic evaluation is available for compatible connected agents regardless of declared exchange. An exchange-agnostic agent can register, connect, and run synthetic evaluation.

Paper evaluation is available only when EVA has a configured compatible execution provider. Declaring Binance, Bybit, Coinbase, another venue, or no venue does not create provider support. The onboarding status reports `NOT_SUPPORTED` when the selected execution venue has no configured adapter.

Onboarding itself sends no `paper_order` and creates no exchange-side write. A completed synthetic run returns score, evidence, weaknesses, and a signed certificate only when certificate signing is configured.

## Production transport

Public authenticated REST and gateway traffic must use HTTPS/WSS. The local development server may use HTTP/WS on a private machine. The legacy `EXTERNAL_HTTP` target flow remains available for compatibility and is fail-closed for unsafe destinations with one-time DNS resolution, HTTPS-only transport, no redirects, bounded body, and timeout controls. The gateway is the preferred integration path.
