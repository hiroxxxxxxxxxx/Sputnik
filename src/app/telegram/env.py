from __future__ import annotations

import os


def env_host_port_symbols() -> tuple[str, int, list[str], int, float]:
    """env から host, port, symbols, client_id, timeout を返す。"""
    host = os.environ.get("IBKR_HOST", "127.0.0.1").strip()
    port_str = os.environ.get("IBKR_PORT", "").strip()
    port = int(port_str) if port_str.isdigit() else 4002
    symbols_str = os.environ.get("TELEGRAM_COCKPIT_SYMBOLS", "NQ,GC").strip()
    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()] or ["NQ", "GC"]
    client_id = int(os.environ.get("IBKR_CLIENT_ID", "3"))
    timeout = 75.0
    return host, port, symbols, client_id, timeout


def parse_optional_telegram_numeric_id(value: str) -> int | None:
    s = value.strip()
    if not s:
        return None
    if s.startswith("-") and s[1:].isdigit():
        return int(s)
    if s.isdigit():
        return int(s)
    return None


def target_admin_user_ids_from_environ() -> frozenset[int]:
    raw = os.environ.get("TELEGRAM_TARGET_ADMIN_USER_IDS", "").strip()
    out: set[int] = set()
    for part in raw.split(","):
        tid = parse_optional_telegram_numeric_id(part)
        if tid is not None:
            out.add(tid)
    chat_tid = parse_optional_telegram_numeric_id(os.environ.get("TELEGRAM_CHAT_ID", ""))
    if chat_tid is not None:
        out.add(chat_tid)
    return frozenset(out)
