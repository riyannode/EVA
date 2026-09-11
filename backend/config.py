import json
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
    bitget_executable: str
    frontend_origin: str
    demo_mode: bool
    target_timeout_ms: int
    target_response_bytes: int
    max_target_steps: int
    control_plane_token: str | None
    control_plane_owner_id: str
    execution_provider: str
    certificate_private_key: str | None
    certificate_key_id: str
    certificate_trusted_keys: dict[str, str]
    public_api_url: str
    gateway_inbound_queue_size: int
    gateway_outbound_queue_size: int
    gateway_message_bytes: int
    gateway_session_seconds: int
    gateway_heartbeat_seconds: int


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).lower()
    if value in {"1", "true", "yes"}:
        return True
    if value in {"0", "false", "no"}:
        return False
    raise ConfigError(f"INVALID_{name}")


def _trusted_keys() -> dict[str, str]:
    value = os.getenv("EVA_CERTIFICATE_TRUSTED_KEYS", "{}")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ConfigError("INVALID_CERTIFICATE_TRUSTED_KEYS") from error
    if not isinstance(parsed, dict) or any(not isinstance(key, str) or not isinstance(item, str) for key, item in parsed.items()):
        raise ConfigError("INVALID_CERTIFICATE_TRUSTED_KEYS")
    return parsed


def load_config() -> Config:
    mode = os.getenv("BITGET_MODE", "read-only")
    if mode not in {"read-only", "paper"}:
        raise ConfigError("INVALID_BITGET_MODE")
    root = Path(__file__).resolve().parent
    return Config(
        model=os.getenv("EVA_MODEL", "qwen3.8-max"),
        llm_base_url=os.getenv("EVA_LLM_BASE_URL", "https://hackathon.bitgetops.com/v1"),
        qwen_api_key=os.getenv("BITGET_QWEN_API_KEY") or None,
        db_path=Path(os.getenv("EVA_DB", str(root / "eva.db"))),
        checkpoint_path=Path(os.getenv("EVA_CHECKPOINT_DB", str(root / "checkpoints.db"))),
        bitget_mode=mode,
        bitget_executable=os.getenv("BITGET_EXECUTABLE", "bgc"),
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        demo_mode=_boolean("DEMO_MODE", True),
        target_timeout_ms=min(max(int(os.getenv("TARGET_TIMEOUT_MS", "5000")), 100), 30000),
        target_response_bytes=min(max(int(os.getenv("TARGET_RESPONSE_BYTES", "200000")), 1000), 1000000),
        max_target_steps=min(max(int(os.getenv("MAX_TARGET_STEPS", "8")), 1), 8),
        control_plane_token=os.getenv("EVA_CONTROL_PLANE_TOKEN") or None,
        control_plane_owner_id=os.getenv("EVA_CONTROL_PLANE_OWNER_ID", "default-owner"),
        execution_provider=os.getenv("EVA_EXECUTION_PROVIDER", "bitget"),
        certificate_private_key=os.getenv("EVA_CERTIFICATE_PRIVATE_KEY") or None,
        certificate_key_id=os.getenv("EVA_CERTIFICATE_KEY_ID", "eva-cert-key-1"),
        certificate_trusted_keys=_trusted_keys(),
        public_api_url=os.getenv("EVA_PUBLIC_API_URL", "http://localhost:8000"),
        gateway_inbound_queue_size=min(max(int(os.getenv("GATEWAY_INBOUND_QUEUE_SIZE", "32")), 1), 256),
        gateway_outbound_queue_size=min(max(int(os.getenv("GATEWAY_OUTBOUND_QUEUE_SIZE", "32")), 1), 256),
        gateway_message_bytes=min(max(int(os.getenv("GATEWAY_MESSAGE_BYTES", "65536")), 1024), 1048576),
        gateway_session_seconds=min(max(int(os.getenv("GATEWAY_SESSION_SECONDS", "900")), 30), 86400),
        gateway_heartbeat_seconds=min(max(int(os.getenv("GATEWAY_HEARTBEAT_SECONDS", "60")), 5), 3600),
    )
