#!/usr/bin/env python3
"""
Telegram から /cockpit または /status で現在の FlightController 計器内容を返すボット。

コマンド: /start, /ping, /health, /cockpit, /status, /breakdown, /daily, /position, /schedule, /target, /settarget
  /schedule: 取引時間スキャン（夏冬・短縮・休場の事前通知）。毎朝のルーチンや週次で実行推奨。
  /target: target_base_futures を MNQ/MGC 相当で表示（現在高度の有効legs付き）。
  /settarget: 片側だけ更新（mnq|mgc|nq|gc と base 数）。要 TELEGRAM_TARGET_ADMIN_USER_IDS。

用法:
  PYTHONPATH=src python scripts/telegram_cockpit_bot.py
  環境変数: TELEGRAM_TOKEN（必須）, IBKR_HOST, IBKR_PORT（IB 取得時）, TELEGRAM_COCKPIT_SYMBOLS（省略時 NQ,GC）
  target 更新許可: TELEGRAM_TARGET_ADMIN_USER_IDS（推奨）またはプライベート運用で TELEGRAM_CHAT_ID と同一 user_id
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

_root = Path(__file__).resolve().parent.parent
_scripts = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

def _env_host_port_symbols() -> tuple[str, int, list[str], int, float]:
    """env から host, port, symbols, client_id, timeout を読み、レポート取得 API に渡す値として返す。"""
    host = os.environ.get("IBKR_HOST", "127.0.0.1").strip()
    port_str = os.environ.get("IBKR_PORT", "").strip()
    port = int(port_str) if port_str.isdigit() else 4002
    symbols_str = os.environ.get("TELEGRAM_COCKPIT_SYMBOLS", "NQ,GC").strip()
    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()] or ["NQ", "GC"]
    client_id = int(os.environ.get("IBKR_CLIENT_ID", "3"))
    timeout = 75.0  # Gateway 起動直後は約60秒かかることがある
    return host, port, symbols, client_id, timeout


# /start と起動完了通知で同じメッセージを使う
COCKPIT_BOT_COMMANDS_MESSAGE = (
    "Sputnik Cockpit Bot\n"
    "/ping … 接続・設定確認\n"
    "/health … IB 接続段階診断（socket / NQ bars / MGC whatIf）\n"
    "/cockpit または /status … 現在の計器（IB から取得）\n"
    "/daily … Daily Flight Log（市場・資本・各層）\n"
    "/position … ポジション明細 + target 差分\n"
    "/breakdown … 各因子の計算内訳（Layer 2 シグナル）\n"
    "/schedule … 取引時間スキャン（夏冬・短縮・休場の事前通知）\n"
    "/target … target_base_futures（MNQ/MGC 相当 + 現在高度の有効legs）\n"
    "/settarget <mnq|mgc|nq|gc> <base> … 該当側のみ更新（要管理者 user_id）"
)


async def start_command(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /start で利用可能コマンドを表示。"""
    msg = update.effective_message
    if msg is None:
        return
    await msg.reply_text(COCKPIT_BOT_COMMANDS_MESSAGE)


