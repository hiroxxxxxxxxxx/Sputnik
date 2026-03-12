"""config/schedule.toml の読込テスト。"""
from __future__ import annotations

from avionics.schedule_config import load_schedule_config


def test_load_schedule_config_returns_dict() -> None:
    """load_schedule_config は辞書を返す（ファイルが無ければ {}）。"""
    config = load_schedule_config()
    assert isinstance(config, dict)
