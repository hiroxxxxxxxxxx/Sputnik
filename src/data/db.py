"""
SQLite 接続とマイグレーション。

**単一ライター前提（計画 B2）**
  書き込みは 1 プロセス（例: cockpit-bot のみ）から行うことを推奨する。
  複数コンテナ・複数プロセスから同時に書く場合は、キューを経由するか、
  書き込み担当を 1 プロセスにまとめる設計にすること。SQLite はマルチライターに弱い。

DB パス: 環境変数 SPUTNIK_DB_PATH で上書き可能。未設定時はプロジェクトルートの data/sputnik.db。
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path


def _project_root() -> Path:
    """src/data/db.py からプロジェクトルートを算出。"""
    return Path(__file__).resolve().parent.parent.parent


def get_db_path() -> Path:
    """
    使用する SQLite ファイルのパスを返す。
    環境変数 SPUTNIK_DB_PATH が設定されていればそれを、なければ data/sputnik.db（プロジェクトルート基準）。
    """
    env = os.environ.get("SPUTNIK_DB_PATH")
    if env:
        return Path(env).resolve()
    return _project_root() / "data" / "sputnik.db"


def _migrations_dir() -> Path:
    """マイグレーション SQL が置かれたディレクトリ。"""
    return _project_root() / "migrations"


def _current_schema_version(conn: sqlite3.Connection) -> int:
    """DB に記録されているスキーマバージョン。テーブルがなければ 0。"""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cur.fetchone() is None:
        return 0
    cur = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    row = cur.fetchone()
    return row[0] if row is not None else 0


def _migration_files_sorted() -> list[tuple[int, Path]]:
    """migrations/ 内の 001_*.sql, 002_*.sql をバージョン番号でソートして返す。"""
    directory = _migrations_dir()
    if not directory.is_dir():
        return []
    pattern = re.compile(r"^(\d+)_(.+)\.sql$")
    out: list[tuple[int, Path]] = []
    for p in directory.iterdir():
        if not p.is_file():
            continue
        m = pattern.match(p.name)
        if m:
            out.append((int(m.group(1)), p))
    out.sort(key=lambda x: x[0])
    return out


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """
    未適用のマイグレーションを順に実行し、schema_version を更新する。
    """
    current = _current_schema_version(conn)
    for version, path in _migration_files_sorted():
        if version <= current:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute("UPDATE schema_version SET version = ?", (version,))
        conn.commit()


def get_connection() -> sqlite3.Connection:
    """
    DB ファイルへの接続を返す。必要ならマイグレーションを適用してから返す。
    呼び出し側で close すること。コンテキストマネージャは使わず、明示的 close を想定。
    """
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    _apply_migrations(conn)
    return conn
