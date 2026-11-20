import test from "node:test";
import assert from "node:assert/strict";

import {
  buildReport,
  decideNotification,
  isWatchedSeat,
  selectCosSession,
} from "../lib/decide.js";

test("watches only top-level Lead seats", () => {
  const cfg = { seatTitlePrefix: "lead:", excludeTitles: ["lead:retired"] };

  assert.equal(isWatchedSeat({ title: "lead:platform / drain" }, cfg), true);
  assert.equal(isWatchedSeat({ title: "Ops-CoS / backlog" }, cfg), false);
  assert.equal(isWatchedSeat({ title: "lead:platform", parentID: "ses_child" }, cfg), false);
  assert.equal(isWatchedSeat({ title: "lead:retired seat" }, cfg), false);
  assert.equal(isWatchedSeat({ title: "" }, cfg), false);
});

test("drops duplicate event retries and respects the cooldown", () => {
  const previous = { last_notified_msg_id: "msg_a", last_notified_ts: 1000 };

  assert.deepEqual(
    decideNotification({ previous, messageID: "msg_a", nowSeconds: 2000, cooldownSeconds: 120 }),
    { notify: false, reason: "duplicate" }
  );
  assert.deepEqual(
    decideNotification({ previous, messageID: "msg_b", nowSeconds: 1060, cooldownSeconds: 120 }),
    { notify: false, reason: "cooldown" }
  );
  assert.deepEqual(
    decideNotification({ previous, messageID: "msg_b", nowSeconds: 1121, cooldownSeconds: 120 }),
    { notify: true, reason: "notify" }
  );
  assert.deepEqual(
    decideNotification({ previous: {}, messageID: "", nowSeconds: 1121 }),
    { notify: false, reason: "no-message" }
  );
});

test("selects the explicit CoS, else the most recently updated matching seat", () => {
  const sessions = [
    { id: "ses_lead", title: "lead:secrets", time: { updated: 30 } },
    { id: "ses_old_cos", title: "ops-CoS / old", time: { updated: 10 } },
    { id: "ses_new_cos", title: "ops-CoS / current", time: { updated: 20 } },
    { id: "ses_child", title: "ops-CoS / child", parentID: "ses_new_cos", time: { updated: 99 } },
  ];

  assert.equal(selectCosSession(sessions, {}), "ses_new_cos");
  assert.equal(selectCosSession(sessions, { cosSessionID: "ses_pinned" }), "ses_pinned");
  assert.equal(selectCosSession([], {}), "");
});

test("report is a notification, not an assignment", () => {
  const report = buildReport({
    title: "lead:platform",
    sessionID: "ses_1",
    updatedISO: "2026-01-01T00:00:00Z",
    messageID: "msg_1",
    excerpt: "DONE: merged #12",
    nowISO: "2026-01-01T00:00:01Z",
  });

  assert.match(report, /\[kovan-lead-watcher @ 2026-01-01T00:00:01Z\]/);
  assert.match(report, /lead:platform \(`ses_1`\)/);
  assert.match(report, /DONE: merged #12/);
  assert.match(report, /Do not blindly re-dispatch/);
});
