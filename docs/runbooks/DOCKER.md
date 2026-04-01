# Docker 環境構築手順

Sputnik を Docker 上でビルド・実行する手順です。定義書「0-1 システム憲章」「6 メンテナンス」に沿った再現可能な実行環境を用意します。Compose に **IB Gateway** を含め、runner / cockpit-bot からコンテナ間で API 接続できます。

---

## 前提条件

- Docker および Docker Compose がインストールされていること
- プロジェクトルートに `requirements.txt`・`src/`・`config/`・`scripts/`・`tests/` があること
- **IB 接続を行う場合**: `docker/.env` に IB のユーザーID・パスワードを設定すること（後述）

---

## 0. 環境変数（.env）の設定

Compose で ib-gateway と cockpit-bot（および runner）を動かすには、`docker/` で `.env` を用意します。

```bash
cd docker
cp .env.example .env
# .env を編集し、IB_USERID と IB_PASSWORD を設定
```

- **IB_USERID** / **IB_PASSWORD**: IB Gateway ログイン用（必須・本番では取り扱いに注意）
- **TELEGRAM_TOKEN** / **TELEGRAM_CHAT_ID**: 任意。設定すると **cockpit-bot 起動時**（`up -d` で起動したとき）に Telegram へ「Sputnik Docker 起動」を送信する（`TELEGRAM_STARTUP_MESSAGE` で文言変更可）

`.env` は git にコミットしないでください（`.env.example` のみリポジトリに含めます）。

**`up -d` で環境変数を読ませる**: プロジェクトルートから `docker compose -f docker/docker-compose.yml up -d` するとき、Compose は**カレントディレクトリ**の `.env` を読む。変数を **docker/.env** にだけ置いている場合は、`--env-file docker/.env` を付けるか、`cd docker` してから `docker compose up -d` する。

---

## 1. イメージのビルドと起動

プロジェクトルートで実行します。

```bash
# ビルド（runner / cockpit-bot 用イメージ。ib-gateway は公式イメージを pull）
docker compose -f docker/docker-compose.yml build

# ib-gateway + cockpit-bot を起動（バックグラウンド）。runner は up では起動しない
docker compose -f docker/docker-compose.yml up -d

# 環境変数が docker/.env にある場合は --env-file を付ける（プロジェクトルートから実行するとき）
# docker compose -f docker/docker-compose.yml --env-file docker/.env up -d

# ログ確認（ib-gateway の起動完了を待つ）
docker compose -f docker/docker-compose.yml logs -f ib-gateway
```

**`--force-recreate` は常に必要？** いいえ。compose の **環境変数・ボリューム・イメージ** を変更したときだけ、変更を反映させるために `docker compose -f docker/docker-compose.yml up -d --force-recreate` を使う。通常の再起動は `docker compose -f docker/docker-compose.yml up -d` または `restart` でよい。

### 1.1 変更内容ごとの最小再起動手順

毎回 `down` → `up -d` は不要。通常は対象サービスだけ再起動する。

```bash
# ソースコード / TOML 変更後（通常運用）
docker compose -f docker/docker-compose.yml restart cockpit-bot
```

- `src/`・`scripts/`・`config/` は bind mount されているため、**ファイル変更はコンテナ内に即反映**される。
- ただし Python プロセス再読込のため、`cockpit-bot` プロセスの再起動は必要。

変更別の目安:

- **コード/TOMLのみ変更**: `restart cockpit-bot`
- **`docker/.env` 変更**（IBKR_HOST, TELEGRAM_* など）: `up -d --force-recreate cockpit-bot`
- **`docker-compose.yml` 変更**: 影響サービスだけ `up -d --force-recreate <service>`
- **Dockerfile/依存変更**: `build` 後に `up -d --force-recreate cockpit-bot`
- **ネットワーク含めて全初期化したい場合のみ**: `down` → `up -d`

