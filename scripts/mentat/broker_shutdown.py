#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, TypeError, ValueError):
        return None


def request_shutdown(port: int, token: str, timeout: float) -> None:
    body = b"{}"
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/admin/shutdown",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "User-Agent": "MentatShutdown/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(4096)
            if response.status not in {200, 202, 204}:
                raise RuntimeError(f"broker shutdown returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"broker shutdown returned HTTP {exc.code}: {details}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Gracefully stop the local Mentat broker")
    parser.add_argument("--port", type=int, default=18890)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--pid-file", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()

    pid = read_pid(args.pid_file)
    token = ""
    try:
        token = args.token_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        pass

    if not pid or not process_exists(pid):
        args.pid_file.unlink(missing_ok=True)
        args.token_file.unlink(missing_ok=True)
        print(json.dumps({"stopped": True, "already_stopped": True}))
        return 0
    if not token:
        print(json.dumps({"stopped": False, "error": "broker admin token is missing"}))
        return 1

    try:
        request_shutdown(args.port, token, min(10.0, args.timeout))
    except (RuntimeError, urllib.error.URLError, TimeoutError) as exc:
        if not process_exists(pid):
            args.pid_file.unlink(missing_ok=True)
            args.token_file.unlink(missing_ok=True)
            print(json.dumps({"stopped": True, "already_stopped": True}))
            return 0
        print(json.dumps({"stopped": False, "error": str(exc)}))
        return 1

    deadline = time.monotonic() + max(1.0, args.timeout)
    while time.monotonic() < deadline:
        if not process_exists(pid):
            args.pid_file.unlink(missing_ok=True)
            args.token_file.unlink(missing_ok=True)
            print(json.dumps({"stopped": True, "pid": pid}))
            return 0
        time.sleep(0.25)

    print(json.dumps({"stopped": False, "pid": pid, "error": "shutdown timed out"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
