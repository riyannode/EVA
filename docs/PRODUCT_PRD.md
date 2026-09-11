# EVA Product PRD

Status: SOURCE OF TRUTH

This document is the authoritative product and productization roadmap for EVA.

If implementation, older documentation, issues, prompts, or assumptions conflict with this document, do not silently choose one. Inspect the current implementation, identify the conflict, and either:

1. implement the PRD through an explicitly scoped task, or
2. update the PRD only with explicit project-owner approval.

Roadmap items are not implemented features unless separately verified in the codebase and runtime.

EVA PRODUCT PRD + ROADMAP
Version: 1.0
Date: 2026-09-10
Status: Productization roadmap after EVA V1
Project: EVA — Evaluation & Verification Agent
Core thesis: EVA tests the agents that trade.

============================================================
1. PRODUCT DEFINITION
============================================================

EVA adalah adaptive adversarial evaluation platform untuk autonomous trading agents.

EVA BUKAN:
- trading strategy
- autonomous trader
- portfolio manager
- exchange terminal
- execution bot milik user

EVA ADALAH:
- evaluator
- red-team system
- behavioral safety verifier
- execution-evidence verifier
- weakness-learning evaluation engine

Primary product question:
"Can this autonomous trading agent be trusted with more autonomy?"

Core loop:
GENERATE
→ TEST TARGET
→ VERIFY
→ CRITIQUE
→ REMEMBER
→ MUTATE
→ RETEST
→ SCORE

Current EVA authority split:
- Qwen: scenario generation, qualitative failure diagnosis, targeted mutation
- Deterministic code/oracles: PASS / FAIL / readiness authority
- LangGraph: evaluation routing, retry/mutation/difficulty progression
- SQLite: runs, episodes, events, weakness memory
- Bitget paper runtime: execution evidence
- External trader: subject under evaluation

============================================================
2. CURRENT EVA V1 — KEEP STABLE
============================================================

Current implementation/test-verified product capabilities:

[CORE]
- Adaptive evaluation loop
- Target/version-scoped weakness memory
- Qwen adversarial scenario generation
- Qwen qualitative critic
- Qwen targeted mutation
- Deterministic oracle authority
- Deterministic readiness score
- Difficulty progression
- Mutation/retest loop
- Tool discipline checks
- Policy checks
- Freshness checks
- Sizing checks
- Takeover checks
- Consistency checks
- Execution checks

[BITGET]
- Official bgc integration
- Market reads
- Instrument reads
- Paper account reads
- Bitget Demo/PAPER execution
- Order reference verification
- Filled order-detail verification
- Decision ↔ execution reconciliation

[EXTERNAL TARGET]
- Existing EXTERNAL_HTTP target flow
- Target can request:
  - market
  - account
  - history
  - paper_order
  - escalate
- Timeout
- Response-size cap
- Tool-step cap

These capabilities describe implementation and test coverage. A standalone runtime component is runtime-verified only when its actual environment evidence is available. Full external-target paper evaluation remains a separate E2E verification state.

Full external-target BITGET_PAPER E2E:

EVA scenario
→ external trader
→ trader requests market/account
→ EVA supplies verified Bitget evidence
→ trader independently decides
→ trader requests paper_order
→ EVA pre-execution gate
→ Bitget PAPER execution
→ verified order fill
→ deterministic oracle reconciliation
→ Qwen critic
→ weakness memory
→ targeted mutation
→ retest
→ final readiness score

STATUS: NOT YET VERIFIED

Standalone implementation and runtime evidence must not be presented as proof of this complete external-target workflow.

Permanent pre-execution financial write gate:

External Trader requests paper_order
→ EVA records attempted action
→ deterministic pre-execution policy gate
→ if blocked: structured rejection, attempted violation recorded, and NO Bitget write
→ if allowed: Bitget PAPER placement, order reference capture, exact order-detail read, and filled-state verification
→ deterministic oracle evaluates trader behavior and execution reconciliation

The gate checks allowed symbol, blocked symbol, action restrictions, max order notional, max exposure, emergency stop, verified account evidence, sufficient available balance, verified instrument constraints, and required market evidence. The oracle may fail a prohibited attempt, but a prohibited financial write is never sent. Live trading remains out of scope.

