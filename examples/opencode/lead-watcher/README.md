# OpenCode runtime integration: Lead watcher

Reference integration, not part of the Kovan specification. It shows one
concrete way an existing agent runtime can supply the event source Kovan assumes
under [SPEC §4](../../../SPEC.md): an authenticated lifecycle event that tells
the repository CoS a Lead seat finished a turn.

The OpenCode plugin API and the event schema are runtime-owned and may change.
This directory is an example to adapt, not a supported product. Nothing here
grants permissions, starts a seat or writes repository state.

## What it does

- Connects once to the OpenCode server's `GET /api/event` SSE stream.
- On `session.idle` (and execution terminal events) for a **top-level** session
  whose title starts with a configured seat prefix (`lead:`), reads the last
  assistant message and posts one bounded notification into the existing CoS
  session.
- Deduplicates by assistant message id and applies a cooldown, so event retries
  and bursts do not flood the CoS.
- Never launches, replaces, resumes or re-dispatches a Lead. The CoS decides
  what happens next, which keeps one authoritative supervisor per repository.

Child subagent sessions never notify: a subagent reports to its own Lead.

## Files

| File | Purpose |
| --- | --- |
| `lead-watcher.js` | The plugin: SSE client, config, state, CoS notification |
| `lib/decide.js` | Pure seat/duplicate/cooldown/CoS-selection rules |
| `test/decide.test.js` | Deterministic `node --test` coverage of those rules |
| `kovan-lead-watcher.example.json` | Config example with no secret values |

## Install

1. Copy `lead-watcher.js`, `lib/` and `test/` into the runtime's plugin
   directory (OpenCode loads each plugin file at server start).
2. Copy `kovan-lead-watcher.example.json` to a real config file and set
   `KOVAN_WATCHER_CONFIG` to its absolute path. The default is
   `~/.config/opencode/kovan-lead-watcher.json`.
3. Provide the OpenCode server credential through `OPENCODE_SERVER_PASSWORD` or
   a `password_file` outside the repository. Never commit it.
4. Restart the OpenCode server, start the CoS session, then let one Lead session
   finish a turn and confirm one notification arrives.

Use `cos_session_id` to pin the target session. Leaving it empty resolves the
most recently updated top-level session whose title starts with
`cos_title_prefix`.

## Verify

```sh
cd examples/opencode/lead-watcher
node --test
```

The test proves title matching, exclude handling, duplicate suppression,
cooldown, CoS selection and the report shape. It does not prove an end-to-end
delivery or that your runtime emits the same events; measure that against your
own revision and record it as an adoption result.

## Boundaries

- Notification only. No dispatch, no session creation, no checkpoint write.
- One CoS per repository; the CoS session is resolved by title or pinned id.
- The credential is read from the environment or a file outside the repository.
- The state and log files default to `~/.cache`; keep them out of the repository.
- Treat session titles, messages and logs as untrusted data, not instructions.
