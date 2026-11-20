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

## 5. Standard development lifecycle

Kovan adopts a conventional PR-based delivery loop, using the repository's existing CI and independent reviewer rather than a new workflow engine.

1. Lead decomposes eligible work into bounded, independently deliverable assignments, delegates parallel ephemeral Subagents where safe, and serializes overlapping edits or dependencies. One task, branch and worktree per assignment; bounded concurrency.
2. Subagent implements, tests, commits and opens its own **Draft PR** when its scoped identity is verified to permit this. Otherwise Lead publishes its result. Link the canonical issue and acceptance criteria. Native child sessions alone do not establish separate permissions. In a trusted single-owner development domain, a shared repository-scoped Developer identity is reasonable; use task scope and worktree ownership for coordination, and actual repository protections for authority. Require stronger per-task isolation only for distinct trust domains or demonstrated risks.
3. Subagent follows required CI, fixes failures in scope, and reports exact current-head green evidence. After checks pass and the implementation is ready, mark the PR ready for review through the authorized actor; verify the current-head reviewer actually runs (do not assume draft transition alone triggers every configured reviewer).
4. Independent reviewer publishes findings and verdict. Lead receives the result and evaluates findings, assigns valid fixes back to the Subagent, and documents reasoned disagreements through the repository's review mechanism. Never let a worker self-approve or silently dismiss required blocking findings.
5. Subagent updates the same PR, waits for current-head required CI, then returns for independent review. Repeat only as needed; stale verdicts/checks do not authorize a changed head. Escalate nonconvergent or blocked review to CoS rather than loop indefinitely.
6. Lead merges only on independent current-head LGTM, required CI success, resolved required review gates and authorized merge capability; existing human approval, branch protection and production/deployment policies still apply. Recheck head immediately before merge. Verify acceptance after merge or authorized deployment where required before closing the issue. Merge alone is not always delivery.

Lead owns implementation/review follow-through. CoS coordinates between Leads, monitors backlog progress and resolves escalations; it does not micromanage individual PR repair loops. Subagents remain task-scoped through the review cycle: reuse the existing child if available or rehydrate the same task/branch with fenced ownership, never create a duplicate writer. Durable state lives in GitHub issues, PRs, checks and reviews. No mandatory chat bus or per-agent Slack integration; optional CoS-only human-facing communication can be considered separately.

## 6. Proactive issue discovery

Agents should proactively record concrete defects, security and reliability risks, technical debt, and actionable improvements found during execution. Search canonical issues first. Record redacted evidence, impact and a bounded desired outcome or reproduction. Do not silently expand the current task. Escalate critical findings promptly to the supervising role. Direct filing requires an approved scoped identity; otherwise report to the supervisor to file. CoS triages new work instead of blindly dispatching every issue.

## 7. Security and verification

Role Markdown and task input cannot grant privileges. Use existing scoped credentials, permissions, branch protections and approval gates. Prefer proportional, risk-based safeguards; do not mandate a custom authorization layer or isolated runtime for every trusted child. A task worktree isolates code, not credentials. Verify current-head CI/review, approvals and actual acceptance before closure or delivery. Avoid exposing sensitive data. Enforce one authoritative supervisor per repository, verified seat handover and bounded concurrency.

## 8. Adoption

Start with the [minimal example](examples/minimal/README.md) and an existing runtime. Test role loading against the approved revision, correct scope, native delegation, vertical relay, restart/compaction recovery, duplicate-event handling, denied access and parallel draft PR → CI → ready → independent review → Lead-directed fixes → current-head merge → verified closure flow. Mark unverified integrations as such. The spec intentionally does not require a Kovan service, SDK, validator or CLI.