V1 must remain available until replacement transport is fully proven.

DO NOT remove EXTERNAL_HTTP before the new Agent Gateway has:
1. contract tests
2. external trader integration
3. full Bitget PAPER E2E
4. persisted evaluation evidence
5. production smoke test

============================================================
3. PRODUCTIZATION GOAL
============================================================

Target state:

A developer should be able to connect any autonomous trading agent to EVA in minutes without:
- exposing an inbound webhook
- configuring a public domain
- configuring TLS
- sharing Bitget credentials
- implementing EVA internals
- understanding LangGraph
- deploying an EVA-specific backend

Desired onboarding:

1. Create EVA agent
2. Copy API key
3. Install SDK or CLI
4. Run one command
5. Agent becomes ONLINE
6. Start evaluation
7. Receive score + evidence + weaknesses + readiness result

Target onboarding time:
< 5 minutes for a developer with an existing trading-agent function.

Target first evaluation:
< 10 minutes from signup to first completed synthetic evaluation.

============================================================
P0 PUBLIC SECURITY BASELINE — REQUIRED BEFORE PUBLIC DISTRIBUTION
============================================================

Public EVA is NOT production-ready unless:

- HTTPS/WSS is used for public authenticated traffic
- plain HTTP is limited to local/private development
- mutating endpoints require authentication
- evaluation creation is rate-limited
- public backend ports are not unnecessarily exposed
- API keys, bearer tokens, target tokens, and secrets never traverse plaintext HTTP
- arbitrary EXTERNAL_HTTP target URLs are disabled, allowlisted, or fully SSRF-hardened before public use
- private, loopback, link-local, and cloud-metadata destinations are denied
- redirects are denied or tightly controlled
- outbound target requests have strict timeout, response-size, request-count, and budget limits

This P0 baseline gates public onboarding, broad external-agent access, and public distribution. The later Security Hardening phase remains for deeper controls and abuse resistance.

============================================================
4. TARGET PRODUCT ARCHITECTURE
============================================================

Canonical architecture:

External Developer / Agent
        |
        | REST Control Plane
        v
+-------------------------------+
| EVA PLATFORM                  |
|                               |
| Agent Registry                |
| Evaluation API                |
| Agent Gateway                 |
| Evaluation Engine             |
| Deterministic Oracles         |
| Qwen Evaluator                |
| Weakness Memory               |
| Evidence Journal              |
| Signed Certificates           |
+---------------+---------------+
                |
                | controlled tools only
                v
        Bitget Paper Gateway
                |
                v
            Bitget Demo

Transport roles:

REST API
= control plane

WebSocket Agent Gateway
= live autonomous evaluation runtime

SDK
= easiest developer integration

CLI
= fastest local onboarding

MCP
= optional convenience adapter for MCP-native environments

x402
= optional payment/access layer later

REST/OpenAPI must remain the canonical public product contract.
MCP must wrap the same product API, not become the internal source of truth.

Lightweight Graph Engineering principle:

- LangGraph remains the workflow/state-machine orchestration layer.
- Current relational persistence remains the source of truth.
- Preserve explicit lineage between evaluations, episodes, weaknesses, mutations, retests, evidence, and execution.
- Store provenance so important results can be traced to the evaluation run and evidence that produced them.
- Do not add a dedicated graph database, Neo4j, or similar infrastructure.
- Do not redesign the current data model just to make it graph-shaped.
- Consider a dedicated graph layer only if real product usage proves relational storage insufficient.

Graph Engineering means lineage and provenance with explicit relationships. It does not mean a knowledge-graph platform, graph database migration, swarm architecture, multi-agent graph infrastructure, or complex DAG service.

============================================================
5. EXTERNAL AGENT GATEWAY
============================================================

Goal:
Remove the requirement for EVA to call arbitrary user-supplied target_url as the primary public integration model.

New preferred model:

External trader initiates outbound connection to EVA.

Flow:

External Trader
    |
    | outbound WSS
    v
EVA Agent Gateway
    |
    +--> scenario
    +--> tool result
    +--> evaluation state
    +--> finalization
    |
    v
EVA Evaluation Engine

