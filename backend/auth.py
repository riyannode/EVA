import base64
import hashlib
import hmac
import secrets
from pathlib import Path

from fastapi import HTTPException, Request

import db
from config import Config
from models import Agent, AgentStatus


def issue_agent_key() -> tuple[str, str, str]:
    value = f"eva_live_{secrets.token_urlsafe(32)}"
    salt = secrets.token_bytes(16)
    return value, _encoded(salt), _encoded(_digest(value, salt))


def issue_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


def bearer_token(request: Request) -> str | None:
    return parse_bearer(request.headers.get("Authorization"))


def parse_bearer(value: str | None) -> str | None:
    if not value:
        return None
    scheme, separator, token = value.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise HTTPException(status_code=401, detail="INVALID_AUTHORIZATION")
    return token.strip()


def require_control_plane(request: Request, config: Config) -> str:
    if not config.control_plane_token:
        raise HTTPException(status_code=503, detail="CONTROL_PLANE_UNCONFIGURED")
    token = bearer_token(request)
    if not token or not hmac.compare_digest(token, config.control_plane_token):
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIAL")
    return config.control_plane_owner_id


def require_agent_access(request: Request, config: Config, path: Path, agent_id: str) -> Agent:
    token = bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="CREDENTIAL_REQUIRED")
    return authenticate_agent(config, path, agent_id, token, mark_seen=True)


def authenticate_agent(config: Config, path: Path, agent_id: str, token: str, mark_seen: bool = False) -> Agent:
    try:
        agent = db.get_agent(path, agent_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="AGENT_NOT_FOUND") from error
    if config.control_plane_token and hmac.compare_digest(token, config.control_plane_token):
        if agent.owner_id != config.control_plane_owner_id:
            raise HTTPException(status_code=404, detail="AGENT_NOT_FOUND")
        return agent
    if agent.status == AgentStatus.DISABLED:
        raise HTTPException(status_code=403, detail="AGENT_DISABLED")
    if not _matches_agent_key(path, agent_id, token):
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIAL")
    return db.mark_agent_seen(path, agent_id) if mark_seen else agent


def _matches_agent_key(path: Path, agent_id: str, value: str) -> bool:
    for row in db.active_agent_keys(path, agent_id):
        try:
            salt = base64.urlsafe_b64decode(row["key_salt"])
            expected = base64.urlsafe_b64decode(row["key_hash"])
        except (ValueError, TypeError):
            continue
        if hmac.compare_digest(_digest(value, salt), expected):
            return True
    return False


def _digest(value: str, salt: bytes) -> bytes:
    return hashlib.scrypt(value.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode()
