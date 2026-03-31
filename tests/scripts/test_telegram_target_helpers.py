"""telegram_cockpit_bot の target 関連ヘルパ。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent.parent
_scripts = _root / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from telegram_cockpit_bot import (  # noqa: E402
    _parse_settarget_float_args,
    _target_admin_user_ids_from_environ,
)


def test_target_admin_user_ids_from_environ_parses_commas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_TARGET_ADMIN_USER_IDS", " 1001 , 1002 ")
    assert _target_admin_user_ids_from_environ() == frozenset({1001, 1002})


def test_target_admin_user_ids_empty_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_TARGET_ADMIN_USER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert _target_admin_user_ids_from_environ() == frozenset()


def test_target_admin_user_ids_includes_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_TARGET_ADMIN_USER_IDS", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "424242")
    assert _target_admin_user_ids_from_environ() == frozenset({424242})


def test_target_admin_user_ids_merges_admin_and_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_TARGET_ADMIN_USER_IDS", "100")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "200")
    assert _target_admin_user_ids_from_environ() == frozenset({100, 200})


def test_parse_settarget_float_args_three_numbers() -> None:
    m, a, b = _parse_settarget_float_args(["80", "20", "0"])
    assert m == 80.0 and a == 20.0 and b == 0.0


def test_parse_settarget_float_args_wrong_count_raises() -> None:
    with pytest.raises(ValueError, match="3 数"):
        _parse_settarget_float_args(["1", "2"])
    with pytest.raises(ValueError, match="3 数"):
        _parse_settarget_float_args([])


def test_parse_settarget_float_args_bad_float_raises() -> None:
    with pytest.raises(ValueError, match="位置 1"):
        _parse_settarget_float_args(["x", "1", "2"])
