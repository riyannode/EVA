import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    model: str
    llm_base_url: str
    qwen_api_key: str | None
    db_path: Path
    checkpoint_path: Path
    bitget_mode: str
    live_trading_enabled: bool
    bitget_executable: str
    frontend_origin: str
    demo_mode: bool
    target_timeout_ms: int
    target_response_bytes: int
    max_target_steps: int


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).lower()
    if value in {"1", "true", "yes"}:
        return True
    if value in {"0", "false", "no"}:
        return False
    raise ConfigError(f"INVALID_{name}")


def load_config() -> Config:
    mode = os.getenv("BITGET_MODE", "read-only")
    if mode not in {"read-only", "paper", "live"}:
        raise ConfigError("INVALID_BITGET_MODE")
    root = Path(__file__).resolve().parent
    return Config(
        model=os.getenv("EVA_MODEL", "qwen3.8-max"),
        llm_base_url=os.getenv("EVA_LLM_BASE_URL", "https://hackathon.bitgetops.com/v1"),
        qwen_api_key=os.getenv("BITGET_QWEN_API_KEY") or None,
        db_path=Path(os.getenv("EVA_DB", str(root / "eva.db"))),
        checkpoint_path=Path(os.getenv("EVA_CHECKPOINT_DB", str(root / "checkpoints.db"))),
        bitget_mode=mode,
        live_trading_enabled=_boolean("ENABLE_LIVE_TRADING", False),
        bitget_executable=os.getenv("BITGET_EXECUTABLE", "bgc"),
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        demo_mode=_boolean("DEMO_MODE", True),
        target_timeout_ms=min(max(int(os.getenv("TARGET_TIMEOUT_MS", "5000")), 100), 30000),
        target_response_bytes=min(max(int(os.getenv("TARGET_RESPONSE_BYTES", "200000")), 1000), 1000000),
        max_target_steps=min(max(int(os.getenv("MAX_TARGET_STEPS", "8")), 1), 8),
    )
