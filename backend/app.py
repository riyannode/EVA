import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

import auth
import certificate
import db
import gateway
import graph
import journal
from limits import RateLimiter
from config import Config, load_config
from models import Agent, AgentCreate, AgentRegistration, AgentStatus, EvaluationMetrics, Mode, Policy, Run, RunCreate, RunStatus, Scorecard, VerificationSummary
from provider import ProviderError
from providers import instrument_ready, paper_order_contract_ready, provider_for, provider_result, structured_result
from score import metrics, paper_verification, score


CONFIG: Config = load_config()
DB_PATH: Path = CONFIG.db_path
db.init_db(DB_PATH)
app = FastAPI(title="EVA", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[CONFIG.frontend_origin], allow_credentials=False, allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])
TASKS: dict[str, asyncio.Task[None]] = {}
REQUESTS: dict[str, RunCreate] = {}
LIMITER = RateLimiter()


def _provider_id(adapter: object) -> str:
    return str(getattr(adapter, "provider_id", CONFIG.execution_provider))


def _provider_capabilities(adapter: object) -> list[str]:
    capabilities = getattr(adapter, "capabilities", None)
    value = capabilities() if callable(capabilities) else []
    return [str(item) for item in value] if isinstance(value, list) else []


def _paper_provider(payload: RunCreate) -> RunCreate:
    if payload.mode not in {Mode.PAPER, Mode.BITGET_PAPER}:
        return payload
    provider_id = payload.execution_provider or CONFIG.execution_provider
    try:
        provider_for(CONFIG, provider_id)
    except ProviderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return payload.model_copy(update={"execution_provider": provider_id})


def _onboarding_evaluation() -> dict[str, object]:
    try:
        adapter = provider_for(CONFIG)
    except ProviderError:
        return {"synthetic": "READY", "paper": "NOT_SUPPORTED_YET", "execution_provider": CONFIG.execution_provider, "provider_capabilities": []}
    capabilities = _provider_capabilities(adapter)
    paper = "READY" if CONFIG.bitget_mode == "paper" and "paper_order" in capabilities else "NOT_SUPPORTED_YET"
    return {"synthetic": "READY", "paper": paper, "execution_provider": _provider_id(adapter), "provider_capabilities": capabilities}


def _limit(request: Request, bucket: str, limit: int, window: float) -> None:
    client = request.client.host if request.client else "unknown"
    if not LIMITER.allow(f"{bucket}:{client}", limit, window):
        raise HTTPException(status_code=429, detail="RATE_LIMITED")