- **ib-gateway**: IB API サーバ。常時起動。ポート 6080（noVNC）、ホスト側 7497（API）。価格・口座・注文などの API を提供。イメージ内の `/root/Jts` を上書きするボリュームは使わない。
- **cockpit-bot**: Telegram ボット。24h 起動。`/cockpit` で ib-gateway に接続し計器を取得して返す。`restart: unless-stopped`。
- **runner**: テスト・一時スクリプト用。**`up -d` では起動しない**（`profiles: [run]` のため）。都度 `docker compose run --rm runner ...` で pytest や `run_cockpit_with_ib.py` などを実行する。デフォルトコマンドは「起動通知 → pytest」で終了するため常駐させない。

---

## 2. テストの実行

runner コンテナ内で pytest を実行します。

```bash
# デフォルト command が pytest のため、run でそのまま実行
docker compose -f docker/docker-compose.yml run --rm runner

# 特定テストのみ
docker compose -f docker/docker-compose.yml run --rm runner python -m pytest tests/avionics/test_ib_data.py -v

# カバレッジ付き
docker compose -f docker/docker-compose.yml run --rm runner python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

---

## 3. アプリ・スクリプトの実行

### Compose 内で IB に接続する場合（推奨）

runner にはすでに `IBKR_HOST`・`IBKR_PORT` が渡っているため、**引数なし**で実行できます。

```bash
# ib-gateway が起動済みであること。Cockpit + IB サンプル
docker compose -f docker/docker-compose.yml run --rm runner python scripts/tools/run_cockpit_with_ib.py
```

必要なら `--symbols NQ GC` などで上書きできます。

### ホストの IB Gateway に接続する場合

ホストで Gateway を動かしている場合は、従来どおり `--host` / `--port` を指定します（Mac/Windows では `host.docker.internal` が使える場合があります）。

```bash
docker compose -f docker/docker-compose.yml run --rm runner \
  python scripts/tools/run_cockpit_with_ib.py --host host.docker.internal --port 7497   # ホストから見た API は 7497
