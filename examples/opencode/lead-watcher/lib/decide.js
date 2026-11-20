// Pure decisions for the OpenCode lead watcher. Keep I/O out of this module so
// the rules can be tested deterministically with `node --test`.

/**
 * A candidate is a top-level session whose title marks it as a Kovan seat.
 * Subagent (child) sessions never notify: they report to their own Lead.
 *
 * @param {{ title?: string, parentID?: string|null }} session
 * @param {{ seatTitlePrefix?: string, excludeTitles?: string[] }} cfg
 */
export function isWatchedSeat(session, cfg = {}) {
  const prefix = (cfg.seatTitlePrefix || "lead:").toLowerCase();
  const title = (session?.title || "").toLowerCase();
  if (!title || !title.startsWith(prefix)) return false;
  if (session?.parentID) return false;
  return !(cfg.excludeTitles || []).some((excluded) => {
    const e = String(excluded || "").toLowerCase();
    return e && title.startsWith(e);
  });
}

/**
 * One notification per finished assistant message, with a cooldown so a burst
 * of idle events does not flood the CoS. Duplicate event retries carry the same
 * message id and are dropped.
 *
 * @param {{
 *   previous?: { last_notified_msg_id?: string, last_notified_ts?: number },
 *   messageID: string,
 *   nowSeconds: number,
 *   cooldownSeconds?: number,
 * }} args
 * @returns {{ notify: boolean, reason: string }}
 */
export function decideNotification({ previous, messageID, nowSeconds, cooldownSeconds = 120 }) {
  if (!messageID) return { notify: false, reason: "no-message" };
  const prev = previous || {};
  if (prev.last_notified_msg_id === messageID) {
    return { notify: false, reason: "duplicate" };
  }
  const elapsed = nowSeconds - (prev.last_notified_ts || 0);
  if (elapsed < cooldownSeconds) {
    return { notify: false, reason: "cooldown" };
  }
  return { notify: true, reason: "notify" };
}

/**
 * Choose the CoS session: an explicit id wins, otherwise the most recently
 * updated top-level session whose title starts with the configured prefix.
 *
 * @param {Array<{ id: string, title?: string, parentID?: string|null, time?: { updated?: number } }>} sessions
 * @param {{ cosSessionID?: string, cosTitlePrefix?: string }} cfg
 */
export function selectCosSession(sessions, cfg = {}) {
  if (cfg.cosSessionID) return cfg.cosSessionID;
  const prefix = (cfg.cosTitlePrefix || "ops-CoS").toLowerCase();
  return (sessions || [])
    .filter((s) => !s?.parentID && (s?.title || "").toLowerCase().startsWith(prefix))
    .sort((a, b) => (b?.time?.updated || 0) - (a?.time?.updated || 0))[0]?.id || "";
}

/**
 * Build the CoS-facing report. It is a notification, never a work assignment:
 * the CoS decides whether to re-dispatch, coordinate a handoff or escalate.
 *
 * @param {{ title: string, sessionID: string, updatedISO: string, messageID: string, excerpt?: string, nowISO: string }} input
 */
export function buildReport(input) {
  return [
    `[kovan-lead-watcher @ ${input.nowISO}] 1 lead session(s) finished or paused:`,
    "",
    `### ${input.title} (\`${input.sessionID}\`)`,
    `- Event: \`session.idle\` | updated: \`${input.updatedISO}\` | msg: \`${input.messageID}\``,
    input.excerpt ? `- Last output: ${input.excerpt}` : "",
    "",
    "CoS guidance: triage the status/blockers above. Do not blindly re-dispatch the same blocker. Coordinate reviews and handoffs, merge verified scoped PRs under the repository review policy, or summarize the real Owner decisions needed.",
  ]
    .filter(Boolean)
    .join("\n");
}
