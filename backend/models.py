from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Mode(str, Enum):
    SYNTHETIC = "SYNTHETIC"
    BITGET_PAPER = "BITGET_PAPER"


class RunStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class OracleStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    REFUSE = "REFUSE"
    ESCALATE = "ESCALATE"


class VerificationLabel(str, Enum):
    LIVE_MARKET = "LIVE_MARKET"
    DEMO_ACCOUNT = "DEMO_ACCOUNT"
    PAPER_EXECUTION = "PAPER_EXECUTION"
    SYNTHETIC_SCENARIO = "SYNTHETIC_SCENARIO"
    SYNTHETIC_MUTATION = "SYNTHETIC_MUTATION"
    DETERMINISTIC_ORACLE = "DETERMINISTIC_ORACLE"
    LLM_CRITIQUE = "LLM_CRITIQUE"
    UNVERIFIED = "UNVERIFIED"


class Category(str, Enum):
    POLICY_LIMIT = "POLICY_LIMIT"
    DISALLOWED_SYMBOL = "DISALLOWED_SYMBOL"
    SIZE_LIMIT = "SIZE_LIMIT"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    AMBIGUOUS_SYMBOL = "AMBIGUOUS_SYMBOL"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    MAX_EXPOSURE = "MAX_EXPOSURE"
    DUPLICATE_ACTION = "DUPLICATE_ACTION"
    NORMAL_SAFE_ACTION = "NORMAL_SAFE_ACTION"
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    TOOL_PRECONDITION = "TOOL_PRECONDITION"


class Evidence(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=80)
    kind: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=500)
    observed_at: datetime
    max_age_seconds: int = Field(default=900, ge=1, le=86400)
    source_labels: list[VerificationLabel] = Field(default_factory=list, max_length=4)
    authoritative: bool = False


class Policy(StrictModel):
    allowed_symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"], max_length=50)
    blocked_symbols: list[str] = Field(default_factory=list, max_length=50)
    max_order_notional: Decimal = Field(default=Decimal("1000"), ge=0)
    max_exposure: Decimal = Field(default=Decimal("5000"), ge=0)
    min_order_notional: Decimal = Field(default=Decimal("10"), ge=0)
    emergency_stop: bool = False
    action_restrictions: list[Action] = Field(default_factory=list, max_length=5)


class Portfolio(StrictModel):
    balance: Decimal = Field(default=Decimal("10000"), ge=0)
    exposure: Decimal = Field(default=Decimal("0"), ge=0)


class Decision(StrictModel):
    action: Action
    symbol: str | None = Field(default=None, max_length=40)
    notional: Decimal | None = Field(default=None, ge=0)
    confidence: float = Field(default=0, ge=0, le=1)
    reason: str = Field(default="", max_length=1000)
    evidence_used: list[str] = Field(default_factory=list, max_length=50)


class Scenario(StrictModel):
    scenario_id: str = Field(min_length=1, max_length=100)
    category: Category
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1200)
    user_intent: str = Field(min_length=1, max_length=500)
    policy: Policy
    portfolio: Portfolio
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    requires_takeover: bool = False
    difficulty: int = Field(ge=1, le=5)
    source_labels: list[VerificationLabel] = Field(default_factory=list, max_length=5)
    parent_scenario_id: str | None = Field(default=None, max_length=100)
    mutation_reason: str | None = Field(default=None, max_length=500)
    prompt_name: str = Field(default="seed", max_length=80)
    prompt_version: str = Field(default="v1", max_length=20)
    model: str = Field(default="deterministic-seed", max_length=80)
    seed: int | None = None
    semantic_key: str = Field(default="default", max_length=100)

    @field_validator("source_labels")
    @classmethod
    def labels_are_distinct(cls, value: list[VerificationLabel]) -> list[VerificationLabel]:
        return list(dict.fromkeys(value))


class ToolCall(StrictModel):
    type: Literal["tool_call"]
    tool: str = Field(min_length=1, max_length=50)
    args: dict[str, object] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=1000)


class FinalResponse(StrictModel):
    type: Literal["final"]
    decision: Decision


class ToolTrace(StrictModel):
    sequence: int = Field(ge=1, le=8)
    tool: str = Field(min_length=1, max_length=50)
    arguments: dict[str, object] = Field(default_factory=dict)
    timestamp: datetime
    result_status: str = Field(min_length=1, max_length=40)
    result: dict[str, object] = Field(default_factory=dict)
    latency_ms: float = Field(default=0, ge=0)
    verification_labels: list[VerificationLabel] = Field(default_factory=list, max_length=5)


class OracleResult(StrictModel):
    name: str = Field(min_length=1, max_length=50)
    category: str = Field(min_length=1, max_length=40)
    status: OracleStatus
    code: str = Field(min_length=1, max_length=50)
    details: str = Field(default="", max_length=300)
    labels: list[VerificationLabel] = Field(default_factory=lambda: [VerificationLabel.DETERMINISTIC_ORACLE], max_length=3)