```

### Telegram で Cockpit を表示する

Telegram から **現在の計器（Cockpit）** を要求して表示するボットを動かせます。

1. `.env` に `TELEGRAM_TOKEN` を設定（Bot トークン）。
2. 同一 compose でボットを常駐させる（24h 稼働推奨）:

```bash
# ib-gateway と cockpit-bot をまとめて起動（バックグラウンド・常時）
docker compose -f docker/docker-compose.yml up -d
```

環境変数（IB_USERID, TELEGRAM_TOKEN 等）が **docker/.env** にだけある場合は、プロジェクトルートから実行するとき `--env-file docker/.env` を付ける。または `cd docker` してから `docker compose up -d` でもよい。  
これで **ib-gateway** と **cockpit-bot** が両方起動する。ボットは `restart: unless-stopped` で落ちても再起動する。

3. Telegram でそのボットに **`/cockpit`** または **`/status`** を送ると、IB から取得した直近の計器（銘柄別モード・理由・raw_metrics）が返ります。  
   **`/ping`** で「接続OK」と現在の IB 接続先（IBKR_HOST:IBKR_PORT）を表示します（ボットが反応するか・設定が読めているかの確認用）。  
   銘柄は環境変数 `TELEGRAM_COCKPIT_SYMBOLS`（省略時 `NQ,GC`）で変更できます。  
   **`/target`** で target_futures を **MNQ/MGC 相当**で表示。**`/settarget <mnq|mgc|nq|gc> …`** で片側更新。更新許可: **`TELEGRAM_TARGET_ADMIN_USER_IDS`**（`user_id` をカンマ区切り）を推奨。**プライベートのみ**なら、通知用 **`TELEGRAM_CHAT_ID`** を自分の `user_id` と同じ数値にしていれば足りる場合がある（ボット再起動後）。**`/ping`** に「settarget 許可ID: N 件」と出る。拒否時はメッセージに自分の `user_id` が出る。

**接続の整理**

- **起動メッセージ**: **cockpit-bot** の起動時（`up -d` のとき）に 1 回送られます。cockpit-bot が再起動すると再送される場合があります。
- **起動メッセージと /cockpit**: どちらも **cockpit-bot** が担当。起動時に通知を送ったあと、同じプロセスでボットが待ち受け、`/cockpit` に反応します。
- **IB 接続先**: ボットは **Docker 内**（cockpit-bot サービス）でのみ動かす想定。compose が `IBKR_HOST=ib-gateway`, `IBKR_PORT=8888` を渡すので追加設定は不要。

**24h 稼働：Docker に統一し、同一 compose でボット常駐（推奨）**

- **同一 Docker でよい**。compose に **cockpit-bot** サービスを入れてあり、`docker compose up -d` で ib-gateway と cockpit-bot が両方起動する。
- ボットは `restart: unless-stopped` で 24h 稼働。落ちても自動再起動する。
- 運用例: `docker compose -f docker/docker-compose.yml up -d` で Gateway ＋ ボットを常時起動（環境変数が読まれること）。`runner` は都度 `docker compose run --rm runner ...` でテストや一時スクリプト用。

**運用は Docker に統一**: ボットは **cockpit-bot サービス（Docker 内）** のみ。`up -d` で ib-gateway と cockpit-bot を起動すれば、同じネットワークで `ib-gateway` が解決され `/cockpit` が動作する。

---

## 4. 開発時のマウント

`docker-compose.yml` では次のディレクトリを runner / cockpit-bot に読み取り専用でマウントしています。

- `../src` → `/app/src`
- `../scripts` → `/app/scripts`
- `../config` → `/app/config`
- `../tests` → `/app/tests`

ソースを編集したあと、再ビルドせずに `docker compose ... run --rm runner` でテスト・スクリプトを実行すれば変更が反映されます。

---

## 5. トラブルシュート

| 現象 | 対処 |
|------|------|
| **VNC 画面が表示できない**（http://localhost:6080 に繋がらない） | (1) ib-gateway が起動しているか `docker compose -f docker/docker-compose.yml ps` で確認。**(2) 起動後 1〜2 分待つ**（noVNC は Xvnc → Gateway のあとに準備できる）。(3) `docker compose ... logs ib-gateway` でエラーや「unable to allocate file descriptor」が出ていないか確認。出ている場合は compose の `ulimits: nofile: 10000` が効いているか確認。(4) ブラウザは **http://localhost:6080**（127.0.0.1 にバインドしているため、他のマシンからは見えない）。 |
| **VNC はつながるが画面が真っ黒** | 正常な場合あり。イメージは ApiOnly で GUI が最小限のため、デスクトップが黒いままになることがある。**API（8888）が応答すれば運用上問題なし**。`run_cockpit_with_ib.py` や Telegram ボットで接続できるかで判断する。 |
| `ModuleNotFoundError: avionics` | コンテナ内の `PYTHONPATH=/app/src` を確認。`docker compose run --rm runner env \| grep PYTHON` |
| IB 接続タイムアウト | ib-gateway のログで「Listening for incoming API connections」を確認。ブラウザで http://localhost:6080 から Gateway 画面を確認。 |
| ペーパー/本番の切り替え | ib-gateway の `TRADING_MODE=paper` を変更（本番は `live` 等。イメージのドキュメント参照）。 |
| `config/factors.toml` がない | `config/` をマウントしているため、プロジェクトの `config/factors.toml` を用意するか、因子を使わないテスト・スクリプトのみ実行する。 |
| **名前解決失敗**（errorno -3） | ホストでボットを動かしている場合（/ping で ib-gateway:7497）: `IBKR_HOST=127.0.0.1 IBKR_PORT=7497` で起動。Docker で /cockpit のみ -3 の場合は api.telegram.org の解決失敗の可能性。dns: 8.8.8.8, 8.8.4.4 とネットワークを確認。 |
| **Error 10141** / **「接続」「承諾」を手動で押す必要がある** | compose で **IBC_AcceptIncomingConnectionAction=accept**（API 接続の自動許可）と **IBC_AcceptNonBrokerageAccountWarning=yes**（Paper 免責の自動承諾）を設定している。これで noVNC で手動操作せずに API が使える。まだ出る場合は `docker compose ... up -d --force-recreate` でコンテナを再作成してから試す。 |
| **clientId 2 already in use** / **TimeoutError** | 別の API クライアントが同じ clientId を使用しているか、上記 10141 で接続が拒否されている。cockpit-bot は **clientId=3** をデフォルトにしている（`IBKR_CLIENT_ID` で変更可）。10141 を解消してから再試行。 |
| /cockpit を送っても何も返ってこない | (1) **`/ping`** で「接続OK」と **IB: 127.0.0.1:8888** が返るか確認（これなら Docker 内で正しく動いている）。(2) 返ればボットは動いているので、60 秒以内にタイムアウトまたは IB 接続失敗のメッセージが返るはず。(3) cockpit-bot は `up -d` で起動し、compose が `IBKR_HOST=127.0.0.1`, `IBKR_PORT=8888` を渡す。 |

---

## やり直し手順（一から実行する場合）

以下は、コンテナを止めてからもう一度ビルド・起動し、Telegram Cockpit ボットまで動かすまでの**詳しい手順**です。プロジェクトルート（`sputnik/`）でターミナルを開いている前提です。

### ステップ 0: 環境変数の確認

```bash
# docker/.env があるか確認
ls -la docker/.env

