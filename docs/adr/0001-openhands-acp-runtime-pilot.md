# ADR 0001: Pilot OpenHands as an optional ACP execution substrate

- **Status:** Proposed — pilot required
- **Date:** 2026-11-13
- **Scope:** First isolated issue-to-reviewed-result vertical slice
- **Related:** [Core milestone #1](https://github.com/yesvus/kovan/issues/1)

## Context

Kovan should own work admission, authorization, human decisions, independently verified evidence, and release policy. It should not recreate a coding harness, an LLM provider gateway, an agent UI, or a general-purpose workflow scheduler.

The [Agent Client Protocol (ACP)](https://agentclientprotocol.com/) standardizes coding-agent interaction. OpenHands Agent Canvas and Agent Server can host ACP-compatible agents, including OpenCode. OpenHands Automation exposes an API for automation definitions, dispatch, run listing, and cancellation. The presence of these APIs does **not** establish that a particular self-hosted installation can execute OpenCode through Automation, nor does an Agent Canvas conversation prove durable unattended execution.

## Decision

1. **Use OpenHands + OpenCode ACP as the first candidate, not a permanent dependency.** The agent runtime remains replaceable. Additional harnesses must not depend on OpenCode-specific session formats.
2. **Delegate agent execution and session lifecycle to the upstream harness/runtime.** Kovan must not build an OpenCode process supervisor, custom ACP bridge, or agent chat UI for this pilot.
3. **Delegate retries, queueing, scheduling and crash recovery to a maintained upstream subsystem when demonstrated.** Evaluate OpenHands Automation first. If its local run semantics are insufficient, compare a maintained durable workflow engine; do not resurrect custom leases, heartbeats or SQLite job scheduling merely to complete the proof.
4. **Keep Kovan policy authoritative.** An authenticated operator admits a specific action against a specific repo/ref and bounded workspace. GitHub issue text, labels, agent instructions and tool output are untrusted data and never grant new privileges.
5. **Keep verification independent.** Agent process exit or self-reported success is not delivery evidence. The verifier reads the current GitHub PR head SHA and the required checks/reviews for that exact SHA. Merge/deploy needs a distinct authorized decision.
6. **Keep infrastructure escape hatches.** Scoped CI, Kubernetes, GitOps and monitoring operations may be invoked through their existing native APIs when authorized; do not force all operational actions through an ACP coding session.

## Evidence captured on 2026-11-13

A read-only inspection of an operator-controlled ARM64 self-hosted installation established:

| Check | Observation | Interpretation |
| --- | --- | --- |
| Agent Canvas image | `ghcr.io/openhands/agent-canvas:1.35.0` running | Existing installation; no upgrade/restart performed |
| Backend readiness | `/alive` HTTP 200 | Agent backend reachable |
| Automation readiness | `/api/automation/ready` HTTP 200 | Automation service available |
| Automation OpenAPI | Version `1.26.1`, dispatch/run endpoints present | API surface exists; dispatch behavior unproven |
| Automation authenticated API | Unauthenticated `GET /v1` and `/v1/capabilities` returned HTTP 401 | Provide supported scoped session/API authentication before inspecting or dispatching |
| ACP agent | A running OpenCode service process was observed | Consistent with existing ACP setup; no new Automation→ACP run proven |
| Worker isolation | Writable persistent workspaces are shared within the existing Canvas container | Not a suitable isolation boundary for untrusted concurrent workers |

These observations are **not** an end-to-end Kovan execution test. No automation was created or dispatched, no paid inference was triggered, no production infrastructure was modified, and no authorization material is included here.

OpenHands local Automation API documentation supports `X-Session-API-Key` with an appropriately provisioned backend session credential. Do not hardcode, log or expose a generated local backend key to make an API request succeed.

References:
- [OpenHands Automation integration](https://github.com/OpenHands/extensions/blob/main/skills/openhands-automation/SKILL.md)
- [OpenHands Agent Canvas self-host setup](https://github.com/OpenHands/docs/blob/main/openhands/usage/agent-canvas/setup.mdx)
- [OpenHands SDK and Automation architecture](https://github.com/OpenHands/OpenHands/blob/main/README.md)

## Minimal pilot — ordered gates

**Gate A: secure local dispatch (read-only first)**

- Reuse the supported backend session authentication without exposing secrets in prompts, files, GitHub, logs or process arguments.
- List existing automations and runs using authenticated API requests; establish the specific local Automation→Agent Server→ACP invocation semantics, version compatibility, persistence and cancellation.
- Confirm the actual selected coding harness and provider/model through safe metadata. Do not silently substitute a different model or start a paid run.

**Gate B: isolation and bounded execution**

- Create one *disposable* per-job workspace/sandbox with no developer home, shared credentials, Docker socket, production kubeconfig, or production mount.
- Restrict repository scope, filesystem, network, tool permissions, model budget and timeout. Initially allow one concurrent worker.
- Verify restart/cleanup and measure CPU, memory, I/O, disk, swap, latency and cost. If the host lacks safe headroom, stop before dispatch.

**Gate C: verified harmless GitHub outcome**

- Admit exactly one low-risk issue or read-only PR review, with explicit repo and immutable target SHA.
- Dispatch an OpenHands Automation that demonstrably invokes OpenCode **via ACP** and yields a run ID, state transitions, and cancellable outcome.
- Persist a concise, safe status/evidence link back to the same authorized work item; no production credentials or secrets.
- If work produces a draft PR, independently validate the current PR head SHA and GitHub checks/reviews; treat absent, pending or stale checks as **not verified**.
- Exercise a blocked/failed/cancelled case; retry without duplicate PRs/comments and without incorrectly reporting success.
- Stop at the human approval boundary. No automatic merge, release, GitOps sync, DNS or production data operation.

## Candidate runtime adapter boundary

Kovan's policy layer should be able to **request**, **inspect**, **cancel**, and, if supported, **resume** a bounded run; receive a stable run identity and evidence references; and report unmet capabilities explicitly. Keep the adapter small and capability-driven. Do not invent a general public protocol until a second harness has demonstrated the actual common denominator.

A job's admission scope should contain the operator authorization reference, repository, requested action, immutable source ref/SHA, workspace policy, permitted credentials, model/profile, deadline, concurrency and spend limits. Runtime execution metadata is not authorization to deliver.

## Non-goals

No additional 24/7 orchestrator chat; no new scheduler, lease engine, inference router, agent UI, auto-merge or production deployment in this milestone. Do not migrate the current interactive Agent Canvas merely to match an infrastructure diagram.

## Decision gate

- **Adopt/extend OpenHands** if isolated ACP automation, run lifecycle, recovery and bounded resource behavior are demonstrated.
- **Keep OpenHands optional and add a thin direct harness adapter** if its automation layer is incompatible, without coupling Kovan policy to any single agent runtime.
- **Select a maintained durable engine only when measurements show missing scheduling/recovery semantics.**

Until those checks pass, this ADR is a proposal, not a statement that Kovan has a working ACP worker or production-ready execution system.
