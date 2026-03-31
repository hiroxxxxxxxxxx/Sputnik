#!/usr/bin/env python3
"""
target_futures(base) を DB に、エンジン（NQ / GC キー）単位で設定する。

数値は **MNQ/MGC 相当枚数**（1 枚のミニ先物 = 10 枚相当）。

用法:
  PYTHONPATH=src python scripts/set_target_futures.py NQ --base 10
  PYTHONPATH=src python scripts/set_target_futures.py MNQ --base 10
  PYTHONPATH=src python scripts/set_target_futures.py MGC --base 8 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_scripts = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))


def _engine_arg(s: str) -> str:
    u = str(s).strip().upper()
    u = {"MNQ": "NQ", "MGC": "GC"}.get(u, u)
    if u not in ("NQ", "GC"):
        raise argparse.ArgumentTypeError("must be NQ, GC, MNQ, or MGC")
    return u


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Set target_futures per engine key NQ/GC (Main/Attitude/Booster); amounts in MNQ/MGC equivalent lots"
    )
    p.add_argument(
        "engine",
        type=_engine_arg,
        help="NQ or GC (MNQ/MGC も可)",
    )
    p.add_argument(
        "--base",
        type=float,
        required=True,
        help="Base target (MNQ/MGC equivalent)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print values without DB update",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    from avionics.data.futures_micro_equiv import engine_symbol_to_micro_notional_label
    from store.db import get_connection
    from store.state import read_target_futures
    from store.target_futures import set_target_futures, validate_target_futures_input

    try:
        if args.dry_run:
            values = validate_target_futures_input(base=args.base)
            ml = engine_symbol_to_micro_notional_label(args.engine)
            print(
                f"[dry-run] {ml} 相当 target_futures "
                f"base={values['base']:.0f}"
            )
            return 0

        conn = get_connection()
        try:
            set_target_futures(
                conn,
                args.engine,
                base=args.base,
            )
            current = read_target_futures(conn)
            lines = ["updated target_futures (MNQ/MGC 相当枚数):"]
            for sym in ("NQ", "GC"):
                ml = engine_symbol_to_micro_notional_label(sym)
                lines.append(
                    f"  {ml}: base={float(current[sym]):.0f}"
                )
            print("\n".join(lines))
            return 0
        finally:
            conn.close()
    except Exception as e:
        print(f"failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
