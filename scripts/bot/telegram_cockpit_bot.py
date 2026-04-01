#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
_scripts = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from app.telegram.bot import (
    COCKPIT_BOT_COMMANDS_MESSAGE,
    _parse_settarget_base_arg,
    _target_admin_user_ids_from_environ,
    main,
)

if __name__ == "__main__":
    sys.exit(main())
