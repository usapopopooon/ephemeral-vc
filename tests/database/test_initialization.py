"""Tests for database initialization and creation edge cases.

新規環境構築時のデータベース初期化パターンをテストする。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.constants import DEFAULT_TEST_DATABASE_URL
from src.database.models import AdminUser, Base, Lobby

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    DEFAULT_TEST_DATABASE_URL,
)


# =============================================================================
# データベース初期化テスト
# =============================================================================


class TestDatabaseInitialization:
    """データベース初期化のテスト。"""

    async def test_create_tables_on_empty_database(self) -> None:
        """空のデータベースにテーブルを作成できる。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            # 全テーブルを削除
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)

            # テーブルが存在しないことを確認
            async with engine.connect() as conn:
                tables = await conn.run_sync(
                    lambda sync_conn: sa_inspect(sync_conn).get_table_names()
                )
            assert "lobbies" not in tables

            # テーブルを作成
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # テーブルが作成されたことを確認
            async with engine.connect() as conn:
                tables = await conn.run_sync(
                    lambda sync_conn: sa_inspect(sync_conn).get_table_names()
                )

            expected_tables = [
                "lobbies",
                "voice_sessions",
                "voice_session_members",
                "bump_reminders",
                "bump_configs",
                "sticky_messages",
                "admin_users",
            ]
            for table in expected_tables:
                assert table in tables, f"Table {table} should exist"
        finally:
            await engine.dispose()

    async def test_init_db_creates_all_expected_tables(self) -> None:
        """init_db が全ての期待されるテーブルを作成する。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)

            async with engine.connect() as conn:
                tables = await conn.run_sync(
                    lambda sync_conn: sa_inspect(sync_conn).get_table_names()
                )

            # 全テーブルが存在
            assert len(tables) >= 7
        finally:
            await engine.dispose()

    async def test_init_db_preserves_existing_data(self) -> None:
        """init_db は既存データを保持する (CREATE TABLE IF NOT EXISTS)。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        try:
            # テーブルを作成してデータを挿入
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)

            async with factory() as session:
                lobby = Lobby(guild_id="test_guild", lobby_channel_id="test_channel")
                session.add(lobby)
                await session.commit()
                lobby_id = lobby.id

            # 再度 init_db を実行
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # データが保持されていることを確認
            async with factory() as session:
                result = await session.execute(
                    select(Lobby).where(Lobby.id == lobby_id)
                )
                found = result.scalar_one_or_none()
                assert found is not None
                assert found.guild_id == "test_guild"
        finally:
            await engine.dispose()

    async def test_multiple_init_db_calls_idempotent(self) -> None:
        """init_db を複数回呼んでもエラーにならない。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)

            # 複数回 create_all を呼ぶ
            for _ in range(3):
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)

            # テーブルが正常に存在
            async with engine.connect() as conn:
                tables = await conn.run_sync(
                    lambda sync_conn: sa_inspect(sync_conn).get_table_names()
                )
            assert "lobbies" in tables
        finally:
            await engine.dispose()


# =============================================================================
# Admin User Creation Tests (get_or_create_admin pattern)
# =============================================================================


class TestAdminUserCreation:
    """AdminUser 作成パターンのテスト。"""

    @pytest.fixture
    async def db_session(self) -> AsyncGenerator[AsyncSession, None]:
        """テスト用の DB セッションを提供する。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as session:
            yield session

        await engine.dispose()

    async def test_create_admin_on_empty_database(
        self, db_session: AsyncSession
    ) -> None:
        """空のデータベースに AdminUser を作成できる。"""
        admin = AdminUser(
            email="admin@example.com",
            password_hash="$2b$12$test",
        )
        db_session.add(admin)
        await db_session.commit()

        assert admin.id is not None
        assert admin.email == "admin@example.com"

    async def test_get_or_create_pattern_creates_when_empty(
        self, db_session: AsyncSession
    ) -> None:
        """get_or_create パターン: 存在しない場合は新規作成。"""
        # 既存の AdminUser を検索
        result = await db_session.execute(select(AdminUser).limit(1))
        admin = result.scalar_one_or_none()

        # 存在しない場合は作成
        if admin is None:
            admin = AdminUser(
                email="new_admin@example.com",
                password_hash="$2b$12$test",
            )
            db_session.add(admin)
            await db_session.commit()
            await db_session.refresh(admin)

        assert admin is not None
        assert admin.email == "new_admin@example.com"

    async def test_get_or_create_pattern_returns_existing(
        self, db_session: AsyncSession
    ) -> None:
        """get_or_create パターン: 既存のものがあればそれを返す。"""
        # 最初の AdminUser を作成
        existing = AdminUser(
            email="existing@example.com",
            password_hash="$2b$12$existing",
        )
        db_session.add(existing)
        await db_session.commit()
        existing_id = existing.id

        # get_or_create パターン
        result = await db_session.execute(select(AdminUser).limit(1))
        admin = result.scalar_one_or_none()

        if admin is None:
            admin = AdminUser(
                email="should_not_be_created@example.com",
                password_hash="$2b$12$new",
            )
            db_session.add(admin)
            await db_session.commit()

        # 既存のものが返される
        assert admin is not None
        assert admin.id == existing_id
        assert admin.email == "existing@example.com"

    async def test_admin_email_unique_constraint(
        self, db_session: AsyncSession
    ) -> None:
        """AdminUser の email はユニーク制約がある。"""
        admin1 = AdminUser(
            email="duplicate@example.com",
            password_hash="$2b$12$hash1",
        )
        db_session.add(admin1)
        await db_session.commit()

        admin2 = AdminUser(
            email="duplicate@example.com",
            password_hash="$2b$12$hash2",
        )
        db_session.add(admin2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_admin_created_with_default_timestamps(
        self, db_session: AsyncSession
    ) -> None:
        """AdminUser は作成時にタイムスタンプが設定される。"""
        admin = AdminUser(
            email="timestamps@example.com",
            password_hash="$2b$12$test",
        )
        db_session.add(admin)
        await db_session.commit()

        assert admin.created_at is not None
        assert admin.updated_at is not None
        assert admin.password_changed_at is None  # 初期状態は None

    async def test_admin_optional_fields_nullable(
        self, db_session: AsyncSession
    ) -> None:
        """AdminUser のオプションフィールドは None を許容する。"""
        admin = AdminUser(
            email="nullable@example.com",
            password_hash="$2b$12$test",
        )
        db_session.add(admin)
        await db_session.commit()

        assert admin.reset_token is None
        assert admin.reset_token_expires_at is None
        assert admin.pending_email is None
        assert admin.email_change_token is None
        assert admin.email_change_token_expires_at is None
        assert admin.email_verified is False


# =============================================================================
# トランザクションとロールバックテスト
# =============================================================================


class TestTransactionHandling:
    """トランザクション処理のテスト。"""

    @pytest.fixture
    async def db_session(self) -> AsyncGenerator[AsyncSession, None]:
        """テスト用の DB セッションを提供する。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as session:
            yield session

        await engine.dispose()

    async def test_rollback_on_integrity_error(self, db_session: AsyncSession) -> None:
        """IntegrityError 発生時にロールバックする。"""
        # 最初のレコードを作成
        lobby1 = Lobby(guild_id="guild1", lobby_channel_id="channel1")
        db_session.add(lobby1)
        await db_session.commit()

        # 重複する channel_id で作成を試みる
        lobby2 = Lobby(guild_id="guild2", lobby_channel_id="channel1")
        db_session.add(lobby2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        # ロールバック
        await db_session.rollback()

        # 最初のレコードは残っている
        result = await db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "channel1")
        )
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.guild_id == "guild1"

    async def test_commit_after_multiple_operations(
        self, db_session: AsyncSession
    ) -> None:
        """複数の操作を1つのトランザクションでコミットできる。"""
        lobby1 = Lobby(guild_id="guild1", lobby_channel_id="ch1")
        lobby2 = Lobby(guild_id="guild2", lobby_channel_id="ch2")
        lobby3 = Lobby(guild_id="guild3", lobby_channel_id="ch3")

        db_session.add_all([lobby1, lobby2, lobby3])
        await db_session.commit()

        # 全て作成されている
        result = await db_session.execute(select(Lobby))
        lobbies = list(result.scalars().all())
        assert len(lobbies) == 3

    async def test_partial_rollback_with_savepoint(
        self, db_session: AsyncSession
    ) -> None:
        """ネストしたトランザクションでセーブポイントを使用できる。"""
        # 最初のレコード
        lobby1 = Lobby(guild_id="guild1", lobby_channel_id="ch1")
        db_session.add(lobby1)
        await db_session.flush()

        # ネストしたトランザクション (begin_nested) を開始
        try:
            async with db_session.begin_nested():
                lobby2 = Lobby(guild_id="guild2", lobby_channel_id="ch1")  # 重複
                db_session.add(lobby2)
                await db_session.flush()
        except IntegrityError:
            pass  # 内側のみロールバック

        # 外側のトランザクションをコミット
        await db_session.commit()

        # 最初のレコードのみ存在
        result = await db_session.execute(select(Lobby))
        lobbies = list(result.scalars().all())
        assert len(lobbies) == 1
        assert lobbies[0].lobby_channel_id == "ch1"


# =============================================================================
# Empty Database Edge Cases
# =============================================================================


class TestEmptyDatabaseEdgeCases:
    """空のデータベースでのエッジケーステスト。"""

    @pytest.fixture
    async def empty_db_session(self) -> AsyncGenerator[AsyncSession, None]:
        """空のテスト用 DB セッションを提供する。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as session:
            yield session

        await engine.dispose()

    async def test_select_from_empty_table_returns_empty(
        self, empty_db_session: AsyncSession
    ) -> None:
        """空のテーブルから SELECT すると空のリストが返る。"""
        result = await empty_db_session.execute(select(Lobby))
        lobbies = list(result.scalars().all())
        assert lobbies == []

    async def test_scalar_one_or_none_on_empty_returns_none(
        self, empty_db_session: AsyncSession
    ) -> None:
        """空のテーブルで scalar_one_or_none は None を返す。"""
        result = await empty_db_session.execute(select(AdminUser).limit(1))
        admin = result.scalar_one_or_none()
        assert admin is None

    async def test_first_insert_after_drop_all(
        self, empty_db_session: AsyncSession
    ) -> None:
        """drop_all 後の最初の INSERT が成功する。"""
        lobby = Lobby(guild_id="first_guild", lobby_channel_id="first_channel")
        empty_db_session.add(lobby)
        await empty_db_session.commit()

        assert lobby.id is not None
        assert lobby.id >= 1

    async def test_count_on_empty_table(self, empty_db_session: AsyncSession) -> None:
        """空のテーブルで COUNT は 0 を返す。"""
        from sqlalchemy import func

        result = await empty_db_session.execute(select(func.count()).select_from(Lobby))
        count = result.scalar()
        assert count == 0


# =============================================================================
# Connection Pool Edge Cases
# =============================================================================


class TestConnectionPoolEdgeCases:
    """コネクションプールのエッジケーステスト。"""

    async def test_dispose_and_reconnect(self) -> None:
        """エンジンを dispose した後に再接続できる。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        # 最初の接続
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        async with factory() as session:
            lobby = Lobby(guild_id="test", lobby_channel_id="test_ch")
            session.add(lobby)
            await session.commit()

        # dispose
        await engine.dispose()

        # 再接続 (新しいエンジン)
        engine2 = create_async_engine(TEST_DATABASE_URL)
        factory2 = async_sessionmaker(
            engine2, class_=AsyncSession, expire_on_commit=False
        )

        async with factory2() as session:
            result = await session.execute(select(Lobby))
            lobbies = list(result.scalars().all())
            assert len(lobbies) == 1

        await engine2.dispose()

    async def test_multiple_concurrent_sessions(self) -> None:
        """複数のセッションを同時に使用できる。"""
        engine = create_async_engine(TEST_DATABASE_URL, pool_size=5)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)

            # 複数のセッションを同時に開く
            async with factory() as session1, factory() as session2:
                lobby1 = Lobby(guild_id="g1", lobby_channel_id="ch1")
                lobby2 = Lobby(guild_id="g2", lobby_channel_id="ch2")

                session1.add(lobby1)
                session2.add(lobby2)

                await session1.commit()
                await session2.commit()

            # 両方のレコードが存在
            async with factory() as session:
                result = await session.execute(select(Lobby))
                lobbies = list(result.scalars().all())
                assert len(lobbies) == 2
        finally:
            await engine.dispose()


# =============================================================================
# Database Schema Edge Cases
# =============================================================================


class TestDatabaseSchemaEdgeCases:
    """データベーススキーマのエッジケーステスト。"""

    async def test_table_indexes_exist(self) -> None:
        """期待されるインデックスが存在する。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)

            async with engine.connect() as conn:
                indexes = await conn.run_sync(
                    lambda sync_conn: sa_inspect(sync_conn).get_indexes("lobbies")
                )

            # guild_id にインデックスがある
            index_columns = [
                col for idx in indexes for col in idx.get("column_names", [])
            ]
            assert "guild_id" in index_columns or "lobby_channel_id" in index_columns
        finally:
            await engine.dispose()

    async def test_foreign_key_constraints_exist(self) -> None:
        """外部キー制約が存在する。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)

            async with engine.connect() as conn:
                fks = await conn.run_sync(
                    lambda sync_conn: sa_inspect(sync_conn).get_foreign_keys(
                        "voice_sessions"
                    )
                )

            # lobbies テーブルへの FK がある
            referred_tables = [fk.get("referred_table") for fk in fks]
            assert "lobbies" in referred_tables
        finally:
            await engine.dispose()

    async def test_unique_constraints_exist(self) -> None:
        """ユニーク制約 (ユニークインデックス含む) が存在する。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)

            async with engine.connect() as conn:
                # ユニーク制約をチェック
                unique_constraints = await conn.run_sync(
                    lambda sync_conn: sa_inspect(sync_conn).get_unique_constraints(
                        "lobbies"
                    )
                )
                # ユニークインデックスもチェック
                # (PostgreSQL では unique=True がインデックスになる)
                indexes = await conn.run_sync(
                    lambda sync_conn: sa_inspect(sync_conn).get_indexes("lobbies")
                )

            # ユニーク制約またはユニークインデックスとして lobby_channel_id がある
            unique_columns = [
                col for uc in unique_constraints for col in uc.get("column_names", [])
            ]
            unique_index_columns = [
                col
                for idx in indexes
                if idx.get("unique", False)
                for col in idx.get("column_names", [])
            ]

            all_unique_columns = unique_columns + unique_index_columns
            assert "lobby_channel_id" in all_unique_columns
        finally:
            await engine.dispose()
