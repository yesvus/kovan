"""Small OpenHands Automation adapter: observe upstream execution, never merge.

No scheduler, worker runtime, credentials brokerage or automatic PR writeback.
An upstream run and a GitHub check report are independent observations: they
do NOT prove that a worker authored the checked commit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from kovan.pr_evidence import GitHubAPI, Policy, verify


MAX_RESPONSE_BYTES = 1_000_000
TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"})
ACTIVE_STATUSES = frozenset({"PENDING", "RUNNING"})
SAFE_STATUSES = TERMINAL_STATUSES | ACTIVE_STATUSES


def _uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _api_base(value: str) -> str:
    """Only loopback HTTP or TLS endpoints; refuse accidental key exposure."""
    url = urllib.parse.urlsplit(value)
    if (
        url.username or url.password or url.path not in ("", "/")
        or url.query or url.fragment or url.port is None
    ):
        raise ValueError("OpenHands base URL must be a plain host and port")
    if url.scheme == "http":
        if url.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("remote OpenHands API requires HTTPS")
    elif url.scheme != "https" or not url.hostname:
        raise ValueError("invalid OpenHands API scheme")
    return value.rstrip("/")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Reader(Protocol):
    def get(self, path: str) -> Any: ...


class OpenHandsHTTP:
    """Authenticated OpenHands Canvas/Automation transport.

    Key stays in the caller process; API reads and dispatch have no token
    argument and no logging. No redirects, to avoid forwarding session keys.
    """

    def __init__(self, base_url: str, key: str):
        self.base_url = _api_base(base_url)
        if not isinstance(key, str) or not key.strip():
            raise ValueError("missing scoped OpenHands API key")
        self._key = key
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _request(self, method: str, path: str) -> Any:
        if (
            not path.startswith("/api/")
            or "://" in path or ".." in path
            or not re.fullmatch(r"[/A-Za-z0-9?&=_-]+", path)
        ):
            raise ValueError("unexpected API path")
        request = urllib.request.Request(
            self.base_url + path,
            method=method,
            data=b"" if method == "POST" else None,
            headers={
                "X-Session-API-Key": self._key,
                "Accept": "application/json",
            },
        )
        with self._opener.open(request, timeout=10) as stream:
            raw = stream.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("OpenHands response exceeded size limit")
        return json.loads(raw)

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str) -> Any:
        return self._request("POST", path)


@dataclass(frozen=True)
class RunIdentity:
    automation_id: str
    run_id: str
    agent_profile_id: str

    def validate(self) -> None:
        if not all(_uuid(v) for v in (
            self.automation_id, self.run_id, self.agent_profile_id
        )):
            raise ValueError("canonical full UUIDs required for execution identity")


def _run_page(api: Reader, aid: str) -> dict:
    response = api.get(f"/api/automation/v1/{aid}/runs?limit=100&offset=0")
    if (
        not isinstance(response, dict)
        or not isinstance(response.get("runs"), list)
        or type(response.get("total")) is not int
        or response["total"] < len(response["runs"])
        or len(response["runs"]) > 100
    ):
        raise ValueError("invalid upstream run-list response")
    return response


def observe_run(
    automation_api: Reader, agent_api: Reader, identity: RunIdentity
) -> dict[str, object]:
    """Correlate a manual Automation run to its Agent Server conversation.

    A completed run without a completed conversation + matching launched
    profile is *not* sufficient evidence. Fail closed on truncated history.
    """
    identity.validate()
    result: dict[str, object] = {
        "execution_observed": False,
        "automation_id": identity.automation_id,
        "run_id": identity.run_id,
        "expected_profile_id": identity.agent_profile_id,
        "conversation_id": None,
        "status": "unknown",
        "reasons": [],
    }
    reasons: list[str] = result["reasons"]  # type: ignore[assignment]
    aid = identity.automation_id
    automation = automation_api.get(f"/api/automation/v1/{aid}")
    if (
        not isinstance(automation, dict)
        or automation.get("id") != aid
        or automation.get("agent_profile_id") != identity.agent_profile_id
    ):
        reasons.append("automation identity/profile does not match")
        return result

    page = _run_page(automation_api, aid)
    matching = [
        r for r in page["runs"]
        if isinstance(r, dict) and r.get("id") == identity.run_id
    ]
    if len(matching) != 1:
        reasons.append("run not present or ambiguous in bounded upstream run history")
        return result
    run = matching[0]
    status = run.get("status")
    result["status"] = status if status in SAFE_STATUSES else "unknown"
    if run.get("automation_id") != aid:
        reasons.append("run is not correlated to the expected automation")
    if run.get("trigger_source") != "manual":
        reasons.append("run was not manually dispatched")
    runtime = run.get("resolved_runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("agent_profile_id") != identity.agent_profile_id
    ):
        reasons.append("run did not resolve to the pinned agent profile")
    if status != "COMPLETED":
        reasons.append("upstream run did not complete successfully")
    if run.get("error_detail") not in (None, ""):
        reasons.append("upstream reported an execution error")
    if not isinstance(run.get("completed_at"), str) or not run["completed_at"]:
        reasons.append("no run completion timestamp")

    cid = run.get("conversation_id")
    if not _uuid(cid):
        reasons.append("run has no correlated Agent Server conversation")
    else:
        result["conversation_id"] = cid

    if reasons:
        return result

    conversation = agent_api.get(f"/api/conversations/{cid}")
    if (
        not isinstance(conversation, dict)
        or conversation.get("id") != cid
        or conversation.get("execution_status") != "finished"
    ):
        reasons.append("Agent Server conversation did not finish")
        return result
    profile = conversation.get("launched_agent_profile")
    if (
        not isinstance(profile, dict)
        or profile.get("agent_profile_id") != identity.agent_profile_id
    ):
        reasons.append("Agent Server conversation used a different profile")
        return result
    final = agent_api.get(f"/api/conversations/{cid}/agent_final_response")
    if (
        not isinstance(final, dict)
        or not isinstance(final.get("response"), str)
        or not final["response"].strip()
    ):
        reasons.append("no final agent response recorded")
        return result

    # Never return untrusted agent text, command logs or secrets.
    result["execution_observed"] = True
    return result


def dispatch_once(
    automation_api: OpenHandsHTTP, automation_id: str,
    expected_profile_id: str, *, operator_authorized: bool = False,
) -> dict[str, str]:
    """Opt-in one-shot upstream dispatch (library API, deliberately no CLI).

    The caller MUST independently enforce sandbox/credential/egress admission
    and cross-controller concurrency/idempotency. The boolean is not an
    authorization control. This adapter cannot authorize arbitrary work.
    """
    if not operator_authorized:
        raise ValueError("operator opt-in required; not a backend authorization")
    if not _uuid(automation_id) or not _uuid(expected_profile_id):
        raise ValueError("canonical UUIDs required")
    auto = automation_api.get(f"/api/automation/v1/{automation_id}")
    if (
        not isinstance(auto, dict)
        or auto.get("id") != automation_id
        or auto.get("agent_profile_id") != expected_profile_id
        or auto.get("state") != "INACTIVE"
        or auto.get("enabled") is not False
    ):
        raise ValueError("existing inactive automation/profile mismatch")
    page = _run_page(automation_api, automation_id)
    if page["total"] != len(page["runs"]):
        raise ValueError("run history is not exhaustive; cannot check active runs")
    if any(
        not isinstance(r, dict) or r.get("status") in ACTIVE_STATUSES
        or r.get("status") not in TERMINAL_STATUSES
        for r in page["runs"]
    ):
        raise ValueError("unknown or active run exists")
    dispatch = automation_api.post(
        f"/api/automation/v1/{automation_id}/dispatch"
    )
    if (
        not isinstance(dispatch, dict)
        or dispatch.get("automation_id") != automation_id
        or not _uuid(dispatch.get("id"))
        or dispatch.get("status") != "PENDING"
    ):
        raise ValueError("unverified dispatch receipt (run may have been created)")
    return {
        "automation_id": automation_id,
        "run_id": dispatch["id"],
        "status": dispatch["status"],
    }


def corroborate(
    automation_api: Reader, agent_api: Reader,
    identity: RunIdentity, pr_policy: Policy, github_api: Reader,
) -> dict[str, object]:
    """Collect *independent* execution and PR checks, never a merge grant."""
    execution = observe_run(automation_api, agent_api, identity)
    checks = verify(pr_policy, github_api.get)
    return {
        "execution": execution,
        "github": checks,
        "both_observations_passed": (
            execution["execution_observed"] is True and checks["verified"] is True
        ),
        "delivery_authorized": False,
        "causal_link_proven": False,
    }


class _GitHubReadAdapter:
    def __init__(self, token: str | None):
        self._client = GitHubAPI(token)

    def get(self, path: str) -> object:
        return self._client(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--automation-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--automation-url", default="http://127.0.0.1:18001")
    parser.add_argument("--agent-url", default="http://127.0.0.1:18000")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--require-check", action="append", required=True)
    args = parser.parse_args(argv)
    try:
        key = os.environ.get("KOVAN_OPENHANDS_API_KEY", "")
        result = corroborate(
            OpenHandsHTTP(args.automation_url, key),
            OpenHandsHTTP(args.agent_url, key),
            RunIdentity(args.automation_id, args.run_id, args.profile_id),
            Policy(
                args.repo, args.pr, args.expected_sha,
                tuple(args.require_check),
            ),
            _GitHubReadAdapter(os.environ.get("GITHUB_TOKEN")),
        )
    except (OSError, ValueError, TimeoutError):
        result = {
            "both_observations_passed": False,
            "delivery_authorized": False,
            "causal_link_proven": False,
            "reasons": ["upstream identity or API evidence unavailable"],
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["both_observations_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
