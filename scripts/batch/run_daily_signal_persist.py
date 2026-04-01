#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))

from app.batch.run_daily_signal_persist import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
