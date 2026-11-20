// OpenCode runtime integration for Kovan: notify the repository CoS when a
// Lead seat session goes idle.
//
// This is a reference example, not part of the Kovan specification. It only
// observes native session lifecycle events and posts one bounded message into
// the existing CoS session. It never starts, replaces or dispatches a lead, and
// it never writes repository or cluster state.
//
// Install: copy this directory into your OpenCode plugins directory, point
// KOVAN_WATCHER_CONFIG at a JSON config file (see kovan-lead-watcher.example.json),
// and restart the server. Use `node --test` for the deterministic decision tests.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  buildReport,
  decideNotification,
  isWatchedSeat,
  selectCosSession,
} from "./lib/decide.js";

const DEFAULT_CONFIG_PATH = path.join(
  os.homedir(),
  ".config/opencode/kovan-lead-watcher.json"
);

const DEFAULT_CFG = {
  cos_session_id: "",
  cos_title_prefix: "ops-CoS",
  seat_title_prefix: "lead:",
  exclude_titles: [],
  cooldown_seconds: 120,
  opencode_url: "http://127.0.0.1:4096",
  password_file: "",
  password_env: "OPENCODE_SERVER_PASSWORD",
  state_file: "~/.cache/kovan-lead-watcher-state.json",
  log_file: "~/.cache/kovan-lead-watcher.log",
};

function expandHome(p) {
  if (!p) return p;
  return p.startsWith("~") ? path.join(os.homedir(), p.slice(1)) : p;
}

function loadConfig() {
  const configPath = process.env.KOVAN_WATCHER_CONFIG || DEFAULT_CONFIG_PATH;
  let fileCfg = {};
  try {
    if (fs.existsSync(configPath)) {
      fileCfg = JSON.parse(fs.readFileSync(configPath, "utf8"));
    }
  } catch {}
  const cfg = { ...DEFAULT_CFG, ...fileCfg };
  cfg.state_file = expandHome(cfg.state_file);
  cfg.log_file = expandHome(cfg.log_file);
  cfg.password_file = expandHome(cfg.password_file);
  return cfg;
}

function logLine(cfg, msg) {
  try {
    fs.mkdirSync(path.dirname(cfg.log_file), { recursive: true });
    fs.appendFileSync(cfg.log_file, `${new Date().toISOString()} ${msg}\n`);
  } catch {}
}

function authHeader(cfg) {
  // Prefer an environment variable so the secret is not duplicated on disk.
  let secret = "";
  if (cfg.password_env) secret = (process.env[cfg.password_env] || "").trim();
  if (!secret && cfg.password_file) {
    secret = fs.readFileSync(cfg.password_file, "utf8").trim();
  }
  if (!secret) throw new Error("no OpenCode server credential configured");
  return "Basic " + Buffer.from(`opencode:${secret}`).toString("base64");
}

