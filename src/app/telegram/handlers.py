from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

from .env import env_host_port_symbols, target_admin_user_ids_from_environ
from .messages import COCKPIT_BOT_COMMANDS_MESSAGE, COCKPIT_FETCH_TIMEOUT
from .usecases import (
    fetch_breakdown_report,
    fetch_cockpit_report,
    fetch_daily_report,
    fetch_health_report,
    fetch_position_report,
    fetch_schedule_alerts,
)

if TYPE_CHECKING:
    from telegram.ext import ContextTypes


def parse_settarget_base_arg(arg: str) -> float:
    try:
        return float(arg)
    except ValueError as e:
        raise ValueError(f"base が数値として解釈できません: {arg!r}") from e


def parse_setaltitude_arg(arg: str) -> str:
    altitude = str(arg).strip().lower()
    if altitude not in ("high", "mid", "low"):
        raise ValueError(f"altitude は high|mid|low のいずれかです: {arg!r}")
    return altitude


def parse_setsbaseline_args(symbol: str, value: str) -> tuple[str, float]:
    s = str(symbol).strip().upper()
    s = {"MNQ": "NQ", "MGC": "GC"}.get(s, s)
    if s not in ("NQ", "GC"):
        raise ValueError(f"symbol は NQ|GC|MNQ|MGC のいずれかです: {symbol!r}")
    try:
        mm = float(value)
    except ValueError as e:
        raise ValueError(f"mm_per_lot が数値として解釈できません: {value!r}") from e
    if mm <= 0:
        raise ValueError(f"mm_per_lot は正の値が必要です: {mm}")
    return s, mm


def parse_setmode_arg(arg: str) -> str:
    mode = str(arg).strip()
    if mode not in ("Manual", "SemiAuto", "Auto"):
        raise ValueError(f"mode は Manual|SemiAuto|Auto のいずれかです: {arg!r}")
    return mode


def parse_setlock_arg(arg: str) -> bool:
    s = str(arg).strip().lower()
    if s in ("on", "1", "true", "lock"):
        return True
    if s in ("off", "0", "false", "unlock"):
        return False
    raise ValueError(f"lock は on|off のいずれかです: {arg!r}")


async def _require_admin(msg: object, user: object | None, *, what: str) -> bool:
    admins = target_admin_user_ids_from_environ()
    if admins and user is not None and getattr(user, "id", None) in admins:
        return True
    extra = f"\nあなたの user_id: {getattr(user, 'id', None)}" if user is not None else ""
    await msg.reply_text(  # type: ignore[attr-defined]
        f"{what} の更新は許可されていません。\n"
        "次のいずれかを設定してボットを再起動してください:\n"
        "・ TELEGRAM_TARGET_ADMIN_USER_IDS に上記 user_id（カンマ区切り可）\n"
        "・ プライベートのみ運用なら TELEGRAM_CHAT_ID を同じ数値にしても可"
        "（通知先と本人の user_id が同じとき）"
        + extra
    )
    return False


async def _run_report_command(
    msg: object,
    *,
    progress_text: str,
    fetch_coro: Callable[[], Awaitable[str]],
    timeout_seconds: int,
    timeout_error_text: str,
) -> None:
    try:
        await msg.reply_text(progress_text)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        report = await asyncio.wait_for(fetch_coro(), timeout=timeout_seconds)
        await msg.reply_text(report[:4000])  # type: ignore[attr-defined]
    except asyncio.TimeoutError:
        try:
            await msg.reply_text(timeout_error_text)  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception as e:
        try:
            await msg.reply_text(f"取得失敗: {type(e).__name__}: {e!s}"[:4000])  # type: ignore[attr-defined]
        except Exception:
            pass