Benefits:
- no arbitrary EVA outbound URL fetch
- no public webhook required from external trader
- no inbound firewall setup
- no custom domain required
- no TLS setup required by user
- much lower SSRF exposure
- easier Cloudflare/serverless integration
- easier local development
- easier SDK abstraction
- stable long-lived evaluation session

Suggested endpoint:

WSS /v1/agent/connect

Authentication:
Authorization: Bearer <EVA_AGENT_KEY>

Initial handshake:

{
  "type": "hello",
  "agent_id": "agt_xxx",
  "protocol": "eva-agent/1",
  "capabilities": [
    "market",
    "account",
    "history",
    "paper_order",
    "escalate"
  ],
  "agent": {
    "name": "TraderX",
    "version": "1.0.0",
    "model": "qwen3.8-max"
  }
}

EVA response:

{
  "type": "ready",
  "connection_id": "conn_xxx",
  "status": "ONLINE"
}

Evaluation runtime messages:

EVA → Trader:
{
  "type": "scenario",
  "evaluation_id": "eval_xxx",
  "episode_id": "ep_xxx",
  "scenario": {...},
  "available_tools": [...],
  "max_steps": 8
}

Trader → EVA:
{
  "type": "tool_call",
  "tool": "market",
  "args": {
    "symbol": "BTCUSDT"
  }
}

EVA → Trader:
{
  "type": "tool_result",
  "tool": "market",
  "result": {...}
}

Trader → EVA:
{
  "type": "final",
  "decision": {
    "action": "BUY",
    "symbol": "BTCUSDT",
    "notional": 5,
    "confidence": 0.81,
    "reason": "..."
  }
}

============================================================
6. ONE-CLICK ONBOARDING
============================================================

Primary onboarding UX:

STEP 1 — Register Agent

Dashboard:
[ Connect External Agent ]

User enters:
- Agent name
- Version
- Declared model
- Environment:
  - Local
  - Cloudflare
  - VPS
  - Other

EVA creates:
- agent_id
- API key
- connection instructions

Response:

Agent ID:
agt_abc123

API Key:
eva_live_xxxxxxxxx

Gateway:
wss://api.eva.example/v1/agent/connect

API key is shown once.

------------------------------------------------------------

STEP 2 — Choose Integration Method

Option A — TypeScript SDK

npm install @eva-ai/sdk

Minimal integration:

import { EvaAgent } from "@eva-ai/sdk";

const eva = new EvaAgent({
  apiKey: process.env.EVA_API_KEY
});

eva.connect({
  agent: {
    name: "My Trader",
    version: "1.0.0",
    model: "qwen3.8-max"
  },

  async decide(ctx) {
    return myTrader(ctx);
  }
});

------------------------------------------------------------

Option B — Python SDK

pip install eva-agent

Minimal integration:

from eva_agent import EvaAgent

eva = EvaAgent(api_key=os.environ["EVA_API_KEY"])

eva.connect(
    name="My Trader",
    version="1.0.0",
    model="qwen3.8-max",
    decide=my_trader
)

------------------------------------------------------------

Option C — CLI

npx eva-agent connect

Interactive flow:

? EVA API key:
? Agent name:
? Version:
? Model:
? Local handler module:

Output:

EVA Agent Connected
Agent ID: agt_abc123
Status: ONLINE

------------------------------------------------------------

Option D — Raw Protocol

For advanced users:
- REST agent registration
- WebSocket eva-agent/1 protocol
- OpenAPI specification
- protocol JSON schema

------------------------------------------------------------

STEP 3 — Connection Test

EVA automatically runs a non-financial handshake test:

- ping
- scenario receive
- market tool request
- tool result receive
- final response schema
- timeout
- reconnect behavior

Result:

CONNECTION VERIFIED

No Bitget order is placed during onboarding.

------------------------------------------------------------

STEP 4 — First Evaluation

User chooses:

[SYNTHETIC]
Safe zero-write evaluator test.

or

[BITGET PAPER]
Real Bitget Demo execution-backed evaluation.

For BITGET PAPER:
- Bitget credentials stay only inside EVA
- external trader never sees them
- external trader only sees standardized tool results
- all writes are EVA-controlled
- live trading remains disabled

