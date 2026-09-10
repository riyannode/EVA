import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import db
import graph
from bitget import BitgetAdapter, BitgetError, instrument_record, paper_order_contract_ready, structured_result
from config import Config, load_config
from models import EvaluationMetrics, Mode, Policy, Run, RunCreate, RunStatus, Scorecard, VerificationSummary
from score import metrics, paper_verification, score


CONFIG: Config = load_config()
DB_PATH: Path = CONFIG.db_path
db.init_db(DB_PATH)
app = FastAPI(title="EVA", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[CONFIG.frontend_origin], allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])
TASKS: dict[str, asyncio.Task[None]] = {}
REQUESTS: dict[str, RunCreate] = {}


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
    adapter = BitgetAdapter(CONFIG)
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
    market_ready = symbol is not None and market is not None and structured_result(market)
    instrument = adapter.instrument(symbol) if market_ready and symbol else None
    instrument_ready = bool(symbol and instrument and structured_result(instrument) and instrument_record(instrument, symbol))
    account_ready = False
    if cli_ready:
        try:
            account = adapter.account()
            account_ready = account.get("status") == "ok" and "DEMO_ACCOUNT" in account.get("labels", []) and structured_result(account)
        except BitgetError:
            account_ready = False
    if not market_ready:
        reasons.append("BITGET_MARKET_UNVERIFIED")
    if not instrument_ready:
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
        "bitget_instrument": "READY" if instrument_ready else "UNVERIFIED",
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


@app.post("/runs", response_model=Run, status_code=201)
async def create_run(request: RunCreate) -> Run:
    if request.mode not in {Mode.SYNTHETIC, Mode.BITGET_PAPER}:
        raise HTTPException(status_code=422, detail="INVALID_MODE")
    if request.target_id == "EXTERNAL_HTTP" and not request.target_url:
        raise HTTPException(status_code=422, detail="TARGET_URL_REQUIRED")
    if request.target_url and urlparse(request.target_url).scheme not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="INVALID_TARGET_URL")
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
    return paper_verification(run.mode, run.target_id, db.get_episodes(DB_PATH, run_id), run.target_url, run.target_name, run.target_version, run.target_model)


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
