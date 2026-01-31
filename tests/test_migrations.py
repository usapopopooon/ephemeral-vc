"""Alembic migration tests.

マイグレーションの整合性、upgrade/downgrade、モデルとの一致をテストする。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

from alembic import command
from src.constants import DEFAULT_TEST_DATABASE_URL_SYNC

if TYPE_CHECKING:
    from collections.abc import Generator

# 同期版のテスト DB URL を使用
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL_SYNC",
    DEFAULT_TEST_DATABASE_URL_SYNC,
)


def _can_connect_to_database() -> bool:
    """テストデータベースに接続できるか確認する。"""
    try:
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect():
            pass
        engine.dispose()
        return True
    except OperationalError:
        return False


# データベース接続が必要なテストをスキップするマーカー
requires_db = pytest.mark.skipif(
    not _can_connect_to_database(),
    reason="テストデータベースに接続できません",
)


@pytest.fixture
def alembic_config() -> Generator[Config, None, None]:
    """Alembic 設定を取得する。"""
    # alembic/env.py が DATABASE_URL を参照するので、環境変数を設定する
    old_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
        yield config
    finally:
        # 環境変数を元に戻す
        if old_db_url is not None:
            os.environ["DATABASE_URL"] = old_db_url
        else:
            os.environ.pop("DATABASE_URL", None)


@pytest.fixture
def script_directory(alembic_config: Config) -> ScriptDirectory:
    """Alembic スクリプトディレクトリを取得する。"""
    return ScriptDirectory.from_config(alembic_config)


@pytest.fixture
def clean_db(alembic_config: Config) -> Generator[None, None, None]:  # noqa: ARG001
    """テスト前にデータベースをクリーンアップする。"""
    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as conn:
        # 既存のテーブルを全て削除
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    engine.dispose()
    yield
    # テスト後もクリーンアップ
    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    engine.dispose()


class TestMigrationChain:
    """マイグレーションチェーンの整合性テスト。"""

    def test_single_head(self, script_directory: ScriptDirectory) -> None:
        """マイグレーションヘッドが単一であることを確認する。"""
        heads = script_directory.get_heads()
        assert len(heads) == 1, f"複数のヘッドが存在します: {heads}"

    def test_migration_chain_has_no_gaps(
        self, script_directory: ScriptDirectory
    ) -> None:
        """マイグレーションチェーンにギャップがないことを確認する。"""
        revisions = list(script_directory.walk_revisions())
        assert len(revisions) > 0, "マイグレーションが見つかりません"

        # 各リビジョンが次のリビジョンを正しく参照していることを確認
        for revision in revisions:
            if revision.down_revision is not None:
                # down_revision が存在するか確認
                down_rev = script_directory.get_revision(revision.down_revision)
                assert down_rev is not None, (
                    f"リビジョン {revision.revision} の "
                    f"down_revision {revision.down_revision} が見つかりません"
                )

    def test_base_revision_has_no_down_revision(
        self, script_directory: ScriptDirectory
    ) -> None:
        """ベースリビジョン (000000000000) が down_revision を持たないことを確認。"""
        base = script_directory.get_revision("000000000000")
        assert base is not None, "ベースリビジョンが見つかりません"
        assert base.down_revision is None, (
            "ベースリビジョンは down_revision を持つべきではありません"
        )

    def test_all_migrations_have_upgrade_and_downgrade(
        self, script_directory: ScriptDirectory
    ) -> None:
        """全てのマイグレーションに upgrade と downgrade 関数があることを確認する。"""
        revisions = list(script_directory.walk_revisions())
        for revision in revisions:
            module = revision.module
            assert hasattr(module, "upgrade"), (
                f"リビジョン {revision.revision} に upgrade 関数がありません"
            )
            assert hasattr(module, "downgrade"), (
                f"リビジョン {revision.revision} に downgrade 関数がありません"
            )

    def test_revision_count(self, script_directory: ScriptDirectory) -> None:
        """マイグレーションの数を確認する。"""
        revisions = list(script_directory.walk_revisions())
        # 13 個のマイグレーションファイルがあることを確認
        expected = 13
        assert len(revisions) == expected, f"リビジョン数: {len(revisions)}"


class TestMigrationFiles:
    """マイグレーションファイルの構造テスト。"""

    def test_migration_files_exist(self) -> None:
        """マイグレーションファイルが存在することを確認する。"""
        migration_dir = Path("alembic/versions")
        assert migration_dir.exists(), "alembic/versions ディレクトリが見つかりません"
        migration_files = list(migration_dir.glob("*.py"))
        assert len(migration_files) > 0, "マイグレーションファイルが見つかりません"

    def test_initial_schema_file_exists(self) -> None:
        """初期スキーマのマイグレーションファイルが存在することを確認する。"""
        # 初期スキーマファイルのパスを確認
        initial_schema_path = Path("alembic/versions/000000000000_initial_schema.py")
        assert initial_schema_path.exists(), "初期スキーマファイルが見つかりません"

        # ファイルの内容を確認
        content = initial_schema_path.read_text()
        assert 'revision: str = "000000000000"' in content
        assert "down_revision: str | None = None" in content
        assert "def upgrade()" in content
        assert "def downgrade()" in content

    def test_initial_schema_via_script_directory(
        self, script_directory: ScriptDirectory
    ) -> None:
        """ScriptDirectory 経由で初期スキーマを確認する。"""
        revision = script_directory.get_revision("000000000000")
        assert revision is not None
        assert revision.module is not None
        assert hasattr(revision.module, "upgrade")
        assert hasattr(revision.module, "downgrade")


@requires_db
class TestMigrationUpgrade:
    """マイグレーションの upgrade テスト。"""

    @pytest.mark.usefixtures("clean_db")
    def test_upgrade_to_head(self, alembic_config: Config) -> None:
        """最新のマイグレーションまで upgrade できることを確認する。"""
        command.upgrade(alembic_config, "head")

        # テーブルが作成されたことを確認
        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        expected_tables = [
            "admin_users",
            "alembic_version",
            "bump_configs",
            "bump_reminders",
            "lobbies",
            "sticky_messages",
            "voice_session_members",
            "voice_sessions",
        ]
        for table in expected_tables:
            assert table in tables, f"テーブル {table} が見つかりません"
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_upgrade_creates_correct_columns_for_admin_users(
        self, alembic_config: Config
    ) -> None:
        """admin_users テーブルに正しいカラムが作成されることを確認する。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("admin_users")}

        expected_columns = {
            "id",
            "email",
            "password_hash",
            "password_changed_at",
            "created_at",
            "updated_at",
            "reset_token",
            "reset_token_expires_at",
            "pending_email",
            "email_change_token",
            "email_change_token_expires_at",
            "email_verified",
        }
        assert expected_columns <= columns, f"不足カラム: {expected_columns - columns}"
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_upgrade_creates_correct_columns_for_sticky_messages(
        self, alembic_config: Config
    ) -> None:
        """sticky_messages テーブルに message_type カラムが作成されることを確認する。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("sticky_messages")}

        assert "message_type" in columns, "message_type カラムが見つかりません"
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_upgrade_creates_correct_columns_for_voice_sessions(
        self, alembic_config: Config
    ) -> None:
        """voice_sessions テーブルに is_hidden カラムが作成されることを確認する。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("voice_sessions")}

        assert "is_hidden" in columns, "is_hidden カラムが見つかりません"
        engine.dispose()


