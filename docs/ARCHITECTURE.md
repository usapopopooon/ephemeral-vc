# Discord Util Bot - アーキテクチャ & 設計ドキュメント

このドキュメントは、プロジェクトの仕様・設計方針・実装詳細をまとめたものです。

## プロジェクト概要

Discord の一時ボイスチャンネル管理 Bot + Bump リマインダー + Sticky メッセージ + Web 管理画面。

### 技術スタック

- **Python 3.12**
- **discord.py 2.x** - Discord Bot フレームワーク
- **SQLAlchemy 2.x (async)** - ORM
- **PostgreSQL** - データベース
- **Alembic** - マイグレーション
- **FastAPI** - Web 管理画面
- **pydantic-settings** - 設定管理
- **pytest + pytest-asyncio** - テスト
- **Ruff** - リンター
- **mypy** - 型チェック

## ディレクトリ構成

```
src/
├── main.py              # エントリーポイント (SIGTERM ハンドラ含む)
├── bot.py               # Bot クラス (on_ready, Cog ローダー)
├── config.py            # pydantic-settings による環境変数管理
├── constants.py         # アプリケーション定数
├── cogs/
│   ├── admin.py         # 管理者用コマンド (/vc lobby)
│   ├── voice.py         # VC 自動作成・削除、/vc コマンドグループ
│   ├── bump.py          # Bump リマインダー
│   ├── sticky.py        # Sticky メッセージ
│   └── health.py        # ヘルスチェック (ハートビート)
├── core/
│   ├── permissions.py   # Discord 権限ヘルパー
│   ├── validators.py    # 入力バリデーション
│   └── builders.py      # チャンネル作成ビルダー
├── database/
│   ├── engine.py        # SQLAlchemy 非同期エンジン (SSL/プール設定)
│   └── models.py        # DB モデル定義
├── services/
│   └── db_service.py    # DB CRUD 操作 (ビジネスロジック)
├── ui/
│   └── control_panel.py # コントロールパネル UI (View/Button/Select)
└── web/
    ├── app.py           # FastAPI Web 管理画面
    ├── email_service.py # メール送信サービス (SMTP)
    └── templates.py     # HTML テンプレート

tests/
├── conftest.py          # pytest fixtures (DB セッション等)
├── cogs/
│   ├── test_voice.py
│   ├── test_bump.py
│   ├── test_sticky.py
│   └── test_health.py
├── database/
│   ├── test_engine.py
│   ├── test_models.py
│   └── test_integration.py
├── ui/
│   └── test_control_panel.py
└── web/
    ├── test_app.py
    └── test_email_service.py
```

## データベースモデル

### AdminUser
Web 管理画面のログインユーザー。

```python
class AdminUser(Base):
    id: Mapped[int]                         # PK
    email: Mapped[str]                      # unique
    password_hash: Mapped[str]              # bcrypt ハッシュ
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    password_changed_at: Mapped[datetime | None]
    reset_token: Mapped[str | None]         # パスワードリセット用
    reset_token_expires_at: Mapped[datetime | None]
    pending_email: Mapped[str | None]       # メールアドレス変更待ち
    email_change_token: Mapped[str | None]
    email_change_token_expires_at: Mapped[datetime | None]
    email_verified: Mapped[bool]
```

### Lobby
ロビー VC の設定を保存。

```python
class Lobby(Base):
    id: Mapped[int]                    # PK
    guild_id: Mapped[str]              # Discord サーバー ID
    lobby_channel_id: Mapped[str]      # ロビー VC の ID (unique)
    category_id: Mapped[str | None]    # 作成先カテゴリ ID
    default_user_limit: Mapped[int]    # デフォルト人数制限 (0 = 無制限)
    # relationship: sessions -> VoiceSession[]
```

### VoiceSession
作成された一時 VC を追跡。

```python
class VoiceSession(Base):
    id: Mapped[int]                    # PK
    lobby_id: Mapped[int]              # FK -> Lobby
    channel_id: Mapped[str]            # 作成された VC の ID (unique)
    owner_id: Mapped[str]              # オーナーの Discord ID
    name: Mapped[str]                  # チャンネル名
    user_limit: Mapped[int]            # 人数制限
    is_locked: Mapped[bool]            # ロック状態
    is_hidden: Mapped[bool]            # 非表示状態
    created_at: Mapped[datetime]
    # relationship: lobby -> Lobby
```

### VoiceSessionMember
VC 参加者の join 時刻を記録 (オーナー引き継ぎ用)。

