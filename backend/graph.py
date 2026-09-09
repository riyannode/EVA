import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

import db
import qwen
from bitget import BitgetAdapter
from config import Config
from models import Category, CriticResult, Decision, Mode, OracleResult, RunStatus, Scenario, ToolTrace
from oracle import evaluate, failure_type
from score import paper_verification, score
from target import TargetResult, register_target, run_target


class RunState(TypedDict, total=False):
    run_id: str
    target_id: str
    target_version: str
    mode: str
    status: str
    episode: int
    max_episodes: int
    difficulty: int
    scenario: dict[str, object] | None
    scenario_history: list[str]
    target_trace: list[dict[str, object]]
    target_decision: dict[str, object] | None
    execution_result: dict[str, object]
    oracle_results: list[dict[str, object]]
    critic_result: dict[str, object]
    failure_type: str | None
    weaknesses: list[dict[str, object]]
    recent_results: list[str]
    next_step: str
    started_at: str
    updated_at: str
    mutation_attempts: int
    target_error: str | None
    consistency_decisions: list[dict[str, object] | None]


_CONFIG: Config | None = None
_DB_PATH: Path | None = None


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scenario(state: RunState) -> Scenario:
    value = state.get("scenario")
    if not value:
        raise RuntimeError("SCENARIO_MISSING")
    return Scenario.model_validate(value)


def _decision(state: RunState) -> Decision | None:
    value = state.get("target_decision")
    return Decision.model_validate(value) if value else None


def _trace(state: RunState) -> list[ToolTrace]:
    return [ToolTrace.model_validate(item) for item in state.get("target_trace", [])]


def _oracles(state: RunState) -> list[OracleResult]:
    return [OracleResult.model_validate(item) for item in state.get("oracle_results", [])]


def _stage(state: RunState, name: str, payload: dict[str, object] | None = None) -> RunState:
    run_id = state["run_id"]
    db.update_run(db_path(state), run_id, stage=name, episode=state.get("episode"), category=Scenario.model_validate(state["scenario"]).category.value if state.get("scenario") else None, difficulty=state.get("difficulty"))
    db.add_event(db_path(state), run_id, name, payload or {})
    state["updated_at"] = _stamp()
    return state


def db_path(state: RunState):
    if _DB_PATH is None:
        raise RuntimeError("DB_NOT_READY")
    return _DB_PATH


def runtime_config() -> Config:
    if _CONFIG is None:
        raise RuntimeError("CONFIG_NOT_READY")
    return _CONFIG


def load_run(state: RunState) -> RunState:
    run = db.get_run(db_path(state), state["run_id"])
    state.update({"target_id": run.target_id, "target_version": run.target_version, "mode": run.mode.value, "status": RunStatus.RUNNING.value, "episode": run.episode, "max_episodes": run.max_episodes, "difficulty": run.difficulty, "scenario": None, "scenario_history": [], "recent_results": [], "mutation_attempts": 0, "started_at": (run.started_at or datetime.now(timezone.utc)).isoformat(), "updated_at": _stamp(), "weaknesses": [item.model_dump(mode="json") for item in db.get_weaknesses(db_path(state), run.target_id, run.target_version)]})
    db.update_run(db_path(state), run.id, status=RunStatus.RUNNING, stage="LOAD_RUN", difficulty=run.difficulty)
    db.add_event(db_path(state), run.id, "LOAD_RUN", {"status": RunStatus.RUNNING.value})
    return state


def _category(state: RunState) -> Category:
    catalog = [Category.SIZE_LIMIT, Category.DISALLOWED_SYMBOL, Category.CONFLICTING_EVIDENCE, Category.STALE_EVIDENCE, Category.MAX_EXPOSURE, Category.HUMAN_TAKEOVER, Category.LOW_LIQUIDITY, Category.VOLATILITY_SPIKE, Category.AMBIGUOUS_SYMBOL, Category.EMERGENCY_STOP, Category.INSUFFICIENT_BALANCE, Category.POLICY_LIMIT, Category.TOOL_PRECONDITION, Category.NORMAL_SAFE_ACTION, Category.DUPLICATE_ACTION]
    weaknesses = state.get("weaknesses", [])
    if weaknesses:
        leading = sorted(weaknesses, key=lambda item: (float(item.get("failure_rate", 0)), int(item.get("fails", 0))), reverse=True)[0]
        if state.get("mutation_attempts", 0) < 2:
            try:
                return Category(str(leading["category"]))
            except ValueError:
                pass
        seen = {episode.category for episode in db.get_episodes(db_path(state), state["run_id"])}
        next_category = next((item for item in catalog if item.value not in seen), None)
        if next_category:
            return next_category
    number = state.get("episode", 0)
    return catalog[number % len(catalog)]


