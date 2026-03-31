"""
Cockpit と Engine を同一の symbols で組み立てる単一ポイント。

FC と Engine の symbol リストの一致を保証する。run_cockpit_with_ib や
Cockpit を pulse で動かすエントリでは build_cockpit_stack を呼び、
pulse には DataSource・as_of・symbols を渡して fc.refresh を実行する。
定義書「4. 修正 Phase」Phase 5 参照。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from avionics import build_flight_controller, FlightController
from avionics.data.signals import AltitudeRegime
from engines.engine import Engine
from engines.factory import (
    _default_blueprints,
    build_gc_engine,
    build_nq_engine,
)


def build_cockpit_stack(
    symbols: list[str],
    *,
    altitude: AltitudeRegime,
    s_baseline_by_symbol: Optional[Dict[str, float]] = None,
    blueprints: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[FlightController, List[Engine]]:
    """
    同一の symbols で FlightController と Engine リストを組み立てる。

    :param symbols: 銘柄リスト（例: ["NQ", "GC"]）。FC の因子と Engine の構成がこの順で一致する。
    :param blueprints: 各 Engine 用の設計図。未指定時は _default_blueprints()。
    :param config: 各 Engine 用の銘柄共通設定（base_unit, boost_ratio 等）。未指定時は {"base_unit": 1.0, "boost_ratio": 1.0}。
    :return: (FlightController, list[Engine])。engines の順は symbols の順に対応する。
    """
    bp = blueprints if blueprints is not None else _default_blueprints()
    cfg = config if config is not None else {"base_unit": 1.0, "boost_ratio": 1.0}
    fc = build_flight_controller(
        symbols,
        altitude=altitude,
        s_baseline_by_symbol=s_baseline_by_symbol,
    )
    engines: List[Engine] = []
    for sym in symbols:
        if sym == "NQ":
            engines.append(build_nq_engine(blueprints=bp, config=cfg))
        elif sym == "GC":
            engines.append(build_gc_engine(blueprints=bp, config=cfg))
        # 未対応の symbol はスキップ（FC には因子が空で登録されている）
    return fc, engines
