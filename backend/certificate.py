import base64
import binascii

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from config import Config
from journal import canonical_json
from models import Certificate


class CertificateError(RuntimeError):
    pass


def issue(config: Config, evaluation_id: str, agent_id: str, agent: dict[str, str], score: int, readiness: str, primary_weakness: str | None, evidence_root: str, completed_at: str, execution_provider: str | None) -> dict[str, object]:
    private_key = _private_key(config)
    public_key = _encode(private_key.public_key().public_bytes_raw())
    model = Certificate.model_validate({"certificate_version": "eva-cert/1", "evaluation_id": evaluation_id, "agent_id": agent_id, "agent": agent, "score": score, "readiness": readiness, "primary_weakness": primary_weakness, "evidence_root": evidence_root, "completed_at": completed_at, "execution_provider": execution_provider, "signing_key_id": config.certificate_key_id, "public_key": public_key, "signature": ""})
    signable = model.model_dump(mode="json")
    signable.pop("signature")
    signature = _encode(private_key.sign(canonical_json(signable)))
    return Certificate.model_validate({**signable, "signature": signature}).model_dump(mode="json")


def verify(value: dict[str, object], expected_evidence_root: str | None = None) -> bool:
    try:
        certificate = Certificate.model_validate(value)
        if expected_evidence_root and certificate.evidence_root != expected_evidence_root:
            return False
        signable = certificate.model_dump(mode="json")
        signature = _decode(str(signable.pop("signature")))
        public_key = Ed25519PublicKey.from_public_bytes(_decode(certificate.public_key))
        public_key.verify(signature, canonical_json(signable))
        return True
    except (ValueError, TypeError, InvalidSignature, binascii.Error):
        return False


def _private_key(config: Config) -> Ed25519PrivateKey:
    if not config.certificate_private_key:
        raise CertificateError("CERTIFICATE_SIGNING_UNCONFIGURED")
    try:
        value = _decode(config.certificate_private_key)
        return Ed25519PrivateKey.from_private_bytes(value)
    except (ValueError, binascii.Error) as error:
        raise CertificateError("CERTIFICATE_KEY_INVALID") from error


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode())
