"""Verify the local ACP fixture without SDK, internet or model credentials."""

import json
from pathlib import Path
import subprocess
import sys
import unittest


ECHO = Path(__file__).parent / "fixtures" / "acp_echo.py"


class AcpEchoTest(unittest.TestCase):
    def test_handshake_prompt_and_method_denial(self):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": 1}},
            {"jsonrpc": "2.0", "id": 2, "method": "session/new",
             "params": {"cwd": ".", "mcpServers": []}},
            {"jsonrpc": "2.0", "id": 3, "method": "session/prompt",
             "params": {"sessionId": "kovan-test-session", "prompt": [
                 {"type": "text", "text": "ping"}]}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "shell", "arguments": {}}},
        ]
        result = subprocess.run(
            [sys.executable, str(ECHO)],
            input="\n".join(json.dumps(item) for item in messages) + "\n",
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        self.assertEqual(result.stderr, "")
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies), 5)
        self.assertEqual(replies[0]["result"]["protocolVersion"], 1)
        self.assertEqual(replies[1]["result"]["sessionId"], "kovan-test-session")
        self.assertEqual(
            replies[2]["params"]["update"]["content"]["text"],
            "KOVAN_ACP_OK",
        )
        self.assertEqual(replies[3]["result"]["stopReason"], "end_turn")
        self.assertEqual(replies[4]["error"]["code"], -32601)

    def test_invalid_json_and_notifications_do_not_trigger_actions(self):
        data = (
            "not-json\n"
            + json.dumps({"jsonrpc": "2.0", "method": "session/cancel"})
            + "\n"
        )
        result = subprocess.run(
            [sys.executable, str(ECHO)],
            input=data,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
