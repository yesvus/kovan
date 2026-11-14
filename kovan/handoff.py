"""Controller-issued, short-lived handoff receipt for public PR evidence.

The controller signs only AFTER it publishes an exact artifact to a Draft PR.
The worker must never see the signing key or be able to issue a receipt.

This is publication provenance, not evidence of the agent's authorship, not
a replacement for artifact scanning and not permission to merge or deploy.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from kovan.openhands_adapter import RunIdentity, corroborate
from kovan.pr_evidence import Policy

_VERSION = 1
_DOMAIN = b"kovan/controller-handoff/v1\x00"
_MAX_AGE_SECONDS = 3600
_BRANCH = re.compile(r"kovan/issue-[1-9][0-9]*-[a-z0-9][a-z0-9-]{0,39}\Z")
_LOGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:\[bot\])?\Z")
_MAC = re.compile(r"[0-9a-f]{64}\Z")


class Reader(Protocol):
    def get(self, path: str) -> Any: ...


@dataclass(frozen=True)
class Publication:
    repo: str
    issue_number: int
    pr_number: int
    branch: str
    base_ref: str
    head_sha: str
    publisher_login: str
    automation_id: str
    run_id: str
    profile_id: str
    issued_at: int
    expires_at: int

    def validate(self, now: int) -> None:
        # Reuse the public core's explicit repository and SHA validators.
        Policy(self.repo, self.pr_number, self.head_sha, ("pinned check",)).validate()
        RunIdentity(self.automation_id, self.run_id, self.profile_id).validate()
        if type(self.issue_number) is not int or self.issue_number < 1:
            raise ValueError("positive issue number required")
        if not isinstance(self.branch, str) or not _BRANCH.fullmatch(self.branch):
            raise ValueError("controller-owned issue branch required")
        if not self.branch.startswith(f"kovan/issue-{self.issue_number}-"):
            raise ValueError("branch must match issue number")
        if (
            not isinstance(self.base_ref, str)
            or not self.base_ref == "main"
        ):
            raise ValueError("pilot only supports the main base branch")
        if not isinstance(self.publisher_login, str) or not _LOGIN.fullmatch(
            self.publisher_login
        ):
            raise ValueError("pinned publication account required")
        if type(self.issued_at) is not int or type(self.expires_at) is not int:
            raise ValueError("timestamps must be integer UTC seconds")
        if (
            self.issued_at > now
            or now >= self.expires_at
            or self.issued_at >= self.expires_at
            or self.expires_at - self.issued_at > _MAX_AGE_SECONDS
        ):
            raise ValueError("handoff receipt missing, expired or too far in future")


def _payload(claim: Publication) -> bytes:
    return _DOMAIN + json.dumps(
        asdict(claim), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _key(raw: bytes) -> None:
    if not isinstance(raw, bytes) or len(raw) < 32:
        raise ValueError("controller-only signing key must have >=32 random bytes")


def mint_receipt(
    claim: Publication, controller_key: bytes, *, now: int | None = None
) -> dict[str, Any]:
    """For a trusted controller only, AFTER GitHub returns publication state.

    This deliberately has no CLI, issue-content parser or worker-facing API.
    Caller is responsible for publishing the artifact and protecting the key.
    """
    _key(controller_key)
    claim.validate(int(time.time()) if now is None else now)
    digest = hmac.new(controller_key, _payload(claim), hashlib.sha256).hexdigest()
    return {"version": _VERSION, "claim": asdict(claim), "mac": digest}


def authenticate_receipt(
    receipt: object, controller_key: bytes, *, now: int | None = None
) -> Publication:
    """Authenticate before any external request or authorization-like action."""
    _key(controller_key)
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {"version", "claim", "mac"}
        or type(receipt["version"]) is not int
        or receipt["version"] != _VERSION
        or not isinstance(receipt["claim"], dict)
        or not isinstance(receipt["mac"], str)
        or not _MAC.fullmatch(receipt["mac"])
    ):
        raise ValueError("invalid receipt envelope")
    try:
        claim = Publication(**receipt["claim"])
    except TypeError as exc:
        raise ValueError("unexpected handoff claim fields") from exc
    claim.validate(int(time.time()) if now is None else now)
    expected = hmac.new(
        controller_key, _payload(claim), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(receipt["mac"], expected):
        raise ValueError("untrusted or modified handoff receipt")
    return claim


def _same_publication(github: Reader, claim: Publication) -> bool:
    root = f"/repos/{claim.repo}"
    issue = github.get(f"{root}/issues/{claim.issue_number}")
    if (
        not isinstance(issue, dict)
        or issue.get("number") != claim.issue_number
        or issue.get("state") != "open"
        or issue.get("repository_url") != f"https://api.github.com{root}"
        or issue.get("pull_request") is not None
    ):
        return False

    pr = github.get(f"{root}/pulls/{claim.pr_number}")
    if not isinstance(pr, dict):
        return False
    head = pr.get("head")
    base = pr.get("base")
    author = pr.get("user")
    return bool(
        pr.get("number") == claim.pr_number
        and pr.get("state") == "open"
        and pr.get("draft") is True
        and isinstance(head, dict)
        and head.get("sha") == claim.head_sha
        and head.get("ref") == claim.branch
        and isinstance(head.get("repo"), dict)
        and head["repo"].get("full_name") == claim.repo
        and isinstance(base, dict)
        and base.get("ref") == claim.base_ref
        and isinstance(base.get("repo"), dict)
        and base["repo"].get("full_name") == claim.repo
        and isinstance(author, dict)
        and author.get("login") == claim.publisher_login
    )


def reconcile(
    receipt: object,
    controller_key: bytes,
    github: Reader,
    automation: Reader,
    agent_server: Reader,
    required_checks: tuple[str, ...],
    *,
    now: int | None = None,
) -> dict[str, object]:
    """Observe an authenticated handoff and two independent upstream sources.

    No positive result authorizes a delivery action. This still cannot prove
    which bytes the worker produced or which process authored the PR.
    """
    outcome: dict[str, object] = {
        "receipt_authenticated": False,
        "github_publication_matches": False,
        "execution_observed": False,
        "checks_verified": False,
        "publication_evidence_consistent": False,
        "agent_authorship_proven": False,
        "delivery_authorized": False,
        "reasons": [],
    }
    reasons: list[str] = outcome["reasons"]  # type: ignore[assignment]
    try:
        claim = authenticate_receipt(receipt, controller_key, now=now)
    except ValueError:
        reasons.append("invalid, expired or unauthenticated receipt")
        return outcome

    outcome["receipt_authenticated"] = True
    try:
        if not _same_publication(github, claim):
            reasons.append("GitHub issue or Draft PR mismatches controller receipt")
            return outcome
        outcome["github_publication_matches"] = True
        combined = corroborate(
            automation,
            agent_server,
            RunIdentity(claim.automation_id, claim.run_id, claim.profile_id),
            Policy(
                claim.repo, claim.pr_number, claim.head_sha,
                required_checks,
            ),
            github,
        )
        outcome["execution_observed"] = bool(
            combined["execution"]["execution_observed"]
        )
        outcome["checks_verified"] = bool(combined["github"]["verified"])
        if not outcome["execution_observed"]:
            reasons.append("OpenHands execution evidence did not pass")
        if not outcome["checks_verified"]:
            reasons.append("GitHub exact-head checks evidence did not pass")
        outcome["publication_evidence_consistent"] = (
            outcome["receipt_authenticated"]
            and outcome["github_publication_matches"]
            and outcome["execution_observed"]
            and outcome["checks_verified"]
        )
    except (OSError, ValueError, KeyError, TypeError):
        reasons.append("upstream evidence unavailable, truncated or invalid")
    return outcome
