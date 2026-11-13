# Architecture boundaries

**Status: proposal — no production implementation in this repository.**

    Steward / user clients
                |
    Kovan work semantics + policy + decisions + verification
                |
                +-- source control and CI (authoritative evidence)
                +-- maintained durable workflow engine (execution state)
                +-- agent harness (coding implementation)
                +-- deployment / GitOps (authorized release)

Kovan must not implement a new coding harness, LLM gateway, scheduler, lease manager, source-control system, CI system, general-purpose chat UI, or GitOps engine just to duplicate existing infrastructure. Agent output is always untrusted until policy and independent verification pass.

First milestone: one **isolated** issue -> PR -> verified current-head CI/review -> human decision / authorized delivery flow, with failure recovery. No component is considered deployed merely because an RFC or Draft PR exists.
