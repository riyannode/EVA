const args = process.argv.slice(2);
const command = args[0] ?? "help";
const flags = parseFlags(args.slice(1));
const jsonOutput = Boolean(flags.json);

async function main() {
  if (command === "onboard") return pairingStart();
  if (command === "agent" && args[1] === "register") return pairingStart();
  if (command === "auth" && args[1] === "start") return pairingStart();
  if (command === "auth" && args[1] === "status") return pairingStatus();
  if (command === "auth" && args[1] === "complete") return pairingComplete();
  if (command === "admin" && args[1] === "approve") return approvePairing();
  if (command === "evaluation" && args[1] === "get") return request(`/v1/evaluations/${required("id")}`, "GET");
  if (command === "evaluation" && args[1] === "watch") return watch();
  if (command === "certificate" && args[1] === "verify") return verifyCertificate();
  return fail("COMMAND_REQUIRED");
}

async function pairingStart() {
  const base = required("api-url").replace(/\/$/, "");
  const response = await fetch(`${base}/v1/pairing-requests`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: required("name"), version: required("version"), declared_model: required("model"), framework: flags.framework, execution_providers: flags.providers ? String(flags.providers).split(",") : [] }) });
  return output(await decode(response));
}

async function pairingStatus() {
  const base = required("api-url").replace(/\/$/, "");
  return output(await decode(await fetch(`${base}/v1/pairing-requests/${encodeURIComponent(required("request-id"))}`)));
}

async function pairingComplete() {
  const base = required("api-url").replace(/\/$/, "");
  const response = await fetch(`${base}/v1/pairing-requests/${encodeURIComponent(required("request-id"))}/exchange`, { method: "POST" });
  const value = await response.json();
  if (response.status === 409 && value.detail === "PAIRING_PENDING") return output({ status: "PENDING" });
  if (!response.ok) return fail(value.detail ?? "REQUEST_FAILED", response.status);
  return output({ ...value, status: "APPROVED", agent_id: value.agent?.agent_id });
}

async function approvePairing() {
  const base = required("api-url").replace(/\/$/, "");
  const response = await fetch(`${base}/v1/pairing-requests/${encodeURIComponent(required("request-id"))}/approve`, { method: "POST", headers: { Authorization: `Bearer ${required("control-token")}` } });
  return output(await decode(response));
}

async function request(path, method) {
  const base = required("api-url").replace(/\/$/, "");
  const response = await fetch(`${base}${path}`, { method, headers: { Authorization: `Bearer ${required("api-key")}` } });
  return output(await decode(response));
}

async function watch() {
  const id = required("id");
  const base = required("api-url").replace(/\/$/, "");
  for (;;) {
    const value = await decode(await fetch(`${base}/v1/evaluations/${id}`, { headers: { Authorization: `Bearer ${required("api-key")}` } }));
    process.stdout.write(`${JSON.stringify(value)}\n`);
    if (["COMPLETED", "STOPPED", "FAILED"].includes(value.status)) return;
    await new Promise(resolve => setTimeout(resolve, Number(flags.interval ?? 1000)));
  }
}

async function verifyCertificate() {
  const value = JSON.parse(await import("node:fs/promises").then(module => module.readFile(required("file"), "utf8")));
  const trusted = await loadTrustedKeys();
  const signable = { ...value };
  delete signable.signature;
  const publicKey = trusted[value.signing_key_id];
  let valid = false;
  if (publicKey) {
    const key = await crypto.subtle.importKey("raw", decodeBase64(publicKey), { name: "Ed25519" }, false, ["verify"]);
    valid = await crypto.subtle.verify({ name: "Ed25519" }, key, decodeBase64(value.signature), new TextEncoder().encode(stableJson(signable)));
  }
  return output({ valid, signing_key_id: value.signing_key_id, evaluation_id: value.evaluation_id });
}

async function loadTrustedKeys() {
  if (flags["trusted-key-file"]) {
    const source = JSON.parse(await import("node:fs/promises").then(module => module.readFile(String(flags["trusted-key-file"]), "utf8")));
    const value = source.keys ?? source;
    if (!value || typeof value !== "object" || Array.isArray(value)) return fail("INVALID_TRUSTED_KEY_FILE");
    return value;
  }
  if (flags["api-url"]) {
    const base = String(flags["api-url"]).replace(/\/$/, "");
    const response = await fetch(`${base}/.well-known/eva-signing-keys.json`);
    const source = await decode(response);
    return source.keys ?? {};
  }
  return fail("TRUSTED_KEY_SOURCE_REQUIRED");
}

function parseFlags(values) {
  const result = {};
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (value === "--json") result.json = true;
    else if (value.startsWith("--")) result[value.slice(2)] = values[index + 1]?.startsWith("--") ? true : values[++index];
  }
  return result;
}

function required(name) {
  if (!flags[name]) return fail(`${name.toUpperCase().replaceAll("-", "_")}_REQUIRED`);
  return String(flags[name]);
}

async function decode(response) {
  const value = await response.json();
  if (!response.ok) return fail(value.detail ?? "REQUEST_FAILED", response.status);
  return value;
}

function output(value) {
  process.stdout.write(jsonOutput ? `${JSON.stringify(value)}\n` : `${JSON.stringify(value, null, 2)}\n`);
}

function fail(code, status = 1) {
  const value = { error: code };
  process.stderr.write(`${JSON.stringify(value)}\n`);
  process.exitCode = status;
  return value;
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}

function decodeBase64(value) {
  const text = value.replaceAll("-", "+").replaceAll("_", "/");
  return Uint8Array.from(Buffer.from(text, "base64"));
}

void main();
