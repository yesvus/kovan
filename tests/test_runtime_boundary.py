"""Credential-free regression tests for Docker worker admission checks."""

import contextlib
import io
import json
import subprocess
import unittest
from unittest.mock import patch

from kovan.runtime_boundary import audit_container, main


def baseline():
    return {
        "HostConfig": {
            "Privileged": False,
            "CapDrop": ["ALL"],
            "CapAdd": None,
            "SecurityOpt": ["no-new-privileges:true"],
            "NetworkMode": "kovan-disposable",
            "PidMode": "",
            "IpcMode": "",
            "Memory": 4 * 1024**3,
            "MemorySwap": 4 * 1024**3,
            "NanoCpus": 1_000_000_000,
            "CpuQuota": 0,
            "PidsLimit": 256,
            "Binds": None,
            "Devices": None,
            "DeviceRequests": None,
        },
        "Config": {"User": "10001:10001"},
        "Mounts": [{"Type": "volume", "Destination": "/work"}],
    }


class DockerBoundaryTest(unittest.TestCase):
    def test_structurally_bounded_container(self):
        self.assertEqual(audit_container(baseline()), [])

    def test_missing_inspection_fails_closed(self):
        self.assertTrue(audit_container(None))
        self.assertTrue(audit_container({"HostConfig": {}}))

    def test_read_only_bind_is_still_forbidden(self):
        obj = baseline()
        obj["Mounts"] = [{"Type": "bind", "RW": False, "Destination": "/work"}]
        self.assertIn("host bind mount forbidden, even if read-only",
                      audit_container(obj))

    def test_socket_and_devices_block(self):
        obj = baseline()
        obj["Mounts"].append({
            "Type": "volume", "Destination": "/var/run/docker.sock"
        })
        obj["HostConfig"]["DeviceRequests"] = [{"Driver": "nvidia"}]
        self.assertIn("Docker socket exposure forbidden", audit_container(obj))
        self.assertIn("host device access forbidden", audit_container(obj))

    def test_privileges_and_root_block(self):
        obj = baseline()
        obj["Config"]["User"] = "root"
        obj["HostConfig"]["Privileged"] = True
        obj["HostConfig"]["CapAdd"] = ["SYS_ADMIN"]
        issues = audit_container(obj)
        self.assertIn("explicit numeric non-root UID required", issues)
        self.assertIn("privileged mode not explicitly disabled", issues)
        self.assertIn("added Linux capabilities are forbidden", issues)

    def test_unicode_uid_fails_closed(self):
        obj = baseline()
        obj["Config"]["User"] = "²"
        self.assertIn("explicit numeric non-root UID required", audit_container(obj))

    def test_missing_cap_drop_and_no_new_privileges(self):
        obj = baseline()
        obj["HostConfig"]["CapDrop"] = []
        obj["HostConfig"]["SecurityOpt"] = ["no-new-privileges:false"]
        issues = audit_container(obj)
        self.assertIn("all Linux capabilities must be dropped", issues)
        self.assertIn("no-new-privileges is required", issues)

    def test_network_and_namespaces_block(self):
        for mode in ("host", "bridge", "container:other", "", None, "default"):
            with self.subTest(mode=mode):
                obj = baseline()
                obj["HostConfig"]["NetworkMode"] = mode
                self.assertTrue(audit_container(obj))
        obj = baseline()
        obj["HostConfig"]["NetworkMode"] = "none"
        self.assertEqual(audit_container(obj), [])
        obj["HostConfig"]["PidMode"] = "host"
        self.assertIn("shared host process or IPC namespace forbidden",
                      audit_container(obj))

    def test_memory_cpu_pid_and_swap_must_be_bounded(self):
        for key, invalid in (
            ("Memory", 0),
            ("MemorySwap", -1),
            ("NanoCpus", 0),
            ("PidsLimit", 0),
        ):
            with self.subTest(key=key):
                obj = baseline()
                obj["HostConfig"][key] = invalid
                self.assertTrue(audit_container(obj))
        obj = baseline()
        obj["HostConfig"]["MemorySwap"] = 8 * 1024**3
        self.assertIn("memory+swap limit must be finite and not exceed memory",
                      audit_container(obj))

    def test_cli_reads_only_docker_inspect(self):
        with patch("kovan.runtime_boundary.inspect_docker_container",
                   return_value=baseline()), contextlib.redirect_stdout(
                       io.StringIO()
                   ) as buffer:
            self.assertEqual(main(["--container", "test-only"]), 0)
            self.assertTrue(json.loads(buffer.getvalue())[
                "structural_preflight_passed"
            ])

    def test_cli_reports_inspection_failure(self):
        with patch("kovan.runtime_boundary.inspect_docker_container",
                   side_effect=subprocess.CalledProcessError(1, ["docker"])), \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            self.assertEqual(main(["--container", "missing"]), 2)
            self.assertFalse(json.loads(buffer.getvalue())[
                "structural_preflight_passed"
            ])


if __name__ == "__main__":
    unittest.main()
