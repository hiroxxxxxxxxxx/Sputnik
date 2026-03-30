#!/usr/bin/env python3
"""
Telegram から /cockpit または /status で現在の FlightController 計器内容を返すボット。

コマンド: /start, /ping, /cockpit, /status, /breakdown, /daily, /schedule
  /schedule: 取引時間スキャン（夏冬・短縮・休場の事前通知）。毎朝のルーチンや週次で実行推奨。

用法:
  PYTHONPATH=src python scripts/telegram_cockpit_bot.py
  環境変数: TELEGRAM_TOKEN（必須）, IBKR_HOST, IBKR_PORT（IB 取得時）, TELEGRAM_COCKPIT_SYMBOLS（省略時 NQ,GC）
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
    "/cockpit または /status … 現在の計器（IB から取得）\n"
    "/daily … Daily Flight Log（市場・資本・各層）\n"
    "/breakdown … 各因子の計算内訳（Layer 2 シグナル）\n"
    "/schedule … 取引時間スキャン（夏冬・短縮・休場の事前通知）"
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
    await msg.reply_text(
        f"接続OK\nIB: {host}:{port}\n（/cockpit はここに接続して取得します）"
    )


# 接続に最大75秒＋取得に余裕。Gateway 起動直後は約60秒かかることがある
COCKPIT_FETCH_TIMEOUT = 90


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
    from store.db import get_connection
    from store.state import read_altitude_regime

    conn = get_connection()
    try:
        altitude = read_altitude_regime(conn)
        async with with_ib_fetcher(host, port, client_id=client_id, timeout=timeout) as fetcher:
            fc, _ = build_cockpit_stack(symbols, altitude=altitude)
            as_of = as_of_for_bundle()
            await fc.refresh(fetcher, as_of, symbols, altitude=altitude)
            yield fc, fetcher
    finally:
        conn.close()


async def _fetch_cockpit_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    from reports.format_cockpit_report import format_cockpit_report

    async with _refreshed_fc(host, port, symbols, client_id=client_id, timeout=timeout) as (fc, _fetcher):
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

    async with _refreshed_fc(host, port, symbols, client_id=client_id, timeout=timeout) as (fc, _fetcher):
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

    async with _refreshed_fc(host, port, symbols, client_id=client_id, timeout=timeout) as (fc, fetcher):
        positions_detail = await fetcher.fetch_position_detail(symbols)
        return await format_daily_report(
            fc,
            symbols,
            positions_detail=positions_detail,
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
    await asyncio.sleep(30)

    from avionics.ib import check_ib_connection

    for attempt in range(3):
        ok = await check_ib_connection(host, port, client_id=client_id, timeout=30.0)
        if ok:
            bot = getattr(application, "bot", None)
            if bot:
                await bot.send_message(
                    chat_id=chat_id,
                    text="Sputnik 起動完了。API 利用可能です。\n\n" + COCKPIT_BOT_COMMANDS_MESSAGE,
                )
            return
        print(
            f"Gateway 接続試行 {attempt + 1}/3 失敗: {host}:{port} clientId={client_id}",
            file=sys.stderr,
        )
        await asyncio.sleep(5)

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
    app.add_handler(CommandHandler("cockpit", cockpit_command))
    app.add_handler(CommandHandler("status", cockpit_command))
    app.add_handler(CommandHandler("breakdown", breakdown_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.run_polling(allowed_updates=["message"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
