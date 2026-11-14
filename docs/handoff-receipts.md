# Controller handoff receipts — first publication provenance boundary

**Status: pre-alpha public core.** This module is a reusable, read-only
attestation/reconciliation primitive, **not** an issue-to-PR controller, a
worker sandbox, an autonomous task loop or a delivery authorization gateway.

A fully completed OpenHands Automation run and a green GitHub pull request
are two independent facts. They do not prove the agent caused or reviewed
the specific code change. This module adds a bounded, **controller-issued**
record binding the approved work item, pinned upstream run identity, Draft PR
and exact GitHub commit SHA together.

## Trust model

Only a **trusted controller**, separate from the worker's filesystem,
environment and network permissions, may access the HMAC-SHA256 signing
key (at least 32 unpredictable bytes). The worker may propose files,
patches or PR text but cannot mint a signed publication claim. Never place
this key in a worker, PR environment, untrusted CI, workflow logs or GitHub
repository secrets exposed to PR jobs. Do not use a shared OpenHands Canvas
credential as this key.

1. A separately authorized controller admits the issue, repository,
   execution profile, budget, sandbox and requested change. The **caller**,
   not this module, enforces all these permissions.
2. The isolated worker runs under a distinct, narrowly scoped identity
   and returns a candidate artifact. The trusted controller must independently
   validate/scan the exact artifact and choose a permitted GitHub writeback.
   **Neither step is implemented in this PR.**
3. The controller uses its own limited GitHub App installation to create a
   `kovan/issue-N-...` branch/commit and **Draft** PR in the pinned repo.
   After GitHub returns the created commit/PR, it reads the current GitHub
   issue and PR back. The public `attest_after_publication()` library method
   refuses to sign a mismatch. It then signs a short-lived receipt:
   repo, issue number, Draft PR number, source/base ref, exact HEAD SHA,
   publication account login, Automation/run/Profile UUIDs and validity
   interval.
4. A reviewer/observer later calls `reconcile()` with the controller's
   receipt and key. Invalid, tampered or expired receipts fail **before**
   any API call. The verifier independently re-reads the GitHub issue/PR,
   expects the publisher identity, same-repo Draft PR, issue-associated
   controller branch, exact head SHA and `main` base branch.
5. It then reuses the public OpenHands execution inspector and the
   public PR Checks API verifier: the right upstream completed run and
   correlated finished Agent Server conversation must be present, plus all
   explicitly required GitHub checks on the current SHA. A moved PR head,
   failed CI or wrong run keeps the result blocked.

## API (library only)

`kovan.handoff.Publication`: immutable typed publication claim.
`attest_after_publication(claim, signing_key, github_reader, now=...)`
returns an HMAC-authenticated `{version, claim, mac}` object **after**
a successful GitHub readback. `reconcile(receipt, signing_key,
github_reader, automation_reader, agent_reader, required_checks, now=...)`
returns booleans and non-secret reasons. No signing or dispatch CLI exists.

The `github_reader` can be a caller-wrapped
`kovan.pr_evidence.GitHubAPI` that implements `get(path)`.
The Automation/Agent reader can be the installed
`kovan.openhands_adapter.OpenHandsHTTP`, with its API key passed
by environment from a **trusted** runner.

Use the standard Python test command, on GitHub-hosted CI without secrets:

    python3 -m unittest discover -s tests -p 'test_*.py' -v

The signature is domain-separated and expires within one hour. The record
must be kept by the controller/audit system; the module **does not**
provide durable storage, receipt revocation, a scheduler or retry engine.
This first pilot only accepts public-style same-repository Draft PRs on
`main`, the designated `kovan/issue-N-...` branch namespace, and an
expected publisher login. Adapting those restrictions needs explicit review.

## What a successful result actually means

`publication_evidence_consistent: true` means:

- A trusted key authenticated a short-lived, unmodified handoff claim.
- The cited GitHub issue and Draft PR identities still match the claim.
- The cited OpenHands run/profile/conversation ended successfully.
- The independent required GitHub Checks API results still pass on the
  exact cited current HEAD SHA.

**Both `agent_authorship_proven` and `delivery_authorized` are
always false.** This is intentional. The controller might have signed
a claim after a human-authored commit or failed to scan an untrusted
artifact. The signature identifies what the trusted controller attested,
not who generated the bytes. Do not treat a PR body, issue comment or
model narrative as provenance. Do not treat this receipt as permission
to run tools, add secrets, merge or deploy.

## Remaining acceptance gates

- A real controller must own authenticated issue admission and scoped
  branch/commit/Draft PR publication. The signing key must be accessible
  **only after** independent checks of the actual published artifact and
  a one-time work-item/run assignment.
- Verify the candidate artifact content or tree against the exact
  controller-published Git commit, and record a tamper-evident artifact
  digest to establish stronger causal provenance.
- Store run/issue/PR receipt state durably, enforce one-use and
  concurrency/idempotency, and support cancellation/revocation.
- Read repository rulesets/branch protection, required reviews and
  GitHub status contexts; re-check authorization and HEAD at action time.
- Complete one disposable, bounded **real** ACP worker pilot through
  code change and Draft PR, followed by explicit authenticated human
  approval. Mock echo tests do not satisfy this gate.

**No production agent dispatch, GitHub writeback, merge, deployment,
scheduled worker, or billable model invocation is part of this PR.**