------------------------------------------------------------

STEP 5 — Result

Dashboard/API returns:

- readiness score
- readiness label
- pass rate
- risk violation rate
- takeover accuracy
- consistency failures
- tool-discipline failures
- primary recurring weakness
- difficulty reached
- mutation count
- mutation recovery rate
- paper execution evidence
- evaluation certificate

============================================================
7. AGENT REGISTRY
============================================================

Add public product entity:

Agent

Fields:
- agent_id
- owner_id
- name
- version
- declared_model
- framework
- created_at
- last_seen_at
- status
- protocol_version
- capabilities
- auth_key_hash
- rate_limit_policy
- evaluation_count
- latest_readiness
- latest_evaluation_id

Agent statuses:
- OFFLINE
- CONNECTING
- ONLINE
- EVALUATING
- DEGRADED
- DISABLED

Never store plaintext API keys.

API key format suggestion:

eva_live_<random>

Store:
SHA-256/HMAC/Argon2-derived key representation only.

Allow:
- create key
- rotate key
- revoke key

============================================================
8. PUBLIC REST API
============================================================

Suggested V1 public API:

POST /v1/agents
Create an external agent identity.

GET /v1/agents/{agent_id}
Read agent state.

POST /v1/agents/{agent_id}/keys
Create/rotate key.

DELETE /v1/agents/{agent_id}/keys/{key_id}
Revoke key.

POST /v1/evaluations
Start evaluation.

GET /v1/evaluations/{evaluation_id}
Get status.

GET /v1/evaluations/{evaluation_id}/score
Get score/readiness.

GET /v1/evaluations/{evaluation_id}/evidence
Get evidence bundle metadata.

GET /v1/evaluations/{evaluation_id}/events
Streaming/SSE event feed.

GET /v1/agents/{agent_id}/weaknesses
Get persisted weakness profile.

GET /v1/agents/{agent_id}/evaluations
Evaluation history.

POST /v1/evaluations/{evaluation_id}/stop
Stop bounded evaluation.

Future:

GET /v1/certificates/{evaluation_id}
GET /v1/certificates/{evaluation_id}/verify

============================================================
9. AUTHENTICATION + RATE LIMITING
============================================================

External client auth:
Bearer API key.

Rules:
- API keys belong to one agent/account scope
- keys stored hashed
- no plaintext logging
- no keys in URLs
- no secrets in event stream
- no secrets in Qwen prompt
- no Bitget credentials returned to external target

Rate limits should exist for:
- agent registration
- evaluation start
- gateway reconnect
- evaluation status polling
- evidence download
- MCP tools later

Suggested initial limits:

Evaluation start:
10/hour/agent

Concurrent evaluations:
1/agent initially

Gateway reconnect:
30/minute/agent

Read endpoints:
120/minute/agent

Adjust later from observed usage.

============================================================
10. SSRF-FREE ONBOARDING
============================================================

Primary mitigation:
The external trader initiates the connection to EVA.
EVA no longer needs arbitrary public target_url as the default product path.

Compatibility:
Keep EXTERNAL_HTTP temporarily for backwards compatibility.

If EXTERNAL_HTTP remains available:
- HTTPS only
- no localhost
- no RFC1918/private networks
- no link-local addresses
- no metadata endpoints
- restricted ports
- DNS resolution verification
- DNS rebinding protection
- no redirects
- response-size cap
- strict timeout
- bounded request count
- per-run outbound budget

Long-term:
Mark EXTERNAL_HTTP as:
LEGACY_EXTERNAL_HTTP

New default:
AGENT_GATEWAY

============================================================
11. TAMPER-EVIDENT EVIDENCE JOURNAL
============================================================

Problem:

SQLite persistence alone stores current values.
An administrator with direct DB access could theoretically change:

FAIL → PASS

without SQLite itself proving that the historical record changed.

Goal:
Make any evidence mutation detectable.

Journal entry canonical payload:

{
  "seq": 12,
  "evaluation_id": "eval_xxx",
  "episode_id": "ep_xxx",
  "timestamp": "...",
  "event_type": "oracle_result",
  "payload": {...},
  "prev_hash": "sha256:..."
}

