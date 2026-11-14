#!/usr/bin/env python3
"""Deterministic ACP v1 test peer; not a model provider or coding agent.

No filesystem access beyond this script, no network, no tools and no secrets.
"""

import json
import sys

SESSION = "kovan-test-session"


def send(value):
    print(json.dumps(value, separators=(",", ":")), flush=True)


def dispatch(message):
    if not isinstance(message, dict) or "id" not in message:
        return
    request_id = message["id"]
    method = message.get("method")

    if method == "initialize":
        result = {
            "protocolVersion": 1,
            "agentCapabilities": {
                "loadSession": False,
                "promptCapabilities": {
                    "image": False,
                    "audio": False,
                    "embeddedContext": False,
                },
            },
        }
    elif method == "session/new":
        result = {"sessionId": SESSION}
    elif method == "session/prompt":
        send({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": SESSION,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "KOVAN_ACP_OK"},
                },
            },
        })
        result = {"stopReason": "end_turn"}
    else:
        send({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        })
        return

    send({"jsonrpc": "2.0", "id": request_id, "result": result})


def main():
    for line in sys.stdin:
        try:
            dispatch(json.loads(line))
        except (TypeError, ValueError):
            # Ignore invalid JSON-RPC input; never execute arbitrary operations.
            continue


if __name__ == "__main__":
    main()
