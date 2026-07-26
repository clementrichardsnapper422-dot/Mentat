import unittest
from pathlib import Path

from gate1_owner_acceptance import GateFailure, validate_container_inspect


def valid_inspect() -> dict:
    return {
        "Id": "a" * 64,
        "Config": {"User": "1000:1000", "Env": ["PATH=/usr/bin"]},
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
        },
        "Mounts": [
            {
                "Source": str(Path("/tmp/gate-workspace").resolve()),
                "Destination": "/workspace",
                "RW": True,
            }
        ],
    }


class ContainerPolicyTests(unittest.TestCase):
    def test_accepts_required_boundary(self):
        result = validate_container_inspect(valid_inspect(), Path("/tmp/gate-workspace"))
        self.assertEqual(result["network_mode"], "none")
        self.assertFalse(result["docker_socket_mounted"])

    def test_rejects_credential_environment(self):
        inspect = valid_inspect()
        inspect["Config"]["Env"].append("VAST_API_KEY=secret")
        with self.assertRaisesRegex(GateFailure, "forbidden credentials"):
            validate_container_inspect(inspect, Path("/tmp/gate-workspace"))

    def test_rejects_docker_socket(self):
        inspect = valid_inspect()
        inspect["Mounts"].append(
            {"Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock", "RW": True}
        )
        with self.assertRaisesRegex(GateFailure, "Docker socket"):
            validate_container_inspect(inspect, Path("/tmp/gate-workspace"))

    def test_rejects_unexpected_writable_mount(self):
        inspect = valid_inspect()
        inspect["Mounts"].append({"Source": "/host", "Destination": "/host", "RW": True})
        with self.assertRaisesRegex(GateFailure, "unexpected writable"):
            validate_container_inspect(inspect, Path("/tmp/gate-workspace"))


if __name__ == "__main__":
    unittest.main()
