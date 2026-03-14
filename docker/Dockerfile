# Sputnik（マクロインカム戦略）実行・テスト用コンテナ。
# 定義書「0-1 システム憲章」「6 メンテナンス」参照。ib_async + asyncio のみ使用。

FROM python:3.12-slim

WORKDIR /app

# 依存のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# テスト用（コンテナ内で pytest を回す場合）
RUN pip install --no-cache-dir pytest pytest-cov

# アプリ本体（config はプロジェクトルートの config/）
COPY src ./src
COPY scripts ./scripts
COPY config ./config
COPY tests ./tests
COPY pyproject.toml .

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# デフォルト: テスト実行。上書きして scripts 等を実行可能。
CMD ["python", "-m", "pytest", "tests/", "-v", "--ignore=tests/avionics/test_factors_config.py"]
