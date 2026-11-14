# Disposable OpenHands ACP artifact smoke

This is a **reproducible opt-in integration test**, not a production
orchestrator. The OpenHands Agent Server and ACP JSON-RPC conversation
are real; the ACP test peer is a deterministic Python fixture, **not**
Codex, OpenCode, an LLM, or an agent authorized to modify production code.

## Offline CI

    python3 -m unittest discover -s tests -p 'test_*.py' -v
    bash -n scripts/disposable-acp-smoke.sh

These credential-free tests reject malformed JSON, unexpected methods,
repeat prompts with mismatching contents, and symlink overwrites.
They run with standard GitHub-hosted runners, no secrets or paid models.

## Explicit opt-in local integration

Requires Docker with an already present
`ghcr.io/openhands/agent-canvas:1.35.0` image (no network pull):

    bash scripts/disposable-acp-smoke.sh

The test uses a **fresh disposable Canvas container**, Docker
`--internal` bridge network, separate Docker state volume and tmpfs.
There are no host bind mounts, published ports, socket mounts,
external network, GitHub or model credentials. It uses numeric non-root
UID, cap-drop ALL, no-new-privileges, 3 GiB RAM, 1.5 CPU and 512 PIDs.

Through the container-local API, it creates a no-secret custom ACP Agent
Profile and runs a real Agent Server conversation. The fixture processes
ACP `initialize`, `session/new` and `session/prompt`, writes a single
harmless file to `/projects/pilot/issue-1/acp.md`, and returns a marker.
The controller checks the actual conversation status, Agent Profile,
final response, file size and SHA-256. Disposable resources are
destroyed on exit, including failure.

**Optional trusted-controller capture:** set `KOVAN_ACP_OUTPUT` to a
nonexistent path on the host. Only after a successful session does the
script copy the *actual file* to that location via `docker exec`.
The host directory is never mounted into the container. The script
refuses to overwrite existing files and symlinks. The caller must
securely manage and remove the captured temporary artifact.

The Canvas image's root layer is writable for its runtime internals:
this is not a VM/microVM security guarantee. The image is pinned only
to a tag, not an immutable OCI digest; production use needs stronger
isolation, digest pinning and supply-chain review.

## Verified separate-controller GitHub publication

On 2026-11-14 a disposable Agent Server ACP conversation finished and
generated a 159-byte Markdown artifact. A separate trusted host
controller copied those bytes, checked SHA-256, and published them using
**only the host's GitHub identity**, never a worker credential.

- Work item: [public issue #1](https://github.com/yesvus/kovan/issues/1)
- [Artifact Draft PR #9](https://github.com/yesvus/kovan/pull/9)
- Git branch: `kovan/issue-1-acp-20261114`
- Exact commit: `e5162682376453b35b2bdb5ecb732c054719952f`
- File: `pilot/issue-1/acp.md`
- Controller-captured SHA-256:
  `eefa7187a04f7b5517487211140544a75146d1b498f1320d9f659211f84538cf`
- Last successful ACP conversation: `b8d8f05e-23b4-49e5-9bda-23e6e88da639`
- Agent Server: `execution_status=finished`, correct Agent Profile,
  final response `KOVAN_ACP_ARTIFACT_WRITTEN`
- After run: **0 containers, 0 networks, 0 volumes** left over

Independently verify the file against the full Git commit SHA with
Kovan's `artifact_evidence.match_committed_bytes` helper. This
establishes the published *bytes*, not a model's authorship.

## Not yet proven

This exercised a direct **Agent Server conversation**, not upstream
OpenHands **Automation dispatch**. It did not use a real paid/free LLM,
agent tool calls, GitHub issue admission, an unattended coding task,
a durable controller state/receipt, an independently scanned Git tree,
or merge/deploy authorization. The final response marker is not
itself a trust or policy decision.

The reusable fixture/runner lives in public core as a **stacked Draft
PR**. The artifact Draft PR #9 is a separate proof and should remain
unmerged. Do not grant the worker broad API credentials to complete
the next phase.
