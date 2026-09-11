# Evaluation certificates

Completed agent evaluations can expose `GET /v1/certificates/{evaluation_id}` and `GET /v1/certificates/{evaluation_id}/verify`. The certificate binds the agent identity, score, readiness label, primary weakness, execution provider metadata, completion time, and tamper-evident journal root.

Certificates use Ed25519. EVA signs only when `EVA_CERTIFICATE_PRIVATE_KEY` is configured as a URL-safe base64 encoded 32-byte seed. `EVA_CERTIFICATE_KEY_ID` identifies the active signing key. Missing or invalid signing configuration fails closed with `CERTIFICATE_SIGNING_UNCONFIGURED` or `CERTIFICATE_KEY_INVALID`; EVA does not generate a repository key or fabricate a certificate.

The certificate includes the public key and signature so it can be verified offline. The CLI command is:

```powershell
node cli/index.mjs certificate verify --file certificate.json --json
```

The evidence root is a SHA-256 hash chain over journal entries. Mutation, deletion, reorder, append, or an evidence-root mismatch makes verification fail. A certificate is not proof of real-money trading or of a model identity beyond the declared registration metadata.