```python
class VoiceSessionMember(Base):
    id: Mapped[int]
    voice_session_id: Mapped[int]      # FK -> VoiceSession (CASCADE)
    user_id: Mapped[str]
    joined_at: Mapped[datetime]
    # unique constraint: (voice_session_id, user_id)
```

### BumpConfig
Bump 監視の設定。

```python
class BumpConfig(Base):
    guild_id: Mapped[str]              # PK
    channel_id: Mapped[str]            # 監視対象チャンネル
    created_at: Mapped[datetime]
```

### BumpReminder
Bump リマインダーの状態。

```python
class BumpReminder(Base):
    id: Mapped[int]
    guild_id: Mapped[str]
    channel_id: Mapped[str]
    service_name: Mapped[str]          # "DISBOARD" or "ディス速報"
    remind_at: Mapped[datetime | None] # 次回リマインド時刻
    is_enabled: Mapped[bool]           # 通知有効/無効
    role_id: Mapped[str | None]        # カスタム通知ロール ID
    # unique constraint: (guild_id, service_name)
```

### StickyMessage
Sticky メッセージの設定。

```python
class StickyMessage(Base):
    channel_id: Mapped[str]            # PK
    guild_id: Mapped[str]
    message_id: Mapped[str | None]     # 現在の sticky メッセージ ID
    message_type: Mapped[str]          # "embed" or "text"
    title: Mapped[str]
    description: Mapped[str]
    color: Mapped[int | None]
    cooldown_seconds: Mapped[int]      # 再投稿までの最小間隔
    last_posted_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
```

## 主要機能の設計

### 1. 一時 VC 機能 (`voice.py` + `control_panel.py`)

#### フロー
1. ユーザーがロビー VC に参加
2. `on_voice_state_update` でイベント検知
3. `VoiceSession` を DB に作成
4. 新しい VC を作成し、ユーザーを移動
5. コントロールパネル Embed + View を送信

#### コントロールパネル
- **永続 View**: `timeout=None` で Bot 再起動後もボタンが動作
- **custom_id**: `{action}:{voice_session_id}` 形式で識別
- **オーナー権限チェック**: 各ボタンの callback で `voice_session.owner_id` と比較

#### パネルボタン (4行構成)
- Row 1: 名前変更、人数制限、ビットレート、リージョン
- Row 2: ロック、非表示、年齢制限、譲渡
- Row 3: キック
- Row 4: ブロック、許可、カメラ禁止、カメラ許可

#### カメラ禁止機能
- `PermissionOverwrite(stream=False)` で配信権限を拒否
- Discord の `stream` 権限はカメラと画面共有の両方を制御
- 解除時は `PermissionOverwrite(stream=None)` で上書きを削除

#### パネル更新方式
- **`refresh_panel_embed()`**: 既存メッセージを `msg.edit()` で更新 (通常の設定変更時)
- **`repost_panel()`**: 旧パネル削除 → 新パネル送信 (オーナー譲渡時、`/panel` コマンド)

### 2. Bump リマインダー機能 (`bump.py`)

#### 対応サービス
| サービス | Bot ID | 検知キーワード |
|---------|--------|---------------|
| DISBOARD | 302050872383242240 | "表示順をアップ" (embed.description) |
| ディス速報 | 761562078095867916 | "アップ" (embed.title/description/message.content) |

#### 検知フロー
1. `on_message` で DISBOARD/ディス速報 Bot のメッセージを監視
2. `_detect_bump_success()` で bump 成功を判定
3. ユーザーが `Server Bumper` ロールを持っているか確認
4. `BumpReminder` を DB に upsert (remind_at = now + 2時間)
5. 検知 Embed + 通知設定ボタンを送信

#### リマインダー送信
- `@tasks.loop(seconds=30)` でループタスク実行
- `get_due_bump_reminders()` で送信予定時刻を過ぎたリマインダーを取得
- 通知先ロール (カスタム or デフォルト) にメンションして Embed 送信
- 送信後 `remind_at` をクリア

#### 通知設定 UI
- **BumpNotificationView**: 通知有効/無効トグル + ロール変更ボタン
- **BumpRoleSelectView**: ロール選択セレクトメニュー + デフォルトに戻すボタン
- サービスごと (DISBOARD/ディス速報) に独立して設定可能

### 3. Sticky メッセージ機能 (`sticky.py`)

#### フロー
1. `/sticky set` コマンドで設定 (Embed or Text を選択)
2. モーダルでタイトル・説明文・色・遅延を入力
3. `StickyMessage` を DB に保存
4. 初回 sticky メッセージを投稿