Hash:

entry_hash =
SHA256(
  canonical_json(
    seq,
    evaluation_id,
    episode_id,
    timestamp,
    event_type,
    payload,
    prev_hash
  )
)

Chain:

event_1 → H1
event_2 + H1 → H2
event_3 + H2 → H3
event_4 + H3 → H4

If event_2 changes:
- H2 changes
- H3 chain reference fails
- H4 chain reference fails
- verification detects tampering

Required journal events:
- evaluation_started
- target_connected
- scenario_created
- tool_called
- tool_result
- decision_received
- paper_order_submitted
- paper_order_verified
- oracle_result
- critic_result
- weakness_updated
- mutation_created
- score_calculated
- evaluation_completed

Important:
Tamper-evident does NOT mean tamper-proof.

A full privileged attacker could rewrite data and recompute hashes.
Therefore hash chain alone is not the final integrity layer.

============================================================
12. SIGNED EVALUATION CERTIFICATE
============================================================

After an evaluation completes:

1. canonicalize final evaluation summary
2. finalize evidence_root
3. sign with EVA signing key
4. expose signed certificate

Certificate example:

{
  "certificate_version": "eva-cert/1",
  "evaluation_id": "eval_abc123",
  "agent": {
    "name": "TraderX",
    "version": "1.0.0",
    "model": "qwen3.8-max"
  },
  "score": 84,
  "readiness": "CONDITIONALLY_READY",
  "primary_weakness": "CONFLICT_IGNORED",
  "evidence_root": "sha256:...",
  "completed_at": "...",
  "signing_key_id": "eva-prod-1",
  "signature": "ed25519:..."
}

Verification:

eva verify certificate.json

Expected:

Certificate: VALID
Signature: VALID
Evidence root: VALID
Evaluation ID: eval_abc123

Recommended signing:
Ed25519.

Signing private key:
- server-only
- never exposed to frontend
- never stored in repo
- rotate using signing_key_id

Public verification key:
safe to publish.

============================================================
13. EVIDENCE BUNDLE
============================================================

Each completed evaluation should produce:

evaluation.json
journal.jsonl
certificate.json

Optional:
paper_execution.json
weaknesses.json
metrics.json

Bundle must exclude:
- API keys
- Bitget secrets
- Qwen key
- bearer tokens
- hidden chain-of-thought

Store only observable target rationale / declared reason.
Do not store hidden model reasoning.

============================================================
14. EXTERNAL AGENT SDK
============================================================

SDK responsibilities:

- authenticate
- connect to gateway
- reconnect with bounded backoff
- validate protocol
- receive scenarios
- route tool requests
- expose tool-result context
- submit final decisions
- heartbeat
- expose local logging hooks
- never handle Bitget credentials

TypeScript:
@eva-ai/sdk

Python:
eva-agent

SDK interface should be framework-neutral.

Adapters can later exist for:
- LangGraph
- OpenAI Agents SDK
- CrewAI
- AutoGen
- Claude/Cursor local workflows
- custom trading bots
- Cloudflare Agents SDK

Do not make framework adapters part of the core protocol.

============================================================
15. CLOUDFLARE REFERENCE TRADER
============================================================

Purpose:
Reference target used to prove that EVA can evaluate a real remote autonomous trader.

It is NOT part of EVA's evaluator logic.

Separate repository/service.

Suggested stack:
- TypeScript
- Cloudflare Workers
- Cloudflare Agents SDK
- Durable Objects
- Cloudflare Workflows
- Qwen/OpenAI-compatible LLM endpoint
- Zod
- Vitest

Trader responsibilities:
- receive EVA scenario
- inspect supplied context
- request tools
- reason independently
- choose:
  - BUY
  - SELL
  - HOLD
  - REFUSE
  - ESCALATE
- obey its own risk policy
- return observable rationale

Trader must NOT contain:
- EVA scoring
- EVA oracle logic
- EVA mutation logic
- EVA weakness scoring
- evaluator-specific PASS/FAIL shortcuts

Otherwise evaluator/target separation becomes invalid.

============================================================
16. FULL TRACK 2 ACCEPTANCE TEST
============================================================

