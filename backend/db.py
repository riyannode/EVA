import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from models import CriticResult, Decision, Episode, Event, LiveOrder, LiveOrderRequest, Mode, OracleResult, Run, RunCreate, RunStatus, Scenario, TargetListing, ToolTrace, Weakness


def now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _text(value: object) -> str:
    return json.dumps(_jsonable(value), separators=(",", ":"), ensure_ascii=True, default=str)


def _payload(value: str) -> dict[str, object]:
    return json.loads(value)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def _session(path: Path):
    connection = _connect(path)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(path: Path) -> None:
    with _session(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                target_id TEXT NOT NULL,
                target_version TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                difficulty INTEGER NOT NULL,
                max_episodes INTEGER NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL,
                current_episode INTEGER NOT NULL DEFAULT 0,
                current_category TEXT,
                current_stage TEXT NOT NULL DEFAULT 'IDLE',
                last_failure TEXT
            );
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id),
                number INTEGER NOT NULL,
                scenario_id TEXT NOT NULL,
                parent_scenario_id TEXT,
                category TEXT NOT NULL,
                difficulty INTEGER NOT NULL,
                scenario_json TEXT NOT NULL,
                target_trace_json TEXT NOT NULL,
                decision_json TEXT,
                oracle_json TEXT NOT NULL,
                critic_json TEXT NOT NULL,
                failure_type TEXT,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, number)
            );
            CREATE TABLE IF NOT EXISTS weaknesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                target_version TEXT NOT NULL,
                failure_type TEXT NOT NULL,
                category TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                fails INTEGER NOT NULL,
                passes INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(target_id, target_version, failure_type, category)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(id),
                episode_id TEXT,
                type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_run_id_id ON events(run_id, id);
            CREATE INDEX IF NOT EXISTS episodes_run_id_number ON episodes(run_id, number);
            CREATE TABLE IF NOT EXISTS live_orders (
                id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                notional TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def create_run(path: Path, request: RunCreate) -> Run:
    run_id = str(uuid.uuid4())
    created = now()
    with _session(path) as connection:
        connection.execute(
            "INSERT INTO runs (id, target_id, target_version, mode, status, difficulty, max_episodes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, request.target_id, request.target_version, request.mode.value, RunStatus.CREATED.value, request.difficulty, request.max_episodes, created.isoformat()),
        )
    return get_run(path, run_id)


def _run(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"],
        target_id=row["target_id"],
        target_version=row["target_version"],
        mode=Mode(row["mode"]),
        status=RunStatus(row["status"]),
        difficulty=row["difficulty"],
        max_episodes=row["max_episodes"],
        episode=row["current_episode"],
        current_category=row["current_category"],
        current_stage=row["current_stage"],
        last_failure=row["last_failure"],
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def get_run(path: Path, run_id: str) -> Run:
    with _session(path) as connection:
        row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise KeyError("RUN_NOT_FOUND")
    return _run(row)


def list_runs(path: Path, limit: int = 25) -> list[Run]:
    with _session(path) as connection:
        rows = connection.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_run(row) for row in rows]


def update_run(path: Path, run_id: str, status: RunStatus | None = None, stage: str | None = None, episode: int | None = None, category: str | None = None, failure: str | None = None, difficulty: int | None = None, finished: bool = False) -> Run:
    fields: list[str] = []
    values: list[object] = []
    if status is not None:
        fields.append("status = ?")
        values.append(status.value)
        if status == RunStatus.RUNNING:
            fields.append("started_at = COALESCE(started_at, ?)")
            values.append(now().isoformat())
    if stage is not None:
        fields.append("current_stage = ?")
        values.append(stage)
    if episode is not None:
        fields.append("current_episode = ?")
        values.append(episode)
    if category is not None:
        fields.append("current_category = ?")
        values.append(category)
    if failure is not None or status in {RunStatus.COMPLETED, RunStatus.STOPPED, RunStatus.FAILED}:
        fields.append("last_failure = ?")
        values.append(failure)
    if difficulty is not None:
        fields.append("difficulty = ?")
        values.append(difficulty)
    if finished:
        fields.append("finished_at = ?")
        values.append(now().isoformat())
    if fields:
        values.append(run_id)
        with _session(path) as connection:
            connection.execute(f"UPDATE runs SET {', '.join(fields)} WHERE id = ?", values)
    return get_run(path, run_id)


def insert_episode(path: Path, run: Run, scenario: Scenario, trace: list[ToolTrace], decision: Decision | None, oracle_results: list[OracleResult], critic: CriticResult, failure_type: str | None, result: str) -> Episode:
    episode_id = str(uuid.uuid4())
    created = now()
    with _session(path) as connection:
        connection.execute(
            "INSERT INTO episodes (id, run_id, number, scenario_id, parent_scenario_id, category, difficulty, scenario_json, target_trace_json, decision_json, oracle_json, critic_json, failure_type, result, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (episode_id, run.id, run.episode, scenario.scenario_id, scenario.parent_scenario_id, scenario.category.value, scenario.difficulty, _text(scenario), _text(trace), _text(decision) if decision else None, _text(oracle_results), _text(critic), failure_type, result, created.isoformat()),
        )
        key_failure = failure_type or "PASS"
        existing = connection.execute(
            "SELECT id, attempts, fails, passes FROM weaknesses WHERE target_id = ? AND target_version = ? AND failure_type = ? AND category = ?",
            (run.target_id, run.target_version, key_failure, scenario.category.value),
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE weaknesses SET attempts = ?, fails = ?, passes = ?, updated_at = ? WHERE id = ?",
                (existing["attempts"] + 1, existing["fails"] + (1 if failure_type else 0), existing["passes"] + (0 if failure_type else 1), created.isoformat(), existing["id"]),
            )
        else:
            connection.execute(
                "INSERT INTO weaknesses (target_id, target_version, failure_type, category, attempts, fails, passes, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run.target_id, run.target_version, key_failure, scenario.category.value, 1, 1 if failure_type else 0, 0 if failure_type else 1, created.isoformat()),
            )
    update_run(path, run.id, stage="SAVE_MEMORY", failure=failure_type)
    return Episode(id=episode_id, run_id=run.id, number=run.episode, scenario_id=scenario.scenario_id, parent_scenario_id=scenario.parent_scenario_id, category=scenario.category.value, difficulty=scenario.difficulty, scenario=scenario, target_trace=trace, decision=decision, oracle_results=oracle_results, critic=critic, failure_type=failure_type, result=result, created_at=created)


def _episode(row: sqlite3.Row) -> Episode:
    return Episode(
        id=row["id"],
        run_id=row["run_id"],
        number=row["number"],
        scenario_id=row["scenario_id"],
        parent_scenario_id=row["parent_scenario_id"],
        category=row["category"],
        difficulty=row["difficulty"],
        scenario=Scenario.model_validate(_payload(row["scenario_json"])),
        target_trace=[ToolTrace.model_validate(item) for item in json.loads(row["target_trace_json"])],
        decision=Decision.model_validate(_payload(row["decision_json"])) if row["decision_json"] else None,
        oracle_results=[OracleResult.model_validate(item) for item in json.loads(row["oracle_json"])],
        critic=CriticResult.model_validate(_payload(row["critic_json"])),
        failure_type=row["failure_type"],
        result=row["result"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def get_episodes(path: Path, run_id: str) -> list[Episode]:
    with _session(path) as connection:
        rows = connection.execute("SELECT * FROM episodes WHERE run_id = ? ORDER BY number", (run_id,)).fetchall()
    return [_episode(row) for row in rows]


def _live_order(row: sqlite3.Row) -> LiveOrder:
    return LiveOrder(
        id=row["id"],
        idempotency_key=row["idempotency_key"],
        symbol=row["symbol"],
        side=row["side"],
        notional=Decimal(row["notional"]),
        status=row["status"],
        result=_payload(row["result_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def get_live_order(path: Path, order_id: str) -> LiveOrder:
    with _session(path) as connection:
        row = connection.execute("SELECT * FROM live_orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        raise KeyError("ORDER_NOT_FOUND")
    return _live_order(row)


def reserve_live_order(path: Path, request: LiveOrderRequest) -> tuple[LiveOrder, bool]:
    order_id = str(uuid.uuid4())
    created = now()
    try:
        with _session(path) as connection:
            connection.execute(
                "INSERT INTO live_orders (id, idempotency_key, symbol, side, notional, status, result_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (order_id, request.idempotency_key, request.symbol, request.side, str(request.notional), "SUBMITTING", "{}", created.isoformat(), created.isoformat()),
            )
    except sqlite3.IntegrityError:
        with _session(path) as connection:
            row = connection.execute("SELECT * FROM live_orders WHERE idempotency_key = ?", (request.idempotency_key,)).fetchone()
        if row is None:
            raise
        if row["symbol"] != request.symbol or row["side"] != request.side or Decimal(row["notional"]) != request.notional:
            raise ValueError("IDEMPOTENCY_CONFLICT")
        return _live_order(row), False
    return get_live_order(path, order_id), True


def update_live_order(path: Path, order_id: str, status: str, result: dict[str, object]) -> LiveOrder:
    updated = now()
    with _session(path) as connection:
        connection.execute("UPDATE live_orders SET status = ?, result_json = ?, updated_at = ? WHERE id = ?", (status, _text(result), updated.isoformat(), order_id))
    return get_live_order(path, order_id)


def get_weaknesses(path: Path, target_id: str | None = None, target_version: str | None = None) -> list[Weakness]:
    query = "SELECT * FROM weaknesses WHERE failure_type != 'PASS'"
    values: list[object] = []
    if target_id is not None:
        query += " AND target_id = ?"
        values.append(target_id)
    if target_version is not None:
        query += " AND target_version = ?"
        values.append(target_version)
    query += " ORDER BY fails DESC, updated_at DESC"
    with _session(path) as connection:
        rows = connection.execute(query, values).fetchall()
    return [Weakness(failure_type=row["failure_type"], category=row["category"], attempts=row["attempts"], fails=row["fails"], passes=row["passes"], failure_rate=round(row["fails"] / row["attempts"], 4), updated_at=datetime.fromisoformat(row["updated_at"])) for row in rows]


def add_event(path: Path, run_id: str, event_type: str, payload: dict[str, object], episode_id: str | None = None) -> Event:
    created = now()
    with _session(path) as connection:
        cursor = connection.execute("INSERT INTO events (run_id, episode_id, type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)", (run_id, episode_id, event_type, _text(payload), created.isoformat()))
        event_id = cursor.lastrowid
    return Event(id=event_id, run_id=run_id, episode_id=episode_id, type=event_type, payload=payload, created_at=created)


def get_events(path: Path, run_id: str, after_id: int = 0) -> list[Event]:
    with _session(path) as connection:
        rows = connection.execute("SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id", (run_id, after_id)).fetchall()
    return [Event(id=row["id"], run_id=row["run_id"], episode_id=row["episode_id"], type=row["type"], payload=_payload(row["payload_json"]), created_at=datetime.fromisoformat(row["created_at"])) for row in rows]


def request_stop(path: Path, run_id: str) -> None:
    add_event(path, run_id, "STOP_REQUESTED", {})


def stop_requested(path: Path, run_id: str) -> bool:
    with _session(path) as connection:
        row = connection.execute("SELECT type FROM events WHERE run_id = ? AND type IN ('STOP_REQUESTED', 'RESUMED') ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()
    return row is not None and row["type"] == "STOP_REQUESTED"


def resume_run(path: Path, run_id: str) -> Run:
    with _session(path) as connection:
        connection.execute("UPDATE runs SET status = ?, finished_at = NULL, current_stage = ? WHERE id = ?", (RunStatus.CREATED.value, "RESUME", run_id))
    add_event(path, run_id, "RESUMED", {})
    return get_run(path, run_id)


def targets() -> list[TargetListing]:
    return [
        TargetListing(target_id="REFERENCE_WEAK", target_version="v1", kind="reference"),
        TargetListing(target_id="REFERENCE_SAFE", target_version="v1", kind="reference"),
        TargetListing(target_id="EXTERNAL_HTTP", target_version="configured", kind="http"),
    ]
