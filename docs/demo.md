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

## Paper benchmark switch

Select `BITGET_PAPER` to exercise the same benchmark loop with the paper adapter. Read and execution evidence must retain separate labels. Without a configured `bgc` installation and demo credentials, Bitget evidence remains `UNVERIFIED`; the run must not be described as live execution.

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
