"""
target_futures 設定の共通ユースケース。

値は **MNQ/MGC 相当枚数**（表記はマイクロ建玉。DB の engine キーは NQ/GC）。
CLI や他スクリプトから再利用するため、入力検証と一括更新をここに寄せる。
"""
from __future__ import annotations

import sqlite3
from typing import Dict

from .db import get_connection
from .state import read_target_futures, upsert_target_futures

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


def validate_target_futures_input(*, base: float | None) -> Dict[str, float]:
    """target_futures(base) 入力を検証する。"""
    if base is None:
        raise ValueError("target_futures base is required")
    return {"base": float(base)}


def set_target_futures(
    conn: sqlite3.Connection,
    engine_symbol: str,
    *,
    base: float | None,
) -> Dict[str, float]:
    """指定エンジン銘柄（NQ / GC）の target_futures(base) を更新する。"""
    es = normalize_engine_symbol(engine_symbol)
    values = validate_target_futures_input(base=base)
    upsert_target_futures(conn, es, values["base"])
    return values


def set_target_futures_in_db(
    engine_symbol: str,
    *,
    base: float | None,
) -> Dict[str, float]:
    """DB 接続を内部で管理して target_futures(base) を更新し、最新値を返す。"""
    conn = get_connection()
    try:
        set_target_futures(conn, engine_symbol, base=base)
        return read_target_futures(conn)
    finally:
        conn.close()