#### 再投稿フロー
1. `on_message` で新規メッセージを監視
2. 設定されているチャンネルならペンディング処理を開始
3. デバウンス: 遅延秒数後に再投稿 (連続投稿時は最後の1回のみ実行)
4. 古い sticky メッセージを削除
5. 新しい sticky メッセージを投稿
6. DB の `message_id` と `last_posted_at` を更新

#### デバウンス方式
```python
# ペンディングタスクを管理
_pending_tasks: dict[str, asyncio.Task[None]] = {}

async def _schedule_repost(channel_id: str, delay: float):
    # 既存タスクがあればキャンセル
    if channel_id in _pending_tasks:
        _pending_tasks[channel_id].cancel()
    # 新しいタスクをスケジュール
    _pending_tasks[channel_id] = asyncio.create_task(_delayed_repost(...))
```

### 4. Web 管理画面 (`web/app.py`)

#### 認証フロー
1. 初回起動時: 環境変数の `ADMIN_EMAIL` / `ADMIN_PASSWORD` で管理者作成
2. ログイン: メール + パスワードで認証
3. セッション: 署名付き Cookie (itsdangerous)
4. パスワードリセット: SMTP 経由でリセットリンクを送信

#### セキュリティ機能
- **レート制限**: 5分間で5回までのログイン試行
- **セキュア Cookie**: HTTPS 環境でのみ Cookie 送信 (設定可能)
- **セッション有効期限**: 24時間
- **パスワードハッシュ**: bcrypt

#### エンドポイント
| パス | 説明 |
|------|------|
| `/` | ダッシュボード (ログイン必須) |
| `/login` | ログイン画面 |
| `/logout` | ログアウト |
| `/lobbies` | ロビー一覧 |
| `/bump` | Bump 設定一覧 |
| `/sticky` | Sticky メッセージ一覧 |
| `/settings` | 設定画面 (パスワード変更等) |
| `/forgot-password` | パスワードリセット |

### 5. Graceful シャットダウン (`main.py`)

#### SIGTERM ハンドラ
```python
def _handle_sigterm(_signum: int, _frame: FrameType | None) -> None:
    """Heroku のシャットダウン時に SIGTERM を受信"""
    logger.info("Received SIGTERM signal, initiating graceful shutdown...")
    if _bot is not None:
        asyncio.create_task(_shutdown_bot())

async def _shutdown_bot() -> None:
    """Bot を安全に停止"""
    if _bot is not None:
        await _bot.close()
```

### 6. データベース接続設定 (`database/engine.py`)

#### SSL 接続 (Heroku 対応)
```python
DATABASE_REQUIRE_SSL = os.environ.get("DATABASE_REQUIRE_SSL", "").lower() == "true"

def _get_connect_args() -> dict[str, Any]:
    if DATABASE_REQUIRE_SSL:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False  # 自己署名証明書
        ssl_context.verify_mode = ssl.CERT_NONE
        return {"ssl": ssl_context}
    return {}
```

#### コネクションプール
```python
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))

engine = create_async_engine(
    settings.async_database_url,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_pre_ping=True,  # 接続前にpingして無効な接続を検出
    connect_args=_get_connect_args(),
)
```

## 設計原則

### 1. 非同期ファースト
- 全ての DB 操作は `async/await`
- `asyncpg` ドライバを使用
- Cog のイベントハンドラも全て非同期

### 2. DB セッション管理
```python
# コンテキストマネージャで自動 commit/rollback
async with async_session() as session:
    result = await some_db_operation(session, ...)
```

### 3. 永続 View パターン
```python
class MyView(discord.ui.View):
    def __init__(self, some_id: int, ...):
        super().__init__(timeout=None)  # 永続化
        # custom_id に識別子を含める
        self.button.custom_id = f"action:{some_id}"
```

Bot 起動時にダミー View を登録:
```python
async def setup(bot):
    bot.add_view(MyView(0, ...))  # custom_id のプレフィックスでマッチ
```

### 4. エラーハンドリング
```python
# Discord API エラーは suppress で握りつぶすことが多い
with contextlib.suppress(discord.HTTPException):
    await message.delete()
```

### 5. 型ヒント
- 全ての関数に型ヒントを付与
- `mypy --strict` でチェック
- `Mapped[T]` で SQLAlchemy モデルの型を明示

### 6. ドキュメント (docstring)
Google スタイルの docstring を使用:
```python
def function(arg1: str, arg2: int) -> bool:
    """関数の説明。

    Args:
        arg1 (str): 引数1の説明。
        arg2 (int): 引数2の説明。

    Returns:
        bool: 返り値の説明。

    Raises:
        ValueError: エラーの説明。

    Examples:
        使用例::

            result = function("foo", 42)

    See Also:
        - :func:`related_function`: 関連する関数
    """
```

