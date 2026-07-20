#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "model-broker"
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

from mentat_broker.safety import install_safety_hooks  # noqa: E402
from mentat_broker.server import main  # noqa: E402


if __name__ == "__main__":
    install_safety_hooks()
    raise SystemExit(main())
