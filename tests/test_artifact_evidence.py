"""Adversarial tests for exact GitHub Contents API SHA-256 evidence."""

import base64
import unittest

from kovan.artifact_evidence import Artifact, capture_candidate, match_committed_bytes

REPO = "yesvus/kovan"
COMMIT = "a" * 40
PATH = "pilot/issue-1/smoke.md"
BYTES = b"# Kovan fixture\n\nGenerated in a disposable worker.\n"


class FakeGitHub:
    def __init__(self, document=None):
        self.calls = []
        self.document = document if document is not None else {
            "type": "file",
            "path": PATH,
            "encoding": "base64",
            "size": len(BYTES),
            "content": base64.b64encode(BYTES).decode(),
        }

    def get(self, path):
        self.calls.append(path)
        return self.document


class ArtifactEvidenceTests(unittest.TestCase):
    def test_exact_head_commit_bytes_pass(self):
        candidate = capture_candidate(PATH, BYTES, issue_number=1)
        client = FakeGitHub()
        self.assertTrue(
            match_committed_bytes(client, REPO, COMMIT, candidate, issue_number=1)
        )
        self.assertEqual(
            client.calls,
            [f"/repos/{REPO}/contents/{PATH}?ref={COMMIT}"],
        )

    def test_modified_bytes_fail_even_with_same_size(self):
        claim = capture_candidate(PATH, BYTES, issue_number=1)
        client = FakeGitHub()
        client.document["content"] = base64.b64encode(
            BYTES.replace(b"Generated", b"Generated"[:-1] + b"x")
        ).decode()
        self.assertFalse(
            match_committed_bytes(client, REPO, COMMIT, claim, issue_number=1)
        )

    def test_malformed_response_and_symlink_fail_closed(self):
        claim = capture_candidate(PATH, BYTES, issue_number=1)
        for change in (
            {"type": "symlink"},
            {"path": "pilot/issue-2/smoke.md"},
            {"size": len(BYTES) + 1},
            {"encoding": "utf-8"},
            {"content": "not valid base64!"},
            {"content": 42},
        ):
            with self.subTest(change=change):
                client = FakeGitHub()
                client.document.update(change)
                self.assertFalse(
                    match_committed_bytes(client, REPO, COMMIT, claim, issue_number=1)
                )

    def test_reject_path_traversal_and_unbounded_candidate(self):
        for path in (
            "../secrets.md", "pilot/issue-2/smoke.md",
            "pilot/issue-1/../bad.md", "pilot/issue-1/smoke.py",
            "pilot/issue-01/smoke.md",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                capture_candidate(path, BYTES, issue_number=1)
        with self.assertRaises(ValueError):
            capture_candidate(PATH, b"x" * 65537, issue_number=1)

    def test_reject_boolean_size_or_invalid_sha(self):
        for bad in (
            Artifact(PATH, True, "a" * 64),
            Artifact(PATH, 12, "b"),
            Artifact(PATH, 65537, "a" * 64),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                bad.validate(1)

    def test_refuse_invalid_repo_or_sha_without_requests(self):
        claim = capture_candidate(PATH, BYTES, issue_number=1)
        for repo, sha in (
            ("yesvus/../kovan", COMMIT),
            ("owner/kovan/other", COMMIT),
            (REPO, "b" * 7),
        ):
            client = FakeGitHub()
            with self.subTest(repo=repo, sha=sha), self.assertRaises(ValueError):
                match_committed_bytes(client, repo, sha, claim, issue_number=1)
            self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