def choose_scenario(state: RunState) -> RunState:
    next_episode = state.get("episode", 0) + 1
    category = _category(state)
    scenario = qwen.generate_scenario(category, state.get("difficulty", 1), state.get("weaknesses", []), runtime_config(), next_episode, None, None)
    state.update({"episode": next_episode, "scenario": scenario.model_dump(mode="json"), "mutation_attempts": 0, "target_trace": [], "target_decision": None, "oracle_results": [], "critic_result": {}, "failure_type": None, "target_error": None, "consistency_decisions": [], "scenario_history": [*state.get("scenario_history", []), scenario.scenario_id]})
    db.update_run(db_path(state), state["run_id"], episode=next_episode, category=scenario.category.value, stage="CHOOSE_SCENARIO", difficulty=scenario.difficulty)
    db.add_event(db_path(state), state["run_id"], "SCENARIO_SELECTED", {"scenario_id": scenario.scenario_id, "category": scenario.category.value, "difficulty": scenario.difficulty, "labels": [item.value for item in scenario.source_labels]})
    return state


def _probe_scenario(scenario: Scenario) -> Scenario:
    return scenario.model_copy(update={"scenario_id": f"{scenario.scenario_id}-variant", "description": f"{scenario.description} Rephrased", "semantic_key": scenario.semantic_key})


def run_target_node(state: RunState) -> RunState:
    scenario = _scenario(state)
    target_url, target_token = target_for_run(state["run_id"])
    if state["mode"] == Mode.BITGET_PAPER.value:
        adapter = BitgetAdapter(runtime_config())
        symbol, market = adapter.resolve_symbol(scenario.policy.allowed_symbols)
        db.add_event(db_path(state), state["run_id"], "BITGET_SYMBOL_RESOLVED", {"symbol": symbol, "result": market or {}})
        if symbol is None:
            state.update({"target_trace": [], "target_decision": None, "target_error": (market or {}).get("code") or "BITGET_MARKET_UNVERIFIED"})
            db.update_run(db_path(state), state["run_id"], stage="RUN_TARGET")
            db.add_event(db_path(state), state["run_id"], "TARGET_COMPLETED", {"trace_steps": 0, "action": None, "error": state["target_error"]})
            return state
        scenario = scenario.model_copy(update={"policy": scenario.policy.model_copy(update={"allowed_symbols": [symbol]})})
        state["scenario"] = scenario.model_dump(mode="json")
    result = run_target(state["target_id"], target_url, target_token, state["run_id"], f"{state['run_id']}-{state['episode']}", scenario, Mode(state["mode"]), runtime_config())
    state.update({"target_trace": [item.model_dump(mode="json") for item in result.trace], "target_decision": result.decision.model_dump(mode="json") if result.decision else None, "target_error": result.error})
    db.update_run(db_path(state), state["run_id"], stage="RUN_TARGET")
    db.add_event(db_path(state), state["run_id"], "TARGET_COMPLETED", {"trace_steps": len(result.trace), "action": result.decision.action.value if result.decision else None, "error": result.error})
    return state


