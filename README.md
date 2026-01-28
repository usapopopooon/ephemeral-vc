# Discord Util Bot

[![CI](https://github.com/usapopopooon/discord-util-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/usapopopooon/discord-util-bot/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/usapopopooon/discord-util-bot/graph/badge.svg)](https://codecov.io/gh/usapopopooon/discord-util-bot)

Discord の一時ボイスチャンネル管理 Bot。ロビー VC に参加すると専用のボイスチャンネルが自動作成され、全員退出すると自動削除される。Bump リマインダー機能も搭載。

## 機能

### 一時 VC 機能
- **自動 VC 作成**: ロビーチャンネルに参加すると個人用 VC が作成される
- **ボタン UI コントロールパネル**: コマンド不要でチャンネルを管理
  - 🏷️ 名前変更
  - 👥 人数制限
  - 🔊 ビットレート変更
  - 🌏 リージョン変更
  - 🔒 ロック / アンロック
  - 🙈 非表示 / 表示
  - 🔞 年齢制限
  - 👑 オーナー譲渡
  - 👟 キック
  - 🚫 ブロック
  - ✅ 許可 (ロック時に特定ユーザーを許可)
- **自動クリーンアップ**: 全員退出したチャンネルは自動削除
- **複数ロビー対応**: サーバーごとに複数のロビーチャンネルを設定可能

### Bump リマインダー機能
- **DISBOARD / ディス速報対応**: 両サービスの bump 成功メッセージを自動検出
- **2時間後通知**: bump 成功から2時間後にリマインダーを送信
- **Server Bumper ロール必須**: bump を実行したユーザーが `Server Bumper` ロールを持っている場合のみリマインダーを登録
- **通知カスタマイズ**: サービスごとに通知の有効/無効、メンションロールを設定可能
  - デフォルト通知先: `Server Bumper` ロール
  - ボタンからサービスごとに任意のロールに変更可能
- **自動検出**: `/bump setup` 時にチャンネル履歴から直近の bump を検出し、次回通知時刻を計算
- **設定状況の表示**: bump 検知時・セットアップ時に現在の通知先ロールを表示

### その他
- **ヘルスモニタリング**: 10 分ごとにハートビート Embed を送信し死活監視

## 環境変数

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `DISCORD_TOKEN` | Yes | Discord Bot トークン |
| `DATABASE_URL` | No | PostgreSQL 接続 URL (デフォルト: `postgresql+asyncpg://user@localhost/discord_util_bot`) |
| `HEALTH_CHANNEL_ID` | No | ヘルスチェック Embed を送信するチャンネル ID (デフォルト: `0` = 無効) |

## セットアップ

### ローカル開発 (Make)

```bash
git clone https://github.com/usapopopooon/discord-util-bot.git
cd discord-util-bot
cp .env.example .env  # DISCORD_TOKEN を設定
make run
```

### ローカル開発 (手動)

```bash
git clone https://github.com/usapopopooon/discord-util-bot.git
cd discord-util-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # DISCORD_TOKEN を設定
python -m src.main
```

### Docker Compose

```bash
cp .env.example .env  # DISCORD_TOKEN を設定
docker-compose up -d
```

PostgreSQL と Bot が一緒に起動する。

## スラッシュコマンド

### 管理者コマンド

| コマンド | 説明 |
|---------|------|
| `/lobby` | ロビー VC を作成 (管理者のみ) |

### ユーザーコマンド

| コマンド | 説明 |
|---------|------|
| `/panel` | コントロールパネルを再投稿 |
| `/bump setup` | bump 監視を開始 (実行したチャンネルを監視) |
| `/bump status` | bump 監視の設定状況を確認 |
| `/bump disable` | bump 監視を停止 |

## コントロールパネル

ロビーに参加して VC が作成されると、チャンネルにコントロールパネル Embed が送信される。オーナーのみがボタンを操作できる。

| ボタン | 説明 |
|--------|------|
| 🏷️ 名前変更 | チャンネル名を変更 (モーダル入力) |
| 👥 人数制限 | 接続人数の上限を設定 (0 = 無制限) |
| 🔊 ビットレート | 音声ビットレートを選択 |
| 🌏 リージョン | ボイスリージョンを選択 |
| 🔒 ロック | チャンネルをロック / アンロック |
| 🙈 非表示 | チャンネルを非表示 / 表示 |
| 🔞 年齢制限 | NSFW の切り替え |
| 👑 譲渡 | オーナー権限を他のユーザーに譲渡 |
| 👟 キック | ユーザーをチャンネルからキック |
| 🚫 ブロック | ユーザーをブロック (キック + 接続拒否) |
| ✅ 許可 | ロック時に特定ユーザーの接続を許可 |

## プロジェクト構成

```
src/
├── main.py              # エントリーポイント
├── bot.py               # Bot クラス定義
├── config.py            # pydantic-settings による設定管理
├── cogs/
│   ├── admin.py         # /lobby コマンド (管理者用)
│   ├── voice.py         # VC 自動作成・削除、/panel コマンド
│   ├── bump.py          # Bump リマインダー (/bump コマンド)
│   └── health.py        # ハートビート死活監視
├── core/
│   ├── permissions.py   # Discord 権限ヘルパー
│   ├── validators.py    # 入力バリデーション
│   └── builders.py      # チャンネル作成ビルダー
├── database/
│   ├── engine.py        # SQLAlchemy 非同期エンジン
│   └── models.py        # Lobby / VoiceSession モデル
├── services/
│   └── db_service.py    # DB CRUD 操作
└── ui/
    └── control_panel.py # コントロールパネル UI (View / Button / Select)
```

## 開発

### Make コマンド

| コマンド | 説明 |
|---------|------|
| `make setup` | venv 作成 + 依存関係インストール |
| `make run` | Bot を起動 |
| `make test` | テスト実行 |
| `make lint` | Ruff リンター実行 |
| `make typecheck` | mypy 型チェック実行 |
| `make clean` | venv とキャッシュを削除 |

### テスト

```bash
# テスト実行
make test

# カバレッジ付き
.venv/bin/pytest --cov --cov-report=html
```

### CI

GitHub Actions で以下を自動実行:
- Ruff (リンター)
- mypy (型チェック)
- pytest + Codecov (テスト + カバレッジ)

## License

MIT