Required full E2E:

EVA creates scenario
→ external Cloudflare trader receives scenario
→ trader requests market
→ EVA fetches Bitget market evidence
→ trader requests account
→ EVA fetches Bitget Demo account evidence
→ trader independently decides
→ trader requests paper_order
→ EVA validates request
→ EVA sends Bitget PAPER order
→ Bitget returns orderId/clientOid
→ EVA reads exact order detail
→ orderStatus = filled
→ deterministic oracle reconciles decision/execution
→ Qwen critic diagnoses behavior
→ weakness memory updates
→ Qwen creates targeted mutation when needed
→ trader receives retest
→ EVA calculates deterministic readiness score
→ journal persists
→ evidence readback succeeds

Acceptance:
Full BITGET_PAPER evaluation = VERIFIED

A direct bgc order alone is NOT sufficient.

============================================================
17. PHASED ROADMAP
============================================================

PHASE 0 — FREEZE CURRENT V1 BASELINE
Priority: Immediate

Goal:
Preserve current verified behavior.

Tasks:
- tag current stable baseline
- preserve synthetic fixtures
- preserve current Bitget paper flow
- preserve current deterministic scoring
- preserve current Qwen prompt roles
- preserve EXTERNAL_HTTP until replacement passes

Exit criteria:
- current tests pass
- current deployment healthy
- synthetic run works
- Qwen runtime works
- Bitget paper direct runtime works

------------------------------------------------------------

PHASE 1 — REFERENCE AUTONOMOUS TRADER
Priority: Highest

Goal:
Prove real external target integration.

Tasks:
- new separate repository
- Cloudflare Worker/Agent
- autonomous LLM decision loop
- compatible with current EVA EXTERNAL_HTTP
- no evaluator logic inside trader
- deploy public endpoint
- run full BITGET_PAPER evaluation

Exit criteria:
- external trader target connected
- market/account tool loop works
- at least one complete paper evaluation
- order evidence verified
- oracle reconciliation verified
- Qwen critic verified
- memory/mutation/retest verified
- full EVA BITGET_PAPER marked VERIFIED

------------------------------------------------------------

PHASE 2 — AGENT REGISTRY + API AUTH
Priority: High

Public access remains gated by the P0 Public Security Baseline.

Goal:
Turn EVA from demo target input into managed platform.

Tasks:
- agent table/entity
- API key generation
- hashed key storage
- rotate/revoke
- agent status
- evaluation history
- authentication middleware
- basic rate limiting

Exit criteria:
- user can register an agent
- user receives one-time API key
- user can authenticate
- unauthorized requests fail
- secrets never appear in logs

------------------------------------------------------------

PHASE 3 — AGENT GATEWAY
Priority: High

Goal:
External traders connect outbound to EVA.

Tasks:
- WSS /v1/agent/connect
- eva-agent/1 protocol
- heartbeat
- reconnect
- session binding
- one active evaluation per agent
- message schema validation
- tool-loop routing
- timeout enforcement
- connection status

Exit criteria:
- external agent requires no public webhook
- local agent can connect outbound
- Cloudflare agent can connect outbound
- full synthetic evaluation works through gateway
- full Bitget PAPER evaluation works through gateway

------------------------------------------------------------

PHASE 4 — ONE-CLICK ONBOARDING
Priority: High

This phase starts only after the P0 Public Security Baseline is in place.

Goal:
<5 minute integration.

Tasks:
- Connect External Agent UI
- TypeScript SDK
- Python SDK
- CLI
- copy-paste quickstart
- automatic handshake test
- online/offline indicator
- first synthetic evaluation wizard

Exit criteria:
New developer can:
1. create agent
2. copy key
3. install SDK
4. connect
5. pass handshake
6. run evaluation

without editing EVA source code.

------------------------------------------------------------

PHASE 5 — SECURITY HARDENING — DEEPER CONTROLS
Priority: Required before public distribution

The P0 Public Security Baseline above is the minimum prerequisite; this phase adds deeper hardening before broad public distribution.

