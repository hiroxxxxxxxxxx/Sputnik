"""target_futures セッターの関数/CLI テスト。"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

_scripts = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))


@pytest.fixture()
def conn():
    from store.db import get_connection

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    old = os.environ.get("SPUTNIK_DB_PATH")
    os.environ["SPUTNIK_DB_PATH"] = db_path
    c = get_connection()
    yield c
    c.close()
    os.unlink(db_path)
    if old is not None:
        os.environ["SPUTNIK_DB_PATH"] = old
    elif "SPUTNIK_DB_PATH" in os.environ:
        del os.environ["SPUTNIK_DB_PATH"]


def _seed_full_targets(conn: sqlite3.Connection) -> None:
    from store.state import upsert_target_futures

    for sym in ("NQ", "GC"):
        upsert_target_futures(conn, sym, "Main", 1.0)
        upsert_target_futures(conn, sym, "Attitude", 0.0)
        upsert_target_futures(conn, sym, "Booster", 0.0)


def test_set_target_futures_function(conn: sqlite3.Connection) -> None:
    from store.state import read_target_futures
    from store.target_futures import set_target_futures

    _seed_full_targets(conn)
    set_target_futures(conn, "NQ", main=8.0, attitude=2.0, booster=0.0)
    current = read_target_futures(conn)
    assert current["NQ"]["Main"] == 8.0
    assert current["NQ"]["Attitude"] == 2.0
    assert current["NQ"]["Booster"] == 0.0
    assert current["GC"]["Main"] == 1.0


def test_set_target_futures_validate_missing_raises() -> None:
    from store.target_futures import validate_target_futures_input

    with pytest.raises(ValueError):
        validate_target_futures_input(main=8.0, attitude=2.0, booster=None)


def test_normalize_engine_symbol_raises() -> None:
    from store.target_futures import normalize_engine_symbol

    with pytest.raises(ValueError, match="NQ or GC"):
        normalize_engine_symbol("ES")


def test_normalize_engine_symbol_mnq_mgc_alias() -> None:
    from store.target_futures import normalize_engine_symbol

    assert normalize_engine_symbol("mnq") == "NQ"
    assert normalize_engine_symbol("MGC") == "GC"


def test_set_target_futures_cli_dry_run(conn: sqlite3.Connection) -> None:
    from set_target_futures import main
    from store.state import read_target_futures

    _seed_full_targets(conn)
    before = read_target_futures(conn)
    code = main(
        ["NQ", "--main", "9", "--attitude", "3", "--booster", "1", "--dry-run"]
    )
    after = read_target_futures(conn)
    assert code == 0
    assert before == after


def test_set_target_futures_cli_updates(conn: sqlite3.Connection) -> None:
    from set_target_futures import main
    from store.state import read_target_futures

    _seed_full_targets(conn)
    code = main(["MNQ", "--main", "9", "--attitude", "3", "--booster", "1"])
    current = read_target_futures(conn)
    assert code == 0
    assert current["NQ"]["Main"] == 9.0
    assert current["NQ"]["Attitude"] == 3.0
    assert current["NQ"]["Booster"] == 1.0
