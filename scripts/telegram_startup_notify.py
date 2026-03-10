#!/usr/bin/env python3
"""
Docker 起動時に Telegram へ「Sputnik 起動」を通知する。

環境変数 TELEGRAM_TOKEN と TELEGRAM_CHAT_ID が設定されているときのみ送信。
未設定または送信失敗時は静かに終了（exit 0）。コンテナ起動を阻害しない。
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def main() -> int:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return 0
    default_msg = (
        "Sputnik 起動中..."
    )
    text = os.environ.get("TELEGRAM_STARTUP_MESSAGE", default_msg.strip())
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if 200 <= resp.status < 300:
                return 0
    except (urllib.error.URLError, OSError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