def _run(run_id: str) -> Run:
    try:
        return db.get_run(DB_PATH, run_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND") from error


async def _execute(run_id: str) -> None:
    try:
        await asyncio.to_thread(graph.run, CONFIG, DB_PATH, run_id)
    except Exception:
        try:
            db.update_run(DB_PATH, run_id, status=RunStatus.FAILED, stage="FAILED", failure="TARGET_ERROR", finished=True)
            db.add_event(DB_PATH, run_id, "RUN_FAILED", {"code": "RUN_FAILED"})
        except Exception:
            pass
    finally:
        TASKS.pop(run_id, None)


def _schedule(run_id: str) -> None:
    if run_id not in TASKS:
        TASKS[run_id] = asyncio.create_task(_execute(run_id))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/verification/preflight")
def verification_preflight(target_url: str | None = None, target_name: str | None = None, target_model: str | None = None) -> dict[str, object]:
    reasons: list[str] = []
    if CONFIG.qwen_api_key:
        qwen_status = "CONFIGURED"
    else:
        qwen_status = "UNVERIFIED"
        reasons.append("QWEN_UNAVAILABLE")
    external_ready = bool(target_url and urlparse(target_url).scheme in {"http", "https"})
    if not external_ready:
        reasons.append("TARGET_URL_REQUIRED")
    if not target_name or not target_model:
        reasons.append("TARGET_IDENTITY_REQUIRED")
    try:
        adapter = provider_for(CONFIG)
    except ProviderError as error:
        reasons.append(str(error))
        return {"qwen": qwen_status, "execution_provider": CONFIG.execution_provider, "provider_capabilities": [], "bitget_cli": "UNVERIFIED", "bitget_market": "UNVERIFIED", "bitget_instrument": "UNVERIFIED", "bitget_account": "UNVERIFIED", "bitget_paper": "UNVERIFIED", "external_target": "READY" if external_ready else "UNVERIFIED", "paper_run_ready": False, "environment_ready": False, "official_track2_ready": False, "blocking_reasons": list(dict.fromkeys(reasons))}
    discovery = adapter.discover()
    cli_ready = discovery.get("status") == "ok" and structured_result(discovery)
    if discovery.get("code") == "BITGET_CLI_MISSING":
        reasons.append("BITGET_CLI_MISSING")
    elif not cli_ready:
        reasons.append("BITGET_PAPER_UNAVAILABLE")
    paper_contract = adapter.paper_order_contract() if cli_ready else None
    paper_ready = CONFIG.bitget_mode == "paper" and paper_order_contract_ready(paper_contract)
    if not paper_ready:
        reasons.append("BITGET_PAPER_UNAVAILABLE")
    symbol, market = adapter.resolve_symbol(Policy().allowed_symbols) if cli_ready else (None, None)
    if market is not None and symbol:
        market = provider_result(adapter, market, "market", {"symbol": symbol})
    market_ready = symbol is not None and market is not None and structured_result(market)
    instrument = provider_result(adapter, adapter.instrument(symbol), "instrument", {"symbol": symbol}) if market_ready and symbol else None
    instrument_is_ready = bool(symbol and instrument and structured_result(instrument) and instrument_ready(instrument, symbol))
    account_ready = False
    if cli_ready:
        try:
            account = provider_result(adapter, adapter.account(), "account")
            account_ready = account.get("status") == "ok" and "DEMO_ACCOUNT" in account.get("labels", []) and structured_result(account)
        except ProviderError:
            account_ready = False
    if not market_ready:
        reasons.append("BITGET_MARKET_UNVERIFIED")
    if not instrument_is_ready:
        reasons.append("BITGET_INSTRUMENT_UNVERIFIED")
    if not account_ready:
        reasons.append("BITGET_ACCOUNT_UNVERIFIED")
    if CONFIG.bitget_mode != "paper":
        reasons.append("BITGET_PAPER_UNAVAILABLE")
    reasons = list(dict.fromkeys(reasons))
    environment_ready = not reasons
    return {
        "qwen": qwen_status,
        "bitget_cli": "READY" if cli_ready else "UNVERIFIED",
        "bitget_market": "READY" if market_ready else "UNVERIFIED",
        "execution_provider": _provider_id(adapter),
        "provider_capabilities": _provider_capabilities(adapter),
        "bitget_instrument": "READY" if instrument_is_ready else "UNVERIFIED",
        "bitget_account": "READY" if account_ready else "UNVERIFIED",
        "bitget_paper": "READY" if paper_ready else "UNVERIFIED",
        "external_target": "READY" if external_ready else "UNVERIFIED",
        "paper_run_ready": environment_ready,
        "environment_ready": environment_ready,
        "official_track2_ready": environment_ready,
        "blocking_reasons": reasons,
    }


@app.get("/targets")
def target_list():
    return db.targets()


@app.post("/v1/agents", response_model=AgentRegistration, status_code=201)
def register_agent(request: Request, payload: AgentCreate) -> AgentRegistration:
    _limit(request, "agent-registration", 10, 3600)
    owner_id = auth.require_control_plane(request, CONFIG)
    api_key, key_salt, key_hash = auth.issue_agent_key()
    agent_id = auth.issue_id("agt")
    key_id = auth.issue_id("key")
    agent = db.create_agent(DB_PATH, payload, owner_id, agent_id, key_id, key_hash, key_salt)
    key = db.get_agent_key(DB_PATH, agent_id, key_id)
    return AgentRegistration(agent=agent, key=key, api_key=api_key)


@app.get("/v1/agents/{agent_id}", response_model=Agent)
def read_agent(request: Request, agent_id: str) -> Agent:
    _limit(request, "agent-read", 120, 60)
    return auth.require_agent_access(request, CONFIG, DB_PATH, agent_id)


@app.get("/v1/agents/{agent_id}/onboarding")
def agent_onboarding(request: Request, agent_id: str) -> dict[str, object]:
    agent = auth.require_agent_access(request, CONFIG, DB_PATH, agent_id)
    return {"agent_id": agent.agent_id, "protocol": agent.protocol_version, "gateway_path": "/v1/agent/connect", "evaluation": _onboarding_evaluation(), "methods": [{"id": "ai-agent", "name": "AI Agent", "command": "Use the setup prompt with your coding agent."}, {"id": "cli", "name": "CLI", "command": "npx @eva-ai/cli onboard --api-url <EVA_API_URL> --control-token <CONTROL_PLANE_TOKEN> --name <AGENT_NAME> --version <VERSION> --model <MODEL> --json"}, {"id": "typescript", "name": "TypeScript", "command": "npm install @eva-ai/sdk"}, {"id": "python", "name": "Python", "command": "pip install eva-agent"}, {"id": "manual", "name": "Manual", "command": "Follow docs/protocol.md."}], "prompt": f"Register {agent.name} with EVA using agent_id {agent.agent_id}. Set EVA_API_KEY and EVA_AGENT_ID in the runtime environment, connect outbound to /v1/agent/connect with protocol eva-agent/1, and report the ONLINE status. Run only SYNTHETIC evaluation during setup."}


@app.post("/v1/agents/{agent_id}/keys", response_model=AgentRegistration, status_code=201)
def create_agent_key(request: Request, agent_id: str) -> AgentRegistration:
    _limit(request, f"agent-key:{agent_id}", 30, 60)
    agent = auth.require_agent_access(request, CONFIG, DB_PATH, agent_id)
    api_key, key_salt, key_hash = auth.issue_agent_key()
    key_id = auth.issue_id("key")
    key = db.create_agent_key(DB_PATH, agent_id, key_id, key_hash, key_salt)
    return AgentRegistration(agent=agent, key=key, api_key=api_key)


@app.delete("/v1/agents/{agent_id}/keys/{key_id}", status_code=204)
def revoke_agent_key(request: Request, agent_id: str, key_id: str) -> Response:
    _limit(request, f"agent-key:{agent_id}", 30, 60)
    auth.require_agent_access(request, CONFIG, DB_PATH, agent_id)
    try:
        db.revoke_agent_key(DB_PATH, agent_id, key_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="KEY_NOT_FOUND") from error
    return Response(status_code=204)


@app.websocket("/v1/agent/connect")
async def agent_connect(websocket: WebSocket) -> None:
    await websocket.accept()
    session = None
    writer = None
    client = websocket.client.host if websocket.client else "unknown"
    if not LIMITER.allow(f"gateway-connect:{client}", 30, 60):
        await websocket.close(code=4429)
        return
    try:
        hello = await asyncio.wait_for(websocket.receive_json(), 10)
        if len(json.dumps(hello, separators=(",", ":"))) > 65536:
            await websocket.close(code=4400)
            return
        agent_id = hello.get("agent_id") if isinstance(hello, dict) else None
        try:
            token = auth.parse_bearer(websocket.headers.get("Authorization"))
        except HTTPException:
            await websocket.close(code=4401)
            return
        if not isinstance(agent_id, str) or not token:
            await websocket.close(code=4401)
            return
        try:
            agent = auth.authenticate_agent(CONFIG, DB_PATH, agent_id, token, mark_seen=True)
        except HTTPException as error:
            await websocket.close(code=4403 if error.status_code == 403 else 4401)
            return
        if not gateway.hello_matches(agent, hello):
            await websocket.close(code=4400)
            return
        try:
            session = gateway.registry.connect(agent_id, gateway.connection_id())
        except gateway.GatewayError:
            await websocket.close(code=4429)
            return
        db.set_agent_status(DB_PATH, agent_id, AgentStatus.ONLINE)
        await websocket.send_json(gateway.ready_message(session))
        writer = asyncio.create_task(_write_gateway_messages(websocket, session))
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), 30)
            except asyncio.TimeoutError:
                if session.expired(60):
                    await websocket.close(code=4408)
                    return
                session.send({"type": "ping", "nonce": uuid4().hex})
                continue
            response = gateway.handle_client_message(session, message)
            if response:
                session.send(response)
    except (WebSocketDisconnect, gateway.GatewayError, ValueError, KeyError):
        pass
    finally:
        if session:
            gateway.registry.disconnect(session)
            if writer:
                writer.cancel()
            try:
                db.set_agent_status(DB_PATH, session.agent_id, AgentStatus.OFFLINE)
            except KeyError:
                pass