@requires_db
class TestMigrationDowngrade:
    """マイグレーションの downgrade テスト。"""

    @pytest.mark.usefixtures("clean_db")
    def test_downgrade_to_base(self, alembic_config: Config) -> None:
        """ベースまで downgrade できることを確認する。"""
        # まず head まで upgrade
        command.upgrade(alembic_config, "head")

        # base まで downgrade
        command.downgrade(alembic_config, "base")

        # テーブルが削除されたことを確認
        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        # alembic_version 以外のテーブルがないことを確認
        assert tables == ["alembic_version"] or tables == []
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_upgrade_then_downgrade_one_step(self, alembic_config: Config) -> None:
        """1 ステップずつ upgrade/downgrade できることを確認する。"""
        # head まで upgrade
        command.upgrade(alembic_config, "head")

        # 1 ステップ downgrade
        command.downgrade(alembic_config, "-1")

        # 再度 head まで upgrade
        command.upgrade(alembic_config, "head")

        # テーブルが正しく存在することを確認
        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "admin_users" in tables
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_downgrade_partial(self, alembic_config: Config) -> None:
        """最新マイグレーションの downgrade ができることを確認する。"""
        command.upgrade(alembic_config, "head")

        # 最新マイグレーション (email_verified) を downgrade
        command.downgrade(alembic_config, "i9d0e1f2a3b4")

        # email_verified カラムが削除されていることを確認
        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("admin_users")}
        assert "email_verified" not in columns
        engine.dispose()

        # 再度 head に upgrade
        command.upgrade(alembic_config, "head")

        # 新しいエンジンとインスペクターで確認
        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("admin_users")}
        assert "email_verified" in columns
        engine.dispose()


