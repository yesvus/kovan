"""Offline tests for signed publication receipts and independent reconciliation."""

import base64
import hashlib
import json
import unittest

from kovan.handoff import (
    Publication, attest_after_publication, authenticate_receipt, mint_receipt, reconcile,
)


KEY = b"TEST-ONLY-32-BYTES-NOT-A-PRODUCTION-KEY!"  # Never use in service.
WRONG_KEY = b"another-controller-only-test-key-of-32-bytes"
NOW = 2_000_000_000
REPO = "yesvus/kovan"
ISSUE = 1
PR = 7
BRANCH = "kovan/issue-1-protocol-smoke"
SHA = "a" * 40
PROFILE = "33333333-3333-4333-8333-333333333333"
AUTOMATION = "11111111-1111-4111-8111-111111111111"
RUN = "22222222-2222-4222-8222-222222222222"
CONVERSATION = "44444444-4444-4444-8444-444444444444"
CHECK = "CI required check"
ARTIFACT_PATH = "pilot/issue-1/smoke.md"
ARTIFACT_BYTES = b"# Kovan isolated fixture\n\nNo model inference.\n"
ARTIFACT_DIGEST = hashlib.sha256(ARTIFACT_BYTES).hexdigest()


def publication(**changes):
    fields = dict(
        repo=REPO,
        issue_number=ISSUE,
        pr_number=PR,
        branch=BRANCH,
        base_ref="main",
        head_sha=SHA,
        publisher_login="kovan-publisher[bot]",
        automation_id=AUTOMATION,
        run_id=RUN,
        profile_id=PROFILE,
        artifact_path=ARTIFACT_PATH,
        artifact_size=len(ARTIFACT_BYTES),
        artifact_sha256=ARTIFACT_DIGEST,
        issued_at=NOW - 30,
        expires_at=NOW + 300,
    )
    fields.update(changes)
    return Publication(**fields)


def signed(claim=None):
    return mint_receipt(claim or publication(), KEY, now=NOW)


class FakeGitHub:
    def __init__(self):
        self.calls = []
        self.issue = {
            "number": ISSUE,
            "state": "open",
            "repository_url": "https://api.github.com/repos/yesvus/kovan",
        }
        self.pr = {
            "number": PR,
            "state": "open",
            "draft": True,
            "head": {
                "sha": SHA,
                "ref": BRANCH,
                "repo": {"full_name": REPO},
            },
            "base": {"ref": "main", "repo": {"full_name": REPO}},
            "user": {"login": "kovan-publisher[bot]"},
        }
        self.artifact = {
            "type": "file", "path": ARTIFACT_PATH,
            "encoding": "base64", "size": len(ARTIFACT_BYTES),
            "content": base64.b64encode(ARTIFACT_BYTES).decode("ascii"),
        }
        self.checks = {
            "total_count": 1,
            "check_runs": [{
                "name": CHECK, "status": "completed",
                "conclusion": "success", "head_sha": SHA,
                "app": {"slug": "github-actions"},
            }],
        }

    def get(self, path):
        self.calls.append(path)
        if "/issues/" in path:
            return self.issue
        if "/contents/" in path:
            return self.artifact
        if "/pulls/" in path:
            return self.pr
        if "/check-runs?" in path:
            return self.checks
        raise AssertionError("Unexpected endpoint: " + path)


class FakeOpenHands:
    def __init__(self):
        self.calls = []
        self.automation = {
            "id": AUTOMATION,
            "agent_profile_id": PROFILE,
            "state": "INACTIVE", "enabled": False,
        }
        self.runs = {
            "total": 1,
            "runs": [{
                "id": RUN,
                "automation_id": AUTOMATION,
                "resolved_runtime": {"agent_profile_id": PROFILE},
                "status": "COMPLETED", "trigger_source": "manual",
                "completed_at": "2026-11-14T12:00:00Z",
                "error_detail": None,
                "conversation_id": CONVERSATION,
            }],
        }
        self.conversation = {
            "id": CONVERSATION,
            "execution_status": "finished",
            "launched_agent_profile": {"agent_profile_id": PROFILE},
        }
        self.final = {"response": "test fixture only — not validated agent text"}

    def get(self, path):
        self.calls.append(path)
        if path.endswith("/runs?limit=100&offset=0"):
            return self.runs
        if path == f"/api/automation/v1/{AUTOMATION}":
            return self.automation
        if path == f"/api/conversations/{CONVERSATION}":
            return self.conversation
        if path.endswith("/agent_final_response"):
            return self.final
        raise AssertionError("Unexpected endpoint: " + path)