Tasks:
- rate limiting
- gateway concurrency limits
- request/message size caps
- strict schemas
- auth scope checks
- key rotation
- audit logs
- abuse controls
- tool budgets
- evaluation budgets
- safe failure behavior
- legacy EXTERNAL_HTTP SSRF hardening
- deny private/metadata destinations
- no redirects
- outbound limits

Exit criteria:
- common abuse tests pass
- SSRF tests pass
- key leakage tests pass
- malformed client tests pass
- dead/slow client cannot block platform
- one agent cannot affect another session

------------------------------------------------------------

PHASE 6 — TAMPER-EVIDENT JOURNAL
Priority: Medium-High

Goal:
Cryptographically detectable evidence modification.

Tasks:
- canonical JSON
- sequence numbers
- prev_hash
- entry_hash
- evidence_root
- verification command/API
- export journal.jsonl

Exit criteria:
- valid untouched journal verifies
- modified entry fails
- removed entry fails
- reordered entry fails
- appended invalid entry fails

------------------------------------------------------------

PHASE 7 — SIGNED EVALUATION CERTIFICATE
Priority: Medium-High

Goal:
Portable third-party-verifiable EVA result.

Tasks:
- Ed25519 signing
- key IDs
- public verification key
- certificate format
- CLI verify
- API verify endpoint
- downloadable evidence bundle

Exit criteria:
- certificate verifies offline
- modified certificate fails
- evidence_root mismatch fails
- rotated key remains verifiable by key_id

------------------------------------------------------------

PHASE 8 — PUBLIC PLATFORM DISTRIBUTION
Priority: Medium

Requires the P0 Public Security Baseline and the applicable deeper Security Hardening controls.

Tasks:
- public docs
- OpenAPI spec
- SDK docs
- onboarding tutorial
- public agent dashboard
- evaluation history
- shareable certificate URL
- usage telemetry
- basic quotas

Optional:
- team/org accounts
- project namespaces
- webhook notifications
- evaluation schedules

------------------------------------------------------------

PHASE 9 — MCP ADAPTER
Priority: Later

Goal:
Make EVA easy to use from MCP-native clients.

Suggested tools:
- eva_register_agent
- eva_start_evaluation
- eva_get_evaluation
- eva_get_score
- eva_get_evidence
- eva_get_weaknesses
- eva_verify_certificate

MCP should call the same public EVA API.

Do NOT duplicate evaluator logic inside MCP.

------------------------------------------------------------

PHASE 10 — x402
Priority: Later

Goal:
Agent-to-agent paid evaluation.

Flow:

External Agent
→ POST /v1/evaluations
→ HTTP 402
→ x402 payment
→ settlement verified
→ EVA evaluation runs
→ score + evidence + certificate returned

Rules:
- payment never affects score
- evaluator rules remain deterministic
- payment layer is authorization/commercial access only
- no pay-to-pass
- no priority affecting evaluation result

Possible pricing:
- synthetic evaluation
- standard paper evaluation
- deep adversarial evaluation
- certification bundle

============================================================
18. PRODUCT UX
============================================================

Dashboard primary pages:

1. Agents
- connected agents
- online/offline state
- latest score
- last evaluation
- weaknesses

2. New Agent
- create agent
- integration method
- API key
- SDK/CLI command
- connection test

3. Evaluations
- running/completed
- mode
- score
- readiness
- duration
- target version

4. Evaluation Detail
- scenario
- target tool calls
- observable decision
- paper execution evidence
- deterministic oracle results
- Qwen diagnosis
- weakness updates
- mutations/retests
- score

5. Weakness Profile
Per target/version:
- weakness type
- attempts
- failures
- passes
- failure rate
- last seen
- recovery trend

6. Certificate
- score
- readiness
- evidence root
- signature
- verify button
- download bundle

============================================================
19. PRODUCT METRICS
============================================================

Platform metrics:
- registered agents
- connected agents
- evaluations started
- evaluations completed
- completion rate
- median evaluation duration
- failed connection rate
- SDK onboarding completion rate
- time-to-first-evaluation
- returning agents
- evaluations per agent

Evaluator metrics:
- total episodes
- pass rate
- risk violation rate
- false autonomy rate
- unnecessary escalation rate
- takeover accuracy
- consistency failure rate
- tool precondition violations
- duplicate action count
- execution mismatch count
- primary weakness
- targeted mutation count
- mutation recovery rate
- highest difficulty reached

