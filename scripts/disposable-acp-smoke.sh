#!/usr/bin/env bash
# Disposable, credential-free OpenHands Agent Server -> ACP -> artifact smoke.
# A deterministic ACP test peer; NO commercial LLM, scheduling, git writes,
# remote agent credentials, production Canvas reuse or host bind mounts.
set -euo pipefail

# Optional controller-only host capture, never a mount inside the worker.
KOVAN_ACP_OUTPUT="${KOVAN_ACP_OUTPUT:-}"

if [[ ! -f tests/fixtures/acp_artifact_agent.py ]]; then
  echo "Run from the Kovan repository root." >&2
  exit 2
fi

suffix="$(date +%s)-$$"
name="kovan-acp-fixture-$suffix"
network="kovan-acp-internal-$suffix"
volume="kovan-acp-state-$suffix"
cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# No image pull or setup network access. This tag is an explicit preflight
# dependency; a future CI integration should pin a verified OCI digest.
image="ghcr.io/openhands/agent-canvas:1.35.0"
docker image inspect "$image" >/dev/null

docker network create --internal --driver bridge "$network" >/dev/null
docker volume create "$volume" >/dev/null
docker run -d --rm --name "$name" --pull never \
  --network "$network" --user 10001:10001 \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --memory 3g --memory-swap 3g --cpus 1.5 --pids-limit 512 \
  -v "$volume":/home/openhands/.openhands \
  --tmpfs /projects:rw,nosuid,nodev,uid=10001,gid=10001,size=64m \
  --tmpfs /home/openhands/workspace:rw,nosuid,nodev,uid=10001,gid=10001,size=128m \
  -e AGENT_CANVAS_DISABLE_TELEMETRY=true \
  "$image" >/dev/null

test "$(docker network inspect -f '{{.Internal}}' "$network")" = "true"
echo "INTERNAL_NETWORK=true"
docker exec -i "$name" sh -c 'cat > /projects/kovan_acp_fixture.py' \
  < tests/fixtures/acp_artifact_agent.py

# Session API key is read only *inside* the disposable container and never
# printed or placed in the host/container environment of the ACP test peer.
docker exec -i "$name" python3 - <<'PY'
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

base = "http://127.0.0.1:18000"
for n in range(40):
    try:
        with urllib.request.urlopen(base + "/alive", timeout=2) as stream:
            if stream.status == 200:
                break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError("disposable Agent Server did not become healthy")
print("AGENT_SERVER_READY=true", flush=True)

key = Path("/home/openhands/.openhands/agent-canvas/api-key.txt").read_text().strip()

def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"X-Session-API-Key": key, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        base + path, method=method, data=data, headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as stream:
            return json.load(stream)
    except urllib.error.HTTPError as error:
        # Never print response bodies, which may contain credentials.
        print("API_ERROR_HTTP_CODE", error.code, flush=True)
        raise

api("POST", "/api/agent-profiles/Kovan-Artifact-ACP", {
    "agent_kind": "acp",
    "acp_server": "custom",
    "acp_command": "python3 /projects/kovan_acp_fixture.py",
    "mcp_server_refs": [],
    "integration_refs": [],
    "secret_refs": [],
})
profile = api("GET", "/api/agent-profiles/Kovan-Artifact-ACP")
profile_id = (profile.get("profile") or {}).get("id")
if not profile_id:
    raise RuntimeError("ACP Agent Profile ID missing")
print("ACP_PROFILE_RESOLVED=true", flush=True)

conversation = api("POST", "/api/conversations", {
    "agent_profile_id": profile_id,
    "workspace": {"kind": "LocalWorkspace", "working_dir": "/projects"},
    "initial_message": {
        "role": "user",
        "content": [{
            "type": "text",
            "text": "Perform the fixed, credential-free ACP artifact smoke.",
        }],
    },
    "autotitle": False,
    "max_iterations": 5,
    "secrets": {},
})
conversation_id = conversation.get("id")
if not conversation_id:
    print("CONVERSATION_RESPONSE_FIELDS", sorted(conversation))
    raise RuntimeError("No Agent Server conversation ID")
print("ACP_CONVERSATION_CREATED=true", flush=True)

artifact = Path("/projects/pilot/issue-1/acp.md")
for n in range(40):
    if artifact.is_file():
        break
    time.sleep(1)
else:
    result = api("GET", f"/api/conversations/{conversation_id}")
    print("CONVERSATION_STATUS", result.get("execution_status"), flush=True)
    raise RuntimeError("ACP agent did not write fixture")

for n in range(30):
    result = api("GET", f"/api/conversations/{conversation_id}")
    if result.get("execution_status") in ("finished", "error", "failed", "stopped"):
        break
    time.sleep(1)
status = result.get("execution_status")
print("ACP_STATUS", status)
print("ACP_PROFILE_MATCH",
      (result.get("launched_agent_profile") or {}).get("agent_profile_id")
      == profile_id)
if status != "finished":
    raise RuntimeError("ACP conversation failed to finish")

final = api(
    "GET", f"/api/conversations/{conversation_id}/agent_final_response"
)
if final.get("response") != "KOVAN_ACP_ARTIFACT_WRITTEN":
    raise RuntimeError("ACP peer final response mismatch")

raw = artifact.read_bytes()
if not raw.startswith(b"# Kovan ACP integration fixture\n"):
    raise RuntimeError("Unexpected artifact bytes")
print("ACP_CONVERSATION_ID", conversation_id)
print("ACP_ARTIFACT_BYTES", len(raw))
print("ACP_ARTIFACT_SHA256", hashlib.sha256(raw).hexdigest())
print("ACP_FINAL_RESPONSE_VERIFIED=true")
print("DISPOSABLE_ACP_SMOKE_SUCCESS=true")
PY

if [[ -n "$KOVAN_ACP_OUTPUT" ]]; then
  if [[ -e "$KOVAN_ACP_OUTPUT" || -L "$KOVAN_ACP_OUTPUT" ]]; then
    echo "Refusing to replace an existing captured artifact" >&2
    exit 2
  fi
  umask 077
  docker exec "$name" cat /projects/pilot/issue-1/acp.md > "$KOVAN_ACP_OUTPUT"
  echo "CONTROLLER_CAPTURE_SHA256=$(sha256sum "$KOVAN_ACP_OUTPUT" | cut -d' ' -f1)"
  echo "CONTROLLER_CAPTURE_BYTES=$(wc -c < "$KOVAN_ACP_OUTPUT")"
fi
