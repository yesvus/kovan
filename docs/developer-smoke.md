# Developer smoke tests (pre-alpha)

The public Kovan repository is the community core. It must be usable without
any commercial edition, private infrastructure or paid model subscription.

## Credential-free tests

From the repository root on Python 3.11+:

    python3 -m unittest discover -s tests -p 'test_*.py' -v

The tests use only Python's standard library. They check:

- A **structural Docker worker admission check** that fails closed on
  risky host privileges, bind mounts, resource limits and missing metadata.
- An **ACP v1 JSON-RPC echo fixture** covering initialize, session creation,
  prompt response and unsupported method rejection.

Neither test launches a real coding agent. Neither test needs network
access, repository secrets, Docker, a language model, GitHub authentication
or a running OpenHands instance.

The same tests run on the standard GitHub-hosted Ubuntu runner for each PR.
Fork PR checks do not receive project secrets. The CI workflow has
read-only repository permissions and does not use self-hosted runners.

## Read-only Docker preflight

A developer may run this manually against a **disposable test container**:

    python3 -m kovan.runtime_boundary --container <disposable-container>

The command runs *only* `docker inspect` (no shell and no container mutation)
and returns JSON with `structural_preflight_passed` and `problems`.
Exit code 0 means its **structural checks** passed; code 2 means blocked.

**This is not permission to dispatch an agent.** Docker inspect cannot
establish that a named network blocks outbound traffic, a named volume is
new or secret-free, the agent has no dangerous inherited credentials, or the
host daemon/kernel is a trustworthy security boundary. Verify those
independently; malicious code may require a stronger VM/microVM boundary.

The guard is intentionally conservative: all host bind mounts (including
read-only), host devices, a root/unknown UID, elevated capabilities, unbounded
CPU/memory/PIDs and shared host namespaces are rejected. A passing result
does **not** imply full isolation or safe production use.

## Still missing

There is no installable orchestrator, UI, scheduler, GitHub writeback, or
end-to-end issue → isolated real agent → draft PR → independently verified
checks → human approval workflow yet. These will be built and tested in
separate, scoped public PRs. The mock ACP fixture is a protocol test,
not evidence of a live model run.
