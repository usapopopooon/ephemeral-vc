"""Configuration settings using pydantic-settings.

pydantic-settings を使い、.env ファイルや環境変数から設定値を読み込む。
Bot トークンや DB 接続先など、環境ごとに異なる値をここで一元管理する。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """アプリケーション設定。環境変数 / .env から自動で読み込まれる。

    pydantic-settings の仕組み:
      - フィールド名を大文字にした環境変数が自動的にマッピングされる
        例: discord_token → DISCORD_TOKEN
      - デフォルト値があるフィールドは環境変数が無くても動く
    """

    # --- pydantic-settings の設定 ---
    # env_file: 読み込む .env ファイルのパス
    # env_file_encoding: .env ファイルのエンコーディング
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # --- 必須フィールド (環境変数が無いと起動時にエラー) ---
    # Discord Bot のトークン。Discord Developer Portal で取得する
    discord_token: str

    # --- オプションフィールド (デフォルト値あり) ---
    # データベース接続URL。デフォルトはローカルの SQLite ファイル
    database_url: str = "sqlite+aiosqlite:///data/ephemeral_vc.db"

    # ヘルスチェック Embed を送信する Discord チャンネルの ID
    # 0 の場合は Discord への送信をスキップし、ログ出力のみ行う
    health_channel_id: int = 0

    @property
    def async_database_url(self) -> str:
        """DATABASE_URL を非同期ドライバ対応の形式に変換する。

        Heroku は postgres:// で始まる URL を提供するが、
        SQLAlchemy の非同期エンジンは postgresql+asyncpg:// を要求する。
        このプロパティで自動的に変換する。

        変換パターン:
          postgres://...     → postgresql+asyncpg://...  (Heroku 形式)
          postgresql://...   → postgresql+asyncpg://...  (標準 PostgreSQL)
          sqlite+aiosqlite:  → そのまま (変換不要)
        """
        url = self.database_url
        # Heroku uses postgres:// but SQLAlchemy needs postgresql+asyncpg://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


# モジュール読み込み時にインスタンスを1つだけ作成し、アプリ全体で共有する
# pydantic-settings が環境変数から値を注入するため、
# 引数なしのコンストラクタ呼び出しに対する型チェッカー警告を抑制している
settings = Settings()  # type: ignore  [call-arg]
