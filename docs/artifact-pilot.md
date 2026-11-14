# Artifact publication smoke: public Draft PR #8

Date: 2026-11-14. Tracking issue: https://github.com/yesvus/kovan/issues/1

This was a **manually controlled, deterministic fixture**. It did not
invoke a language model, an OpenHands Automation run, an ACP coding agent,
or an unattended GitHub publication process.

## Worker isolation

A Python subprocess ran inside an existing disposable Docker image with:
- No network access or host mounts
- Read-only root filesystem, numeric non-root UID
- Dropped capabilities and no-new-privileges
- 128 MiB memory, 0.5 CPU, 32 PIDs
- No GitHub token, upstream API key, HMAC signing key or LLM credential

It emitted one harmless Markdown file to stdout. The container exited;
the controller captured its 232 bytes before publishing through its own
GitHub identity.

## Real GitHub publication and readback

- Source file: `pilot/issue-1/smoke.md`
- Controller-captured SHA-256:
  `165090ef0c84b2e14373df393806aac37b2116eec2c3166ca730b274dfc17e18`
- GitHub branch: `kovan/issue-1-smoke-20261114`
- Draft PR: https://github.com/yesvus/kovan/pull/8
- Exact HEAD commit: `a41de010a751627b467280001a9d6c41058609f0`

In a disposable checkout of public Kovan's still-unmerged handoff code,
the controller independently fetched GitHub's actual Issue and Draft PR
objects, then fetched the file via GitHub Contents API at the **full pinned
commit SHA**. The byte count and SHA-256 matched the captured worker
output.

A version-2 domain-separated HMAC receipt was minted with an **ephemeral
random controller-only key**, verified within the same process, and
invalidated by modifying the digest or the pinned commit SHA. No key or
receipt was persisted into GitHub or given to the worker.

## Security and completion limits

This test proves only that the public Draft PR contains the exact
controller-recorded artifact bytes at a specific commit and that a
controller-issued record can be authenticated while its ephemeral key
exists. It does **not** prove an LLM or ACP agent authored those bytes.
It does **not** implement durable provenance state, review policy,
branch protection enforcement, production issue admission, artifact
scanning, a real OpenHands run, or merge authorization.

The pilot PR remains **Draft and unmerged**; it is deliberately separate
from the core implementation PRs. The accepted file format is limited
to issue-scoped Markdown artifacts up to 64 KiB. A future implementation
must bind the complete Git tree to a privileged controller's immutable
worker result and enforce human approval at delivery time.

To reproduce offline unit tests in the stacked implementation branch:

    python3 -m unittest discover -s tests -p 'test_*.py' -v
