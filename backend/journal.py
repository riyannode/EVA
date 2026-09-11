import hashlib
import json
from collections.abc import Iterable


ZERO_HASH = "0" * 64


def canonical_entry(run_id: str, sequence: int, episode_id: str | None, event_type: str, payload: dict[str, object], created_at: str, prev_hash: str) -> dict[str, object]:
    return {"run_id": run_id, "sequence": sequence, "episode_id": episode_id, "type": event_type, "payload": payload, "created_at": created_at, "prev_hash": prev_hash}


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


def hash_entry(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def verify_entries(entries: Iterable[dict[str, object]], evidence_root: str | None = None) -> bool:
    previous = ZERO_HASH
    expected_sequence = 1
    last_hash = ZERO_HASH
    for entry in entries:
        if entry.get("sequence") != expected_sequence or entry.get("prev_hash") != previous:
            return False
        content = canonical_entry(str(entry.get("run_id", "")), expected_sequence, entry.get("episode_id") if isinstance(entry.get("episode_id"), str) else None, str(entry.get("type", "")), entry.get("payload") if isinstance(entry.get("payload"), dict) else {}, str(entry.get("created_at", "")), previous)
        current = hash_entry(content)
        if entry.get("entry_hash") != current:
            return False
        previous = current
        last_hash = current
        expected_sequence += 1
    return evidence_root in {None, last_hash}


def event_entry(event) -> dict[str, object]:
    return {"id": event.id, "run_id": event.run_id, "sequence": event.sequence, "episode_id": event.episode_id, "type": event.type, "payload": event.payload, "created_at": event.created_at.isoformat(), "prev_hash": event.prev_hash, "entry_hash": event.entry_hash}