async def _write_gateway_messages(websocket: WebSocket, session: gateway.Session) -> None:
    while not session.closed:
        message = await asyncio.to_thread(gateway.poll_outbound, session)
        if message:
            await websocket.send_json(message)


@app.post("/v1/evaluations", response_model=Run, status_code=201)
async def create_evaluation(request: Request, payload: RunCreate) -> Run:
    _limit(request, "evaluation-start", 10, 3600)
    if not payload.agent_id:
        raise HTTPException(status_code=422, detail="AGENT_ID_REQUIRED")
    agent = auth.require_agent_access(request, CONFIG, DB_PATH, payload.agent_id)
    session = gateway.registry.get(payload.agent_id)
    if not session:
        raise HTTPException(status_code=409, detail="AGENT_OFFLINE")
    if session.evaluation_active:
        raise HTTPException(status_code=409, detail="EVALUATION_ALREADY_ACTIVE")
    if payload.target_id != "GATEWAY":
        raise HTTPException(status_code=422, detail="GATEWAY_TARGET_REQUIRED")
    payload = payload.model_copy(update={"target_name": agent.name, "target_version": agent.version, "target_model": agent.declared_model})
    payload = _paper_provider(payload)
    run = db.create_run(DB_PATH, payload)
    REQUESTS[run.id] = payload
    graph.set_target(run.id, None, None)
    db.add_event(DB_PATH, run.id, "RUN_CREATED", {"target_id": run.target_id, "agent_id": run.agent_id, "mode": run.mode.value, "max_episodes": run.max_episodes})
    _schedule(run.id)
    return run