Integrity metrics:
- journal verification pass rate
- invalid certificate attempts
- evidence-root mismatch count

============================================================
20. NON-GOALS
============================================================

Do NOT turn EVA into:
- alpha strategy marketplace
- historical backtesting platform
- trading leaderboard clone
- signal provider
- live portfolio manager
- autonomous execution bot
- exchange account manager

Do NOT add before core productization:
- large historical replay engine
- alpha/beta decomposition
- strategy ranking leaderboard
- social trading
- copy trading
- multi-exchange live execution
- real-money execution

Reason:
These dilute EVA's core positioning and overlap with benchmark/trading products.

============================================================
21. POSITIONING
============================================================

Primary:

"EVA is an adaptive adversarial evaluation and verification platform for autonomous trading agents."

Short:

"EVA tests the agents that trade."

Developer value:

"Connect your autonomous trader. EVA stress-tests its decisions, discovers recurring weaknesses, retests them under harder conditions, verifies execution evidence, and returns a deterministic readiness verdict."

Differentiation:

Traditional benchmark:
"How well did the agent perform?"

EVA:
"Where does this agent fail, does it recover, and can its autonomous behavior be trusted?"

============================================================
22. RELEASE STRATEGY
============================================================

Release A:
EVA V1 + Cloudflare reference trader
Goal:
Hackathon-complete external BITGET_PAPER proof.

Release B:
Agent Registry + Gateway
Goal:
External developers can connect their own agents.

Release C:
SDK + CLI + onboarding
Goal:
<5 minute integration.

Release D:
Security + evidence journal
Goal:
Public-safe beta.

Release E:
Signed certificates
Goal:
Portable verifiable evaluation result.

Release F:
MCP
Goal:
Agent-native access.

Release G:
x402
Goal:
Paid agent-to-agent evaluation service.

============================================================
23. DEFINITION OF "EVA IS A PRODUCT, NOT JUST A DEMO"
============================================================

EVA graduates from demo to product when:

[REQUIRED]
- external user can register an agent
- external agent can connect without EVA code changes
- external agent does not need a public webhook
- external agent does not receive Bitget credentials
- user can start evaluation through public API/UI
- evaluation runs independently
- evidence is persisted
- score is deterministic
- weakness profile persists across runs
- adaptive retest works
- Bitget PAPER evidence is verified where applicable
- result is retrievable through API
- auth and rate limiting exist
- onboarding docs/SDK exist

[TRUST LAYER]
- journal is tamper-evident
- final certificate is signed
- evidence can be independently verified

[COMMERCIAL LAYER — LATER]
- x402 payment gates evaluation access
- payment never affects verdict

============================================================
24. IMPLEMENTATION PRIORITY SUMMARY
============================================================

P0
1. Cloudflare reference trader
2. Full existing EXTERNAL_HTTP BITGET_PAPER E2E

P1
3. Agent Registry
4. API keys
5. WebSocket Agent Gateway
6. Cloudflare trader migration to Gateway
7. TypeScript SDK
8. Python SDK
9. CLI onboarding
10. first-run wizard

P2
11. Rate limiting
12. Gateway isolation/security
13. Legacy EXTERNAL_HTTP SSRF hardening
14. Tamper-evident evidence journal
15. Signed evaluation certificate

P3
16. OpenAPI/public docs
17. public beta distribution
18. MCP adapter
19. x402 paid evaluation

============================================================
25. FINAL ARCHITECTURE PRINCIPLE
============================================================

Keep these boundaries permanent:

EVA
= evaluator
= scenario/adversarial engine
= deterministic oracle
= weakness memory
= execution verifier
= evidence/certificate authority

Trader
= autonomous decision-maker
= target under test

Bitget
= market/account/paper execution environment

Qwen
= EVA red-team intelligence
= scenario + diagnosis + mutation

Qwen is NOT:
= score authority
= execution authority
= policy authority

External Agent Gateway
= transport only

MCP
= adapter only

x402
= payment/access only

The central invariant:

EVA must remain able to evaluate an arbitrary autonomous trader without becoming that trader.
