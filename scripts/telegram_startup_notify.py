#!/usr/bin/env python3
"""
Docker 起動時に Telegram へ「Sputnik 起動」を通知する。

環境変数 TELEGRAM_TOKEN と TELEGRAM_CHAT_ID が設定されているときのみ送信。
未設定または送信失敗時は静かに終了（exit 0）。コンテナ起動を阻害しない。
"""

from __future__ import annotations

import os
import sys

from notifications.telegram import send_telegram_message


def main() -> int:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return 0
    default_msg = (
        "Sputnik 起動中..."
    )
    text = os.environ.get("TELEGRAM_STARTUP_MESSAGE", default_msg.strip())
    send_telegram_message(token=token, chat_id=chat_id, text=text, timeout=10.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
