# OpenHands Automation evidence adapter (pre-alpha)

This is a **provider-independent adapter** to the maintained upstream
[OpenHands Automation](https://github.com/OpenHands/automation) API, not a new
job queue, execution sandbox, agent harness or scheduler. It belongs to
Kovan's public community core. There is no Kovan EE dependency.

## Supported upstream protocol

The adapter was designed against the upstream Automation API:

- `GET /api/automation/v1/{automation_id}`: read registered automation,
  its resolved Agent Profile and enabled/state metadata.
- `GET /api/automation/v1/{automation_id}/runs?limit=100&offset=0`:
  inspect the run receipt and its status, execution profile, completion
  timestamp and correlated `conversation_id`.
- `GET /api/conversations/{conversation_id}` and
  `GET /api/conversations/{conversation_id}/agent_final_response`:
  independently inspect the Agent Server conversation and final-response
  **presence**, not the raw untrusted text.
- `POST /api/automation/v1/{automation_id}/dispatch`: an opt-in *library-only*
  primitive for an existing **INACTIVE/disabled** automation that matches a
  pinned Agent Profile. It has no CLI entry point and **must not** be called
  before a separate, authenticated worker admission, scoped credentials,
  isolated task runtime, network policy, budget and concurrency/idempotency
  gate. A boolean opt-in is NOT an authorization boundary.

All API calls are bounded and never render credentials or model output.
OpenHands session keys are read from `KOVAN_OPENHANDS_API_KEY` in the caller's
environment, not from hard-coded paths or versioned configuration. The client
accepts local HTTP loopback or remote HTTPS and refuses redirects.

## Read-only combined inspection

Prepare a **full, operator-pinned** GitHub PR SHA and the exact names of
required CI checks. From an environment that can reach a trusted, configured
OpenHands Automation and Agent Server endpoint, call:

    python3 -m kovan.openhands_adapter \
      --automation-id <automation-uuid> \
      --run-id <run-uuid> \
      --profile-id <agent-profile-uuid> \
      --automation-url http://127.0.0.1:18001 \
      --agent-url http://127.0.0.1:18000 \
      --repo owner/repository \
      --pr <pull-request-number> \
      --expected-sha <full-40-character-PR-head> \
      --require-check 'Your actual required CI job name'

The read-only command queries both sources independently. For a verified
manual upstream run, it requires all of:

- Automation ID and pinned Agent Profile match.
- A unique run ID with `trigger_source=manual`,
  `status=COMPLETED`, no error and a completion timestamp.
- Exact profile identity in the run's `resolved_runtime`.
- An Agent Server conversation ID on that run, whose
  `execution_status=finished` and launched Agent Profile match.
- A nonempty recorded Agent Server final response. The response is **not
  included** in the report: it may contain untrusted or sensitive content.
- The independent GitHub PR verifier's exact-head / configured required
  Checks API evidence must also pass (see [PR evidence](pr-evidence.md)).

The CLI emits `execution`, `github`, `both_observations_passed`,
`causal_link_proven: false` and **`delivery_authorized: false`**.
Exit code `0` only means both independent observations passed;
`2` means blocked/unavailable. **It does not prove the agent authored or
reviewed that exact PR commit.** Work-item admission and a durable binding
of issue, run, task policy, PR and reviewed SHA are separate future work.
Never promote this result into merge approval.

No Automation, GitHub repository, issue, PR, runner, branch, or secret is
modified by the CLI. It will not automatically register cron triggers,
write PR comments, merge or deploy.

## Offline tests and GitHub Actions

    python3 -m unittest discover -s tests -p 'test_*.py' -v

Tests use standard-library fake API responses and must not require Docker,
LLM credentials, internet, an actual OpenHands installation or GitHub
write permissions. They exercise stale/mismatched run IDs, wrong profiles,
running/failed/cancelled runs, missing conversations, incomplete responses,
missing/failed GitHub checks, explicit dispatch refusal, and restricted
HTTP URL parsing. GitHub-hosted CI executes them with a read-only token and
no project secrets.

**Limitations:** An Automation `COMPLETED` status is a receipt from the
upstream service, not a cryptographic proof of agent behavior. The reader
inspects up to the latest 100 runs and fails closed if the requested run is
absent/ambiguous; dispatch refuses a non-exhaustive run history. Neither
check creates a concurrency lock, deduplication key, egress restriction,
sandbox attestation, or authenticated human approval. Upstream API schemas
and auth policies should be revalidated on upgrades. No production deployment,
paid model invocation or unattended job was performed for this adapter.
