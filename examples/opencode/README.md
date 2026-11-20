# OpenCode runtime examples

Kovan is runtime-neutral. These examples show how the convention maps onto one
existing agent runtime, OpenCode, without adding a scheduler, harness or
permission layer to Kovan.

| Example | Purpose | Claims |
| --- | --- | --- |
| [`lead-watcher`](lead-watcher/README.md) | Notify the CoS session when a Lead seat goes idle, using the runtime's own event stream | Notification only; no dispatch or session management |

Each example is source and documentation to adapt. Read the runtime's own
documentation for loading plugins and authenticating API calls; neither is
specified by Kovan. Keep credentials out of the repository and verify the
integration against your own runtime revision before relying on it.

Related Kovan material:

- [SPEC §3 bootstrap and resumption](../../SPEC.md) for seat binding and
  rejected unknown roles
- [SPEC §4 work lifecycle](../../SPEC.md) for authenticated triggers,
  deduplication and verified acceptance
- [docs/architecture.md](../../docs/architecture.md) for the trust boundary
  between role text, runtime identity and tool permissions