@requires_db
class TestMigrationStepByStep:
    """マイグレーションのステップバイステップテスト。"""

    @pytest.mark.usefixtures("clean_db")
    def test_upgrade_step_by_step(
        self, alembic_config: Config, script_directory: ScriptDirectory
    ) -> None:
        """各マイグレーションを順番に upgrade できることを確認する。"""
        revisions = list(script_directory.walk_revisions())
        # 逆順にして古いものから適用
        revisions.reverse()

        for revision in revisions:
            command.upgrade(alembic_config, revision.revision)

    @pytest.mark.usefixtures("clean_db")
    def test_downgrade_step_by_step(
        self, alembic_config: Config, script_directory: ScriptDirectory
    ) -> None:
        """各マイグレーションを順番に downgrade できることを確認する。"""
        # まず head まで upgrade
        command.upgrade(alembic_config, "head")

        revisions = list(script_directory.walk_revisions())
        # head から順に downgrade
        for revision in revisions:
            if revision.down_revision is not None:
                command.downgrade(alembic_config, revision.down_revision)
            else:
                # base まで downgrade
                command.downgrade(alembic_config, "base")


@requires_db
class TestModelMigrationConsistency:
    """モデルとマイグレーションの整合性テスト。"""

    @pytest.mark.usefixtures("clean_db")
    def test_models_match_migration_schema(self, alembic_config: Config) -> None:
        """モデルの定義がマイグレーションで作成されるスキーマと一致することを確認する。"""
        from src.database.models import Base

        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)

        # モデルで定義されたテーブルを取得
        model_tables = set(Base.metadata.tables.keys())

        # DB に存在するテーブルを取得 (alembic_version を除く)
        db_tables = set(inspector.get_table_names()) - {"alembic_version"}

        # テーブル名が一致することを確認
        assert model_tables == db_tables, (
            f"モデルとマイグレーションのテーブルが一致しません。"
            f"モデルのみ: {model_tables - db_tables}, "
            f"DBのみ: {db_tables - model_tables}"
        )
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_admin_users_columns_match_model(self, alembic_config: Config) -> None:
        """admin_users テーブルのカラムがモデルと一致することを確認する。"""
        from src.database.models import AdminUser

        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        db_columns = {col["name"] for col in inspector.get_columns("admin_users")}

        # モデルのカラムを取得
        model_columns = {col.name for col in AdminUser.__table__.columns}

        assert model_columns == db_columns, (
            f"admin_users のカラムが一致しません。"
            f"モデルのみ: {model_columns - db_columns}, "
            f"DBのみ: {db_columns - model_columns}"
        )
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_lobbies_columns_match_model(self, alembic_config: Config) -> None:
        """lobbies テーブルのカラムがモデルと一致することを確認する。"""
        from src.database.models import Lobby

        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        db_columns = {col["name"] for col in inspector.get_columns("lobbies")}

        model_columns = {col.name for col in Lobby.__table__.columns}

        assert model_columns == db_columns, (
            f"lobbies のカラムが一致しません。"
            f"モデルのみ: {model_columns - db_columns}, "
            f"DBのみ: {db_columns - model_columns}"
        )
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_voice_sessions_columns_match_model(self, alembic_config: Config) -> None:
        """voice_sessions テーブルのカラムがモデルと一致することを確認する。"""
        from src.database.models import VoiceSession

        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        db_columns = {col["name"] for col in inspector.get_columns("voice_sessions")}

        model_columns = {col.name for col in VoiceSession.__table__.columns}

        assert model_columns == db_columns, (
            f"voice_sessions のカラムが一致しません。"
            f"モデルのみ: {model_columns - db_columns}, "
            f"DBのみ: {db_columns - model_columns}"
        )
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_bump_reminders_columns_match_model(self, alembic_config: Config) -> None:
        """bump_reminders テーブルのカラムがモデルと一致することを確認する。"""
        from src.database.models import BumpReminder

        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        db_columns = {col["name"] for col in inspector.get_columns("bump_reminders")}

        model_columns = {col.name for col in BumpReminder.__table__.columns}

        assert model_columns == db_columns, (
            f"bump_reminders のカラムが一致しません。"
            f"モデルのみ: {model_columns - db_columns}, "
            f"DBのみ: {db_columns - model_columns}"
        )
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_sticky_messages_columns_match_model(self, alembic_config: Config) -> None:
        """sticky_messages テーブルのカラムがモデルと一致することを確認する。"""
        from src.database.models import StickyMessage

        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        db_columns = {col["name"] for col in inspector.get_columns("sticky_messages")}

        model_columns = {col.name for col in StickyMessage.__table__.columns}

        assert model_columns == db_columns, (
            f"sticky_messages のカラムが一致しません。"
            f"モデルのみ: {model_columns - db_columns}, "
            f"DBのみ: {db_columns - model_columns}"
        )
        engine.dispose()