async def start_command(update, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = update.effective_message
    if msg is None:
        return
    await msg.reply_text(COCKPIT_BOT_COMMANDS_MESSAGE)


async def ping_command(update, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = update.effective_message
    if msg is None:
        return
    host, port, _symbols, _cid, _timeout = env_host_port_symbols()
    admins = target_admin_user_ids_from_environ()
    admin_line = (
        f"settarget 許可ID: {len(admins)} 件（TELEGRAM_TARGET_ADMIN_USER_IDS / TELEGRAM_CHAT_ID）"
    )
    await msg.reply_text(
        f"接続OK\nIB: {host}:{port}\n（/cockpit はここに接続して取得します）\n{admin_line}"
    )


async def cockpit_command(update, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = update.effective_message
    if msg is None:
        return
    host, port, symbols, client_id, ib_timeout = env_host_port_symbols()
    await _run_report_command(
        msg,
        progress_text="計器取得中…",
        fetch_coro=lambda: fetch_cockpit_report(
            host, port, symbols, client_id=client_id, timeout=ib_timeout
        ),
        timeout_seconds=COCKPIT_FETCH_TIMEOUT,
        timeout_error_text=(
            "取得失敗: タイムアウトしました。\n"
            "Gateway 起動直後は約60秒かかります。しばらく待ってから再実行するか、"
            "http://localhost:6080 で Gateway が起動済みか確認してください。"
        ),
    )


async def breakdown_command(update, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    host, port, symbols, client_id, ib_timeout = env_host_port_symbols()
    await _run_report_command(
        msg,
        progress_text="内訳取得中…",
        fetch_coro=lambda: fetch_breakdown_report(
            host, port, symbols, client_id=client_id, timeout=ib_timeout
        ),
        timeout_seconds=COCKPIT_FETCH_TIMEOUT,
        timeout_error_text="取得失敗: タイムアウト。Gateway 起動直後は約60秒かかります。しばらく待ってから再実行してください。",
    )


async def daily_command(update, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    host, port, symbols, client_id, ib_timeout = env_host_port_symbols()
    await _run_report_command(
        msg,
        progress_text="Daily Log 取得中…",
        fetch_coro=lambda: fetch_daily_report(
            host, port, symbols, client_id=client_id, timeout=ib_timeout
        ),
        timeout_seconds=COCKPIT_FETCH_TIMEOUT,
        timeout_error_text="取得失敗: タイムアウト。Gateway 起動直後は約60秒かかります。しばらく待ってから再実行してください。",
    )


async def position_command(update, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    host, port, symbols, client_id, ib_timeout = env_host_port_symbols()
    await _run_report_command(
        msg,
        progress_text="Positions 取得中…",
        fetch_coro=lambda: fetch_position_report(
            host, port, symbols, client_id=client_id, timeout=ib_timeout
        ),
        timeout_seconds=COCKPIT_FETCH_TIMEOUT,
        timeout_error_text="取得失敗: タイムアウト。Gateway 起動直後は約60秒かかります。しばらく待ってから再実行してください。",
    )


async def health_command(update, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    host, port, _symbols, client_id, _timeout = env_host_port_symbols()
    await _run_report_command(
        msg,
        progress_text="Health Check 実行中…",
        fetch_coro=lambda: fetch_health_report(host, port, client_id=client_id),
        timeout_seconds=45,
        timeout_error_text="取得失敗: タイムアウト。",
    )


async def schedule_command(update, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    host, port, symbols, _cid, _timeout = env_host_port_symbols()
    await _run_report_command(
        msg,
        progress_text="取引時間スキャン中…",
        fetch_coro=lambda: fetch_schedule_alerts(host, port, symbols),
        timeout_seconds=45,
        timeout_error_text="取得失敗: タイムアウト。",
    )


async def target_command(update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    from avionics.data.futures_micro_equiv import engine_symbol_to_micro_notional_label
    from engines.blueprint import PART_NAMES, load_effective_mode_part_config_from_toml_path
    from store.db import get_connection
    from store.state import read_altitude_regime, read_target_futures

    conn = get_connection()
    try:
        try:
            cur = read_target_futures(conn)
            altitude = read_altitude_regime(conn)
        except ValueError as e:
            await msg.reply_text(
                f"{e}\n/settarget で MNQ/MGC 側を設定してください。"
            )
            return
    finally:
        conn.close()

    root = Path(__file__).resolve().parent.parent.parent.parent
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
    msg = getattr(update, "effective_message", None)
    user = getattr(update, "effective_user", None)
    if msg is None:
        return
    if not await _require_admin(msg, user, what="target"):
        return
    args = list(context.args) if context.args else []
    if len(args) < 2:
        await msg.reply_text("使い方: /settarget <mnq|mgc|nq|gc> <base>\n例: /settarget mnq 10")
        return

    from avionics.data.futures_micro_equiv import engine_symbol_to_micro_notional_label
    from store.db import get_connection
    from store.state import read_target_futures
    from store.target_futures import normalize_engine_symbol, set_target_futures

    try:
        engine_sym = normalize_engine_symbol(args[0])
    except ValueError as e:
        await msg.reply_text(str(e))
        return
    try:
        base = parse_settarget_base_arg(args[1])
    except ValueError as e:
        await msg.reply_text(f"{e}\n例: /settarget mnq 10")
        return

    conn = get_connection()
    try:
        try:
            set_target_futures(conn, engine_sym, base=base)
        except ValueError as e:
            await msg.reply_text(f"検証エラー: {e}")
            return
        cur = read_target_futures(conn)
    finally:
        conn.close()
    ml = engine_symbol_to_micro_notional_label(engine_sym)
    await msg.reply_text(f"{ml} 相当の target(base) を更新。\nbase={float(cur[engine_sym]):.0f}")


async def altitude_command(update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    from store.db import get_connection
    from store.state import read_altitude_regime

    conn = get_connection()
    try:
        altitude = read_altitude_regime(conn)
    finally:
        conn.close()
    await msg.reply_text(f"現在の altitude: {altitude}")


async def setaltitude_command(update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    user = getattr(update, "effective_user", None)
    if msg is None:
        return
    if not await _require_admin(msg, user, what="altitude"):
        return
    args = list(context.args) if context.args else []
    if len(args) < 1:
        await msg.reply_text("使い方: /setaltitude <high|mid|low>\n例: /setaltitude mid")
        return
    try:
        new_altitude = parse_setaltitude_arg(args[0])
    except ValueError as e:
        await msg.reply_text(str(e))
        return

    from store.db import get_connection
    from store.state import read_altitude_regime, update_altitude

    conn = get_connection()
    try:
        old_altitude = read_altitude_regime(conn)
        update_altitude(conn, new_altitude)  # type: ignore[arg-type]
        updated = read_altitude_regime(conn)
    finally:
        conn.close()
    await msg.reply_text(f"altitude を更新しました: {old_altitude} -> {updated}")


async def sbaseline_command(update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    from store.db import get_connection
    from store.state import read_s_factor_baseline

    conn = get_connection()
    try:
        baseline = read_s_factor_baseline(conn)
    finally:
        conn.close()
    await msg.reply_text(
        "S baseline（mm_per_lot）\n"
        f"NQ={baseline['NQ']:.2f}\n"
        f"GC={baseline['GC']:.2f}"
    )


async def setsbaseline_command(update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    user = getattr(update, "effective_user", None)
    if msg is None:
        return
    if not await _require_admin(msg, user, what="s baseline"):
        return
    args = list(context.args) if context.args else []
    if len(args) < 2:
        await msg.reply_text(
            "使い方: /setsbaseline <nq|gc|mnq|mgc> <mm_per_lot>\n例: /setsbaseline nq 1250"
        )
        return
    try:
        symbol, mm_per_lot = parse_setsbaseline_args(args[0], args[1])
    except ValueError as e:
        await msg.reply_text(str(e))
        return

    from store.db import get_connection
    from store.state import read_s_factor_baseline, upsert_s_factor_baseline

    conn = get_connection()
    try:
        upsert_s_factor_baseline(conn, symbol, mm_per_lot)
        baseline = read_s_factor_baseline(conn)
    finally:
        conn.close()
    await msg.reply_text(
        f"S baseline を更新しました ({symbol}={mm_per_lot:.2f})\n"
        f"NQ={baseline['NQ']:.2f}, GC={baseline['GC']:.2f}"
    )


async def mode_command(update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    if msg is None:
        return
    from store.db import get_connection
    from store.mode import read_mode

    conn = get_connection()
    try:
        mode = read_mode(conn)
    finally:
        conn.close()
    lock = bool(mode.get("execution_lock", 0))
    await msg.reply_text(
        "制御モード\n"
        f"ap_mode={mode.get('ap_mode')}\n"
        f"execution_lock={'ON' if lock else 'OFF'}"
    )


async def setmode_command(update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    user = getattr(update, "effective_user", None)
    if msg is None:
        return
    if not await _require_admin(msg, user, what="ap_mode"):
        return
    args = list(context.args) if context.args else []
    if len(args) < 1:
        await msg.reply_text("使い方: /setmode <Manual|SemiAuto|Auto>\n例: /setmode Auto")
        return
    try:
        new_mode = parse_setmode_arg(args[0])
    except ValueError as e:
        await msg.reply_text(str(e))
        return

    from store.db import get_connection
    from store.mode import read_mode, update_ap_mode

    conn = get_connection()
    try:
        old_mode = str(read_mode(conn).get("ap_mode"))
        update_ap_mode(conn, new_mode)  # type: ignore[arg-type]
        updated_mode = str(read_mode(conn).get("ap_mode"))
    finally:
        conn.close()
    await msg.reply_text(f"ap_mode を更新しました: {old_mode} -> {updated_mode}")


async def setlock_command(update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = getattr(update, "effective_message", None)
    user = getattr(update, "effective_user", None)
    if msg is None:
        return
    if not await _require_admin(msg, user, what="execution_lock"):
        return
    args = list(context.args) if context.args else []
    if len(args) < 1:
        await msg.reply_text("使い方: /setlock <on|off>\n例: /setlock on")
        return
    try:
        locked = parse_setlock_arg(args[0])
    except ValueError as e:
        await msg.reply_text(str(e))
        return

    from store.db import get_connection
    from store.mode import read_mode, update_execution_lock

    conn = get_connection()
    try:
        old = bool(read_mode(conn).get("execution_lock", 0))
        update_execution_lock(conn, locked)
        new = bool(read_mode(conn).get("execution_lock", 0))
    finally:
        conn.close()
    await msg.reply_text(
        f"execution_lock を更新しました: {'ON' if old else 'OFF'} -> {'ON' if new else 'OFF'}"
    )
