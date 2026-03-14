"""
因子しきい値の設定ファイル読込。ロジックと戦略パラメータの分離（0-1-Ⅵ）。

config/factors.toml を読み、銘柄別・因子別のしきい値を返す。
設定がない（ファイル未読込・該当キーなし）場合は例外を上げる。フォールバックは持たない。
EngineFactory または Cockpit の組み立て時に利用する。

設定の探し方（path=None 時）:
  1) 環境変数 SPUTNIK_CONFIG_DIR が設定されていればそのディレクトリ内の factors.toml
  2) プロジェクトルートの config/factors.toml（推奨）
  3) プロジェクトルートの src/config/factors.toml（旧位置・後方互換）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


class FactorsConfigError(ValueError):
    """設定ファイル未読込または該当キーがないときに raise する。"""
    pass


def get_p_thresholds(config: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """
    設定から P 因子しきい値を返す。該当キーがなければ FactorsConfigError を上げる。

    :param config: load_factors_config() の戻り値
    :param symbol: "NQ" または "GC"
    """
    if not config or symbol not in config:
        raise FactorsConfigError(
            f"factors config missing or no entry for symbol {symbol!r}. "
            f"Provide config/factors.toml with [{symbol}.P]."
        )
    p = config[symbol].get("P")
    if not p:
        raise FactorsConfigError(
            f"factors config missing P thresholds for {symbol!r}. "
            f"Add [{symbol}.P] in config/factors.toml."
        )
    out = dict(p)
    if "confirm_days" not in out:
        raise FactorsConfigError(
            f"factors config [{symbol}.P] must have 'confirm_days'. Add in config/factors.toml."
        )
    return out


def get_v_thresholds(config: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """
    設定から V 因子しきい値（高度別）を返す。該当キーがなければ FactorsConfigError を上げる。

    :param config: load_factors_config() の戻り値
    :param symbol: "NQ" または "GC"
    """
    if not config or symbol not in config:
        raise FactorsConfigError(
            f"factors config missing or no entry for symbol {symbol!r}. "
            f"Provide config/factors.toml with [{symbol}.V.high_mid] and [{symbol}.V.low]."
        )
    v = config[symbol].get("V")
    if not v or "high_mid" not in v or "low" not in v:
        raise FactorsConfigError(
            f"factors config missing V thresholds for {symbol!r}. "
            f"Add [{symbol}.V.high_mid] and [{symbol}.V.low] in config/factors.toml."
        )
    return {k: dict(inner) for k, inner in v.items()}


def get_t_thresholds(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    設定から T 因子しきい値を返す。該当キーがなければ FactorsConfigError を上げる。

    :param config: load_factors_config() の戻り値
    """
    if not config or "T" not in config:
        raise FactorsConfigError(
            "factors config missing [T]. Add [T] in config/factors.toml."
        )
    out = dict(config["T"])
    if "confirm_days" not in out:
        raise FactorsConfigError(
            "factors config [T] must have 'confirm_days'. Add in config/factors.toml."
        )
    return out


def get_u_thresholds(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    設定から U 因子しきい値を返す。該当キーがなければ FactorsConfigError を上げる。

    :param config: load_factors_config() の戻り値
    """
    if not config or "U" not in config:
        raise FactorsConfigError(
            "factors config missing [U]. Add [U] in config/factors.toml."
        )
    return dict(config["U"])


def get_s_thresholds(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    設定から S 因子しきい値を返す。該当キーがなければ FactorsConfigError を上げる。

    :param config: load_factors_config() の戻り値
    """
    if not config or "S" not in config:
        raise FactorsConfigError(
            "factors config missing [S]. Add [S] in config/factors.toml."
        )
    return dict(config["S"])


def get_c_thresholds(config: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """
    設定から C 因子（Credit Stress：NQ系）しきい値を返す。該当キーがなければ FactorsConfigError を上げる。

    :param config: load_factors_config() の戻り値
    :param symbol: "NQ"（C は NQ 系専用）
    """
    if not config or symbol not in config:
        raise FactorsConfigError(
            f"factors config missing or no entry for symbol {symbol!r}. "
            f"Provide config/factors.toml with [{symbol}.C]."
        )
    c = config[symbol].get("C")
    if not c:
        raise FactorsConfigError(
            f"factors config missing C thresholds for {symbol!r}. "
            f"Add [{symbol}.C] in config/factors.toml."
        )
    out = dict(c)
    if "confirm_days" not in out:
        raise FactorsConfigError(
            f"factors config [{symbol}.C] must have 'confirm_days'. Add in config/factors.toml."
        )
    if "daily_change_C2" not in out:
        raise FactorsConfigError(
            f"factors config [{symbol}.C] must have 'daily_change_C2'. Add in config/factors.toml."
        )
    return out


def get_r_thresholds(config: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """
    設定から R 因子（Real-Rate Stress：GC系）しきい値（高度別）を返す。該当キーがなければ FactorsConfigError を上げる。

    :param config: load_factors_config() の戻り値
    :param symbol: "GC"（R は GC 系専用）
    """
    if not config or symbol not in config:
        raise FactorsConfigError(
            f"factors config missing or no entry for symbol {symbol!r}. "
            f"Provide config/factors.toml with [{symbol}.R]."
        )
    r = config[symbol].get("R")
    if not r:
        raise FactorsConfigError(
            f"factors config missing R thresholds for {symbol!r}. "
            f"Add [{symbol}.R] in config/factors.toml."
        )
    out = dict(r)
    for key in ("drawdown_high_mid_L2", "drawdown_low_L2", "drawdown_high_mid_L0", "drawdown_low_L0", "confirm_days"):
        if key not in out:
            raise FactorsConfigError(
                f"factors config [{symbol}.R] must have '{key}'. Add in config/factors.toml."
            )
    return out


def load_factors_config(path: str | Path | None = None) -> Dict[str, Any]:
    """
    因子しきい値の TOML を読み、銘柄別の辞書を返す。

    :param path: 設定ファイルパス。None のときはプロジェクトルートの config/factors.toml を探す。
    :return: {"NQ": {"P": {...}, "V": {"high_mid": {...}, "low": {...}}}, "GC": {...}}
    :raises FactorsConfigError: ファイルが見つからない、または path がファイルでない場合。
    """
    if path is None:
        # __file__ = .../src/avionics/Instruments/factors_config.py -> project_root = .../Sputnik
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        env_dir = os.environ.get("SPUTNIK_CONFIG_DIR")
        candidates = []
        if env_dir:
            candidates.append(Path(env_dir).resolve() / "factors.toml")
        candidates.extend([
            project_root / "config" / "factors.toml",
            project_root / "src" / "config" / "factors.toml",
        ])
        for candidate in candidates:
            if candidate.is_file():
                path = candidate
                break
        else:
            raise FactorsConfigError(
                "factors config file not found. "
                "Provide config/factors.toml at project root or set SPUTNIK_CONFIG_DIR or pass path= to load_factors_config(path)."
            )

    path = Path(path)
    if not path.is_file():
        raise FactorsConfigError(
            f"factors config path is not a file: {path!s}. "
            "Provide a valid config/factors.toml path."
        )

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return dict(data)
