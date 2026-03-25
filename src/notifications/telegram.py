"""
Telegram 通知ユーティリティ（urllib ベース、依存なし）。

目的:
- scripts 内で Telegram 送信処理が重複しないようにする
- TELEGRAM_TOKEN / TELEGRAM_CHAT_ID から呼び出し側で渡してもらう（送信先は呼び出し側で決める）
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request


def send_telegram_message(
    *,
    token: str,
    chat_id: str,
    text: str,
    timeout: float = 20.0,
) -> bool:
    """
    Telegram にテキストメッセージを送信する。

    :return: 送信成功なら True（HTTP 2xx）、それ以外は False。
    """
    token = (token or "").strip()
    chat_id = (chat_id or "").strip()
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError):
        return False

