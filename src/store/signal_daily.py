from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Optional

import sqlite3

from avionics.data.flight_controller_signal import FlightControllerSignal


def upsert_signal_daily(
    conn: sqlite3.Connection,
    *,
    as_of: date,
    signal: FlightControllerSignal,
    created_at: Optional[datetime] = None,
) -> None:
    """
    signal_daily に日次の FlightControllerSignal を upsert する。

    - as_of: 対象日（date）
    - created_at: 省略時は UTC now
    """
    ts = created_at or datetime.now(timezone.utc)
    row = asdict(signal)
    row["as_of"] = as_of.isoformat()
    row["created_at"] = ts.isoformat()

    conn.execute(
        """
        INSERT INTO signal_daily (
            as_of,
            scl, lcl,
            nq_icl, gc_icl,
            nq_p, nq_v, nq_c, nq_r,
            gc_p, gc_v, gc_c, gc_r,
            t, u, s,
            created_at
        ) VALUES (
            :as_of,
            :scl, :lcl,
            :nq_icl, :gc_icl,
            :nq_p, :nq_v, :nq_c, :nq_r,
            :gc_p, :gc_v, :gc_c, :gc_r,
            :t, :u, :s,
            :created_at
        )
        ON CONFLICT(as_of) DO UPDATE SET
            scl = excluded.scl,
            lcl = excluded.lcl,
            nq_icl = excluded.nq_icl,
            gc_icl = excluded.gc_icl,
            nq_p = excluded.nq_p,
            nq_v = excluded.nq_v,
            nq_c = excluded.nq_c,
            nq_r = excluded.nq_r,
            gc_p = excluded.gc_p,
            gc_v = excluded.gc_v,
            gc_c = excluded.gc_c,
            gc_r = excluded.gc_r,
            t = excluded.t,
            u = excluded.u,
            s = excluded.s,
            created_at = excluded.created_at
        """,
        row,
    )
    conn.commit()

