from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))

from .env import target_admin_user_ids_from_environ
from .handlers import (
    altitude_command,
    breakdown_command,
    cockpit_command,
    daily_command,
    health_command,
    mode_command,
    parse_settarget_base_arg,
    ping_command,
    position_command,
    sbaseline_command,
    schedule_command,
    setlock_command,
    setmode_command,
    setsbaseline_command,
    settarget_command,
    setaltitude_command,
    start_command,
    target_command,
)
from .messages import COCKPIT_BOT_COMMANDS_MESSAGE
from .usecases import notify_gateway_ready

_target_admin_user_ids_from_environ = target_admin_user_ids_from_environ
_parse_settarget_base_arg = parse_settarget_base_arg


def main() -> int:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_TOKEN を設定してください。", file=sys.stderr)
        return 1
    try:
        from telegram.ext import Application, CommandHandler
    except ImportError:
        print("python-telegram-bot をインストールしてください: pip install python-telegram-bot", file=sys.stderr)
        return 1

    async def post_init(app: Application) -> None:
        asyncio.create_task(notify_gateway_ready(app))

    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("cockpit", cockpit_command))
    app.add_handler(CommandHandler("status", cockpit_command))
    app.add_handler(CommandHandler("breakdown", breakdown_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("position", position_command))
    app.add_handler(CommandHandler("health", health_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("altitude", altitude_command))
    app.add_handler(CommandHandler("setaltitude", setaltitude_command))
    app.add_handler(CommandHandler("sbaseline", sbaseline_command))
    app.add_handler(CommandHandler("setsbaseline", setsbaseline_command))
    app.add_handler(CommandHandler("mode", mode_command))
    app.add_handler(CommandHandler("setmode", setmode_command))
    app.add_handler(CommandHandler("setlock", setlock_command))
    app.add_handler(CommandHandler("target", target_command))
    app.add_handler(CommandHandler("settarget", settarget_command))
    app.run_polling(allowed_updates=["message"])
    return 0
