# Independent GitHub PR/CI evidence — first read-only slice

**Status:** Pre-alpha. This module does **not** merge PRs, approve code,
interpret agent output as a security decision, or deploy anything.

It implements a small, replaceable, **read-only GitHub REST adapter** that
checks an operator-pinned open pull request and explicitly configured required
GitHub check names. It uses Python's standard library and belongs in the
public community core; it needs no Kovan EE service.

## Example against an existing public PR

First look up the exact current SHA independently:

    gh pr view 4 -R yesvus/kovan --json headRefOid --jq .headRefOid

Then run the offline-installable verifier from this repository root (replace
`SHA_HERE` with the *complete* 40-character commit SHA):

    python3 -m kovan.pr_evidence \
      --repo yesvus/kovan \
      --pr 4 \
      --expected-sha SHA_HERE \
      --require-check 'Offline core and ACP contract tests' \
      --require-check 'Repository integrity (not product tests)'

The default trusted publisher is GitHub Actions (app slug `github-actions`).
Use `--app-slug` only when the operator has explicitly approved a different
GitHub App. The verifier never guesses required checks from model text or the
PR description.

- Query the current PR via `GET /repos/{owner}/{repo}/pulls/{number}`.
  Require `state=open` and the **exact operator-pinned HEAD SHA**.
- Query `GET /repos/{owner}/{repo}/commits/{SHA}/check-runs`, filtered to
  latest runs. Require all named checks to be uniquely present on the exact
  SHA, from the trusted GitHub App, with `status=completed` and
  `conclusion=success`. Reject missing, ambiguous, pending, failed,
  cancelled, skipped and non-exhaustive results.
- Re-read the PR after collecting checks. Fail if HEAD moved or PR closed.
- Return structured JSON with `verified: true/false`, named per-check
  verdicts, and reasons. Exit `0` only if all requested evidence is current,
  otherwise `2`.

Public GitHub REST reads work without a token, subject to API rate limits.
To read private repos, set a **read-only fine-grained** `GITHUB_TOKEN` in the
invoking process environment, with only required PR and Checks read access.
The CLI never accepts a token argument, prints it or transfers it to an ACP
agent. The transport uses a fixed GitHub API host and GET requests only.

For offline tests:

    python3 -m unittest discover -s tests -p 'test_pr_evidence.py' -v

They simulate changed HEADs, bad apps, wrong SHA, missing checks, duplicate
check names, failures, pending results, truncated API pages, unavailable
transport and malformed scopes. The public hosted Actions job has read-only
repository permissions and uses no secrets.

## Deliberate limits

- **Explicit expected check names, not discovered branch protections.** This
  slice does not read all GitHub rulesets, branch protection, merge queue
  state, commit signature verification, approval review states or CODEOWNERS.
  A green verdict means **the specifically requested checks succeeded**; it
  is neither comprehensive delivery evidence nor approval to merge.
- API pagination is bounded at 100 latest check runs; overflow **fails
  closed**. Duplicate required check names also fail closed, including those
  from different GitHub Apps. Larger installations need a complete paginated
  adapter with explicit trusted publisher IDs.
- GitHub check-runs and commit status contexts are distinct APIs; this
  minimal adapter verifies **Checks API only**. Add status-context support
  only with separately tested, explicit requirements.
- The second PR read narrows but does not eliminate all race conditions.
  Any future authorized merge gateway **must independently recheck** the
  protected branch, policy, required reviews, current head, approval scope
  and exact execution identity at action time. Never reuse a stale positive
  JSON result as a long-lived permission.
- This module is not a workflow engine, hosted SaaS backend, GitHub App,
  webhook receiver or approval policy controller. It performs no writes.