# なければ作成して編集
cp docker/.env.example docker/.env
nano docker/.env   # または code / vim など
```

**必須**: `IB_USERID` と `IB_PASSWORD` に IB のログインID・パスワードを書く。  
**Telegram を使う場合**: `TELEGRAM_TOKEN` に Bot トークン、必要なら `TELEGRAM_CHAT_ID` も書く。保存して閉じる。

---

### ステップ 1: 既存コンテナの停止・削除

```bash
# Compose で起動したコンテナを止めて削除する（ネットワークは「まだ使われている」と出たら残るが問題なし）
docker compose -f docker/docker-compose.yml down
```

表示で `Container ... Removed` が出れば OK。`Network ... Resource is still in use` は警告なので無視してよい。

---

### ステップ 2: イメージのビルド

```bash
docker compose -f docker/docker-compose.yml build
```

初回や `requirements.txt` を変えたあとは数分かかることがある。完了するまで待つ。

---

### ステップ 3: ib-gateway と cockpit-bot の起動

```bash
# バックグラウンドで起動（環境変数が docker/.env のみの場合は --env-file docker/.env を付ける）
docker compose -f docker/docker-compose.yml up -d

# コンテナが上がっているか確認
docker compose -f docker/docker-compose.yml ps
```

`ib-gateway` と `cockpit-bot` が **Up** になっていればよい。

**ib-gateway の起動を待つ（重要）**:

```bash
# ログで「Listening for incoming API connections」などが出るまで待つ（数十秒〜1分程度）
docker compose -f docker/docker-compose.yml logs -f ib-gateway
```

問題なさそうなら **Ctrl+C** でログ表示をやめる。ブラウザで http://localhost:6080 を開き、Gateway の画面（noVNC）が出れば OK。表示できない場合は下記「VNC 画面が表示できない」を参照。

---

### ステップ 4: （任意）起動メッセージの確認

`.env` に `TELEGRAM_TOKEN` と `TELEGRAM_CHAT_ID` を入れている場合、**cockpit-bot** 起動時（`up -d` のとき）に Telegram に「Sputnik Docker 起動」が送られる。届いていれば通知まわりは正常。  
起動通知の接続確認は固定30秒待ちではなく短い再試行で行うため、通知時刻は起動直後から数秒の範囲で前後する。

---

### ステップ 5: Telegram Cockpit ボットの起動

**cockpit-bot は `up -d` で既に起動している**ため、別途コマンドは不要。ログを確認する場合:

```bash
docker compose -f docker/docker-compose.yml logs -f cockpit-bot
```

- 「Application started」などと出ていればボットはポーリング中。`IB: 127.0.0.1:8888` で IB に接続する設定になっている。

---

### ステップ 6: Telegram で動作確認

1. Telegram で、`.env` の `TELEGRAM_TOKEN` に対応するボットを開く。
2. **`/ping`** を送る → 「接続OK」と **「IB: 127.0.0.1:8888」** が返れば、Docker 内の cockpit-bot として正しく動いている。**「IB: ib-gateway:7497」** と出る場合はホストで動いており、名前解決で -3 になるので後述「ホストでボットを動かす場合」のとおり 127.0.0.1:7497 で起動する。
3. **`/cockpit`** を送る → 「計器取得中…」のあと、最大 60 秒以内に計器レポートか「取得失敗: …」が返る。  
   - タイムアウトや接続失敗のメッセージが出た場合は、ib-gateway のログで「Listening for incoming API connections」を再確認する。

---

### ホストでボットを動かす場合（errorno -3 を避ける）

ボットを **Docker ではなくホスト**で動かす場合、ib-gateway は Docker 内の名前なのでホストからは解決できず -3 になる。**IB は localhost:7497**（ホストにマッピングされたポート）で接続する。

```bash
# プロジェクトルートで。TELEGRAM_TOKEN 等は .env から読むか環境変数で渡す
export TELEGRAM_TOKEN=...
export TELEGRAM_CHAT_ID=...
IBKR_HOST=127.0.0.1 IBKR_PORT=7497 python scripts/bot/telegram_cockpit_bot.py
```

このとき `/ping` では **IB: 127.0.0.1:7497** と出る。

### ボットをバックグラウンドで動かしたい場合（Docker）

通常は **cockpit-bot は `up -d` で常駐**するので、別途 run は不要。以前のように runner でボットを run すると ib-gateway 名前解決で -3 になることがあるため、**Docker で動かす場合は `docker compose -f docker/docker-compose.yml up -d` で cockpit-bot を起動**すること。

---

## まとめ（手順の流れ）

1. **環境変数**: `docker/.env` に `IB_USERID`・`IB_PASSWORD` を設定（`cp docker/.env.example docker/.env`）
2. **ビルド・起動**: `docker compose -f docker/docker-compose.yml up -d`（ib-gateway の起動を待つ）
3. **テスト**: `docker compose -f docker/docker-compose.yml run --rm runner`
4. **Cockpit+IB**: `docker compose -f docker/docker-compose.yml run --rm runner python scripts/tools/run_cockpit_with_ib.py`
5. **Telegram ボット**: `up -d` で cockpit-bot が起動しているので、Telegram で `/ping`（**IB: 127.0.0.1:8888** と出れば OK）→ `/cockpit` を試す

---

## cron で日次バッチ／1h監視を回す（runner を定期起動）

本番（例: AWS EC2）では、`runner` は **常駐させず**、ホスト側の cron から `docker compose run --rm runner ...` を定期実行する。

### 事前準備

- ログ保存先を作る（ホスト側）:

```bash
mkdir -p /home/hiro/projects/Sputnik/logs
```

- cron は PATH が限定的なので、**crontab 冒頭に PATH を明記**する（推奨）。
- また、標準出力が捨てられないように **`>> ... 2>&1` でログへリダイレクト**する（必須）。

### crontab 例

以下は「日次バッチは1日1回」「1h監視は毎時起動（pending が無い日は即終了）」の例。
環境変数は `docker/.env` を使う前提で `--env-file docker/.env` を付ける。

```cron
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
SHELL=/bin/bash

