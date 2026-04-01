#!/bin/bash

# プロジェクトの絶対パス（あなたの環境に合わせてください）
PROJECT_DIR="/home/hiro/projects/Sputnik"
LOG_FILE="$PROJECT_DIR/logs/daily_batch.log"

# プロジェクトディレクトリへ移動
cd "$PROJECT_DIR" || exit

# 開始ログを記録
echo "--- Batch Start: $(date) ---" >> "$LOG_FILE" 2>&1

# メイン処理を実行し、結果をログへ追記
/usr/bin/docker compose -f docker/docker-compose.yml --env-file docker/.env run --rm runner \
  python /app/scripts/batch/run_daily_signal_persist.py >> "$LOG_FILE" 2>&1

# 終了ログを記録
echo "--- Batch End: $(date) ---" >> "$LOG_FILE" 2>&1