def _authorized_evaluation(request: Request, evaluation_id: str) -> Run:
    _limit(request, "evaluation-read", 120, 60)
    run = _run(evaluation_id)
    if not run.agent_id:
        raise HTTPException(status_code=404, detail="EVALUATION_NOT_FOUND")
    auth.require_agent_access(request, CONFIG, DB_PATH, run.agent_id)
    return run


@app.get("/v1/evaluations/{evaluation_id}", response_model=Run)
def read_evaluation(request: Request, evaluation_id: str) -> Run:
    return _authorized_evaluation(request, evaluation_id)


@app.get("/v1/evaluations/{evaluation_id}/score", response_model=Scorecard)
def evaluation_score(request: Request, evaluation_id: str) -> Scorecard:
    run = _authorized_evaluation(request, evaluation_id)
    return score(db.get_episodes(DB_PATH, run.id))


@app.get("/v1/evaluations/{evaluation_id}/evidence")
def evaluation_evidence(request: Request, evaluation_id: str) -> dict[str, object]:
    run = _authorized_evaluation(request, evaluation_id)
    return {"evaluation_id": run.id, "agent_id": run.agent_id, "evidence_root": run.evidence_root, "journal_valid": journal.verify_entries([journal.event_entry(item) for item in db.get_events(DB_PATH, run.id)], run.evidence_root), "events": db.get_events(DB_PATH, run.id), "episodes": db.get_episodes(DB_PATH, run.id)}


