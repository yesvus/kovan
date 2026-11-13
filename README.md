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

This repository contains publication scaffolding, a design outline, security and contribution policies, and credential-free CI for repository integrity. Functional application code will be extracted only after provenance and security reviews. There is **no production release**.

See [architecture boundaries](docs/architecture.md), [contribution guidelines](CONTRIBUTING.md) and [security policy](SECURITY.md).

## Principles

1. Adopt existing runtimes; do not invent schedulers, coding harnesses or GitOps.
2. Model outputs and issue content never grant execution privileges.
3. Verified delivery requires independent evidence pinned to an exact commit.
4. Keep owner-specific infrastructure, secrets and commercial modules outside this repository.

## License

Apache-2.0. See [LICENSE](LICENSE). Trademark rights are separate.