async function ocFetch(cfg, urlPath, opts = {}) {
  const res = await fetch(`${cfg.opencode_url.replace(/\/$/, "")}${urlPath}`, {
    ...opts,
    headers: {
      Authorization: authHeader(cfg),
      Accept: "application/json",
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
      ...(opts.headers || {}),
    },
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`HTTP ${res.status} ${urlPath}: ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : null;
}

function loadState(cfg) {
  try {
    if (fs.existsSync(cfg.state_file)) {
      return JSON.parse(fs.readFileSync(cfg.state_file, "utf8"));
    }
  } catch {}
  return { sessions: {} };
}

function saveState(cfg, state) {
  fs.mkdirSync(path.dirname(cfg.state_file), { recursive: true });
  const tmp = `${cfg.state_file}.tmp.${process.pid}.${Date.now()}`;
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2));
  fs.renameSync(tmp, cfg.state_file);
}

// The lock makes the check-and-write in claimNotification atomic across plugin
// reloads and multiple event handlers. A stale lock older than 15s is removed.
function claimNotification(cfg, sessionID, messageID, title, updatedISO) {
  fs.mkdirSync(path.dirname(cfg.state_file), { recursive: true });
  const lockPath = `${cfg.state_file}.lock`;
  let fd = null;
  for (let i = 0; i < 20; i++) {
    try {
      fd = fs.openSync(lockPath, "wx");
      break;
    } catch {
      try {
        const st = fs.statSync(lockPath);
        if (Date.now() - st.mtimeMs > 15000) fs.unlinkSync(lockPath);
      } catch {}
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 50);
    }
  }
  if (fd === null) return { ok: false, reason: "lock-busy" };
  try {
    const nowSeconds = Math.floor(Date.now() / 1000);
    const state = loadState(cfg);
    state.sessions = state.sessions || {};
    const decision = decideNotification({
      previous: state.sessions[sessionID],
      messageID,
      nowSeconds,
      cooldownSeconds: cfg.cooldown_seconds,
    });
    if (!decision.notify) return { ok: false, reason: decision.reason };

    state.sessions[sessionID] = {
      title,
      last_notified_msg_id: messageID,
      last_notified_ts: nowSeconds,
      updated: updatedISO,
    };
    saveState(cfg, state);
    return { ok: true };
  } finally {
    try { fs.closeSync(fd); } catch {}
    try { fs.unlinkSync(lockPath); } catch {}
  }
}

async function resolveCosSessionID(cfg) {
  if (cfg.cos_session_id) return cfg.cos_session_id;
  const resp = await ocFetch(cfg, "/api/session?limit=50");
  const list = resp?.data || resp || [];
  return selectCosSession(list, {
    cosTitlePrefix: cfg.cos_title_prefix,
  });
}

const inflight = new Set();

async function handleSeatIdle(sessionID) {
  if (!sessionID || inflight.has(sessionID)) return;
  inflight.add(sessionID);
  const cfg = loadConfig();
  try {
    const cosID = await resolveCosSessionID(cfg);
    if (!cosID || sessionID === cosID) return;

    const sessResp = await ocFetch(cfg, `/api/session/${sessionID}`);
    const session = sessResp?.data || sessResp;
    if (!isWatchedSeat(session, {
      seatTitlePrefix: cfg.seat_title_prefix,
      excludeTitles: cfg.exclude_titles,
    })) return;

    const msgResp = await ocFetch(cfg, `/api/session/${sessionID}/message?limit=5`);
    const messages = msgResp?.data || [];
    const lastAssistant = messages.find((m) => m.type === "assistant");
    if (!lastAssistant?.id) return;

    const updatedMs = session.time?.updated || Date.now();
    const updatedISO = new Date(updatedMs).toISOString().replace(/\.\d+Z$/, "Z");
    const claim = claimNotification(cfg, sessionID, lastAssistant.id, session.title || "", updatedISO);
    if (!claim.ok) {
      if (claim.reason === "cooldown") {
        logLine(cfg, `cooldown-skip session=${sessionID} msg=${lastAssistant.id}`);
      }
      return;
    }

    const excerpt = (lastAssistant.content || [])
      .filter((block) => block.type === "text" && block.text)
      .map((block) => block.text.trim())
      .join(" ")
      .replace(/\s+/g, " ")
      .slice(0, 600);

    const report = buildReport({
      title: session.title || "",
      sessionID,
      updatedISO,
      messageID: lastAssistant.id,
      excerpt,
      nowISO: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
    });

    await ocFetch(cfg, `/api/session/${cosID}/prompt`, {
      method: "POST",
      body: JSON.stringify({ text: report }),
    });
    logLine(cfg, `notified cos=${cosID} from session=${sessionID} msg=${lastAssistant.id}`);
  } catch (err) {
    logLine(cfg, `error session=${sessionID}: ${err?.message || err}`);
  } finally {
    inflight.delete(sessionID);
  }
}

const TERMINAL_EVENTS = new Set([
  "session.idle",
  "session.execution.succeeded",
  "session.execution.failed",
  "session.execution.interrupted",
]);

async function startEventLoop(signal) {
  let backoffMs = 1000;
  while (!signal.aborted) {
    const cfg = loadConfig();
    try {
      const res = await fetch(`${cfg.opencode_url.replace(/\/$/, "")}/api/event`, {
        signal,
        headers: {
          Authorization: authHeader(cfg),
          Accept: "text/event-stream",
        },
      });
      if (!res.ok || !res.body) throw new Error(`SSE HTTP ${res.status}`);
      logLine(cfg, "sse-connected /api/event");
      backoffMs = 1000;

      const decoder = new TextDecoder();
      let buffer = "";
      for await (const chunk of res.body) {
        if (signal.aborted) break;
        buffer += decoder.decode(chunk, { stream: true });
        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          for (const line of block.split("\n")) {
            if (!line.startsWith("data:")) continue;
            const raw = line.slice(5).trim();
            if (!raw) continue;
            try {
              const event = JSON.parse(raw);
              if (TERMINAL_EVENTS.has(event?.type)) {
                const sid = event?.data?.sessionID || event?.properties?.sessionID;
                handleSeatIdle(sid);
              }
            } catch {}
          }
        }
      }
      if (!signal.aborted) logLine(cfg, "sse-eof reconnecting");
    } catch (err) {
      if (signal.aborted) break;
      logLine(cfg, `sse-error: ${err?.message || err} (retry in ${backoffMs}ms)`);
    }
    if (signal.aborted) break;
    await new Promise((resolve) => setTimeout(resolve, backoffMs));
    backoffMs = Math.min(backoffMs * 2, 10000);
  }
}

export default {
  id: "kovan-lead-watcher",
  setup() {
    if (globalThis.__kovanLeadWatcherAbort) {
      try { globalThis.__kovanLeadWatcherAbort.abort(); } catch {}
    }
    const controller = new AbortController();
    globalThis.__kovanLeadWatcherAbort = controller;
    logLine(loadConfig(), "plugin-setup starting SSE watcher");
    startEventLoop(controller.signal);
  },
};
