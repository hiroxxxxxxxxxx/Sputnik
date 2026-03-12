#!/usr/bin/env python3
"""
Telegram から /cockpit または /status で現在の Cockpit 計器内容を返すボット。

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
from datetime import date, datetime, timezone
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


def _build_cockpit(symbols: list[str]):
    """因子登録済み Cockpit を組み立てる。"""
    from avionics import Cockpit
    from avionics import CFactor, PFactor, RFactor, SFactor, TFactor, UFactor, VFactor
    from avionics.factors_config import (
        FactorsConfigError,
        get_c_thresholds,
        get_p_thresholds,
        get_r_thresholds,
        get_s_thresholds,
        get_t_thresholds,
        get_u_thresholds,
        get_v_thresholds,
        load_factors_config,
    )

    try:
        config = load_factors_config()
        global_market_factors = []
        global_capital_factors = []
        symbol_factors = {s: [] for s in symbols}
        for sym in symbols:
            try:
                p_th = get_p_thresholds(config, sym)
                v_th = get_v_thresholds(config, sym)
                t_th = get_t_thresholds(config)
                symbol_factors[sym].append(PFactor(name="P", thresholds=p_th))
                symbol_factors[sym].append(VFactor(name="V", thresholds=v_th))
                symbol_factors[sym].append(TFactor(symbol=sym, thresholds=t_th))
            except FactorsConfigError:
                pass
            try:
                c_th = get_c_thresholds(config, sym)
                symbol_factors[sym].append(CFactor(name="C", thresholds=c_th))
            except FactorsConfigError:
                pass
            try:
                r_th = get_r_thresholds(config, sym)
                symbol_factors[sym].append(RFactor(name="R", thresholds=r_th))
            except FactorsConfigError:
                pass
        try:
            u_th = get_u_thresholds(config)
            s_th = get_s_thresholds(config)
            global_capital_factors.extend([UFactor(thresholds=u_th), SFactor(thresholds=s_th)])
        except FactorsConfigError:
            pass
        return Cockpit(
            global_market_factors=global_market_factors,
            global_capital_factors=global_capital_factors,
            symbol_factors=symbol_factors,
        )
    except FactorsConfigError:
        return Cockpit(
            global_market_factors=[],
            global_capital_factors=[],
            symbol_factors={s: [] for s in symbols},
        )


async def fetch_cockpit_report(host: str, port: int, symbols: list[str]) -> str:
    """
    IB から SignalBundle を取得し Cockpit を更新したうえで、計器レポート文字列を返す。
    接続失敗時は例外を投げる。
    """
    from avionics import Cockpit
    from avionics.factors_config import (
        FactorsConfigError,
        get_v_thresholds,
        load_factors_config,
    )
    from avionics.ib_data import IBDataFetcher
    from ib_async import IB

    ib = IB()
    client_id = int(os.environ.get("IBKR_CLIENT_ID", "3"))  # 2 は競合しやすいためデフォルト 3
    # Gateway 起動直後は約60秒かかるため、接続タイムアウトを長めに（デフォルト2〜4秒では即失敗する）
    await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=75)
    try:
        try:
            config = load_factors_config()
            v_recovery_params = {
                s: get_v_thresholds(config, s)["high_mid"] for s in symbols
            }
        except (FactorsConfigError, KeyError):
            v_recovery_params = None
        fetcher = IBDataFetcher(ib)
        from util import ny_date_now
        as_of = ny_date_now()  # バー日付（NY Trade Date）と整合
        bundle, _ = await fetcher.fetch_signal_bundle(
            as_of=as_of,
            price_symbols=symbols,
            liquidity_credit_symbol="HYG",
            liquidity_tip=True,
            base_density=1.0,
            v_recovery_params=v_recovery_params,
        )
        cockpit = _build_cockpit(symbols)
        await cockpit.update_all(signal_bundle=bundle)
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        from reports.format_cockpit_report import format_cockpit_report
        return await format_cockpit_report(cockpit, symbols, now_utc, bundle=bundle)
    finally:
        ib.disconnect()


async def fetch_breakdown_report(host: str, port: int, symbols: list[str]) -> str:
    """
    IB から SignalBundle を取得し、各因子の入力となる Layer 2 シグナル内訳を返す。
    接続失敗時は例外を投げる。
    """
    from avionics.factors_config import (
        FactorsConfigError,
        get_v_thresholds,
        load_factors_config,
    )
    from avionics.ib_data import IBDataFetcher
    from reports.format_breakdown_report import format_breakdown_report
    from ib_async import IB

    ib = IB()
    client_id = int(os.environ.get("IBKR_CLIENT_ID", "3"))
    await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=75)
    try:
        try:
            config = load_factors_config()
            v_recovery_params = {
                s: get_v_thresholds(config, s)["high_mid"] for s in symbols
            }
        except (FactorsConfigError, KeyError):
            v_recovery_params = None
        fetcher = IBDataFetcher(ib)
        from util import ny_date_now
        as_of = ny_date_now()
        bundle, _ = await fetcher.fetch_signal_bundle(
            as_of=as_of,
            price_symbols=symbols,
            liquidity_credit_symbol="HYG",
            liquidity_tip=True,
            base_density=1.0,
            v_recovery_params=v_recovery_params,
        )
        return format_breakdown_report(bundle)
    finally:
        ib.disconnect()


async def fetch_daily_report(host: str, port: int, symbols: list[str]) -> str:
    """
    IB から SignalBundle と RawCapitalSnapshot を取得し、Cockpit を更新したうえで
    Daily Flight Log 形式のレポート文字列を返す。接続失敗時は例外を投げる。
    """
    from avionics.factors_config import (
        FactorsConfigError,
        get_v_thresholds,
        load_factors_config,
    )
    from reports.format_daily_report import format_daily_flight_log
    from avionics.ib_data import IBDataFetcher
    from ib_async import IB

    ib = IB()
    client_id = int(os.environ.get("IBKR_CLIENT_ID", "3"))
    await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=75)
    try:
        try:
            config = load_factors_config()
            v_recovery_params = {
                s: get_v_thresholds(config, s)["high_mid"] for s in symbols
            }
        except (FactorsConfigError, KeyError):
            v_recovery_params = None
        fetcher = IBDataFetcher(ib)
        from util import ny_date_now
        as_of = ny_date_now()
        bundle, capital_snapshot = await fetcher.fetch_signal_bundle(
            as_of=as_of,
            price_symbols=symbols,
            liquidity_credit_symbol="HYG",
            liquidity_tip=True,
            base_density=1.0,
            v_recovery_params=v_recovery_params,
        )
        cockpit = _build_cockpit(symbols)
        await cockpit.update_all(signal_bundle=bundle)
        return await format_daily_flight_log(
            cockpit, bundle, symbols,
            capital_snapshot=capital_snapshot,
            as_of=as_of,
        )
    finally:
        ib.disconnect()


async def start_command(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /start で利用可能コマンドを表示。"""
    msg = update.effective_message
    if msg is None:
        return
    await msg.reply_text(
        "Sputnik Cockpit Bot\n"
        "/ping … 接続・設定確認\n"
        "/cockpit または /status … 現在の計器（IB から取得）\n"
        "/daily … Daily Flight Log（市場・資本・各層）\n"
        "/breakdown … 各因子の計算内訳（Layer 2 シグナル）"
    )


