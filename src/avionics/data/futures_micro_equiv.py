"""
CME ミニ/マイクロ先物の換算定数とマイクロ相当の集計。

目標・実ポジ・制御の future レッグは **マイクロ相当枚数（MNQ / MGC を 1 単位）** で統一する。
1 枚のミニ（NQ / GC）= 10 枚のマイクロ（MNQ / MGC）。別取引所・別比率は扱わない。
"""

from __future__ import annotations

from typing import Mapping

# 先物レッグのみ。オプション倍率は別契約のためここでは扱わない。
MICRO_CONTRACTS_PER_MINI_FUTURES = 10

# エンジン／DB の symbol（NQ, GC）を、マイクロ換算の表記（MNQ, MGC）へ対応させる。
_ENGINE_SYMBOL_TO_MICRO_NOTIONAL_LABEL: dict[str, str] = {"NQ": "MNQ", "GC": "MGC"}


def engine_symbol_to_micro_notional_label(engine_symbol: str) -> str:
    """NQ→MNQ、GC→MGC。DB の engine symbol のみ受け付ける（表記用）。"""
    s = str(engine_symbol).strip().upper()
    if s not in _ENGINE_SYMBOL_TO_MICRO_NOTIONAL_LABEL:
        raise ValueError(f"engine symbol must be NQ or GC, got {engine_symbol!r}")
    return _ENGINE_SYMBOL_TO_MICRO_NOTIONAL_LABEL[s]


def signed_future_root_qty_to_micro_equivalent(raw_contract_symbol: str, signed_qty: float) -> float:
    """
    1 先物建玉のシンボルと符号付き枚数から、グループ内ネットへのマイクロ相当寄与を返す。
    未対応の先物ルートは ValueError。
    """
    s = raw_contract_symbol.strip().upper()
    if s in ("NQ", "GC"):
        return float(signed_qty) * MICRO_CONTRACTS_PER_MINI_FUTURES
    if s in ("MNQ", "MGC"):
        return float(signed_qty) * 1.0
    raise ValueError(
        f"unsupported futures root for micro equivalent: {raw_contract_symbol!r} "
        f"(expected NQ, MNQ, GC, or MGC)"
    )


def micro_equivalent_net_nq_family(futures: Mapping[str, float]) -> float:
    """
    fetch_position_detail の futures 辞書（nq_*, mnq_*）から、
    買い=+ / 売り=− のネットをマイクロ相当枚数で返す。
    """
    nq_b = float(futures.get("nq_buy", 0.0))
    nq_s = float(futures.get("nq_sell", 0.0))
    mnq_b = float(futures.get("mnq_buy", 0.0))
    mnq_s = float(futures.get("mnq_sell", 0.0))
    return MICRO_CONTRACTS_PER_MINI_FUTURES * (nq_b - nq_s) + (mnq_b - mnq_s)


def micro_equivalent_net_gc_family(futures: Mapping[str, float]) -> float:
    """GC 群（gc_*, mgc_*）のネットをマイクロ相当枚数で返す。"""
    gc_b = float(futures.get("gc_buy", 0.0))
    gc_s = float(futures.get("gc_sell", 0.0))
    mgc_b = float(futures.get("mgc_buy", 0.0))
    mgc_s = float(futures.get("mgc_sell", 0.0))
    return MICRO_CONTRACTS_PER_MINI_FUTURES * (gc_b - gc_s) + (mgc_b - mgc_s)
