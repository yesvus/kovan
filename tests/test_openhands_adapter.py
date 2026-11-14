"""Offline OpenHands Automation integration contract and adversarial tests."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from kovan.openhands_adapter import (
    OpenHandsHTTP, RunIdentity, _api_base, corroborate, dispatch_once,
    main, observe_run,
)
from kovan.pr_evidence import Policy


AUTOMATION = "11111111-1111-4111-8111-111111111111"
RUN = "22222222-2222-4222-8222-222222222222"
PROFILE = "33333333-3333-4333-8333-333333333333"
CONVERSATION = "44444444-4444-4444-8444-444444444444"
SHA = "a" * 40
CHECK = "Unit contract"
API = f"/api/automation/v1/{AUTOMATION}"


def upstream_fixture():
    return {
        API: {
            "id": AUTOMATION,
            "state": "INACTIVE",
            "enabled": False,
            "agent_profile_id": PROFILE,
        },
        API + "/runs?limit=100&offset=0": {
            "total": 1,
            "runs": [{
                "id": RUN,
                "automation_id": AUTOMATION,
                "status": "COMPLETED",
                "trigger_source": "manual",
                "resolved_runtime": {"agent_profile_id": PROFILE},
                "error_detail": None,
                "completed_at": "2026-11-14T12:01:00Z",
                "conversation_id": CONVERSATION,
            }],
        },
        f"/api/conversations/{CONVERSATION}": {
            "id": CONVERSATION,
            "execution_status": "finished",
            "launched_agent_profile": {"agent_profile_id": PROFILE},
        },
        f"/api/conversations/{CONVERSATION}/agent_final_response": {
            "response": "KOVAN_ACP_OK",
        },
    }


class FakeAPI:
    def __init__(self, fixture=None):
        self.fixture = fixture if fixture is not None else upstream_fixture()
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path))
        return self.fixture[path]

    def post(self, path):
        self.calls.append(("POST", path))
        return {
            "id": "55555555-5555-4555-8555-555555555555",
            "automation_id": AUTOMATION,
            "status": "PENDING",
        }


class FakeGitHub:
    def __init__(self):
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        if "/pulls/" in path:
            return {"state": "open", "head": {"sha": SHA}}
        return {"total_count": 1, "check_runs": [{
            "name": CHECK,
            "status": "completed",
            "conclusion": "success",
            "head_sha": SHA,
            "app": {"slug": "github-actions"},
        }]}


def identity():
    return RunIdentity(AUTOMATION, RUN, PROFILE)


class OpenHandsAdapterTests(unittest.TestCase):
    def test_correlated_finished_run_accepted(self):
        api = FakeAPI()
        result = observe_run(api, api, identity())
        self.assertTrue(result["execution_observed"])
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["conversation_id"], CONVERSATION)
        self.assertEqual(result["reasons"], [])
        self.assertEqual(len(api.calls), 4)
        self.assertNotIn("KOVAN_ACP_OK", json.dumps(result))

    def test_profile_mismatch_at_automation_blocks(self):
        data = upstream_fixture()
        data[API]["agent_profile_id"] = "other"
        api = FakeAPI(data)
        result = observe_run(api, api, identity())
        self.assertFalse(result["execution_observed"])
        self.assertEqual(len(api.calls), 1)

    def test_duplicate_and_missing_run_block(self):
        for runs in ([], [upstream_fixture()[API + "/runs?limit=100&offset=0"]["runs"][0]] * 2):
            with self.subTest(total=len(runs)):
                data = upstream_fixture()
                data[API + "/runs?limit=100&offset=0"] = {
                    "total": len(runs), "runs": runs,
                }
                self.assertFalse(
                    observe_run(FakeAPI(data), FakeAPI(data), identity())[
                        "execution_observed"
                    ]
                )

    def test_run_negative_cases_fail_closed(self):
        changes = (
            ("status", "FAILED"), ("status", "RUNNING"),
            ("trigger_source", "cron"), ("automation_id", PROFILE),
            ("error_detail", "failure"), ("completed_at", None),
            ("conversation_id", None), ("resolved_runtime", {}),
        )
        for field, value in changes:
            with self.subTest(field=field, value=value):
                data = upstream_fixture()
                data[API + "/runs?limit=100&offset=0"]["runs"][0][field] = value
                self.assertFalse(
                    observe_run(FakeAPI(data), FakeAPI(data), identity())[
                        "execution_observed"
                    ]
                )

    def test_conversation_not_finished_blocks(self):
        data = upstream_fixture()
        data[f"/api/conversations/{CONVERSATION}"]["execution_status"] = "running"
        self.assertFalse(observe_run(FakeAPI(data), FakeAPI(data), identity())[
            "execution_observed"
        ])

    def test_agent_server_profile_mismatch_blocks(self):
        data = upstream_fixture()
        data[f"/api/conversations/{CONVERSATION}"]["launched_agent_profile"] = {
            "agent_profile_id": AUTOMATION,
        }
        self.assertFalse(observe_run(FakeAPI(data), FakeAPI(data), identity())[
            "execution_observed"
        ])

    def test_missing_final_response_blocks(self):
        data = upstream_fixture()
        data[f"/api/conversations/{CONVERSATION}/agent_final_response"] = {
            "response": "  ",
        }
        self.assertFalse(observe_run(FakeAPI(data), FakeAPI(data), identity())[
            "execution_observed"
        ])

    def test_malformed_run_page_blocks(self):
        for page in (
            {"total": 2, "runs": [{}, {}, {}]},
            {"total": -1, "runs": []},
            {"total": 101, "runs": [None] * 101},
            {"runs": []},
        ):
            with self.subTest(page=page):
                data = upstream_fixture()
                data[API + "/runs?limit=100&offset=0"] = page
                with self.assertRaises(ValueError):
                    observe_run(FakeAPI(data), FakeAPI(data), identity())

    def test_identity_requires_canonical_uuid(self):
        with self.assertRaises(ValueError):
            observe_run(FakeAPI(), FakeAPI(), RunIdentity("invalid", RUN, PROFILE))
        with self.assertRaises(ValueError):
            observe_run(FakeAPI(), FakeAPI(), RunIdentity(
                "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA", RUN, PROFILE,
            ))

    def test_independent_github_conjunction_never_authorizes_delivery(self):
        a = FakeAPI()
        g = FakeGitHub()
        result = corroborate(
            a, a, identity(),
            Policy("yesvus/kovan", 4, SHA, (CHECK,)),
            g,
        )
        self.assertTrue(result["both_observations_passed"])
        self.assertTrue(result["execution"]["execution_observed"])
        self.assertTrue(result["github"]["verified"])
        self.assertFalse(result["delivery_authorized"])
        self.assertFalse(result["causal_link_proven"])
        self.assertEqual(len(g.calls), 3)

    def test_github_fails_even_if_execution_completes(self):
        g = FakeGitHub()
        old = g.get

        def fake(path):
            result = old(path)
            if "/check-runs" in path:
                result["check_runs"][0]["conclusion"] = "failure"
            return result

        g.get = fake
        result = corroborate(
            FakeAPI(), FakeAPI(), identity(),
            Policy("yesvus/kovan", 4, SHA, (CHECK,)), g,
        )
        self.assertFalse(result["both_observations_passed"])
        self.assertFalse(result["delivery_authorized"])

    def test_dispatch_is_library_only_and_requires_explicit_opt_in(self):
        api = FakeAPI()
        with self.assertRaisesRegex(ValueError, "opt-in"):
            dispatch_once(api, AUTOMATION, PROFILE)
        self.assertEqual(api.calls, [])

    def test_dispatch_matches_inactive_profile_and_returns_receipt(self):
        api = FakeAPI()
        result = dispatch_once(api, AUTOMATION, PROFILE, operator_authorized=True)
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["automation_id"], AUTOMATION)
        self.assertEqual([x[0] for x in api.calls], ["GET", "GET", "POST"])

    def test_dispatch_refuses_active_or_unknown_runs(self):
        for status in ("PENDING", "RUNNING", "SOMETHING_NEW"):
            with self.subTest(status=status):
                data = upstream_fixture()
                data[API + "/runs?limit=100&offset=0"]["runs"][0]["status"] = status
                api = FakeAPI(data)
                with self.assertRaises(ValueError):
                    dispatch_once(api, AUTOMATION, PROFILE, operator_authorized=True)
                self.assertNotIn("POST", [x[0] for x in api.calls])

    def test_dispatch_rejects_inactive_profile_mismatch_or_paginated_history(self):
        for key, value in (
            ("state", "ACTIVE"), ("enabled", True),
            ("agent_profile_id", AUTOMATION),
        ):
            with self.subTest(key=key):
                data = upstream_fixture()
                data[API][key] = value
                api = FakeAPI(data)
                with self.assertRaises(ValueError):
                    dispatch_once(api, AUTOMATION, PROFILE, operator_authorized=True)
                self.assertNotIn("POST", [x[0] for x in api.calls])
        data = upstream_fixture()
        data[API + "/runs?limit=100&offset=0"]["total"] = 2
        with self.assertRaises(ValueError):
            dispatch_once(FakeAPI(data), AUTOMATION, PROFILE,
                          operator_authorized=True)

    def test_transport_url_rejects_unencrypted_remote_and_credential_urls(self):
        for url in (
            "http://example.com:18001",
            "http://localhost:18001/api",
            "https://user:pass@example.com:443",
            "http://localhost:abc",
            "http://localhost:18001?key=x",
            "file:///tmp/secret",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _api_base(url)
        self.assertEqual(
            _api_base("http://127.0.0.1:18001"),
            "http://127.0.0.1:18001",
        )

    def test_cli_failure_does_not_echo_credential(self):
        with patch.dict("os.environ", {
            "KOVAN_OPENHANDS_API_KEY": "super-secret-value"
        }), patch("kovan.openhands_adapter.OpenHandsHTTP",
                  side_effect=OSError("super-secret-value")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = main([
                "--automation-id", AUTOMATION, "--run-id", RUN,
                "--profile-id", PROFILE, "--repo", "yesvus/kovan",
                "--pr", "4", "--expected-sha", SHA,
                "--require-check", CHECK,
            ])
        self.assertEqual(code, 2)
        self.assertNotIn("super-secret-value", output.getvalue())
        self.assertFalse(json.loads(output.getvalue())[
            "both_observations_passed"
        ])


if __name__ == "__main__":
    unittest.main()
