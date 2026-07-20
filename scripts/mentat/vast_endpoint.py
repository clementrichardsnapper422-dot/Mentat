#!/usr/bin/env python3
from __future__ import annotations

from vast_endpoint_hardening import install
from vast_endpoint_production import main


if __name__ == "__main__":
    install()
    raise SystemExit(main())