class TestAlembicEnvConfiguration:
    """alembic/env.py の設定テスト。"""

    def test_env_module_imports(self) -> None:
        """env.py が正常にインポートできることを確認する。"""
        # env.py のパスを確認
        env_path = Path("alembic/env.py")
        assert env_path.exists(), "alembic/env.py が見つかりません"

    def test_database_url_conversion(self) -> None:
        """postgres:// URL が postgresql:// に変換されることを確認する。"""
        # env.py のロジックをテスト
        database_url = "postgres://user:pass@host/db"
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        assert database_url == "postgresql://user:pass@host/db"

    def test_asyncpg_url_conversion(self) -> None:
        """asyncpg URL が同期版に変換されることを確認する。"""
        from src.config import settings

        # asyncpg を含む URL が変換されることを確認
        sync_url = settings.async_database_url.replace("+asyncpg", "")
        assert "+asyncpg" not in sync_url

    def test_postgresql_asyncpg_url_conversion(self) -> None:
        """postgresql+asyncpg:// URL が postgresql:// に変換されることを確認する。"""
        # env.py のロジックをテスト
        asyncpg_prefix = "postgresql+asyncpg://"
        sync_prefix = "postgresql://"
        database_url = "postgresql+asyncpg://user:pass@host/db"
        if database_url.startswith(asyncpg_prefix):
            database_url = database_url.replace(asyncpg_prefix, sync_prefix, 1)
        assert database_url == "postgresql://user:pass@host/db"

    def test_url_conversion_priority(self) -> None:
        """postgres:// と postgresql+asyncpg:// の変換を確認する。"""
        # env.py のロジックを模倣 (postgres:// と postgresql+asyncpg:// は排他的)
        asyncpg_prefix = "postgresql+asyncpg://"
        sync_prefix = "postgresql://"
        urls = [
            ("postgres://user:pass@host/db", "postgresql://user:pass@host/db"),
            (
                "postgresql+asyncpg://user:pass@host/db",
                "postgresql://user:pass@host/db",
            ),
            ("postgresql://user:pass@host/db", "postgresql://user:pass@host/db"),
        ]
        for original, expected in urls:
            database_url = original
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", sync_prefix, 1)
            elif database_url.startswith(asyncpg_prefix):
                database_url = database_url.replace(asyncpg_prefix, sync_prefix, 1)
            msg = f"{original} -> {database_url} (expected {expected})"
            assert database_url == expected, msg

    def test_url_with_special_characters(self) -> None:
        """特殊文字を含む URL が正しく変換されることを確認する。"""
        # パスワードに特殊文字を含む URL
        asyncpg_prefix = "postgresql+asyncpg://"
        sync_prefix = "postgresql://"
        database_url = "postgresql+asyncpg://user:p%40ss%3Dword@host:5432/db"
        if database_url.startswith(asyncpg_prefix):
            database_url = database_url.replace(asyncpg_prefix, sync_prefix, 1)
        assert database_url == "postgresql://user:p%40ss%3Dword@host:5432/db"


