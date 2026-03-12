"""
データ遅延など、スケジュール・取得タイミング用の設定読込。

config/schedule.toml を読み、因子しきい値（factors.toml）とは分離する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


def _default_config_path() -> Path:
    base = Path(__file__).resolve().parent.parent  # src
    return base / "config" / "schedule.toml"


def load_schedule_config(path: str | Path | None = None) -> Dict[str, Any]:
    """
    config/schedule.toml を読み、設定辞書を返す。

    :param path: 設定ファイルパス。None のときは src/config/schedule.toml を探す。
    :return: 設定辞書（将来のキー用に予約）
    """
    if path is None:
        path = _default_config_path()
    path = Path(path)
    if not path.is_file():
        return {}
    with open(path, "rb") as f:
        return dict(tomllib.load(f))
