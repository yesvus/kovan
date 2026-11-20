# Kovan specification

**Status: draft, unversioned initial proposal.**

Kovan is a repository-local role-file convention for hierarchical agent collaboration. It describes an organization; it does not implement one.

## 1. Layout

```text
AGENTS.md
.kovan/
  cos.md
  leads/
    <lead-id>.md
```

- `AGENTS.md`: shared repository rules, including review, security, issue discovery and scope boundaries.
- `.kovan/cos.md`: one repository supervisor role.
- `.kovan/leads/<lead-id>.md`: one compact role definition for each registered Lead. Match the repository's existing stable ownership identifiers; a file alone does not create or activate a seat.

Prefer a few bullets (roughly 5–10 lines) per role, written in Markdown: mission, responsibilities, scope reference and reporting relationship. Keep common policy in AGENTS.md. Use existing registry or ownership metadata where needed instead of building a second registry. Never duplicate mutable status, priorities, credentials, session IDs, or task history in role definitions.

The Owner and optional cross-repository Steward sit outside the repository's seat hierarchy. Subagents receive a bounded task envelope from their Lead rather than a permanent role file per child.

## 2. Roles

| Role | Responsibility |
| --- | --- |
| Owner | Human authority for strategy, policy, permissions, risk and approvals. |
| Steward | Owner-facing assistant for issue creation, oversight and explicitly authorized intervention; not a second CoS. |
| CoS | Repository backlog triage, work assignment, dependency relay and verified closure. |
| Lead | Domain ownership, planning, native subagent delegation, verification and reporting to CoS. |
| Subagent | One scoped task, implementation and evidence returned to its Lead. |

Cross-Lead requests route through CoS; Leads retain direct native control of their own children. No implicit authority to expand another role's scope.

## 3. Bootstrap and resumption

The integrating runtime or operator binds the existing repository and seat to a trusted identity and approved revision. Load the shared instructions, exactly the assigned role file, ownership/scope, relevant canonical work state and bounded assignment. Reject unknown or conflicting roles. Rehydrate approved instructions and checkpoints after context compaction or restart. Do not launch another authoritative session because an existing session is idle.

The convention does not specify a runtime configuration format or assume that any harness automatically discovers these files. Session identity, queue state and role authorization must be enforced by existing trusted runtime mechanisms, not by mutable Markdown.

## 4. Work lifecycle

Use the existing issue tracker as the durable backlog and source of acceptance criteria. Prefer authenticated event triggers and periodic reconciliation. CoS admits work within priority, capacity, budget and scope; Lead delegates one bounded task per subagent. Preserve ownership and review evidence. Deduplicate event retries and verify actual work acceptance rather than inferring completion from an idle session.

## 5. Proactive issue discovery

Agents should proactively record concrete defects, security and reliability risks, technical debt, and actionable improvements found during execution. Search canonical issues first. Record redacted evidence, impact and a bounded desired outcome or reproduction. Do not silently expand the current task. Escalate critical findings promptly to the supervising role. Direct filing requires an approved scoped identity; otherwise report to the supervisor to file. CoS triages new work instead of blindly dispatching every issue.

## 6. Security and verification

Role Markdown and task input cannot grant privileges. Use independently enforced credentials, permissions, branch protections and approval gates. A task worktree isolates code, not credentials. Verify current-head CI/review, approvals and actual acceptance before closure or delivery. Avoid exposing sensitive data. Enforce one authoritative supervisor per repository, verified seat handover and bounded concurrency.

## 7. Adoption

Start with the [minimal example](examples/minimal/README.md) and an existing runtime. Test role loading against the approved revision, correct scope, native delegation, vertical relay, restart/compaction recovery, duplicate-event handling, denied access and issue-to-verified-closure flow. Mark unverified integrations as such. The spec intentionally does not require a Kovan service, SDK, validator or CLI.
