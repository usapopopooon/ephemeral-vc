"""SQLAlchemy async engine setup.

非同期データベースエンジンとセッションファクトリを作成する。
アプリ全体で共有する DB 接続の設定をここで一元管理する。

用語:
  - engine: DB への接続を管理するオブジェクト (コネクションプール)
  - session: 1回の DB 操作単位。クエリの実行・コミット・ロールバックを行う
  - sessionmaker: セッションを生成するファクトリ (工場)
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.database.models import Base

# --- 非同期エンジンの作成 ---
# create_async_engine: 非同期で DB に接続するためのエンジンを作る
# echo=False: SQL 文をログに出力しない (True にするとデバッグ時に便利)
engine = create_async_engine(settings.async_database_url, echo=False)

# --- セッションファクトリの作成 ---
# async_sessionmaker: セッション (DB 操作の単位) を生成するファクトリ
# expire_on_commit=False: commit 後もオブジェクトの属性にアクセスできるようにする
#   (False にしないと、commit 後に session.name 等を読むとエラーになる)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """データベーステーブルを初期化する。

    テーブルが存在しなければ作成する (CREATE TABLE IF NOT EXISTS に相当)。
    既存のテーブルは変更しない。スキーマ変更には Alembic マイグレーションを使う。

    engine.begin() でトランザクションを開始し、
    run_sync() で同期関数 (metadata.create_all) を非同期コンテキストから実行する。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """新しい非同期 DB セッションを取得する。

    通常は ``async with async_session() as session:`` の形で直接使うので、
    この関数はあまり使わない。依存注入パターン等で使う想定。
    """
    async with async_session() as session:
        return session
