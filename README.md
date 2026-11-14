# Kovan

**Open-source, self-hostable policy and delivery verification for AI-assisted software engineering.**

> **Status: pre-alpha / clean core extraction.** This repository intentionally starts with new Git history. The reusable application implementation has **not** been migrated or released. There is no installable Kovan server or proven end-to-end delivery workflow here yet.

Kovan aims to connect task intake, isolated coding agents, independently verified Git/CI/review evidence, human decisions, and authorized delivery—without replacing established agent harnesses, workflow engines, Git hosting, CI or GitOps.

## Intended open-source core

- Canonical work and run state, independent of any chat conversation.
- Scoped permissions, explicit authorization, and durable human decisions.
- Replaceable backlog and coding-agent runtime adapters.
- Independent verification of PR, CI, review and delivery evidence.
- Self-hostable operation without mandatory proprietary cloud services.

**These are product goals, not currently shipped features.**

## Current status

The first pre-alpha, standard-library Python checks now include a **read-only Docker worker boundary preflight** and a credential-free **ACP protocol echo fixture**. They are tested on public GitHub-hosted CI, but they are **not a production-ready orchestrator** or evidence of a live agent run. There is still no installable Kovan server, GitHub delivery controller, or production release.

Run the offline checks with `python3 -m unittest discover -s tests -p 'test_*.py' -v` and see [developer smoke tests](docs/developer-smoke.md) for scope and limitations. Implementation of the remaining community core is tracked in [issue #1](https://github.com/yesvus/kovan/issues/1).

See [architecture boundaries](docs/architecture.md), [contribution guidelines](CONTRIBUTING.md) and [security policy](SECURITY.md).

## Principles

1. Adopt existing runtimes; do not invent schedulers, coding harnesses or GitOps.
2. Model outputs and issue content never grant execution privileges.
3. Verified delivery requires independent evidence pinned to an exact commit.
4. Keep owner-specific infrastructure, secrets and commercial modules outside this repository.

## License

Apache-2.0. See [LICENSE](LICENSE). Trademark rights are separate.