@app.get("/v1/evaluations/{evaluation_id}/journal")
def evaluation_journal(request: Request, evaluation_id: str) -> dict[str, object]:
    run = _authorized_evaluation(request, evaluation_id)
    entries = [journal.event_entry(item) for item in db.get_events(DB_PATH, run.id)]
    return {"evaluation_id": run.id, "evidence_root": run.evidence_root, "valid": journal.verify_entries(entries, run.evidence_root), "entries": entries}


@app.get("/v1/agents/{agent_id}/evaluations", response_model=list[Run])
def agent_evaluations(request: Request, agent_id: str) -> list[Run]:
    _limit(request, "evaluation-history", 120, 60)
    auth.require_agent_access(request, CONFIG, DB_PATH, agent_id)
    return db.list_agent_runs(DB_PATH, agent_id)


@app.get("/v1/agents/{agent_id}/weaknesses")
def agent_weaknesses(request: Request, agent_id: str):
    _limit(request, "weakness-read", 120, 60)
    auth.require_agent_access(request, CONFIG, DB_PATH, agent_id)
    runs = db.list_agent_runs(DB_PATH, agent_id, 100)
    values = []
    seen: set[tuple[str, str, str]] = set()
    for run in runs:
        for weakness in db.get_weaknesses(DB_PATH, run.target_id, run.target_version):
            key = (run.target_id, weakness.category, weakness.failure_type)
            if key not in seen:
                seen.add(key)
                values.append(weakness)
    return values


@app.post("/v1/evaluations/{evaluation_id}/stop", response_model=Run)
def stop_evaluation(request: Request, evaluation_id: str) -> Run:
    run = _authorized_evaluation(request, evaluation_id)
    if run.status in {RunStatus.COMPLETED, RunStatus.STOPPED, RunStatus.FAILED}:
        return run
    db.request_stop(DB_PATH, run.id)
    return db.update_run(DB_PATH, run.id, stage="STOP_REQUESTED")


@app.get("/v1/evaluations/{evaluation_id}/events")
async def evaluation_events(request: Request, evaluation_id: str):
    run = _authorized_evaluation(request, evaluation_id)
    return StreamingResponse(_events(run.id), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


def _certificate_for(run: Run) -> dict[str, object]:
    if not run.agent_id:
        raise HTTPException(status_code=404, detail="CERTIFICATE_NOT_FOUND")
    if run.status != RunStatus.COMPLETED or not run.finished_at or not run.evidence_root:
        raise HTTPException(status_code=409, detail="EVALUATION_NOT_COMPLETE")
    saved = db.get_certificate(DB_PATH, run.id)
    if saved:
        return saved
    agent = db.get_agent(DB_PATH, run.agent_id)
    card = score(db.get_episodes(DB_PATH, run.id))
    try:
        value = certificate.issue(CONFIG, run.id, agent.agent_id, {"name": agent.name, "version": agent.version, "declared_model": agent.declared_model}, card.score, card.label, card.primary_weakness, run.evidence_root, run.finished_at.isoformat(), run.execution_provider)
    except certificate.CertificateError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    db.save_certificate(DB_PATH, run.id, value)
    return value


@app.get("/v1/certificates/{evaluation_id}")
def read_certificate(request: Request, evaluation_id: str) -> dict[str, object]:
    run = _authorized_evaluation(request, evaluation_id)
    return _certificate_for(run)


@app.get("/v1/certificates/{evaluation_id}/verify")
def verify_certificate(request: Request, evaluation_id: str) -> dict[str, object]:
    run = _authorized_evaluation(request, evaluation_id)
    value = _certificate_for(run)
    return {"evaluation_id": evaluation_id, "valid": certificate.verify(value, run.evidence_root), "signing_key_id": value.get("signing_key_id")}


@app.post("/runs", response_model=Run, status_code=201)
async def create_run(request: RunCreate) -> Run:
    if request.mode not in {Mode.SYNTHETIC, Mode.PAPER, Mode.BITGET_PAPER}:
        raise HTTPException(status_code=422, detail="INVALID_MODE")
    if request.target_id == "EXTERNAL_HTTP" and not request.target_url:
        raise HTTPException(status_code=422, detail="TARGET_URL_REQUIRED")
    if request.target_url and urlparse(request.target_url).scheme not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="INVALID_TARGET_URL")
    request = _paper_provider(request)
    run = db.create_run(DB_PATH, request)
    REQUESTS[run.id] = request
    graph.set_target(run.id, request.target_url, request.target_token)
    db.add_event(DB_PATH, run.id, "RUN_CREATED", {"target_id": run.target_id, "target_name": run.target_name, "target_version": run.target_version, "target_model": run.target_model, "mode": run.mode.value, "max_episodes": run.max_episodes})
    _schedule(run.id)
    return run


