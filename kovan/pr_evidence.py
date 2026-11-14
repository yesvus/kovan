"""Independent, read-only GitHub PR/CI evidence verification.

Check results are advisory evidence, never authorization to merge or deploy.
No GitHub workflow or agent self-report is trusted as a delivery decision.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_APP = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
_MAX_JSON_BYTES = 2_000_000


@dataclass(frozen=True)
class Policy:
    repo: str
    number: int
    expected_sha: str
    required_checks: tuple[str, ...]
    app_slug: str = "github-actions"

    def validate(self) -> None:
        parts = self.repo.split("/")
        if (
            len(parts) != 2
            or any(not _PART.fullmatch(part) or ".." in part for part in parts)
        ):
            raise ValueError("repo must be an owner/repository name")
        if type(self.number) is not int or self.number < 1:
            raise ValueError("PR number must be positive")
        if not _SHA.fullmatch(self.expected_sha):
            raise ValueError("full lowercase 40-character expected HEAD SHA required")
        if (
            not self.required_checks
            or len(set(self.required_checks)) != len(self.required_checks)
            or any(not isinstance(name, str) or not name.strip()
                   or len(name) > 200 for name in self.required_checks)
        ):
            raise ValueError("nonempty distinct required check names are mandatory")
        if not _APP.fullmatch(self.app_slug):
            raise ValueError("valid expected GitHub App slug is required")


def _pr_at_sha(pr: object, policy: Policy) -> bool:
    if not isinstance(pr, dict):
        return False
    head = pr.get("head")
    return (
        pr.get("state") == "open"
        and isinstance(head, dict)
        and head.get("sha") == policy.expected_sha
    )


def verify(
    policy: Policy, fetch_json: Callable[[str], object]
) -> dict[str, object]:
    """Independently fetch PR -> SHA-pinned checks -> PR again.

    A check is accepted only if exactly one latest run matches the required
    check name, authorized GitHub App, full SHA, completed status and success.
    Re-reading the PR closes the common moved-head race in this simple pilot.
    """
    policy.validate()
    base = f"/repos/{policy.repo}"
    pr_path = f"{base}/pulls/{policy.number}"
    check_path = (
        f"{base}/commits/{policy.expected_sha}/check-runs"
        "?per_page=100&filter=latest"
    )
    response: dict[str, object] = {
        "verified": False,
        "repo": policy.repo,
        "pr": policy.number,
        "expected_sha": policy.expected_sha,
        "app_slug": policy.app_slug,
        "checks": {},
        "reasons": [],
    }
    reasons: list[str] = []
    response["reasons"] = reasons

    first = fetch_json(pr_path)
    if not _pr_at_sha(first, policy):
        reasons.append("PR closed, missing, or head SHA differs from expected")
        return response

    checks = fetch_json(check_path)
    if not isinstance(checks, dict):
        reasons.append("check-runs response is malformed")
        return response
    runs = checks.get("check_runs")
    count = checks.get("total_count")
    if (
        not isinstance(runs, list)
        or type(count) is not int
        or count != len(runs)
        or count > 100
    ):
        reasons.append("check-runs response malformed, truncated or not exhaustive")
        return response

    verdicts: dict[str, str] = {}
    for name in policy.required_checks:
        # Reject duplicate names even if a different app supplied one:
        # branch-protection semantics may not match a naive app filter.
        matching = [
            item for item in runs
            if isinstance(item, dict) and item.get("name") == name
        ]
        if len(matching) != 1:
            verdicts[name] = "missing_or_ambiguous"
            reasons.append(f"required check {name!r} is missing or ambiguous")
            continue
        run = matching[0]
        app = run.get("app")
        if not isinstance(app, dict) or app.get("slug") != policy.app_slug:
            verdicts[name] = "unexpected_app"
            reasons.append(f"required check {name!r} came from an unexpected app")
        elif run.get("head_sha") != policy.expected_sha:
            verdicts[name] = "stale_sha"
            reasons.append(f"required check {name!r} does not match pinned SHA")
        elif run.get("status") != "completed" or run.get("conclusion") != "success":
            verdicts[name] = "not_successful"
            reasons.append(f"required check {name!r} is not completed successfully")
        else:
            verdicts[name] = "success"
    response["checks"] = verdicts

    # Re-read even if a check failed; preserve a moved-head finding.
    last = fetch_json(pr_path)
    if not _pr_at_sha(last, policy):
        reasons.append("PR head moved or PR closed during evidence collection")
    response["verified"] = not reasons
    return response


class GitHubAPI:
    """Fixed-host read-only REST transport; public access works token-free."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token

    def __call__(self, path: str) -> object:
        # Paths are constructed from validated policy, never arbitrary URLs.
        request = urllib.request.Request(
            "https://api.github.com" + path,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "kovan-pr-evidence/0.1",
                **(
                    {"Authorization": f"Bearer {self._token}"}
                    if self._token else {}
                ),
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=15) as stream:
            data = stream.read(_MAX_JSON_BYTES + 1)
        if len(data) > _MAX_JSON_BYTES:
            raise ValueError("GitHub API payload exceeded size limit")
        return json.loads(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument(
        "--require-check", action="append", required=True,
        help="Exact required GitHub check run name (repeat for each)",
    )
    parser.add_argument(
        "--app-slug", default="github-actions",
        help="Trusted check publisher; default: github-actions",
    )
    args = parser.parse_args(argv)
    policy = Policy(
        args.repo, args.pr, args.expected_sha,
        tuple(args.require_check), args.app_slug,
    )
    try:
        result = verify(policy, GitHubAPI(os.environ.get("GITHUB_TOKEN")))
    except (OSError, ValueError, TimeoutError):
        result = {
            "verified": False,
            "reasons": ["invalid policy or GitHub API unavailable"],
        }
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