# 日次バッチ（NY クローズ後に 1 回）
# ※時刻は運用で確定する（ET と UTC の対応に注意）
30 5 * * * cd /home/hiro/projects/Sputnik && \
  /usr/bin/flock -n /tmp/sputnik-daily.lock \
  /usr/bin/docker compose -f docker/docker-compose.yml --env-file docker/.env run --rm runner \
  python /app/scripts/batch/run_daily_signal_persist.py \
  >> /home/hiro/projects/Sputnik/logs/daily-persist.log 2>&1

# 1h監視（毎時起動）
0 * * * * cd /home/hiro/projects/Sputnik && \
  /usr/bin/flock -n /tmp/sputnik-vwatch.lock \
  /usr/bin/docker compose -f docker/docker-compose.yml --env-file docker/.env run --rm runner \
  python /app/scripts/batch/run_v_knockin_monitor.py \
  >> /home/hiro/projects/Sputnik/logs/v-monitor.log 2>&1
```

### 補足

- `flock` は **二重起動防止**（同一ホストで同時に走らないようにする）。
- `run_v_knockin_monitor.py` は DB の `knockin_watch` を見て、当日 pending が無ければ **即終了**する。
- 監視日の pending がある場合は、VXN tradingHours から当日のコアタイムを解決し、プロセス内で待機してから 1h ごとに判定する。
