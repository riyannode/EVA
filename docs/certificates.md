# Evaluation certificates

Completed agent evaluations can expose `GET /v1/certificates/{evaluation_id}` and `GET /v1/certificates/{evaluation_id}/verify`. The certificate binds the agent identity, score, readiness label, primary weakness, execution provider metadata, completion time, and tamper-evident journal root.

## Trust model

Certificates use Ed25519. EVA signs only when `EVA_CERTIFICATE_PRIVATE_KEY` is configured as a URL-safe base64 encoded 32-byte seed and the matching public key is registered under `EVA_CERTIFICATE_KEY_ID` in `EVA_CERTIFICATE_TRUSTED_KEYS`.

The certificate's `signing_key_id` selects a public key from an external trusted registry. The embedded `public_key` is metadata and is never used to establish trust. A modified certificate signed with an attacker-generated replacement key remains invalid. Unknown or revoked key IDs are invalid.

The server publishes the read-only registry at:

```text
GET /.well-known/eva-signing-keys.json
```

The response contains public keys only. An offline verifier can use a separately obtained file:

```json
{"eva-cert-key-1":"<base64url-ed25519-public-key>"}
```

```powershell
node cli/index.mjs certificate verify --file certificate.json --trusted-key-file eva-signing-keys.json --json
```

Online verification can resolve the same trusted registry from `--api-url`:

```powershell
node cli/index.mjs certificate verify --file certificate.json --api-url https://eva.example --json
```

EVA does not generate a repository key or fabricate a certificate. Missing or invalid signing configuration fails closed with `CERTIFICATE_SIGNING_UNCONFIGURED`, `CERTIFICATE_TRUST_UNCONFIGURED`, or `CERTIFICATE_KEY_INVALID`.

## Rotation and evidence

Key rotation is keyed by `signing_key_id`. A new key can be trusted alongside the old key. Historical certificates remain verifiable while their old public key remains in the trusted registry. Removing an old key intentionally makes certificates signed by that key untrusted.

The certificate signature covers the canonical certificate payload, including score, `evidence_root`, `signing_key_id`, and embedded public-key metadata. The evidence root is a SHA-256 hash chain over journal entries. Mutation, deletion, reorder, append, or an evidence-root mismatch makes verification fail.

A certificate is not proof of real-money trading or of a model identity beyond the declared registration metadata.
