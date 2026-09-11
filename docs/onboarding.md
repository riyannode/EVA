# External-agent onboarding

The primary product path is an outbound connection from the external agent to EVA. The flow is inspired by agent-platform onboarding patterns: create an identity, copy a one-time key, install a small integration, connect, and run a zero-write synthetic evaluation. It does not add wallets, tokens, signers, a marketplace, or trading commerce.

## Registration

The dashboard's `Connect External Agent` action calls `POST /v1/agents` with a control-plane bearer token. The request contains:

- name;
- version;
- declared model;
- optional framework;
- optional declared trading venues/providers.

The response contains `agent_id` and one `eva_live_...` API key. EVA stores only a derived key hash. The dashboard displays the raw key once and does not send it to an exchange.

Trading venue metadata is optional. `exchange-agnostic` agents can register without a venue and are eligible for synthetic evaluation after they connect.

## Connection

The agent opens an outbound `WSS /v1/agent/connect` connection with `Authorization: Bearer <EVA_AGENT_KEY>`. The agent sends `hello` using `eva-agent/1` and its registered identity. EVA returns `ready` only after authentication and identity validation.

The TypeScript SDK is in `sdk/typescript`; the Python SDK is in `sdk/python`. The CLI in `cli` provides registration, evaluation inspection, and certificate verification. The raw message contract is documented in [protocol.md](protocol.md).

Example TypeScript integration:

```ts
import { EvaAgent } from "@eva-ai/sdk";

const eva = new EvaAgent({
  apiKey: process.env.EVA_API_KEY!,
  agentId: process.env.EVA_AGENT_ID!,
  gatewayUrl: process.env.EVA_GATEWAY_URL!
});

await eva.connect({ name: "My Trader", version: "1.0.0", model: "my-model" }, async context => {
  const market = await context.request("market", { symbol: "BTCUSDT" });
  return { action: "HOLD", reason: JSON.stringify(market) };
});
```

Example Python integration:

```python
from eva_agent import AgentIdentity, EvaAgent

agent = EvaAgent(
    api_key=os.environ["EVA_API_KEY"],
    agent_id=os.environ["EVA_AGENT_ID"],
    gateway_url=os.environ["EVA_GATEWAY_URL"],
)
await agent.connect(AgentIdentity("My Trader", "1.0.0", "my-model"), decide)
```

## Readiness states

Connection promotes a registered agent to `ONLINE` and `SYNTHETIC_READY`. Synthetic evaluation is available for compatible connected agents regardless of declared exchange. The onboarding response reports `synthetic: READY` and the current provider's paper capability. Paper evaluation is available only when the selected provider is registered and configured by EVA. Declaring Binance, Bybit, Coinbase, or another venue does not create support or provide credentials; those adapters are not integrated in this phase.

Onboarding itself sends no `paper_order` and creates no exchange-side write. A completed synthetic run returns score, evidence, weaknesses, and the signed certificate only when certificate signing is configured.

## Production transport

Public authenticated REST and gateway traffic must use HTTPS/WSS. The local development server may use HTTP/WS on a private machine. The legacy `EXTERNAL_HTTP` target flow remains available for compatibility and is SSRF-hardened; the gateway is the preferred integration path.
