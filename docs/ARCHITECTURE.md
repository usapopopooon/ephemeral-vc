# Discord Util Bot - アーキテクチャ & 設計ドキュメント

このドキュメントは、プロジェクトの仕様・設計方針・実装詳細をまとめたものです。

## プロジェクト概要

Discord の一時ボイスチャンネル管理 Bot + Bump リマインダー機能。

### 技術スタック

- **Python 3.12**
- **discord.py 2.x** - Discord Bot フレームワーク
- **SQLAlchemy 2.x (async)** - ORM
- **PostgreSQL** - データベース
- **Alembic** - マイグレーション
- **pytest + pytest-asyncio** - テスト
- **Ruff** - リンター
- **mypy** - 型チェック

## ディレクトリ構成

```
src/
├── main.py              # エントリーポイント
├── bot.py               # Bot クラス (on_ready, Cog ローダー)
├── config.py            # pydantic-settings による環境変数管理
├── cogs/
│   ├── admin.py         # /lobby コマンド
│   ├── voice.py         # VC 自動作成・削除、/panel コマンド
│   ├── bump.py          # Bump リマインダー
│   └── health.py        # ヘルスチェック (ハートビート)
├── core/
│   ├── permissions.py   # Discord 権限ヘルパー
│   ├── validators.py    # 入力バリデーション
│   └── builders.py      # チャンネル作成ビルダー
├── database/
│   ├── engine.py        # SQLAlchemy 非同期エンジン
│   └── models.py        # DB モデル定義
├── services/
│   └── db_service.py    # DB CRUD 操作 (ビジネスロジック)
└── ui/
    └── control_panel.py # コントロールパネル UI (View/Button/Select)

tests/
├── conftest.py          # pytest fixtures (DB セッション等)
├── cogs/
│   ├── test_voice.py
│   └── test_bump.py
└── ui/
    └── test_control_panel.py
```

## データベースモデル

### Lobby
ロビー VC の設定を保存。

```python
class Lobby(Base):
    id: Mapped[int]                    # PK
    guild_id: Mapped[str]              # Discord サーバー ID
    channel_id: Mapped[str]            # ロビー VC の ID
    category_id: Mapped[str | None]    # 作成先カテゴリ ID
    created_at: Mapped[datetime]
```

### VoiceSession
作成された一時 VC を追跡。

```python
class VoiceSession(Base):
    id: Mapped[int]                    # PK
    lobby_id: Mapped[int]              # FK -> Lobby
    channel_id: Mapped[str]            # 作成された VC の ID
    owner_id: Mapped[str]              # オーナーの Discord ID
    is_locked: Mapped[bool]            # ロック状態
    is_hidden: Mapped[bool]            # 非表示状態
    created_at: Mapped[datetime]
```

### VoiceSessionMember
VC 参加者の join 時刻を記録 (参加時間計測用)。

```python
class VoiceSessionMember(Base):
    id: Mapped[int]
    voice_session_id: Mapped[int]      # FK -> VoiceSession
    user_id: Mapped[str]
    joined_at: Mapped[datetime]
```

### BumpConfig
Bump 監視の設定。

```python
class BumpConfig(Base):
    id: Mapped[int]
    guild_id: Mapped[str]              # unique
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
    created_at: Mapped[datetime]
    # unique constraint: (guild_id, service_name)
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

#### 表示される情報
- bump 検知時: リマインド時刻 (`<t:timestamp:t>` 形式) + 現在の通知先ロール
- `/bump setup`: 監視チャンネル + 通知先ロール + 直近の bump 情報
- `/bump status`: 監視チャンネル + 設定日時 + 各サービスの通知先ロール

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

## CI/CD

### GitHub Actions
- Ruff リント
- mypy 型チェック
- pytest + Codecov

### Heroku デプロイ
- `main` ブランチへの push で自動デプロイ
- デプロイ = Bot 再起動

## 関連リンク

- [discord.py ドキュメント](https://discordpy.readthedocs.io/)
- [SQLAlchemy 2.0 ドキュメント](https://docs.sqlalchemy.org/en/20/)
- [DISBOARD](https://disboard.org/)