## テスト方針

### モック戦略
- `discord.py` のオブジェクトは `MagicMock(spec=discord.XXX)` でモック
- DB 操作は `patch("src.xxx.async_session")` でセッションをモック
- 個別の DB 関数も `patch()` でモック

### テストヘルパー
```python
def _make_message(...) -> MagicMock:
    """Discord Message のモックを作成"""

def _make_member(has_target_role: bool) -> MagicMock:
    """Discord Member のモックを作成"""

def _make_reminder(...) -> MagicMock:
    """BumpReminder のモックを作成"""
```

### テスト実行
```bash
# 通常実行
DISCORD_TOKEN=test-token pytest

# カバレッジ付き
DISCORD_TOKEN=test-token pytest --cov --cov-report=term-missing

# 特定ファイル
DISCORD_TOKEN=test-token pytest tests/cogs/test_bump.py -v
```

## 実装時の注意点

### 1. Discord ID は文字列で保存
- DB には `str` で保存 (bigint の精度問題を回避)
- 使用時に `int()` で変換

### 2. ロール検索
```python
# 名前で検索 (デフォルトロール)
role = discord.utils.get(guild.roles, name="Server Bumper")

# ID で検索 (カスタムロール)
role = guild.get_role(int(role_id))
```

### 3. Discord タイムスタンプ
```python
ts = int(datetime_obj.timestamp())
f"<t:{ts}:t>"  # 短い時刻 (例: 21:30)
f"<t:{ts}:R>"  # 相対時刻 (例: 2時間後)
f"<t:{ts}:F>"  # フル表示 (例: 2024年1月15日 21:30)
```

### 4. Embed の description は改行で構造化
```python
description = (
    f"**項目1:** {value1}\n"
    f"**項目2:** {value2}\n\n"
    f"説明文..."
)
```

### 5. 環境変数の URL 変換
```python
# Heroku は postgres:// を使用、SQLAlchemy は postgresql+asyncpg:// を要求
@property
def async_database_url(self) -> str:
    url = self.database_url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url
```

## よくあるタスク

### 新しいボタンを追加
1. `control_panel.py` の `ControlPanelView` にボタンを追加
2. callback でオーナー権限チェック
3. 処理後に `refresh_panel_embed()` または `repost_panel()` を呼ぶ
4. テストを追加

### 新しいスラッシュコマンドを追加
1. 適切な Cog に `@app_commands.command()` を追加
2. ギルド専用なら最初に `interaction.guild` をチェック
3. `interaction.response.send_message()` で応答
4. テストを追加

### DB モデルを変更
1. `models.py` を編集
2. `alembic revision --autogenerate -m "説明"` でマイグレーション生成
3. `alembic upgrade head` で適用
4. 関連する `db_service.py` の関数を更新
5. テストを更新

### 新しい Cog を追加
1. `src/cogs/` に新しいファイルを作成
2. `Cog` クラスを定義し、`setup()` 関数をエクスポート
3. `bot.py` の `setup_hook()` で `load_extension()` を追加
4. テストを追加

### 新しい Web エンドポイントを追加
1. `src/web/app.py` にルートを追加
2. 認証が必要なら `get_current_user()` を Depends に追加
3. テンプレートが必要なら `src/web/templates.py` に追加
4. テストを追加

## CI/CD

### GitHub Actions
- cspell (スペルチェック)
- JSON / YAML / TOML lint (構文チェック)
- Ruff format (フォーマットチェック)
- Ruff check (リンター)
- mypy 型チェック
- pytest + Codecov (カバレッジ 98%+)

### Heroku デプロイ
- `main` ブランチへの push でテストが実行される
- GitHub Actions で手動トリガーによりテスト → デプロイ
- デプロイ = Bot 再起動
- SIGTERM で graceful シャットダウン

**ローカルからの手動デプロイは禁止**
- バージョンの齟齬が発生する可能性がある
- テストの見逃しが起こる可能性がある
- 必ず GitHub Actions 経由でデプロイすること

### 必要な環境変数 (Heroku)
```
DISCORD_TOKEN=xxx
DATABASE_URL=(自動設定)
DATABASE_REQUIRE_SSL=true
```

## 関連リンク

- [discord.py ドキュメント](https://discordpy.readthedocs.io/)
- [SQLAlchemy 2.0 ドキュメント](https://docs.sqlalchemy.org/en/20/)
- [FastAPI ドキュメント](https://fastapi.tiangolo.com/)
- [Alembic ドキュメント](https://alembic.sqlalchemy.org/)
- [DISBOARD](https://disboard.org/)
