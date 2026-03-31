#!/usr/bin/env python3
"""
target_futures（Main/Attitude/Booster）を DB に、エンジン（NQ / GC キー）単位で設定する。

数値は **MNQ/MGC 相当枚数**（1 枚のミニ先物 = 10 枚相当）。表記はマイクロ建玉に合わせる。

用法:
  PYTHONPATH=src python scripts/set_target_futures.py NQ --main 80 --attitude 20 --booster 0
  PYTHONPATH=src python scripts/set_target_futures.py MNQ --main 80 --attitude 20 --booster 0
  PYTHONPATH=src python scripts/set_target_futures.py MGC --main 50 --attitude 10 --booster 0 --dry-run
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
        "--main",
        type=float,
        required=True,
        help="Main layer target (MNQ/MGC equivalent)",
    )
    p.add_argument(
        "--attitude",
        type=float,
        required=True,
        help="Attitude layer target (MNQ/MGC equivalent)",
    )
    p.add_argument(
        "--booster",
        type=float,
        required=True,
        help="Booster layer target (MNQ/MGC equivalent)",
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
            values = validate_target_futures_input(
                main=args.main,
                attitude=args.attitude,
                booster=args.booster,
            )
            ml = engine_symbol_to_micro_notional_label(args.engine)
            print(
                f"[dry-run] {ml} 相当 target_futures "
                f"Main={values['Main']:.0f} "
                f"Attitude={values['Attitude']:.0f} "
                f"Booster={values['Booster']:.0f}"
            )
            return 0

        conn = get_connection()
        try:
            set_target_futures(
                conn,
                args.engine,
                main=args.main,
                attitude=args.attitude,
                booster=args.booster,
            )
            current = read_target_futures(conn)
            lines = ["updated target_futures (MNQ/MGC 相当枚数):"]
            for sym in ("NQ", "GC"):
                c = current[sym]
                ml = engine_symbol_to_micro_notional_label(sym)
                lines.append(
                    f"  {ml}: Main={float(c['Main']):.0f} "
                    f"Attitude={float(c['Attitude']):.0f} "
                    f"Booster={float(c['Booster']):.0f}"
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
