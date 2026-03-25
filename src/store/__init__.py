"""
データ層: SQLite 接続・マイグレーション・テーブル操作。

計画 B1: デフォルト DB はプロジェクトルート data/sputnik.db。環境変数 SPUTNIK_DB_PATH で上書き可能。
計画 B2: 単一ライター前提。複数プロセスから書く場合はキュー経由または専用書き込みサービスに集約すること。
"""

from .db import get_connection, get_db_path

__all__ = ["get_connection", "get_db_path"]