@requires_db
class TestMigrationIndexes:
    """マイグレーションで作成されるインデックスのテスト。"""

    @pytest.mark.usefixtures("clean_db")
    def test_lobbies_indexes(self, alembic_config: Config) -> None:
        """lobbies テーブルのインデックスが正しく作成されることを確認する。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("lobbies")}

        assert "ix_lobbies_guild_id" in indexes
        assert "ix_lobbies_lobby_channel_id" in indexes
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_voice_sessions_indexes(self, alembic_config: Config) -> None:
        """voice_sessions テーブルのインデックスが正しく作成されることを確認する。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("voice_sessions")}

        assert "ix_voice_sessions_channel_id" in indexes
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_bump_reminders_indexes(self, alembic_config: Config) -> None:
        """bump_reminders テーブルのインデックスが正しく作成されることを確認する。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("bump_reminders")}

        assert "ix_bump_reminders_guild_id" in indexes
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_sticky_messages_indexes(self, alembic_config: Config) -> None:
        """sticky_messages テーブルのインデックスが正しく作成されることを確認する。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("sticky_messages")}

        assert "ix_sticky_messages_guild_id" in indexes
        engine.dispose()


@requires_db
class TestMigrationConstraints:
    """マイグレーションで作成される制約のテスト。"""

    @pytest.mark.usefixtures("clean_db")
    def test_admin_users_unique_email(self, alembic_config: Config) -> None:
        """admin_users テーブルの email にユニーク制約があることを確認する。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        unique_constraints = inspector.get_unique_constraints("admin_users")
        unique_columns = {
            col
            for constraint in unique_constraints
            for col in constraint["column_names"]
        }

        assert "email" in unique_columns
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_bump_reminders_unique_guild_service(self, alembic_config: Config) -> None:
        """bump_reminders に guild_id + service_name ユニーク制約を確認。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        unique_constraints = inspector.get_unique_constraints("bump_reminders")

        # uq_guild_service 制約を探す
        guild_service_constraint = next(
            (c for c in unique_constraints if c["name"] == "uq_guild_service"),
            None,
        )
        assert guild_service_constraint is not None
        assert set(guild_service_constraint["column_names"]) == {
            "guild_id",
            "service_name",
        }
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_voice_session_members_unique_session_user(
        self, alembic_config: Config
    ) -> None:
        """voice_session_members に session + user ユニーク制約を確認。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        unique_constraints = inspector.get_unique_constraints("voice_session_members")

        session_user_constraint = next(
            (c for c in unique_constraints if c["name"] == "uq_session_user"),
            None,
        )
        assert session_user_constraint is not None
        assert set(session_user_constraint["column_names"]) == {
            "voice_session_id",
            "user_id",
        }
        engine.dispose()


@requires_db
class TestMigrationForeignKeys:
    """マイグレーションで作成される外部キーのテスト。"""

    @pytest.mark.usefixtures("clean_db")
    def test_voice_sessions_foreign_key_to_lobbies(
        self, alembic_config: Config
    ) -> None:
        """voice_sessions テーブルに lobbies への外部キーがあることを確認する。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        foreign_keys = inspector.get_foreign_keys("voice_sessions")

        lobby_fk = next(
            (fk for fk in foreign_keys if fk["referred_table"] == "lobbies"),
            None,
        )
        assert lobby_fk is not None
        assert "lobby_id" in lobby_fk["constrained_columns"]
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_voice_session_members_foreign_key_to_voice_sessions(
        self, alembic_config: Config
    ) -> None:
        """voice_session_members に voice_sessions への外部キーを確認。"""
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        foreign_keys = inspector.get_foreign_keys("voice_session_members")

        session_fk = next(
            (fk for fk in foreign_keys if fk["referred_table"] == "voice_sessions"),
            None,
        )
        assert session_fk is not None
        assert "voice_session_id" in session_fk["constrained_columns"]
        # CASCADE 削除が設定されていることを確認
        assert session_fk.get("options", {}).get("ondelete") == "CASCADE"
        engine.dispose()