class HandoffTests(unittest.TestCase):
    def reconcile(self, claim=None, github=None, upstream=None):
        return reconcile(
            signed(claim), KEY,
            github or FakeGitHub(),
            upstream or FakeOpenHands(),
            upstream or FakeOpenHands(),
            (CHECK,), now=NOW,
        )

    def test_signed_controller_receipt_is_authenticated(self):
        receipt = signed()
        self.assertEqual(receipt["version"], 2)
        self.assertEqual(len(receipt["mac"]), 64)
        self.assertEqual(
            authenticate_receipt(receipt, KEY, now=NOW), publication()
        )

    def test_deterministic_envelope_and_no_secret_in_claim(self):
        one, two = signed(), signed()
        self.assertEqual(one, two)
        self.assertNotIn(KEY.hex(), json.dumps(one))
        self.assertNotIn("TEST-ONLY", json.dumps(one))

    def test_authenticated_github_and_execution_checks_consistent(self):
        github, upstream = FakeGitHub(), FakeOpenHands()
        out = reconcile(signed(), KEY, github, upstream, upstream,
                        (CHECK,), now=NOW)
        self.assertTrue(out["receipt_authenticated"])
        self.assertTrue(out["github_publication_matches"])
        self.assertTrue(out["execution_observed"])
        self.assertTrue(out["checks_verified"])
        self.assertTrue(out["publication_evidence_consistent"])
        self.assertFalse(out["delivery_authorized"])
        self.assertFalse(out["agent_authorship_proven"])
        self.assertEqual(len(github.calls), 6)
        self.assertNotIn(upstream.final["response"], json.dumps(out))

    def test_tampered_receipt_blocked_before_any_api_request(self):
        for change in (
            {"head_sha": "b" * 40}, {"issue_number": 2},
            {"run_id": "99999999-9999-4999-8999-999999999999"},
        ):
            with self.subTest(change=change):
                receipt = signed()
                receipt["claim"].update(change)
                github, upstream = FakeGitHub(), FakeOpenHands()
                out = reconcile(receipt, KEY, github, upstream, upstream,
                                (CHECK,), now=NOW)
                self.assertFalse(out["receipt_authenticated"])
                self.assertEqual(github.calls, [])
                self.assertEqual(upstream.calls, [])

    def test_wrong_controller_key_blocks_without_io(self):
        github, upstream = FakeGitHub(), FakeOpenHands()
        out = reconcile(signed(), WRONG_KEY, github, upstream, upstream,
                        (CHECK,), now=NOW)
        self.assertFalse(out["publication_evidence_consistent"])
        self.assertEqual(github.calls, [])

    def test_expired_receipt_blocks_without_io(self):
        github = FakeGitHub()
        result = reconcile(signed(), KEY, github, FakeOpenHands(),
                           FakeOpenHands(), (CHECK,), now=NOW + 301)
        self.assertFalse(result["receipt_authenticated"])
        self.assertEqual(github.calls, [])

    def test_unsupported_receipt_version_and_malformed_mac_block(self):
        for change in ({"version": 2}, {"mac": "x" * 64}):
            with self.subTest(change=change):
                receipt = signed()
                receipt.update(change)
                with self.assertRaises(ValueError):
                    authenticate_receipt(receipt, KEY, now=NOW)

    def test_oversized_ttl_and_short_signing_key_block(self):
        with self.assertRaises(ValueError):
            mint_receipt(publication(expires_at=NOW + 7200), KEY, now=NOW)
        with self.assertRaises(ValueError):
            mint_receipt(publication(), b"short", now=NOW)

    def test_untrusted_issue_and_branch_claims_block(self):
        bad = (
            {"issue_number": -1}, {"branch": "feat/my-branch"},
            {"branch": "kovan/issue-2-protocol-smoke"},
            {"base_ref": "production"},
            {"publisher_login": "bot@evil"},
            {"repo": "yesvus/../bad"},
            {"head_sha": "b"},
            {"automation_id": "not-a-uuid"},
            {"issued_at": NOW + 20},
        )
        for values in bad:
            with self.subTest(values=values), self.assertRaises(ValueError):
                mint_receipt(publication(**values), KEY, now=NOW)

    def test_draft_only_and_repository_scope_enforced(self):
        for mutation in (
            lambda gh: gh.pr.update(draft=False),
            lambda gh: gh.pr["head"].update(sha="b" * 40),
            lambda gh: gh.pr["head"].update(ref="other"),
            lambda gh: gh.pr["head"]["repo"].update(full_name="fork/kovan"),
            lambda gh: gh.pr["base"]["repo"].update(full_name="fork/kovan"),
            lambda gh: gh.pr["user"].update(login="malicious-bot"),
            lambda gh: gh.pr.update(state="closed"),
            lambda gh: gh.issue.update(number=12),
            lambda gh: gh.issue.update(state="closed"),
            lambda gh: gh.issue.update(pull_request={"url": "not-an-issue"}),
            lambda gh: gh.issue.update(
                repository_url="https://api.github.com/repos/other/repo"
            ),
        ):
            with self.subTest(mutation=mutation):
                github = FakeGitHub()
                mutation(github)
                result = self.reconcile(github=github)
                self.assertTrue(result["receipt_authenticated"])
                self.assertFalse(result["github_publication_matches"])
                self.assertFalse(result["publication_evidence_consistent"])

    def test_upstream_run_mismatch_blocks_even_with_valid_receipt(self):
        upstream = FakeOpenHands()
        upstream.runs["runs"][0]["conversation_id"] = None
        out = self.reconcile(upstream=upstream)
        self.assertTrue(out["github_publication_matches"])
        self.assertFalse(out["execution_observed"])
        self.assertFalse(out["publication_evidence_consistent"])

    def test_failed_github_ci_blocks_even_if_execution_finished(self):
        github = FakeGitHub()
        github.checks["check_runs"][0]["conclusion"] = "failure"
        result = self.reconcile(github=github)
        self.assertTrue(result["execution_observed"])
        self.assertFalse(result["checks_verified"])
        self.assertFalse(result["publication_evidence_consistent"])

    def test_empty_configured_check_list_never_passes(self):
        out = reconcile(signed(), KEY, FakeGitHub(),
                        FakeOpenHands(), FakeOpenHands(), (), now=NOW)
        self.assertFalse(out["publication_evidence_consistent"])
        self.assertFalse(out["delivery_authorized"])

    def test_missing_claim_fields_rejected(self):
        receipt = signed()
        receipt["claim"].pop("automation_id")
        with self.assertRaises(ValueError):
            authenticate_receipt(receipt, KEY, now=NOW)

    def test_only_attest_after_exact_live_github_publication(self):
        github = FakeGitHub()
        result = attest_after_publication(publication(), KEY, github, now=NOW)
        self.assertEqual(authenticate_receipt(result, KEY, now=NOW), publication())
        self.assertEqual(len(github.calls), 3)
        github.pr["head"]["sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "cannot attest"):
            attest_after_publication(publication(), KEY, github, now=NOW)

    def test_malformed_signed_receipt_types_fail_closed_before_io(self):
        malformed = (
            {"repo": None},
            {"repo": 1},
            {"branch": 1},
            {"head_sha": 1},
            {"profile_id": None},
        )
        for change in malformed:
            with self.subTest(change=change):
                r = signed()
                r["claim"].update(change)
                github, upstream = FakeGitHub(), FakeOpenHands()
                out = reconcile(r, KEY, github, upstream, upstream,
                                (CHECK,), now=NOW)
                self.assertFalse(out["receipt_authenticated"])
                self.assertEqual(github.calls, [])
                self.assertEqual(upstream.calls, [])

    def test_artifact_content_mismatch_blocks_provenance(self):
        github = FakeGitHub()
        github.artifact["content"] = base64.b64encode(
            b"# malicious change\n"
        ).decode("ascii")
        github.artifact["size"] = len(b"# malicious change\n")
        result = self.reconcile(github=github)
        self.assertTrue(result["receipt_authenticated"])
        self.assertTrue(result["github_publication_matches"])
        self.assertFalse(result["artifact_bytes_match"])
        self.assertFalse(result["publication_evidence_consistent"])

    def test_artifact_digest_cannot_be_minted_from_wrong_live_bytes(self):
        github = FakeGitHub()
        github.artifact["content"] = base64.b64encode(
            b"# different content\n"
        ).decode("ascii")
        github.artifact["size"] = len(b"# different content\n")
        with self.assertRaisesRegex(ValueError, "artifact bytes"):
            attest_after_publication(publication(), KEY, github, now=NOW)

    def test_claim_must_pin_valid_issue_scoped_sha256_artifact(self):
        for modification in (
            {"artifact_path": "private/secrets.md"},
            {"artifact_path": "pilot/issue-2/smoke.md"},
            {"artifact_sha256": "00"},
            {"artifact_size": 0},
            {"artifact_size": 99999999},
        ):
            with self.subTest(modification=modification):
                with self.assertRaises(ValueError):
                    mint_receipt(publication(**modification), KEY, now=NOW)

    def test_receipt_is_not_interpreted_as_a_merge_grant(self):
        out = self.reconcile()
        self.assertNotIn("merge_approved", out)
        self.assertIs(out["delivery_authorized"], False)
        self.assertIs(out["agent_authorship_proven"], False)


if __name__ == "__main__":
    unittest.main()
