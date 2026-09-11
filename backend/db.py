import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from models import Agent, AgentCapabilityState, AgentCreate, AgentKey, AgentStatus, CriticResult, Decision, Episode, Event, Mode, OracleResult, PairingRequest, PairingRequestCreate, Run, RunCreate, RunStatus, Scenario, TargetListing, ToolTrace, Weakness
from journal import ZERO_HASH, canonical_entry, hash_entry


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


def _backfill_journal(connection: sqlite3.Connection) -> None:
    run_ids = connection.execute("SELECT DISTINCT run_id FROM events ORDER BY run_id").fetchall()
    for item in run_ids:
        run_id = item["run_id"]
        previous = ZERO_HASH
        latest = None
        rows = connection.execute("SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        if rows and all(row["sequence"] and row["prev_hash"] and row["entry_hash"] for row in rows):
            continue
        for sequence, row in enumerate(rows, 1):
            content = canonical_entry(run_id, sequence, row["episode_id"], row["type"], _payload(row["payload_json"]), row["created_at"], previous)
            entry = hash_entry(content)
            connection.execute("UPDATE events SET sequence = ?, prev_hash = ?, entry_hash = ? WHERE id = ?", (sequence, previous, entry, row["id"]))
            previous = entry
            latest = entry
        if latest:
            connection.execute("UPDATE runs SET evidence_root = COALESCE(evidence_root, ?) WHERE id = ?", (latest, run_id))


def init_db(path: Path) -> None:
    with _session(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                agent_id TEXT,
                execution_provider TEXT,
                target_id TEXT NOT NULL,
                target_version TEXT NOT NULL,
                target_name TEXT,
                target_model TEXT,
                target_url TEXT,
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
                last_failure TEXT,
                evidence_root TEXT
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
                sequence INTEGER,
                type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                prev_hash TEXT,
                entry_hash TEXT
            );
            CREATE INDEX IF NOT EXISTS events_run_id_id ON events(run_id, id);
            CREATE INDEX IF NOT EXISTS episodes_run_id_number ON episodes(run_id, number);
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                declared_model TEXT NOT NULL,
                framework TEXT,
                created_at TEXT NOT NULL,
                last_seen_at TEXT,
                status TEXT NOT NULL,
                capability_state TEXT NOT NULL,
                protocol_version TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                execution_providers_json TEXT NOT NULL,
                provider_capabilities_json TEXT NOT NULL,
                evaluation_count INTEGER NOT NULL DEFAULT 0,
                latest_readiness TEXT,
                latest_evaluation_id TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_keys (
                key_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL REFERENCES agents(agent_id),
                key_hash TEXT NOT NULL,
                key_salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                last_used_at TEXT
            );
            CREATE INDEX IF NOT EXISTS agent_keys_agent_id ON agent_keys(agent_id);
            CREATE TABLE IF NOT EXISTS certificates (
                evaluation_id TEXT PRIMARY KEY REFERENCES runs(id),
                certificate_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pairing_requests (
                request_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                declared_model TEXT NOT NULL,
                framework TEXT,
                protocol_version TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                execution_providers_json TEXT NOT NULL,
                provider_capabilities_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                approved_at TEXT,
                exchanged_at TEXT,
                agent_id TEXT REFERENCES agents(agent_id)
            );
            CREATE TABLE IF NOT EXISTS certificate_shares (
                share_token_hash TEXT PRIMARY KEY,
                evaluation_id TEXT NOT NULL REFERENCES certificates(evaluation_id),
                created_at TEXT NOT NULL
            );
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(runs)").fetchall()}
        if "agent_id" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN agent_id TEXT")
        if "execution_provider" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN execution_provider TEXT")
        if "target_name" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN target_name TEXT")
        if "target_model" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN target_model TEXT")
        if "target_url" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN target_url TEXT")
        if "evidence_root" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN evidence_root TEXT")
        event_columns = {row["name"] for row in connection.execute("PRAGMA table_info(events)").fetchall()}
        if "sequence" not in event_columns:
            connection.execute("ALTER TABLE events ADD COLUMN sequence INTEGER")
        if "prev_hash" not in event_columns:
            connection.execute("ALTER TABLE events ADD COLUMN prev_hash TEXT")
        if "entry_hash" not in event_columns:
            connection.execute("ALTER TABLE events ADD COLUMN entry_hash TEXT")
        _backfill_journal(connection)
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS events_run_sequence ON events(run_id, sequence)")
        connection.execute("DROP TABLE IF EXISTS live_orders")


def create_run(path: Path, request: RunCreate) -> Run:
    run_id = str(uuid.uuid4())
    created = now()
    with _session(path) as connection:
        connection.execute(
            "INSERT INTO runs (id, agent_id, execution_provider, target_id, target_version, target_name, target_model, target_url, mode, status, difficulty, max_episodes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, request.agent_id, request.execution_provider or ("bitget" if request.mode == Mode.BITGET_PAPER else None), request.target_id, request.target_version, request.target_name, request.target_model, request.target_url, request.mode.value, RunStatus.CREATED.value, request.difficulty, request.max_episodes, created.isoformat()),
        )
    return get_run(path, run_id)


def _run(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"],
        agent_id=row["agent_id"],
        execution_provider=row["execution_provider"],
        evidence_root=row["evidence_root"],
        target_id=row["target_id"],
        target_version=row["target_version"],
        target_name=row["target_name"],
        target_model=row["target_model"],
        target_url=row["target_url"],
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


def _update_weakness(connection: sqlite3.Connection, run: Run, failure: str, category: str, failed: bool, created: datetime) -> None:
    existing = connection.execute(
        "SELECT id, attempts, fails, passes FROM weaknesses WHERE target_id = ? AND target_version = ? AND failure_type = ? AND category = ?",
        (run.target_id, run.target_version, failure, category),
    ).fetchone()
    if existing:
        connection.execute(
            "UPDATE weaknesses SET attempts = ?, fails = ?, passes = ?, updated_at = ? WHERE id = ?",
            (existing["attempts"] + 1, existing["fails"] + int(failed), existing["passes"] + int(not failed), created.isoformat(), existing["id"]),
        )
    else:
        connection.execute(
            "INSERT INTO weaknesses (target_id, target_version, failure_type, category, attempts, fails, passes, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run.target_id, run.target_version, failure, category, 1, int(failed), int(not failed), created.isoformat()),
        )


def insert_episode(path: Path, run: Run, scenario: Scenario, trace: list[ToolTrace], decision: Decision | None, oracle_results: list[OracleResult], critic: CriticResult, failure_type: str | None, result: str) -> Episode:
    episode_id = str(uuid.uuid4())
    created = now()
    with _session(path) as connection:
        connection.execute(
            "INSERT INTO episodes (id, run_id, number, scenario_id, parent_scenario_id, category, difficulty, scenario_json, target_trace_json, decision_json, oracle_json, critic_json, failure_type, result, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (episode_id, run.id, run.episode, scenario.scenario_id, scenario.parent_scenario_id, scenario.category.value, scenario.difficulty, _text(scenario), _text(trace), _text(decision) if decision else None, _text(oracle_results), _text(critic), failure_type, result, created.isoformat()),
        )
        targeted_failure = scenario.mutation_reason if scenario.parent_scenario_id and scenario.mutation_reason else None
        if targeted_failure:
            _update_weakness(connection, run, targeted_failure, scenario.category.value, failure_type == targeted_failure, created)
        if failure_type and failure_type != targeted_failure:
            _update_weakness(connection, run, failure_type, scenario.category.value, True, created)
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
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT sequence, entry_hash FROM events WHERE run_id = ? ORDER BY sequence DESC, id DESC LIMIT 1", (run_id,)).fetchone()
        sequence = int(row["sequence"] or 0) + 1 if row else 1
        previous = str(row["entry_hash"] or ZERO_HASH) if row else ZERO_HASH
        created_text = created.isoformat()
        content = canonical_entry(run_id, sequence, episode_id, event_type, payload, created_text, previous)
        entry = hash_entry(content)
        cursor = connection.execute("INSERT INTO events (run_id, episode_id, sequence, type, payload_json, created_at, prev_hash, entry_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (run_id, episode_id, sequence, event_type, _text(payload), created_text, previous, entry))
        event_id = cursor.lastrowid
        connection.execute("UPDATE runs SET evidence_root = ? WHERE id = ?", (entry, run_id))
    return Event(id=event_id, run_id=run_id, sequence=sequence, episode_id=episode_id, type=event_type, payload=payload, created_at=created, prev_hash=previous, entry_hash=entry)


def get_events(path: Path, run_id: str, after_id: int = 0) -> list[Event]:
    with _session(path) as connection:
        rows = connection.execute("SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id", (run_id, after_id)).fetchall()
    return [Event(id=row["id"], run_id=row["run_id"], sequence=row["sequence"] or 0, episode_id=row["episode_id"], type=row["type"], payload=_payload(row["payload_json"]), created_at=datetime.fromisoformat(row["created_at"]), prev_hash=row["prev_hash"] or "", entry_hash=row["entry_hash"] or "") for row in rows]


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


def create_agent(path: Path, request: AgentCreate, owner_id: str, agent_id: str, key_id: str, key_hash: str, key_salt: str) -> Agent:
    created = now()
    with _session(path) as connection:
        connection.execute(
            "INSERT INTO agents (agent_id, owner_id, name, version, declared_model, framework, created_at, status, capability_state, protocol_version, capabilities_json, execution_providers_json, provider_capabilities_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, owner_id, request.name, request.version, request.declared_model, request.framework, created.isoformat(), AgentStatus.OFFLINE.value, AgentCapabilityState.REGISTERED.value, request.protocol_version, _text(request.capabilities), _text(request.execution_providers), _text(request.provider_capabilities)),
        )
        connection.execute(
            "INSERT INTO agent_keys (key_id, agent_id, key_hash, key_salt, created_at) VALUES (?, ?, ?, ?, ?)",
            (key_id, agent_id, key_hash, key_salt, created.isoformat()),
        )
    return get_agent(path, agent_id)


def _agent(row: sqlite3.Row) -> Agent:
    return Agent(
        agent_id=row["agent_id"],
        owner_id=row["owner_id"],
        name=row["name"],
        version=row["version"],
        declared_model=row["declared_model"],
        framework=row["framework"],
        created_at=datetime.fromisoformat(row["created_at"]),
        last_seen_at=datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None,
        status=AgentStatus(row["status"]),
        capability_state=AgentCapabilityState(row["capability_state"]),
        protocol_version=row["protocol_version"],
        capabilities=json.loads(row["capabilities_json"]),
        execution_providers=json.loads(row["execution_providers_json"]),
        provider_capabilities=json.loads(row["provider_capabilities_json"]),
        evaluation_count=row["evaluation_count"],
        latest_readiness=row["latest_readiness"],
        latest_evaluation_id=row["latest_evaluation_id"],
    )


def get_agent(path: Path, agent_id: str) -> Agent:
    with _session(path) as connection:
        row = connection.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    if row is None:
        raise KeyError("AGENT_NOT_FOUND")
    return _agent(row)


def get_agent_key(path: Path, agent_id: str, key_id: str) -> AgentKey:
    with _session(path) as connection:
        row = connection.execute("SELECT * FROM agent_keys WHERE agent_id = ? AND key_id = ?", (agent_id, key_id)).fetchone()
    if row is None:
        raise KeyError("KEY_NOT_FOUND")
    return AgentKey(key_id=row["key_id"], agent_id=row["agent_id"], created_at=datetime.fromisoformat(row["created_at"]), revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None, last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None)


def active_agent_keys(path: Path, agent_id: str) -> list[sqlite3.Row]:
    with _session(path) as connection:
        return connection.execute("SELECT * FROM agent_keys WHERE agent_id = ? AND revoked_at IS NULL ORDER BY created_at", (agent_id,)).fetchall()


def create_agent_key(path: Path, agent_id: str, key_id: str, key_hash: str, key_salt: str) -> AgentKey:
    created = now()
    with _session(path) as connection:
        connection.execute("INSERT INTO agent_keys (key_id, agent_id, key_hash, key_salt, created_at) VALUES (?, ?, ?, ?, ?)", (key_id, agent_id, key_hash, key_salt, created.isoformat()))
    return get_agent_key(path, agent_id, key_id)


def revoke_agent_key(path: Path, agent_id: str, key_id: str) -> AgentKey:
    revoked = now()
    with _session(path) as connection:
        cursor = connection.execute("UPDATE agent_keys SET revoked_at = COALESCE(revoked_at, ?) WHERE agent_id = ? AND key_id = ?", (revoked.isoformat(), agent_id, key_id))
        if cursor.rowcount == 0:
            raise KeyError("KEY_NOT_FOUND")
    return get_agent_key(path, agent_id, key_id)


def mark_agent_seen(path: Path, agent_id: str) -> Agent:
    seen = now()
    with _session(path) as connection:
        connection.execute("UPDATE agents SET last_seen_at = ? WHERE agent_id = ?", (seen.isoformat(), agent_id))
    return get_agent(path, agent_id)


def set_agent_status(path: Path, agent_id: str, status: AgentStatus) -> Agent:
    with _session(path) as connection:
        capability = AgentCapabilityState.SYNTHETIC_READY.value if status == AgentStatus.ONLINE else None
        if capability:
            connection.execute("UPDATE agents SET status = ?, capability_state = CASE WHEN capability_state = ? THEN ? ELSE capability_state END WHERE agent_id = ?", (status.value, AgentCapabilityState.REGISTERED.value, capability, agent_id))
        else:
            connection.execute("UPDATE agents SET status = ? WHERE agent_id = ?", (status.value, agent_id))
    return get_agent(path, agent_id)


def set_agent_capability_state(path: Path, agent_id: str, owner_id: str, eligible: bool) -> Agent:
    with _session(path) as connection:
        row = connection.execute("SELECT capability_state, status, last_seen_at FROM agents WHERE agent_id = ? AND owner_id = ?", (agent_id, owner_id)).fetchone()
        if row is None:
            raise KeyError("AGENT_NOT_FOUND")
        if eligible:
            capability = AgentCapabilityState.PAPER_ELIGIBLE.value
        else:
            synthetic_ready = row["capability_state"] != AgentCapabilityState.REGISTERED.value or row["last_seen_at"] is not None or row["status"] != AgentStatus.OFFLINE.value
            capability = AgentCapabilityState.SYNTHETIC_READY.value if synthetic_ready else AgentCapabilityState.REGISTERED.value
        connection.execute("UPDATE agents SET capability_state = ? WHERE agent_id = ? AND owner_id = ?", (capability, agent_id, owner_id))
    return get_agent(path, agent_id)


def list_agent_runs(path: Path, agent_id: str, limit: int = 25) -> list[Run]:
    with _session(path) as connection:
        rows = connection.execute("SELECT * FROM runs WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?", (agent_id, limit)).fetchall()
    return [_run(row) for row in rows]


def record_agent_evaluation(path: Path, agent_id: str, evaluation_id: str, readiness: str) -> Agent:
    with _session(path) as connection:
        connection.execute("UPDATE agents SET evaluation_count = evaluation_count + 1, latest_readiness = ?, latest_evaluation_id = ? WHERE agent_id = ?", (readiness, evaluation_id, agent_id))
    return get_agent(path, agent_id)


def get_certificate(path: Path, evaluation_id: str) -> dict[str, object] | None:
    with _session(path) as connection:
        row = connection.execute("SELECT certificate_json FROM certificates WHERE evaluation_id = ?", (evaluation_id,)).fetchone()
    return json.loads(row["certificate_json"]) if row else None


def save_certificate(path: Path, evaluation_id: str, certificate: dict[str, object]) -> None:
    with _session(path) as connection:
        connection.execute("INSERT OR REPLACE INTO certificates (evaluation_id, certificate_json, created_at) VALUES (?, ?, ?)", (evaluation_id, _text(certificate), now().isoformat()))


def create_pairing(path: Path, request_id: str, request: PairingRequestCreate, expires_at: datetime, approval_url: str) -> PairingRequest:
    created = now()
    with _session(path) as connection:
        connection.execute(
            "INSERT INTO pairing_requests (request_id, name, version, declared_model, framework, protocol_version, capabilities_json, execution_providers_json, provider_capabilities_json, status, created_at, expires_at, approved_at, exchanged_at, agent_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (request_id, request.name, request.version, request.declared_model, request.framework, request.protocol_version, _text(request.capabilities), _text(request.execution_providers), _text(request.provider_capabilities), "PENDING", created.isoformat(), expires_at.isoformat(), None, None, None),
        )
    return get_pairing(path, request_id, approval_url)


def _pairing(row: sqlite3.Row, approval_url: str) -> PairingRequest:
    return PairingRequest(request_id=row["request_id"], status=row["status"], expires_at=datetime.fromisoformat(row["expires_at"]), approval_url=approval_url, agent_id=row["agent_id"])


def get_pairing(path: Path, request_id: str, approval_url: str) -> PairingRequest:
    with _session(path) as connection:
        row = connection.execute("SELECT * FROM pairing_requests WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:
            raise KeyError("PAIRING_NOT_FOUND")
        if row["status"] == "PENDING" and datetime.fromisoformat(row["expires_at"]) <= now():
            connection.execute("UPDATE pairing_requests SET status = ? WHERE request_id = ?", ("EXPIRED", request_id))
            row = connection.execute("SELECT * FROM pairing_requests WHERE request_id = ?", (request_id,)).fetchone()
    return _pairing(row, approval_url)


def approve_pairing(path: Path, request_id: str) -> None:
    with _session(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT status, expires_at FROM pairing_requests WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:
            raise KeyError("PAIRING_NOT_FOUND")
        if row["status"] != "PENDING":
            raise ValueError("PAIRING_NOT_PENDING")
        if datetime.fromisoformat(row["expires_at"]) <= now():
            connection.execute("UPDATE pairing_requests SET status = ? WHERE request_id = ?", ("EXPIRED", request_id))
            raise ValueError("PAIRING_EXPIRED")
        connection.execute("UPDATE pairing_requests SET status = ?, approved_at = ? WHERE request_id = ?", ("APPROVED", now().isoformat(), request_id))


def exchange_pairing(path: Path, request_id: str, owner_id: str, agent_id: str, key_id: str, key_hash: str, key_salt: str) -> Agent:
    created = now()
    with _session(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM pairing_requests WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:
            raise KeyError("PAIRING_NOT_FOUND")
        if row["status"] != "APPROVED":
            raise ValueError("PAIRING_NOT_APPROVED")
        if datetime.fromisoformat(row["expires_at"]) <= created:
            connection.execute("UPDATE pairing_requests SET status = ? WHERE request_id = ?", ("EXPIRED", request_id))
            raise ValueError("PAIRING_EXPIRED")
        connection.execute(
            "INSERT INTO agents (agent_id, owner_id, name, version, declared_model, framework, created_at, status, capability_state, protocol_version, capabilities_json, execution_providers_json, provider_capabilities_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, owner_id, row["name"], row["version"], row["declared_model"], row["framework"], created.isoformat(), AgentStatus.OFFLINE.value, AgentCapabilityState.REGISTERED.value, row["protocol_version"], row["capabilities_json"], row["execution_providers_json"], row["provider_capabilities_json"]),
        )
        connection.execute("INSERT INTO agent_keys (key_id, agent_id, key_hash, key_salt, created_at) VALUES (?, ?, ?, ?, ?)", (key_id, agent_id, key_hash, key_salt, created.isoformat()))
        connection.execute("UPDATE pairing_requests SET status = ?, exchanged_at = ?, agent_id = ? WHERE request_id = ?", ("EXCHANGED", created.isoformat(), agent_id, request_id))
    return get_agent(path, agent_id)


def create_share(path: Path, evaluation_id: str, token_hash: str) -> None:
    with _session(path) as connection:
        connection.execute("INSERT INTO certificate_shares (share_token_hash, evaluation_id, created_at) VALUES (?, ?, ?)", (token_hash, evaluation_id, now().isoformat()))


def shared_evaluation(path: Path, token_hash: str) -> str:
    with _session(path) as connection:
        row = connection.execute("SELECT evaluation_id FROM certificate_shares WHERE share_token_hash = ?", (token_hash,)).fetchone()
    if row is None:
        raise KeyError("SHARE_NOT_FOUND")
    return str(row["evaluation_id"])
