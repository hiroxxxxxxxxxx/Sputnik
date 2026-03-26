#!/bin/bash
# プロジェクトルートへ移動（絶対パスで指定）
cd /home/hiro/projects/Sputnik

echo "--- Batch Start: $(date) ---"

# Docker Composeでバッチを実行
# --rm を付けることで、実行後にコンテナが残りません（24h稼働でゴミがたまらない）
/usr/bin/docker compose -f docker/docker-compose.yml --env-file docker/.env run --rm runner \
  python /app/scripts/run_daily_signal_persist.py

echo "--- Batch End: $(date) ---"