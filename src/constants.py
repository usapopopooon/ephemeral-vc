"""Application constants.

アプリケーション全体で使用する定数を定義する。
他のモジュールへの依存がないため、どこからでも安全にインポートできる。
"""

# アプリケーション名
APP_NAME = "discord-util-bot"

# DB 名用にハイフンをアンダースコアに変換
DB_NAME = APP_NAME.replace("-", "_")

# テスト用 DB 名
TEST_DB_NAME = f"{DB_NAME}_test"

# デフォルトのデータベース URL (Docker用)
DEFAULT_DATABASE_URL = f"postgresql+asyncpg://user:password@localhost/{DB_NAME}"

# テスト用データベース URL (デフォルト、Docker用)
DEFAULT_TEST_DATABASE_URL = f"postgresql+asyncpg://user:password@localhost/{TEST_DB_NAME}"
DEFAULT_TEST_DATABASE_URL_SYNC = f"postgresql://user:password@localhost/{TEST_DB_NAME}"
