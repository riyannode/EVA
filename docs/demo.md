# EVA Demo

## Start the backend

```powershell
cd backend
uv sync
uv run fastapi dev app.py
```

## Start the dashboard

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`.

## Weak target

Select `REFERENCE_WEAK`, version `v1`, mode `SYNTHETIC`, 12 episodes, and difficulty 1. Start the run. The target intentionally trades through size, blocked-symbol, stale-evidence, conflict, or exposure constraints. EVA records machine-readable failures and targets later mutations at the observed weakness.

## Safe target

Start a second run with `REFERENCE_SAFE` and the same settings. It refuses blocked symbols, escalates when takeover is required, respects sizing, and should produce a higher readiness score.

## Official Track 2 paper benchmark

Install Node.js 20 or newer and the official CLI before configuring the benchmark:

```powershell
npm install -g @bitget-ai/bitget-agent-cli
bgc --version
bgc discover
bgc discover --tool order --action place
bgc discover --tool order --action detail
```

Configure `BITGET_MODE=paper`, select `EXTERNAL_HTTP`, provide the external target URL, declared target name, and declared target model, and run `GET /verification/preflight?target_url=...&target_name=...&target_model=...`. Preflight reports environment/run readiness only and never submits an order. A complete Track 2 run needs same-symbol market/instrument/account evidence, a safe target BUY/SELL decision, a `paper_order`, a documented `orderId` or `clientOid`, a filled `orderStatus` detail response, `PAPER_EXECUTION`, oracle reconciliation, persisted episode evidence, critic output, and metrics. Pending detail responses receive only a bounded retry of detail reads; placement is never retried. Without `bgc`, paper credentials, or Qwen credentials, the relevant status remains `UNVERIFIED`. Protected legacy creation of this run requires an operator-authenticated request; anonymous legacy creation is limited to deterministic synthetic reference fixtures.

`REFERENCE_WEAK` and `REFERENCE_SAFE` remain local deterministic verification fixtures and do not qualify as the official Track 2 paper target.

## After credentials arrive

From `backend`, configure the supported environment values and the official `bgc` authentication/setup:

```powershell
$env:EVA_MODEL = 'qwen3.8-max'
$env:EVA_LLM_BASE_URL = 'https://hackathon.bitgetops.com/v1'
$env:BITGET_QWEN_API_KEY = '<provided-qwen-key>'
$env:BITGET_MODE = 'paper'
$env:BITGET_EXECUTABLE = 'bgc'
$adminHeaders = @{ Authorization = 'Bearer <ADMIN_TOKEN>' }
```

Configure the official Bitget demo API credentials in the shell variables consumed by `bgc`:

```powershell
$env:BITGET_API_KEY = '<provided-demo-api-key>'
$env:BITGET_SECRET_KEY = '<provided-demo-secret-key>'
$env:BITGET_PASSPHRASE = '<provided-demo-passphrase>'
bgc --version
bgc discover
```

Run the backend, call preflight, then create the external-target paper run:

```powershell
uv run fastapi dev app.py
Invoke-RestMethod 'http://localhost:8000/verification/preflight?target_url=https%3A%2F%2Ftarget.example&target_name=Target%20Agent&target_model=external-model-v1'
$body = @{ target_id = 'EXTERNAL_HTTP'; target_name = 'Target Agent'; target_version = 'target-v1'; target_model = 'external-model-v1'; target_url = 'https://target.example'; mode = 'BITGET_PAPER'; max_episodes = 20; difficulty = 1 } | ConvertTo-Json
$run = Invoke-RestMethod http://localhost:8000/runs -Method Post -Headers $adminHeaders -ContentType 'application/json' -Body $body
Invoke-RestMethod "http://localhost:8000/runs/$($run.id)/events"
Invoke-RestMethod "http://localhost:8000/runs/$($run.id)/verification"
Invoke-RestMethod "http://localhost:8000/runs/$($run.id)/metrics"
Invoke-RestMethod "http://localhost:8000/runs/$($run.id)/score"
```

Only the resulting persisted `PAPER_EXECUTION` order reference, order-detail evidence, target trace, oracle result, verification summary, and metrics can establish runtime evidence. Do not reuse this sequence for a missing, pending, cancelled, or ambiguous paper result.

## API smoke flow

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/targets
$body = @{ target_id = 'REFERENCE_SAFE'; target_version = 'v1'; mode = 'SYNTHETIC'; max_episodes = 3; difficulty = 1 } | ConvertTo-Json
$run = Invoke-RestMethod http://localhost:8000/runs -Method Post -ContentType 'application/json' -Body $body
Invoke-RestMethod "http://localhost:8000/runs/$($run.id)"
Invoke-RestMethod "http://localhost:8000/runs/$($run.id)/score"
```

The SSE endpoint is `GET /runs/{run_id}/events`. Stop uses `POST /runs/{run_id}/stop`; resume uses `POST /runs/{run_id}/resume` for a stopped or failed run.