class CriticResult(StrictModel):
    diagnosis: str = Field(min_length=1, max_length=500)
    failure_class: str = Field(min_length=1, max_length=50)
    trigger: str = Field(min_length=1, max_length=300)
    mutation_direction: str = Field(min_length=1, max_length=300)
    model: str = Field(default="unavailable", max_length=80)
    prompt_name: str = Field(default="critic", max_length=80)
    prompt_version: str = Field(default="v1", max_length=20)
    labels: list[VerificationLabel] = Field(default_factory=list, max_length=3)


class RunCreate(StrictModel):
    target_id: str = Field(min_length=1, max_length=100)
    target_version: str = Field(default="demo", min_length=1, max_length=40)
    target_url: str | None = Field(default=None, max_length=500)
    target_token: str | None = Field(default=None, max_length=500)
    mode: Mode = Mode.SYNTHETIC
    max_episodes: int = Field(default=20, ge=1, le=100)
    difficulty: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="after")
    def validate_paper_target(self) -> "RunCreate":
        if self.mode == Mode.BITGET_PAPER and self.target_id != "EXTERNAL_HTTP":
            raise ValueError("BITGET_PAPER_EXTERNAL_TARGET_REQUIRED")
        if self.mode == Mode.BITGET_PAPER and not self.target_url:
            raise ValueError("TARGET_URL_REQUIRED")
        return self


class Run(StrictModel):
    id: str
    target_id: str
    target_version: str
    target_url: str | None = None
    mode: Mode
    status: RunStatus
    difficulty: int
    max_episodes: int
    episode: int = 0
    current_category: str | None = None
    current_stage: str = "IDLE"
    last_failure: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class ScoreBreakdown(StrictModel):
    policy: int = Field(ge=0, le=20)
    freshness: int = Field(ge=0, le=15)
    sizing: int = Field(ge=0, le=15)
    takeover: int = Field(ge=0, le=15)
    execution: int = Field(ge=0, le=15)
    consistency: int = Field(ge=0, le=10)
    tool_discipline: int = Field(ge=0, le=10)


class Scorecard(StrictModel):
    score: int = Field(ge=0, le=100)
    label: str
    breakdown: ScoreBreakdown
    measured: dict[str, dict[str, int]] = Field(default_factory=dict)
    primary_weakness: str | None = None
    labels: list[VerificationLabel] = Field(default_factory=lambda: [VerificationLabel.DETERMINISTIC_ORACLE], max_length=2)


class VerificationSummary(StrictModel):
    status: Literal["NOT_APPLICABLE", "UNVERIFIED", "READY"]
    official_track2_ready: bool
    evidence: dict[str, bool] = Field(default_factory=dict)
    blocking_reasons: list[str] = Field(default_factory=list, max_length=20)


class EvaluationMetrics(StrictModel):
    total_scenarios: int = Field(ge=0)
    total_episodes: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    failure_rate: float = Field(ge=0, le=1)
    risk_violation_count: int = Field(ge=0)
    risk_violation_rate: float = Field(ge=0, le=1)
    false_autonomy_count: int = Field(ge=0)
    false_autonomy_rate: float = Field(ge=0, le=1)
    unnecessary_escalation_count: int = Field(ge=0)
    unnecessary_escalation_rate: float = Field(ge=0, le=1)
    takeover_required_count: int = Field(ge=0)
    takeover_success_count: int = Field(ge=0)
    takeover_accuracy: float | None = Field(default=None, ge=0, le=1)
    consistency_failure_count: int = Field(ge=0)
    consistency_failure_rate: float = Field(ge=0, le=1)
    tool_precondition_violation_count: int = Field(ge=0)
    duplicate_action_count: int = Field(ge=0)
    execution_mismatch_count: int = Field(ge=0)
    primary_recurring_weakness: str | None = None
    difficulty_reached: int = Field(ge=0, le=5)
    targeted_mutations: int = Field(ge=0)
    mutation_retest_passes: int = Field(ge=0)
    mutation_retest_failures: int = Field(ge=0)
    paper_trade_count: int = Field(ge=0)
    paper_metrics_status: Literal["UNAVAILABLE", "UNVERIFIED"]
    win_rate: float | None = Field(default=None, ge=0, le=1)
    pnl: float | None = None
    return_pct: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    max_drawdown: float | None = None
    turnover: float | None = None
    fees: float | None = None
    slippage: float | None = None


class Weakness(StrictModel):
    failure_type: str
    category: str
    attempts: int
    fails: int
    passes: int
    failure_rate: float
    updated_at: datetime


class Event(StrictModel):
    id: int | None = None
    run_id: str
    episode_id: str | None = None
    type: str
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class Episode(StrictModel):
    id: str
    run_id: str
    number: int
    scenario_id: str
    parent_scenario_id: str | None
    category: str
    difficulty: int
    scenario: Scenario
    target_trace: list[ToolTrace]
    decision: Decision | None
    oracle_results: list[OracleResult]
    critic: CriticResult
    failure_type: str | None
    result: str
    created_at: datetime


class TargetListing(StrictModel):
    target_id: str
    target_version: str
    kind: str
    target_url: str | None = None
