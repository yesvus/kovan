"""Structural, read-only preflight for a proposed disposable Docker worker.

This is NOT a sandbox certification. In particular, Docker inspect cannot
prove network egress policy, mount freshness, or child-agent permissions.
All validation errors fail closed. Only bounded, non-secret verdicts are output.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Mapping


def _positive_integer(value: object) -> bool:
    return type(value) is int and value > 0


def audit_container(inspect: object) -> list[str]:
    """Return policy violations without exposing host paths or secret metadata."""
    if not isinstance(inspect, Mapping):
        return ["invalid container inspection payload"]

    host = inspect.get("HostConfig")
    config = inspect.get("Config")
    mounts = inspect.get("Mounts")
    if not isinstance(host, Mapping) or not isinstance(config, Mapping):
        return ["incomplete Docker host or container configuration"]

    problems: list[str] = []

    if host.get("Privileged") is not False:
        problems.append("privileged mode not explicitly disabled")
    dropped = host.get("CapDrop")
    if not isinstance(dropped, list) or "ALL" not in [
        str(value).upper() for value in dropped
    ]:
        problems.append("all Linux capabilities must be dropped")
    added = host.get("CapAdd")
    if added not in (None, []):
        problems.append("added Linux capabilities are forbidden")
    opts = host.get("SecurityOpt")
    if not isinstance(opts, list) or not any(
        opt in ("no-new-privileges", "no-new-privileges:true")
        for opt in opts
    ):
        problems.append("no-new-privileges is required")

    user = config.get("User")
    uid = user.split(":", 1)[0] if isinstance(user, str) else ""
    if not uid.isascii() or not uid.isdecimal() or int(uid) == 0:
        problems.append("explicit numeric non-root UID required")

    network = host.get("NetworkMode")
    if (
        not isinstance(network, str)
        or not network
        or network in ("host", "bridge", "default")
        or network.startswith("container:")
    ):
        problems.append("network must be none or a dedicated named network")
    if host.get("PidMode") == "host" or host.get("IpcMode") == "host":
        problems.append("shared host process or IPC namespace forbidden")

    if not _positive_integer(host.get("Memory")):
        problems.append("finite memory limit required")
    memory = host.get("Memory")
    memory_swap = host.get("MemorySwap")
    if (
        not _positive_integer(memory_swap)
        or (type(memory) is int and memory_swap > memory)
    ):
        problems.append("memory+swap limit must be finite and not exceed memory")
    if not (
        _positive_integer(host.get("NanoCpus"))
        or _positive_integer(host.get("CpuQuota"))
    ):
        problems.append("finite CPU budget required")
    if not _positive_integer(host.get("PidsLimit")):
        problems.append("finite PID limit required")

    if host.get("Binds") not in (None, []):
        problems.append("host bind configuration is forbidden")
    if not isinstance(mounts, list):
        problems.append("Docker mounts not inspectable")
    else:
        for mount in mounts:
            if not isinstance(mount, Mapping):
                problems.append("invalid Docker mount")
                continue
            if mount.get("Type") == "bind":
                problems.append("host bind mount forbidden, even if read-only")
            if mount.get("Destination") == "/var/run/docker.sock":
                problems.append("Docker socket exposure forbidden")
    if host.get("Devices") not in (None, []) or host.get(
        "DeviceRequests"
    ) not in (None, []):
        problems.append("host device access forbidden")
    return problems


def inspect_docker_container(name: str) -> object:
    """Read exactly one container with no shell or mutation."""
    result = subprocess.run(
        ["docker", "inspect", "--type", "container", name],
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    objects = json.loads(result.stdout)
    if not isinstance(objects, list) or len(objects) != 1:
        raise ValueError("expected exactly one Docker container")
    return objects[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    args = parser.parse_args(argv)

    try:
        problems = audit_container(inspect_docker_container(args.container))
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ):
        problems = ["Docker inspection unavailable or invalid"]

    print(json.dumps({
        "structural_preflight_passed": not problems,
        "problems": problems,
    }, indent=2))
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())
