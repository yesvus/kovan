"""Bounded GitHub Contents API proof of an exact controller-captured artifact.

This proves *file bytes* at the pinned Git commit match a trusted SHA-256,
not the identity of the process which generated those bytes.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Protocol

_MAX_BYTES = 64 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PATH = re.compile(r"pilot/issue-([1-9][0-9]*)/[a-z0-9][a-z0-9_-]{0,48}\.md\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class Reader(Protocol):
    def get(self, path: str) -> Any: ...


@dataclass(frozen=True)
class Artifact:
    path: str
    size: int
    sha256: str

    def validate(self, issue_number: int) -> None:
        if (
            not isinstance(self.path, str)
            or not (match := _PATH.fullmatch(self.path))
            or int(match.group(1)) != issue_number
        ):
            raise ValueError("only a bounded issue-scoped pilot Markdown path is allowed")
        if type(self.size) is not int or not 0 < self.size <= _MAX_BYTES:
            raise ValueError("pilot artifact has invalid or unsafe length")
        if not isinstance(self.sha256, str) or not _SHA256.fullmatch(self.sha256):
            raise ValueError("full SHA-256 digest required")


def capture_candidate(path: str, content: bytes, *, issue_number: int) -> Artifact:
    """Trusted controller hashes already-inspected worker bytes, never model text."""
    if not isinstance(content, bytes):
        raise ValueError("artifact bytes required")
    claim = Artifact(path, len(content), hashlib.sha256(content).hexdigest())
    claim.validate(issue_number)
    return claim


def match_committed_bytes(
    github: Reader, repo: str, commit_sha: str, artifact: Artifact,
    *, issue_number: int,
) -> bool:
    """Re-read GitHub at the exact pinned commit; no branch-name fallbacks.

    A positive result is a byte-for-byte match to the controller-recorded
    digest, NOT proof of worker authorship, security, or delivery approval.
    """
    artifact.validate(issue_number)
    if (
        not isinstance(repo, str)
        or len(repo.split("/")) != 2
        or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", x) or ".." in x
               for x in repo.split("/"))
        or not isinstance(commit_sha, str)
        or not _COMMIT.fullmatch(commit_sha)
    ):
        raise ValueError("untrusted GitHub repository or commit SHA")
    response = github.get(
        f"/repos/{repo}/contents/{artifact.path}?ref={commit_sha}"
    )
    if not isinstance(response, dict):
        return False
    if (
        response.get("type") != "file"
        or response.get("path") != artifact.path
        or response.get("encoding") != "base64"
        or type(response.get("size")) is not int
        or response.get("size") != artifact.size
    ):
        return False
    encoded = response.get("content")
    if not isinstance(encoded, str) or len(encoded) > 100_000:
        return False
    try:
        # GitHub's Contents API normally wraps base64 at 60 characters.
        raw = base64.b64decode("".join(encoded.split()).encode("ascii"),
                               validate=True)
    except (ValueError, UnicodeEncodeError, binascii.Error):
        return False
    if len(raw) != artifact.size:
        return False
    return hashlib.sha256(raw).hexdigest() == artifact.sha256