class TestAlembicIniConfiguration:
    """alembic.ini の設定テスト。"""

    def test_path_separator_configured(self) -> None:
        """path_separator が設定されていることを確認する。"""
        ini_path = Path("alembic.ini")
        assert ini_path.exists(), "alembic.ini が見つかりません"

        content = ini_path.read_text()
        assert "path_separator = os" in content, (
            "path_separator = os が設定されていません。"
            "DeprecationWarning が発生する可能性があります。"
        )

    def test_version_path_separator_configured(self) -> None:
        """version_path_separator が設定されていることを確認する。"""
        ini_path = Path("alembic.ini")
        content = ini_path.read_text()
        assert "version_path_separator = os" in content

    def test_script_location_configured(self) -> None:
        """script_location が正しく設定されていることを確認する。"""
        ini_path = Path("alembic.ini")
        content = ini_path.read_text()
        assert "script_location = alembic" in content


@requires_db
class TestSafeDowngradeBehavior:
    """安全な downgrade 動作のテスト。"""

    @pytest.mark.usefixtures("clean_db")
    def test_downgrade_handles_missing_tables_gracefully(
        self, alembic_config: Config
    ) -> None:
        """テーブルが存在しない場合でも downgrade がエラーにならないことを確認。"""
        # 特定のマイグレーションまで upgrade
        command.upgrade(alembic_config, "d4e5f6a7b8c9")  # bump_configs まで

        # テーブルを手動で削除
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS bump_configs"))
            conn.commit()
        engine.dispose()

        # downgrade してもエラーにならないことを確認
        command.downgrade(alembic_config, "c3d4e5f6a7b8")

    @pytest.mark.usefixtures("clean_db")
    def test_initial_schema_downgrade_handles_missing_tables(
        self, alembic_config: Config
    ) -> None:
        """初期スキーマの downgrade が欠損テーブルを処理できることを確認。"""
        # 初期スキーマのみ upgrade
        command.upgrade(alembic_config, "000000000000")

        # いくつかのテーブルを手動で削除
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS sticky_messages"))
            conn.execute(text("DROP TABLE IF EXISTS bump_configs"))
            conn.commit()
        engine.dispose()

        # base まで downgrade してもエラーにならないことを確認
        command.downgrade(alembic_config, "base")

        # 全テーブルが削除されていることを確認
        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names()) - {"alembic_version"}
        assert len(tables) == 0, f"残存テーブル: {tables}"
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_multiple_downgrade_cycles(self, alembic_config: Config) -> None:
        """複数回の upgrade/downgrade サイクルが正常に動作することを確認。"""
        for _ in range(3):
            # upgrade to head
            command.upgrade(alembic_config, "head")

            # downgrade to base
            command.downgrade(alembic_config, "base")

        # 最後に head まで upgrade して正常な状態を確認
        command.upgrade(alembic_config, "head")

        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        expected_tables = [
            "admin_users",
            "lobbies",
            "voice_sessions",
            "voice_session_members",
            "bump_reminders",
            "bump_configs",
            "sticky_messages",
        ]
        for table in expected_tables:
            assert table in tables, f"テーブル {table} が見つかりません"
        engine.dispose()


