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
from bitget import BitgetAdapter, BitgetError
from config import Config, load_config
from models import LiveOrder, LiveOrderDraft, LiveOrderRequest, Mode, Run, RunCreate, RunStatus, Scorecard
from score import score


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


@app.get("/trading/status")
def trading_status() -> dict[str, object]:
    return {
        "mode": CONFIG.bitget_mode,
        "live_trading_enabled": CONFIG.live_trading_enabled,
        "market_reads": True,
        "paper_orders": CONFIG.bitget_mode == "paper",
        "live_orders": CONFIG.bitget_mode == "live" and CONFIG.live_trading_enabled,
    }


@app.post("/trading/orders/preview")
def preview_live_order(request: LiveOrderDraft) -> dict[str, object]:
    return {
        "symbol": request.symbol,
        "side": request.side,
        "notional": str(request.notional),
        "mode": CONFIG.bitget_mode,
        "armed": CONFIG.bitget_mode == "live" and CONFIG.live_trading_enabled,
    }


@app.post("/trading/orders", response_model=LiveOrder)
def execute_live_order(request: LiveOrderRequest) -> LiveOrder:
    if not request.confirm:
        raise HTTPException(status_code=409, detail="LIVE_CONFIRMATION_REQUIRED")
    if CONFIG.bitget_mode != "live":
        raise HTTPException(status_code=409, detail="LIVE_MODE_REQUIRED")
    if not CONFIG.live_trading_enabled:
        raise HTTPException(status_code=503, detail="LIVE_TRADING_DISABLED")
    try:
        order, created = db.reserve_live_order(DB_PATH, request)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not created:
        return order
    try:
        result = BitgetAdapter(CONFIG).live_order(request.symbol, request.side, request.notional)
    except BitgetError as error:
        result = {"status": "error", "code": str(error)}
    status = "SUBMITTED" if result.get("status") == "ok" else "UNKNOWN" if result.get("status") == "unknown" else "FAILED"
    return db.update_live_order(DB_PATH, order.id, status, result)


@app.get("/trading/orders/{order_id}", response_model=LiveOrder)
def read_live_order(order_id: str) -> LiveOrder:
    try:
        return db.get_live_order(DB_PATH, order_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND") from error


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
    db.add_event(DB_PATH, run.id, "RUN_CREATED", {"target_id": run.target_id, "mode": run.mode.value, "max_episodes": run.max_episodes})
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
