"""
target_futures 設定の共通ユースケース。

値は **MNQ/MGC 相当枚数**（表記はマイクロ建玉。DB の engine キーは NQ/GC）。
CLI や他スクリプトから再利用するため、入力検証と一括更新をここに寄せる。
"""
from __future__ import annotations

import sqlite3
from typing import Dict

from .state import upsert_target_futures

PART_MAIN = "Main"
PART_ATTITUDE = "Attitude"
PART_BOOSTER = "Booster"

ENGINE_SYMBOLS: tuple[str, ...] = ("NQ", "GC")


def normalize_engine_symbol(symbol: str) -> str:
    """CLI/Telegram 用: NQ/GC に正規化（MNQ/MGC はマイクロ表記の別名として受け付ける）。"""
    s = str(symbol).strip().upper()
    s = {"MNQ": "NQ", "MGC": "GC"}.get(s, s)
    if s not in ENGINE_SYMBOLS:
        raise ValueError(
            f"engine symbol must be NQ or GC (or MNQ/MGC as alias), got {symbol!r}"
        )
    return s


def validate_target_futures_input(
    *,
    main: float | None,
    attitude: float | None,
    booster: float | None,
) -> Dict[str, float]:
    """target_futures 入力を検証し、Part 辞書へ正規化する。"""
    if main is None or attitude is None or booster is None:
        raise ValueError(
            "All target_futures values are required: main, attitude, booster"
        )
    return {
        PART_MAIN: float(main),
        PART_ATTITUDE: float(attitude),
        PART_BOOSTER: float(booster),
    }


def set_target_futures(
    conn: sqlite3.Connection,
    engine_symbol: str,
    *,
    main: float | None,
    attitude: float | None,
    booster: float | None,
) -> Dict[str, float]:
    """指定エンジン銘柄（NQ / GC）の target_futures を Main/Attitude/Booster で一括更新する。"""
    es = normalize_engine_symbol(engine_symbol)
    values = validate_target_futures_input(
        main=main,
        attitude=attitude,
        booster=booster,
    )
    upsert_target_futures(conn, es, PART_MAIN, values[PART_MAIN])
    upsert_target_futures(conn, es, PART_ATTITUDE, values[PART_ATTITUDE])
    upsert_target_futures(conn, es, PART_BOOSTER, values[PART_BOOSTER])
    return values
