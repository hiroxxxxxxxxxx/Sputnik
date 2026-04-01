"""telegram_cockpit_bot の target 関連ヘルパ。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent.parent
_scripts_bot = _root / "scripts" / "bot"
if str(_scripts_bot) not in sys.path:
    sys.path.insert(0, str(_scripts_bot))

from telegram_cockpit_bot import (  # noqa: E402
    COCKPIT_BOT_COMMANDS_MESSAGE,
    _parse_settarget_base_arg,
    _target_admin_user_ids_from_environ,
)
from reports.format_health_report import format_health_report  # noqa: E402


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


def test_parse_settarget_base_arg() -> None:
    assert _parse_settarget_base_arg("80") == 80.0


def test_parse_settarget_base_arg_bad_float_raises() -> None:
    with pytest.raises(ValueError, match="base"):
        _parse_settarget_base_arg("x")


def test_commands_message_includes_position() -> None:
    assert "/position" in COCKPIT_BOT_COMMANDS_MESSAGE
    assert "/settarget" in COCKPIT_BOT_COMMANDS_MESSAGE
    assert "/health" in COCKPIT_BOT_COMMANDS_MESSAGE


def test_format_health_report_ok() -> None:
    text = format_health_report(
        {
            "ib_connected": True,
            "historical_nq_ok": True,
            "historical_nq_bars": 3,
            "whatif_mnq_ok": True,
            "whatif_mnq_account": "U123",
            "whatif_mnq_warning": "none",
            "whatif_mnq_contract": "symbol='MNQ'",
            "whatif_stock_ok": True,
            "whatif_stock_margin_path": "initMarginChange",
            "overall": "OK",
        }
    )
    assert "IB socket: OK" in text
    assert "Historical NQ: OK (bars=3" in text
    assert "whatIf MNQ: OK" in text
    assert "MNQ contract: symbol='MNQ'" in text
    assert "whatIf AAPL: OK" in text
    assert "account=U123" in text
    assert "Overall: OK" in text