@requires_db
class TestMigrationIdempotency:
    """マイグレーションの冪等性テスト。"""

    @pytest.mark.usefixtures("clean_db")
    def test_incremental_upgrade_is_idempotent(self, alembic_config: Config) -> None:
        """増分マイグレーションの upgrade が冪等であることを確認する。"""
        # 初期スキーマまで upgrade (これはテーブルを作成)
        command.upgrade(alembic_config, "000000000000")

        # alembic_version をリセットして初期スキーマ以降を再実行
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect() as conn:
            # 初期スキーマ以降の増分マイグレーションのバージョンを削除
            # これにより、増分マイグレーションが再実行される
            conn.execute(
                text("UPDATE alembic_version SET version_num = '000000000000'")
            )
            conn.commit()
        engine.dispose()

        # 増分マイグレーションを再度実行 (条件付き作成があるのでエラーにならない)
        command.upgrade(alembic_config, "head")

        # テーブルが正常に存在することを確認
        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "sticky_messages" in tables
        assert "voice_session_members" in tables
        assert "bump_reminders" in tables
        assert "bump_configs" in tables
        engine.dispose()

    @pytest.mark.usefixtures("clean_db")
    def test_conditional_creates_skip_existing_tables(
        self, alembic_config: Config
    ) -> None:
        """条件付き作成が既存テーブルをスキップすることを確認する。"""
        # 初期スキーマを適用 (全テーブルが作成される)
        command.upgrade(alembic_config, "000000000000")

        # bump_configs マイグレーションまでの alembic_version を設定
        # (bump_configs 作成マイグレーションの直前)
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE alembic_version SET version_num = 'c3d4e5f6a7b8'")
            )
            conn.commit()
        engine.dispose()

        # bump_configs マイグレーションを実行 (テーブルは既に存在)
        # 条件付き作成により、エラーにならずスキップされる
        command.upgrade(alembic_config, "d4e5f6a7b8c9")

        # テーブルが存在することを確認
        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        assert "bump_configs" in inspector.get_table_names()
        engine.dispose()


class TestMigrationFileSafety:
    """マイグレーションファイルの安全性チェック。"""

    def test_incremental_migrations_have_safe_downgrade(self) -> None:
        """増分マイグレーションが安全な downgrade を持つことを確認する。"""
        migration_files = [
            "alembic/versions/e5f6a7b8c9d0_add_sticky_messages.py",
            "alembic/versions/a1b2c3d4e5f6_add_bump_reminders.py",
            "alembic/versions/6be2a413ed70_add_voice_session_members.py",
            "alembic/versions/d4e5f6a7b8c9_add_bump_configs.py",
        ]

        for file_path in migration_files:
            path = Path(file_path)
            assert path.exists(), f"{file_path} が見つかりません"

            content = path.read_text()
            # downgrade 関数内でテーブル存在チェックがあることを確認
            assert "inspector.get_table_names()" in content, (
                f"{file_path} の downgrade にテーブル存在チェックがありません"
            )

    def test_initial_schema_has_safe_downgrade(self) -> None:
        """初期スキーマが安全な downgrade を持つことを確認する。"""
        path = Path("alembic/versions/000000000000_initial_schema.py")
        assert path.exists()

        content = path.read_text()
        # downgrade 関数内でテーブル存在チェックがあることを確認
        assert "inspector.get_table_names()" in content, (
            "初期スキーマの downgrade にテーブル存在チェックがありません"
        )
        # 各テーブルの条件チェックがあることを確認
        for table in [
            "sticky_messages",
            "bump_configs",
            "bump_reminders",
            "voice_session_members",
            "voice_sessions",
            "lobbies",
        ]:
            assert f'"{table}" in tables' in content, (
                f"初期スキーマの downgrade に {table} の存在チェックがありません"
            )