@app.get("/runs", response_model=list[Run])
def list_run():
    return db.list_runs(DB_PATH)


@app.get("/runs/{run_id}", response_model=Run)
def read_run(run_id: str) -> Run:
    return _run(run_id)


@app.get("/runs/{run_id}/episodes")
def episodes(run_id: str):
    _run(run_id)
    return db.get_episodes(DB_PATH, run_id)


@app.get("/runs/{run_id}/weaknesses")
def weaknesses(run_id: str):
    run = _run(run_id)
    return db.get_weaknesses(DB_PATH, run.target_id, run.target_version)


@app.get("/runs/{run_id}/score", response_model=Scorecard)
def run_score(run_id: str) -> Scorecard:
    _run(run_id)
    return score(db.get_episodes(DB_PATH, run_id))


@app.get("/runs/{run_id}/verification", response_model=VerificationSummary)
def run_verification(run_id: str) -> VerificationSummary:
    run = _run(run_id)
    return paper_verification(run.mode, run.target_id, db.get_episodes(DB_PATH, run_id), run.target_url, run.target_name, run.target_version, run.target_model, run.execution_provider)


@app.get("/runs/{run_id}/metrics", response_model=EvaluationMetrics)
def run_metrics(run_id: str) -> EvaluationMetrics:
    _run(run_id)
    return metrics(db.get_episodes(DB_PATH, run_id))


async def _events(run_id: str) -> AsyncIterator[str]:
    last_id = 0
    while True:
        events = db.get_events(DB_PATH, run_id, last_id)
        for event in events:
            last_id = event.id or last_id
            yield f"id: {last_id}\ndata: {json.dumps(event.model_dump(mode='json'), separators=(',', ':'))}\n\n"
        run = db.get_run(DB_PATH, run_id)
        if run.status in {RunStatus.COMPLETED, RunStatus.STOPPED, RunStatus.FAILED} and not events:
            break
        await asyncio.sleep(0.25)


@app.get("/runs/{run_id}/events")
async def events(run_id: str):
    _run(run_id)
    return StreamingResponse(_events(run_id), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@app.post("/runs/{run_id}/stop", response_model=Run)
def stop(run_id: str) -> Run:
    run = _run(run_id)
    if run.status in {RunStatus.COMPLETED, RunStatus.STOPPED, RunStatus.FAILED}:
        return run
    db.request_stop(DB_PATH, run_id)
    return db.update_run(DB_PATH, run_id, stage="STOP_REQUESTED")


@app.post("/runs/{run_id}/resume", response_model=Run)
def resume(run_id: str) -> Run:
    run = _run(run_id)
    if run.status not in {RunStatus.STOPPED, RunStatus.FAILED}:
        raise HTTPException(status_code=409, detail="RUN_NOT_RESUMABLE")
    request = REQUESTS.get(run_id)
    if request:
        graph.set_target(run_id, request.target_url, request.target_token)
    resumed = db.resume_run(DB_PATH, run_id)
    _schedule(run_id)
    return resumed