async def ping_command(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /ping で接続OKと接続設定を返す。ボットが反応するか・env が読めているか確認用。"""
    msg = update.effective_message
    if msg is None:
        return
    host = os.environ.get("IBKR_HOST", "127.0.0.1").strip()
    port_str = os.environ.get("IBKR_PORT", "").strip()
    port = port_str if port_str.isdigit() else "4002"
    await msg.reply_text(
        f"接続OK\nIB: {host}:{port}\n（/cockpit はここに接続して取得します）"
    )


# 接続に最大75秒＋取得に余裕。Gateway 起動直後は約60秒かかることがある
COCKPIT_FETCH_TIMEOUT = 90


async def cockpit_command(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ /cockpit および /status で現在の計器内容を取得して返す。"""
    msg = update.effective_message
    if msg is None:
        return
    host = os.environ.get("IBKR_HOST", "127.0.0.1").strip()
    port_str = os.environ.get("IBKR_PORT", "").strip()
    port = int(port_str) if port_str.isdigit() else 4002
    symbols_str = os.environ.get("TELEGRAM_COCKPIT_SYMBOLS", "NQ,GC").strip()
    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()] or ["NQ", "GC"]
    try:
        await msg.reply_text("計器取得中…")
    except Exception:
        pass
    try:
        report = await asyncio.wait_for(
            fetch_cockpit_report(host, port, symbols),
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
    host = os.environ.get("IBKR_HOST", "127.0.0.1").strip()
    port_str = os.environ.get("IBKR_PORT", "").strip()
    port = int(port_str) if port_str.isdigit() else 4002
    symbols_str = os.environ.get("TELEGRAM_COCKPIT_SYMBOLS", "NQ,GC").strip()
    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()] or ["NQ", "GC"]
    try:
        await msg.reply_text("内訳取得中…")
    except Exception:
        pass
    try:
        report = await asyncio.wait_for(
            fetch_breakdown_report(host, port, symbols),
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
    host = os.environ.get("IBKR_HOST", "127.0.0.1").strip()
    port_str = os.environ.get("IBKR_PORT", "").strip()
    port = int(port_str) if port_str.isdigit() else 4002
    symbols_str = os.environ.get("TELEGRAM_COCKPIT_SYMBOLS", "NQ,GC").strip()
    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()] or ["NQ", "GC"]
    try:
        await msg.reply_text("Daily Log 取得中…")
    except Exception:
        pass
    try:
        report = await asyncio.wait_for(
            fetch_daily_report(host, port, symbols),
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
    from avionics.trading_hours import run_daily_schedule_scan
    from ib_async import IB

    ib = IB()
    client_id = int(os.environ.get("IBKR_CLIENT_ID", "3"))
    await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=30)
    try:
        results = await run_daily_schedule_scan(ib, symbols)
    finally:
        ib.disconnect()

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
    host = os.environ.get("IBKR_HOST", "127.0.0.1").strip()
    port_str = os.environ.get("IBKR_PORT", "").strip()
    port = int(port_str) if port_str.isdigit() else 4002
    symbols_str = os.environ.get("TELEGRAM_COCKPIT_SYMBOLS", "NQ,GC").strip()
    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()] or ["NQ", "GC"]
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
    ボット起動後、Gateway が API 接続可能になるまで待ち、完了メッセージを送る。
    post_init から create_task で呼ばれる。
    """
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        return
    host = os.environ.get("IBKR_HOST", "127.0.0.1").strip()
    port_str = os.environ.get("IBKR_PORT", "").strip()
    port = int(port_str) if port_str.isdigit() else 8888
    client_id = int(os.environ.get("IBKR_CLIENT_ID", "3"))
    await asyncio.sleep(15)
    from ib_async import IB

    for _ in range(6):
        try:
            ib = IB()
            await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=15)
            ib.disconnect()
            bot = getattr(application, "bot", None)
            if bot:
                await bot.send_message(
                    chat_id=chat_id,
                    text="Sputnik 起動完了。API 利用可能です。",
                )
            return
        except Exception:
            await asyncio.sleep(15)


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
