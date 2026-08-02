#!/usr/bin/env python3
"""Generate and verify Mentat release checksums, SBOM, and provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256(path),
            "size": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def authenticode(path: Path) -> dict[str, Any]:
    if os.name != "nt":
        return {"checked": False, "status": "unsupported_on_non_windows"}
    script = (
        "$s=Get-AuthenticodeSignature -LiteralPath $args[0];"
        "@{Status=[string]$s.Status;StatusMessage=$s.StatusMessage;"
        "Signer=if($s.SignerCertificate){$s.SignerCertificate.Subject}else{$null};"
        "Thumbprint=if($s.SignerCertificate){$s.SignerCertificate.Thumbprint}else{$null}}"
        "|ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", script, str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Authenticode inspection failed")
    return {"checked": True, **json.loads(result.stdout)}


def build_metadata(artifact: Path, payload_root: Path | None) -> dict[str, Any]:
    signature = authenticode(artifact)
    return {
        "schema_version": 1,
        "product": "Mentat",
        "version": "1.0.0-rc.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "artifact": {
            "name": artifact.name,
            "size": artifact.stat().st_size,
            "sha256": sha256(artifact),
            "authenticode": signature,
        },
        "runtime_inventory": file_inventory(payload_root) if payload_root else [],
        "builder": {
            "platform": platform.platform(),
            "python": sys.version,
            "github_repository": os.getenv("GITHUB_REPOSITORY"),
            "github_sha": os.getenv("GITHUB_SHA"),
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "source_date_epoch": os.getenv("SOURCE_DATE_EPOCH"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--payload-root", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--require-signature", action="store_true")
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if not artifact.is_file():
        raise SystemExit(f"release artifact does not exist: {artifact}")
    payload = args.payload_root.resolve() if args.payload_root else None
    if payload and not payload.is_dir():
        raise SystemExit(f"runtime payload does not exist: {payload}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metadata = build_metadata(artifact, payload)
    signature = metadata["artifact"]["authenticode"]
    if args.require_signature and signature.get("Status") != "Valid":
        raise SystemExit(f"Authenticode signature is not valid: {signature}")

    checksum = f"{metadata['artifact']['sha256']}  {artifact.name}\n"
    (args.output_dir / "SHA256SUMS").write_text(checksum, encoding="utf-8")
    provenance = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {
                "name": artifact.name,
                "digest": {"sha256": metadata["artifact"]["sha256"]},
            }
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": (
                    "https://github.com/clementrichardsnapper422-dot/Mentat/"
                    "mentat-windows"
                ),
                "externalParameters": {"version": metadata["version"]},
                "internalParameters": {
                    "source_date_epoch": os.getenv("SOURCE_DATE_EPOCH")
                },
                "resolvedDependencies": [
                    {
                        "uri": (
                            "git+https://github.com/"
                            f"{os.getenv('GITHUB_REPOSITORY', 'unknown')}"
                        ),
                        "digest": {
                            "gitCommit": os.getenv("GITHUB_SHA", "unknown")
                        },
                    }
                ],
            },
            "runDetails": {"builder": {"id": "https://github.com/actions/runner"}},
        },
    }
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:"
        + hashlib.sha256(
            (artifact.name + metadata["artifact"]["sha256"]).encode()
        ).hexdigest()[:32],
        "version": 1,
        "metadata": {
            "timestamp": metadata["generated_at"],
            "component": {
                "type": "application",
                "name": "Mentat",
                "version": metadata["version"],
            },
        },
        "components": [
            {
                "type": "file",
                "name": item["path"],
                "hashes": [{"alg": "SHA-256", "content": item["sha256"]}],
                "properties": [
                    {"name": "mentat:fileSize", "value": str(item["size"])}
                ],
            }
            for item in metadata["runtime_inventory"]
        ],
    }
    outputs = {
        "mentat-release-metadata.json": metadata,
        "mentat-provenance.intoto.json": provenance,
        "mentat-sbom.cdx.json": sbom,
    }
    for name, value in outputs.items():
        (args.output_dir / name).write_text(
            json.dumps(value, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "passed": True,
                "output_dir": str(args.output_dir),
                **metadata["artifact"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