async def ping_command(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /ping で接続OKと接続設定を返す。ボットが反応するか・env が読めているか確認用。"""
    msg = update.effective_message
    if msg is None:
        return
    host, port, symbols, _cid, _timeout = _env_host_port_symbols()
    admins = _target_admin_user_ids_from_environ()
    admin_line = f"settarget 許可ID: {len(admins)} 件（TELEGRAM_TARGET_ADMIN_USER_IDS / TELEGRAM_CHAT_ID）"
    await msg.reply_text(
        f"接続OK\nIB: {host}:{port}\n（/cockpit はここに接続して取得します）\n{admin_line}"
    )


def _health_flag(ok: bool) -> str:
    return "OK" if ok else "FAIL"


def _format_health_report(diag: dict) -> str:
    ib_ok = bool(diag.get("ib_connected", False))
    hist_ok = bool(diag.get("historical_nq_ok", False))
    hist_bars = diag.get("historical_nq_bars")
    hist_err = str(diag.get("historical_nq_error") or "none")
    whatif_ok = bool(diag.get("whatif_mgc_ok", False))
    whatif_err = str(diag.get("whatif_mgc_error") or "none")
    overall = str(diag.get("overall") or "FAIL")
    return (
        "IB Health Check\n"
        f"IB socket: {_health_flag(ib_ok)}\n"
        f"Historical NQ: {_health_flag(hist_ok)} (bars={hist_bars}, err={hist_err})\n"
        f"whatIf MGC: {_health_flag(whatif_ok)} (err={whatif_err})\n"
        f"Overall: {overall}"
    )


async def health_command(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /health で IB 段階診断を返す。"""
    msg = update.effective_message
    if msg is None:
        return
    host, port, _symbols, client_id, ib_timeout = _env_host_port_symbols()
    try:
        await msg.reply_text("Health check 実行中…")
    except Exception:
        pass
    try:
        from avionics.ib import run_ib_healthcheck

        diag = await asyncio.wait_for(
            run_ib_healthcheck(
                host,
                port,
                client_id=client_id,
                timeout=min(ib_timeout, 30.0),
            ),
            timeout=45,
        )
        await msg.reply_text(_format_health_report(diag)[:4000])
    except asyncio.TimeoutError:
        await msg.reply_text("Health check 取得失敗: タイムアウト")
    except Exception as e:
        await msg.reply_text(
            f"Health check 取得失敗: {type(e).__name__}: {e!s}"[:4000]
        )


# 接続に最大75秒＋取得に余裕。Gateway 起動直後は約60秒かかることがある
COCKPIT_FETCH_TIMEOUT = 90


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_optional_telegram_numeric_id(value: str) -> int | None:
    """環境変数用: 数値のみの user/chat id（先頭のマイナス可）を int にする。不正なら None。"""
    s = value.strip()
    if not s:
        return None
    if s.startswith("-") and s[1:].isdigit():
        return int(s)
    if s.isdigit():
        return int(s)
    return None


def _target_admin_user_ids_from_environ() -> frozenset[int]:
    """
    /settarget 許可ユーザーの Telegram 数値 ID 集合。

    - TELEGRAM_TARGET_ADMIN_USER_IDS: カンマ区切り（必須推奨）
    - TELEGRAM_CHAT_ID: 未設定のときのフォールバック。プライベートチャットでは
      通知先 chat_id と自分の user_id が同じことが多いので、その 1 名分として合流する。
      グループ id（負の大きい数）は user_id と一致しないため、実質プライベート向け。
    """
    raw = os.environ.get("TELEGRAM_TARGET_ADMIN_USER_IDS", "").strip()
    out: set[int] = set()
    for part in raw.split(","):
        tid = _parse_optional_telegram_numeric_id(part)
        if tid is not None:
            out.add(tid)
    chat_tid = _parse_optional_telegram_numeric_id(
        os.environ.get("TELEGRAM_CHAT_ID", "")
    )
    if chat_tid is not None:
        out.add(chat_tid)
    return frozenset(out)


def _parse_settarget_base_arg(arg: str) -> float:
    """ /settarget の base 引数を float にする。"""
    try:
        return float(arg)
    except ValueError as e:
        raise ValueError(f"base が数値として解釈できません: {arg!r}") from e


async def target_command(update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
    """ /target で DB の target_base_futures を表示。"""
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    from avionics.data.futures_micro_equiv import engine_symbol_to_micro_notional_label
    from engines.blueprint import (
        PART_NAMES,
        load_effective_mode_part_config_from_toml_path,
    )
    from store.state import (
        read_altitude_regime_from_db,
        read_target_futures_from_db,
    )
    try:
        cur = read_target_futures_from_db()
        altitude = read_altitude_regime_from_db()
    except ValueError as e:
        await msg.reply_text(
            f"{e}\n"
            "set_target_futures CLI または /settarget で MNQ/MGC 側を設定してください。"
        )
        return
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    targets_toml = str(root / "config" / "targets.toml")
    effective = load_effective_mode_part_config_from_toml_path(
        targets_toml, altitude=altitude  # type: ignore[arg-type]
    )

    lines = [f"target_base_futures（MNQ/MGC 相当枚数） altitude={altitude}"]
    for sym in ("NQ", "GC"):
        ml = engine_symbol_to_micro_notional_label(sym)
        lines.append(f"{ml}: base={float(cur[sym]):.0f}")
    lines.append("")
    lines.append("effective legs (by mode/part)")
    for mode in ("Boost", "Cruise", "Emergency"):
        lines.append(f"- {mode}")
        for part in PART_NAMES:
            legs = effective[mode][part]["legs"]
            pb = "on" if bool(legs.get("pb", False)) else "off"
            bps = "on" if bool(legs.get("bps", False)) else "off"
            cc = "on" if bool(legs.get("cc", False)) else "off"
            lines.append(f"  {part}: PB={pb} BPS={bps} CC={cc}")
    await msg.reply_text("\n".join(lines))


async def settarget_command(update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
    """ /settarget <mnq|mgc|nq|gc> <base> で該当側の target を更新。"""
    msg = getattr(update, "effective_message", None)
    user = getattr(update, "effective_user", None)
    if msg is None:
        return
    admins = _target_admin_user_ids_from_environ()
    if not admins or user is None or user.id not in admins:
        extra = ""
        if user is not None:
            extra = f"\nあなたの user_id: {user.id}"
        await msg.reply_text(
            "target の更新は許可されていません。\n"
            "次のいずれかを設定してボットを再起動してください:\n"
            "・ TELEGRAM_TARGET_ADMIN_USER_IDS に上記 user_id（カンマ区切り可）\n"
            "・ プライベートのみ運用なら TELEGRAM_CHAT_ID を同じ数値にしても可"
            "（通知先と本人の user_id が同じとき）"
            + extra
        )
        return
    args = list(context.args) if context.args else []
    if len(args) < 2:
        await msg.reply_text(
            "使い方: /settarget <mnq|mgc|nq|gc> <base>\n"
            "例: /settarget mnq 10"
        )
        return
    from avionics.data.futures_micro_equiv import engine_symbol_to_micro_notional_label
    from store.target_futures import normalize_engine_symbol, set_target_futures_in_db

    try:
        engine_sym = normalize_engine_symbol(args[0])
    except ValueError as e:
        await msg.reply_text(str(e))
        return
    try:
        base = _parse_settarget_base_arg(args[1])
    except ValueError as e:
        await msg.reply_text(f"{e}\n例: /settarget mnq 10")
        return

    try:
        cur = set_target_futures_in_db(engine_sym, base=base)
    except ValueError as e:
        await msg.reply_text(f"検証エラー: {e}")
        return
    ml = engine_symbol_to_micro_notional_label(engine_sym)
    await msg.reply_text(
        f"{ml} 相当の target(base) を更新。\n"
        f"base={float(cur[engine_sym]):.0f}"
    )


@asynccontextmanager
async def _refreshed_fc(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
):
    """IB 接続 → FC refresh の共通処理。"""
    from avionics.ib import with_ib_fetcher
    from avionics.calendar import as_of_for_bundle
    from cockpit.stack import build_cockpit_stack
    from store.state import (
        read_altitude_regime_from_db,
        read_s_factor_baseline_from_db,
        read_target_futures_from_db,
    )

    altitude = read_altitude_regime_from_db()
    target_base_by_symbol = read_target_futures_from_db()
    s_baseline_by_symbol = read_s_factor_baseline_from_db()
    async with with_ib_fetcher(host, port, client_id=client_id, timeout=timeout) as fetcher:
        fc, _ = build_cockpit_stack(
            symbols, altitude=altitude, s_baseline_by_symbol=s_baseline_by_symbol
        )
        as_of = as_of_for_bundle()
        await fc.refresh(fetcher, as_of, symbols, altitude=altitude)
        yield fc, fetcher, target_base_by_symbol


async def _fetch_cockpit_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    from reports.format_cockpit_report import format_cockpit_report

    async with _refreshed_fc(host, port, symbols, client_id=client_id, timeout=timeout) as (fc, _fetcher, _targets):
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return await format_cockpit_report(fc, symbols, now_utc)


async def _fetch_breakdown_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    from reports.format_breakdown_report import format_breakdown_report

    async with _refreshed_fc(host, port, symbols, client_id=client_id, timeout=timeout) as (fc, _fetcher, _targets):
        return format_breakdown_report(fc)


async def _fetch_daily_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    from reports.format_daily_report import format_daily_report

    async with _refreshed_fc(host, port, symbols, client_id=client_id, timeout=timeout) as (fc, fetcher, target_base_by_symbol):
        positions_detail = await fetcher.fetch_position_detail(symbols)
        return await format_daily_report(
            fc,
            symbols,
            positions_detail=positions_detail,
            target_base_by_symbol=target_base_by_symbol,
        )


async def _fetch_position_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    from reports.format_daily_report import format_position_report

    async with _refreshed_fc(host, port, symbols, client_id=client_id, timeout=timeout) as (
        _fc,
        fetcher,
        target_base_by_symbol,
    ):
        positions_detail = await fetcher.fetch_position_detail(symbols)
        return await format_position_report(
            _fc,
            symbols,
            positions_detail=positions_detail,
            target_base_by_symbol=target_base_by_symbol,
        )


async def cockpit_command(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /cockpit および /status で現在の計器内容を取得して返す。"""
    msg = update.effective_message
    if msg is None:
        return
    host, port, symbols, client_id, ib_timeout = _env_host_port_symbols()
    try:
        await msg.reply_text("計器取得中…")
    except Exception:
        pass
    try:
        report = await asyncio.wait_for(
            _fetch_cockpit_report(host, port, symbols, client_id=client_id, timeout=ib_timeout),
            timeout=COCKPIT_FETCH_TIMEOUT,
        )
        await msg.reply_text(report)
    except asyncio.TimeoutError:
        await msg.reply_text(
            "取得失敗: タイムアウトしました。\n"
            "Gateway 起動直後は約60秒かかります。しばらく待ってから再実行するか、"
            "http://localhost:6080 で Gateway が起動済みか確認してください。"
        )
    except (OSError, ConnectionError) as e:
        errno = getattr(e, "errno", None)
        is_name_error = errno == -3 or "name resolution" in str(e).lower() or "Temporary failure" in str(e)
        if is_name_error:
            h = host.lower()
            if "ib-gateway" in h or "ibgateway" in h:
                hint = "ホストで動かす場合は IBKR_HOST=127.0.0.1 IBKR_PORT=7497 で起動してください。"
            else:
                hint = "Docker の場合は docker compose -f docker/docker-compose.yml up -d で cockpit-bot を起動し、/ping で IB: 127.0.0.1:8888 と出るか確認してください。"
        else:
            hint = str(e)
        try:
            await msg.reply_text(f"取得失敗: {e!s}\n{hint}"[:4000])
        except Exception:
            pass
    except Exception as e:
        try:
            await msg.reply_text(f"取得失敗: {type(e).__name__}: {e!s}"[:4000])
        except Exception:
            pass


async def breakdown_command(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /breakdown で各因子の入力となる Layer 2 シグナル内訳を返す。"""
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    host, port, symbols, client_id, ib_timeout = _env_host_port_symbols()
    try:
        await msg.reply_text("内訳取得中…")
    except Exception:
        pass
    try:
        report = await asyncio.wait_for(
            _fetch_breakdown_report(host, port, symbols, client_id=client_id, timeout=ib_timeout),
            timeout=COCKPIT_FETCH_TIMEOUT,
        )
        await msg.reply_text(report[:4000])
    except asyncio.TimeoutError:
        try:
            await msg.reply_text("取得失敗: タイムアウト。Gateway 起動直後は約60秒かかります。しばらく待ってから再実行してください。")
        except Exception:
            pass
    except Exception as e:
        try:
            await msg.reply_text(f"取得失敗: {type(e).__name__}: {e!s}"[:4000])
        except Exception:
            pass


async def daily_command(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /daily で Daily Flight Log（市場・資本・各層）を取得して返す。"""
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    host, port, symbols, client_id, ib_timeout = _env_host_port_symbols()
    try:
        await msg.reply_text("Daily Log 取得中…")
    except Exception:
        pass
    try:
        report = await asyncio.wait_for(
            _fetch_daily_report(host, port, symbols, client_id=client_id, timeout=ib_timeout),
            timeout=COCKPIT_FETCH_TIMEOUT,
        )
        await msg.reply_text(report[:4000])
    except asyncio.TimeoutError:
        try:
            await msg.reply_text("取得失敗: タイムアウト。Gateway 起動直後は約60秒かかります。しばらく待ってから再実行してください。")
        except Exception:
            pass
    except Exception as e:
        try:
            await msg.reply_text(f"取得失敗: {type(e).__name__}: {e!s}"[:4000])
        except Exception:
            pass


async def position_command(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /position でポジション明細 + target 差分を取得して返す。"""
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    host, port, symbols, client_id, ib_timeout = _env_host_port_symbols()
    try:
        await msg.reply_text("Positions 取得中…")
    except Exception:
        pass
    try:
        report = await asyncio.wait_for(
            _fetch_position_report(
                host, port, symbols, client_id=client_id, timeout=ib_timeout
            ),
            timeout=COCKPIT_FETCH_TIMEOUT,
        )
        await msg.reply_text(report[:4000])
    except asyncio.TimeoutError:
        try:
            await msg.reply_text(
                "取得失敗: タイムアウト。Gateway 起動直後は約60秒かかります。しばらく待ってから再実行してください。"
            )
        except Exception:
            pass
    except Exception as e:
        try:
            await msg.reply_text(f"取得失敗: {type(e).__name__}: {e!s}"[:4000])
        except Exception:
            pass


async def fetch_schedule_alerts(host: str, port: int, symbols: list[str]) -> str:
    """
    IB から取引時間を取得し、翌日以降の DST・短縮・休場の通知文を組み立てて返す。
    """
    from avionics.ib import run_daily_schedule_scan, with_ib_connection

    client_id = int(os.environ.get("IBKR_CLIENT_ID", "3"))
    async with with_ib_connection(host, port, client_id=client_id, timeout=30.0) as ib:
        results = await run_daily_schedule_scan(ib, symbols)

    lines = ["【取引時間スキャン】"]
    for symbol, messages in results:
        lines.append(f"\n{symbol}:")
        if messages:
            for m in messages:
                lines.append(f"  {m}")
        else:
            lines.append("  特記事項なし（明日以降の変化なし）")
    return "\n".join(lines)


async def schedule_command(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /schedule で取引時間スキャン（夏冬・短縮・休場の事前通知）を取得して返す。"""
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    host, port, symbols, _cid, _timeout = _env_host_port_symbols()
    try:
        await msg.reply_text("取引時間スキャン中…")
    except Exception:
        pass
    try:
        report = await asyncio.wait_for(
            fetch_schedule_alerts(host, port, symbols),
            timeout=45,
        )
        await msg.reply_text(report[:4000])
    except asyncio.TimeoutError:
        try:
            await msg.reply_text("取得失敗: タイムアウト。")
        except Exception:
            pass
    except Exception as e:
        try:
            await msg.reply_text(f"取得失敗: {type(e).__name__}: {e!s}"[:4000])
        except Exception:
            pass


async def _notify_gateway_ready(application: object) -> None:
    """
    ボット起動後、Gateway に接続を試みる。
    成功したら「起動完了」、失敗したら「接続できませんでした」をすぐに Telegram で通知する。
    待ち時間は短め（約2分で成否が決まる）。
    """
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        print("TELEGRAM_CHAT_ID が未設定のため、起動完了メッセージは送信しません。", file=sys.stderr)
        return
    host, port, _symbols, client_id, _timeout = _env_host_port_symbols()
    initial_delay_sec = _env_float("STARTUP_NOTIFY_INITIAL_DELAY_SEC", 5.0)
    connect_timeout_sec = _env_float("STARTUP_NOTIFY_CONNECT_TIMEOUT_SEC", 10.0)
    retry_interval_sec = _env_float("STARTUP_NOTIFY_RETRY_INTERVAL_SEC", 2.0)
    max_attempts = _env_int("STARTUP_NOTIFY_MAX_ATTEMPTS", 3)
    if max_attempts <= 0:
        max_attempts = 1
    await asyncio.sleep(initial_delay_sec)

    from avionics.ib import check_ib_connection

    for attempt in range(max_attempts):
        ok = await check_ib_connection(
            host,
            port,
            client_id=client_id,
            timeout=connect_timeout_sec,
        )
        if ok:
            bot = getattr(application, "bot", None)
            if bot:
                await bot.send_message(
                    chat_id=chat_id,
                    text="Sputnik 起動完了。API 利用可能です。\n\n" + COCKPIT_BOT_COMMANDS_MESSAGE,
                )
            return
        print(
            f"Gateway 接続試行 {attempt + 1}/{max_attempts} 失敗: {host}:{port} clientId={client_id}",
            file=sys.stderr,
        )
        if attempt + 1 < max_attempts:
            await asyncio.sleep(retry_interval_sec)

    bot = getattr(application, "bot", None)
    if bot:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "Sputnik ボットは起動していますが、Gateway に接続できませんでした。\n"
                    "しばらくしてから /cockpit を試すか、Gateway とログを確認してください。\n\n"
                    + COCKPIT_BOT_COMMANDS_MESSAGE
                ),
            )
        except Exception as e:
            print(f"接続失敗の通知送信に失敗: {e}", file=sys.stderr)
    print(f"Gateway に接続できませんでした: {host}:{port}", file=sys.stderr)


def main() -> int:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_TOKEN を設定してください。", file=sys.stderr)
        return 1
    try:
        from telegram.ext import Application, CommandHandler, ContextTypes
    except ImportError:
        print("python-telegram-bot をインストールしてください: pip install python-telegram-bot", file=sys.stderr)
        return 1

    async def post_init(app: Application) -> None:
        asyncio.create_task(_notify_gateway_ready(app))

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("health", health_command))
    app.add_handler(CommandHandler("cockpit", cockpit_command))
    app.add_handler(CommandHandler("status", cockpit_command))
    app.add_handler(CommandHandler("breakdown", breakdown_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("position", position_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("target", target_command))
    app.add_handler(CommandHandler("settarget", settarget_command))
    app.run_polling(allowed_updates=["message"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