def run_oracles_node(state: RunState) -> RunState:
    scenario = _scenario(state)
    decision = _decision(state)
    trace = _trace(state)
    consistency: list[Decision | None] = [decision]
    if state["mode"] == Mode.SYNTHETIC.value and state["target_id"] in {"REFERENCE_WEAK", "REFERENCE_SAFE"} and decision:
        probe = run_target(state["target_id"], None, None, state["run_id"], f"{state['run_id']}-{state['episode']}-variant", _probe_scenario(scenario), Mode.SYNTHETIC, runtime_config())
        consistency.append(probe.decision)
    results = evaluate(scenario, Mode(state["mode"]), decision, trace, consistency, state.get("target_error"))
    state.update({"oracle_results": [item.model_dump(mode="json") for item in results], "consistency_decisions": [item.model_dump(mode="json") if item else None for item in consistency], "failure_type": failure_type(results)})
    db.update_run(db_path(state), state["run_id"], stage="RUN_ORACLES", failure=state.get("failure_type"))
    db.add_event(db_path(state), state["run_id"], "ORACLES_COMPLETED", {"failure_type": state.get("failure_type"), "results": [item.model_dump(mode="json") for item in results]})
    return state


def critic_node(state: RunState) -> RunState:
    value = qwen.critic(_scenario(state), _trace(state), _decision(state), _oracles(state), runtime_config())
    state["critic_result"] = value.model_dump(mode="json")
    db.update_run(db_path(state), state["run_id"], stage="CRITIC")
    db.add_event(db_path(state), state["run_id"], "CRITIC_COMPLETED", {"failure_class": value.failure_class, "model": value.model})
    return state


def save_memory_node(state: RunState) -> RunState:
    run = db.get_run(db_path(state), state["run_id"])
    scenario = _scenario(state)
    critic = CriticResult.model_validate(state["critic_result"])
    result = "FAIL" if state.get("failure_type") else "PASS"
    episode = db.insert_episode(db_path(state), run, scenario, _trace(state), _decision(state), _oracles(state), critic, state.get("failure_type"), result)
    state["recent_results"] = [*state.get("recent_results", []), result]
    state["weaknesses"] = [item.model_dump(mode="json") for item in db.get_weaknesses(db_path(state), run.target_id, run.target_version)]
    db.add_event(db_path(state), state["run_id"], "MEMORY_SAVED", {"episode_id": episode.id, "result": result, "failure_type": state.get("failure_type")}, episode.id)
    return state


def _three_passes(path, run_id: str, category: str) -> bool:
    episodes = db.get_episodes(path, run_id)
    recent = episodes[-3:]
    return len(recent) == 3 and all(episode.category == category and episode.failure_type is None for episode in recent)


def route_node(state: RunState) -> RunState:
    run_id = state["run_id"]
    if db.stop_requested(db_path(state), run_id) or state.get("episode", 0) >= state.get("max_episodes", 0):
        next_step = "FINISH"
    elif state.get("failure_type") and state.get("mutation_attempts", 0) < 2:
        next_step = "MUTATE"
    else:
        next_step = "HARDER"
        if state.get("scenario") and _three_passes(db_path(state), run_id, _scenario(state).category.value):
            state["difficulty"] = min(5, state.get("difficulty", 1) + 1)
            db.update_run(db_path(state), run_id, difficulty=state["difficulty"])
    state["next_step"] = next_step
    db.update_run(db_path(state), run_id, stage="ROUTE", difficulty=state.get("difficulty"))
    db.add_event(db_path(state), run_id, "ROUTE_SELECTED", {"next_step": next_step, "difficulty": state.get("difficulty")})
    return state


def mutate_node(state: RunState) -> RunState:
    parent = _scenario(state)
    next_episode = state.get("episode", 0) + 1
    scenario = qwen.mutate_scenario(parent, state.get("failure_type") or "WEAKNESS", runtime_config(), next_episode)
    state.update({"episode": next_episode, "scenario": scenario.model_dump(mode="json"), "mutation_attempts": state.get("mutation_attempts", 0) + 1, "target_trace": [], "target_decision": None, "oracle_results": [], "critic_result": {}, "failure_type": None, "target_error": None, "consistency_decisions": [], "scenario_history": [*state.get("scenario_history", []), scenario.scenario_id]})
    db.update_run(db_path(state), state["run_id"], episode=next_episode, category=scenario.category.value, stage="MUTATE", difficulty=scenario.difficulty)
    db.add_event(db_path(state), state["run_id"], "SCENARIO_MUTATED", {"scenario_id": scenario.scenario_id, "parent_scenario_id": scenario.parent_scenario_id, "mutation_reason": scenario.mutation_reason, "difficulty": scenario.difficulty})
    return state


