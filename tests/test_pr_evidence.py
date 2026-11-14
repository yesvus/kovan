"""Offline tests for fresh-head, independent GitHub PR check evidence."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from kovan.pr_evidence import Policy, main, verify


SHA = "a" * 40
NEW_SHA = "b" * 40
CHECKS = ("Offline core and ACP contract tests", "Repository integrity (not product tests)")


def policy(**changes):
    obj = {
        "repo": "yesvus/kovan",
        "number": 4,
        "expected_sha": SHA,
        "required_checks": CHECKS,
        "app_slug": "github-actions",
    }
    obj.update(changes)
    return Policy(**obj)


def check(name, **kwargs):
    obj = {
        "name": name,
        "status": "completed",
        "conclusion": "success",
        "head_sha": SHA,
        "app": {"slug": "github-actions"},
    }
    obj.update(kwargs)
    return obj


def pr(sha=SHA, state="open"):
    return {"state": state, "head": {"sha": sha}}


class FakeFetch:
    def __init__(self, runs=None, first=None, last=None, total=None):
        self.runs = list(runs) if runs is not None else [check(name) for name in CHECKS]
        self.first = first if first is not None else pr()
        self.last = last if last is not None else pr()
        self.total = total if total is not None else len(self.runs)
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        if "/pulls/" in path:
            return self.first if sum("/pulls/" in c for c in self.calls) == 1 else self.last
        if "/check-runs" in path:
            return {"total_count": self.total, "check_runs": self.runs}
        raise AssertionError("unexpected endpoint")


class PrEvidenceTests(unittest.TestCase):
    def test_valid_current_sha_and_required_checks(self):
        transport = FakeFetch()
        result = verify(policy(), transport)
        self.assertTrue(result["verified"])
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["checks"], dict.fromkeys(CHECKS, "success"))
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(transport.calls[0], transport.calls[2])
        self.assertIn(SHA, transport.calls[1])
        self.assertIn("filter=latest", transport.calls[1])

    def test_stale_head_blocks_before_loading_checks(self):
        transport = FakeFetch(first=pr(NEW_SHA))
        result = verify(policy(), transport)
        self.assertFalse(result["verified"])
        self.assertEqual(len(transport.calls), 1)

    def test_pr_closed_blocks(self):
        self.assertFalse(verify(policy(), FakeFetch(first=pr(state="closed")))["verified"])

    def test_head_changes_during_checks(self):
        result = verify(policy(), FakeFetch(last=pr(NEW_SHA)))
        self.assertFalse(result["verified"])
        self.assertIn("PR head moved", result["reasons"][-1])

    def test_pr_closed_during_checks(self):
        self.assertFalse(verify(policy(), FakeFetch(last=pr(state="closed")))["verified"])

    def test_missing_required_check_fails(self):
        result = verify(policy(), FakeFetch(runs=[check(CHECKS[0])]))
        self.assertFalse(result["verified"])
        self.assertEqual(result["checks"][CHECKS[1]], "missing_or_ambiguous")

    def test_duplicate_check_name_blocks_even_with_other_app(self):
        runs = [check(name) for name in CHECKS]
        runs.append(check(CHECKS[0], app={"slug": "not-github-actions"}))
        result = verify(policy(), FakeFetch(runs=runs))
        self.assertFalse(result["verified"])
        self.assertEqual(result["checks"][CHECKS[0]], "missing_or_ambiguous")

    def test_fake_app_blocks(self):
        runs = [check(CHECKS[0], app={"slug": "other"}), check(CHECKS[1])]
        result = verify(policy(), FakeFetch(runs=runs))
        self.assertEqual(result["checks"][CHECKS[0]], "unexpected_app")
        self.assertFalse(result["verified"])

    def test_stale_check_sha_blocks(self):
        runs = [check(CHECKS[0], head_sha=NEW_SHA), check(CHECKS[1])]
        result = verify(policy(), FakeFetch(runs=runs))
        self.assertEqual(result["checks"][CHECKS[0]], "stale_sha")
        self.assertFalse(result["verified"])

    def test_queued_check_blocks(self):
        runs = [check(CHECKS[0], status="queued", conclusion=None), check(CHECKS[1])]
        result = verify(policy(), FakeFetch(runs=runs))
        self.assertFalse(result["verified"])
        self.assertEqual(result["checks"][CHECKS[0]], "not_successful")

    def test_failed_check_blocks(self):
        runs = [check(CHECKS[0], conclusion="failure"), check(CHECKS[1])]
        self.assertFalse(verify(policy(), FakeFetch(runs=runs))["verified"])

    def test_skipped_check_is_not_success(self):
        runs = [check(CHECKS[0], conclusion="skipped"), check(CHECKS[1])]
        self.assertFalse(verify(policy(), FakeFetch(runs=runs))["verified"])

    def test_truncation_is_not_success(self):
        result = verify(policy(), FakeFetch(total=101))
        self.assertFalse(result["verified"])
        self.assertIn("not exhaustive", result["reasons"][0])

    def test_invalid_api_response_is_not_success(self):
        class Broken:
            def __init__(self):
                self.calls = 0
            def __call__(self, _path):
                self.calls += 1
                return pr() if self.calls == 1 else {"check_runs": []}
        self.assertFalse(verify(policy(), Broken())["verified"])

    def test_requires_explicit_nonempty_check_set(self):
        with self.assertRaises(ValueError):
            verify(policy(required_checks=()), FakeFetch())
        with self.assertRaises(ValueError):
            verify(policy(required_checks=(CHECKS[0], CHECKS[0])), FakeFetch())

    def test_bad_scope_sha_and_app_fail_closed(self):
        variations = (
            {"repo": "yesvus/../kovan"},
            {"repo": "yesvus/kovan/other"},
            {"number": 0},
            {"expected_sha": NEW_SHA.upper()},
            {"app_slug": "foo/bar"},
        )
        for values in variations:
            with self.subTest(values=values), self.assertRaises(ValueError):
                verify(policy(**values), FakeFetch())

    def test_cli_success_emits_structured_non_authorizing_evidence(self):
        with patch("kovan.pr_evidence.GitHubAPI", return_value=FakeFetch()), \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            status = main([
                "--repo", "yesvus/kovan", "--pr", "4",
                "--expected-sha", SHA,
                "--require-check", CHECKS[0],
                "--require-check", CHECKS[1],
            ])
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(buffer.getvalue())["verified"])
        self.assertNotIn("merge_approved", buffer.getvalue())

    def test_cli_network_exception_fails_closed_without_leaking(self):
        def down(_path):
            raise OSError("sensitive transport information not for output")
        with patch("kovan.pr_evidence.GitHubAPI", return_value=down), \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            status = main([
                "--repo", "yesvus/kovan", "--pr", "4",
                "--expected-sha", SHA, "--require-check", CHECKS[0],
            ])
        self.assertEqual(status, 2)
        self.assertFalse(json.loads(buffer.getvalue())["verified"])
        self.assertNotIn("sensitive", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