def harder_node(state: RunState) -> RunState:
    state["scenario"] = None
    db.update_run(db_path(state), state["run_id"], stage="HARDER", difficulty=state.get("difficulty"))
    db.add_event(db_path(state), state["run_id"], "CURRICULUM_ADVANCED", {"difficulty": state.get("difficulty")})
    return state


def finish_node(state: RunState) -> RunState:
    status = RunStatus.STOPPED if db.stop_requested(db_path(state), state["run_id"]) else RunStatus.COMPLETED
    run = db.get_run(db_path(state), state["run_id"])
    episodes = db.get_episodes(db_path(state), state["run_id"])
    verification = paper_verification(run.mode, run.target_id, episodes, run.target_url, run.target_name, run.target_version, run.target_model)
    db.update_run(db_path(state), state["run_id"], status=status, stage="FINISH", failure=state.get("failure_type"), finished=True)
    db.add_event(db_path(state), state["run_id"], "RUN_VERIFICATION", verification.model_dump(mode="json"))
    db.add_event(db_path(state), state["run_id"], "RUN_FINISHED", {"status": status.value, "score": score(episodes).score, "official_track2_ready": verification.official_track2_ready, "verification_status": verification.status})
    state["status"] = status.value
    return state


def _route(state: RunState) -> str:
    return state.get("next_step", "FINISH")


def target_for_run(run_id: str) -> tuple[str | None, str | None]:
    return _TARGETS.get(run_id, (None, None))


_TARGETS: dict[str, tuple[str | None, str | None]] = {}


def set_target(run_id: str, url: str | None, token: str | None) -> None:
    _TARGETS[run_id] = (url, token)
    register_target(run_id, url, token)


def _build_graph(config: Config):
    builder = StateGraph(RunState)
    builder.add_node("LOAD_RUN", load_run)
    builder.add_node("CHOOSE_SCENARIO", choose_scenario)
    builder.add_node("RUN_TARGET", run_target_node)
    builder.add_node("RUN_ORACLES", run_oracles_node)
    builder.add_node("CRITIC", critic_node)
    builder.add_node("SAVE_MEMORY", save_memory_node)
    builder.add_node("ROUTE", route_node)
    builder.add_node("MUTATE", mutate_node)
    builder.add_node("HARDER", harder_node)
    builder.add_node("FINISH", finish_node)
    builder.add_edge(START, "LOAD_RUN")
    builder.add_edge("LOAD_RUN", "CHOOSE_SCENARIO")
    builder.add_edge("CHOOSE_SCENARIO", "RUN_TARGET")
    builder.add_edge("RUN_TARGET", "RUN_ORACLES")
    builder.add_edge("RUN_ORACLES", "CRITIC")
    builder.add_edge("CRITIC", "SAVE_MEMORY")
    builder.add_edge("SAVE_MEMORY", "ROUTE")
    builder.add_conditional_edges("ROUTE", _route, {"MUTATE": "MUTATE", "HARDER": "HARDER", "FINISH": "FINISH"})
    builder.add_edge("MUTATE", "RUN_TARGET")
    builder.add_edge("HARDER", "CHOOSE_SCENARIO")
    builder.add_edge("FINISH", END)
    connection = sqlite3.connect(config.checkpoint_path, check_same_thread=False)
    connection.commit()
    saver = SqliteSaver(connection)
    saver.setup()
    return builder.compile(checkpointer=saver), connection


def build_graph(config: Config):
    compiled, _ = _build_graph(config)
    return compiled


def run(config: Config, path, run_id: str) -> None:
    global _CONFIG, _DB_PATH
    _CONFIG = config
    _DB_PATH = path
    initial: RunState = {"run_id": run_id}
    compiled, connection = _build_graph(config)
    try:
        compiled.invoke(initial, {"configurable": {"thread_id": run_id}})
    finally:
        connection.close()
