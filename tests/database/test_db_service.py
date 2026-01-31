"""Tests for db_service using factory fixtures and faker."""

from __future__ import annotations

import pytest
from faker import Faker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Lobby, VoiceSession
from src.services.db_service import (
    create_lobby,
    create_voice_session,
    delete_lobby,
    delete_voice_session,
    get_all_voice_sessions,
    get_lobbies_by_guild,
    get_lobby_by_channel_id,
    get_voice_session,
    update_voice_session,
)

from .conftest import snowflake

fake = Faker()


# ===========================================================================
# Lobby CRUD — faker 利用
# ===========================================================================


class TestLobbyWithFaker:
    """faker で生成したデータでの Lobby テスト。"""

    async def test_create_with_all_options(self, db_session: AsyncSession) -> None:
        """全オプション指定で Lobby を作成できる。"""
        gid = snowflake()
        cid = snowflake()
        cat = snowflake()
        limit = fake.random_int(min=1, max=99)

        lobby = await create_lobby(
            db_session,
            guild_id=gid,
            lobby_channel_id=cid,
            category_id=cat,
            default_user_limit=limit,
        )

        assert lobby.guild_id == gid
        assert lobby.lobby_channel_id == cid
        assert lobby.category_id == cat
        assert lobby.default_user_limit == limit
        assert lobby.id is not None

    async def test_get_by_channel_returns_correct_lobby(
        self, db_session: AsyncSession
    ) -> None:
        """複数ロビー存在時に正しいロビーが返る。"""
        target_cid = snowflake()
        await create_lobby(
            db_session, guild_id=snowflake(), lobby_channel_id=snowflake()
        )
        await create_lobby(
            db_session, guild_id=snowflake(), lobby_channel_id=target_cid
        )

        found = await get_lobby_by_channel_id(db_session, target_cid)
        assert found is not None
        assert found.lobby_channel_id == target_cid

    async def test_get_lobbies_filters_by_guild(self, db_session: AsyncSession) -> None:
        """guild_id でフィルタされる。"""
        guild_a = snowflake()
        guild_b = snowflake()
        for _ in range(3):
            await create_lobby(
                db_session,
                guild_id=guild_a,
                lobby_channel_id=snowflake(),
            )
        for _ in range(2):
            await create_lobby(
                db_session,
                guild_id=guild_b,
                lobby_channel_id=snowflake(),
            )

        assert len(await get_lobbies_by_guild(db_session, guild_a)) == 3
        assert len(await get_lobbies_by_guild(db_session, guild_b)) == 2

    async def test_get_lobbies_empty_guild(self, db_session: AsyncSession) -> None:
        """存在しないギルドは空リスト。"""
        result = await get_lobbies_by_guild(db_session, snowflake())
        assert result == []

    async def test_delete_lobby_cascades(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """ロビー削除でセッションもカスケード削除される。"""
        ch_id = snowflake()
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_id,
            owner_id=snowflake(),
            name=fake.word(),
        )

        result = await delete_lobby(db_session, lobby.id)
        assert result is True

        assert await get_voice_session(db_session, ch_id) is None

    async def test_delete_nonexistent_lobby(self, db_session: AsyncSession) -> None:
        """存在しない ID の削除は False。"""
        assert await delete_lobby(db_session, 999999) is False


# ===========================================================================
# VoiceSession CRUD — faker + fixture 利用
# ===========================================================================


class TestVoiceSessionWithFaker:
    """faker/fixture で生成したデータでの VoiceSession テスト。"""

    async def test_create_with_user_limit(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """user_limit 指定で作成できる。"""
        limit = fake.random_int(min=1, max=99)
        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name=fake.word(),
            user_limit=limit,
        )
        assert vs.user_limit == limit

    async def test_get_session_returns_correct_one(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """複数セッション存在時に正しいものが返る。"""
        target_cid = snowflake()
        for _ in range(3):
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=snowflake(),
                owner_id=snowflake(),
                name=fake.word(),
            )
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=target_cid,
            owner_id=snowflake(),
            name="target",
        )

        found = await get_voice_session(db_session, target_cid)
        assert found is not None
        assert found.name == "target"

    async def test_get_all_sessions(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """get_all_voice_sessions が全件返す。"""
        count = fake.random_int(min=2, max=5)
        for _ in range(count):
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=snowflake(),
                owner_id=snowflake(),
                name=fake.word(),
            )

        sessions = await get_all_voice_sessions(db_session)
        assert len(sessions) == count

    async def test_get_all_sessions_empty(self, db_session: AsyncSession) -> None:
        """セッションがなければ空リスト。"""
        assert await get_all_voice_sessions(db_session) == []


class TestUpdateVoiceSession:
    """update_voice_session の各フィールド個別テスト。"""

    async def test_update_name(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """名前だけ更新できる。"""
        new_name = fake.word()
        updated = await update_voice_session(db_session, voice_session, name=new_name)
        assert updated.name == new_name

    async def test_update_user_limit(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """user_limit だけ更新できる。"""
        new_limit = fake.random_int(min=1, max=99)
        updated = await update_voice_session(
            db_session, voice_session, user_limit=new_limit
        )
        assert updated.user_limit == new_limit

    async def test_update_is_locked(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """is_locked だけ更新できる。"""
        updated = await update_voice_session(db_session, voice_session, is_locked=True)
        assert updated.is_locked is True

    async def test_update_is_hidden(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """is_hidden だけ更新できる。"""
        updated = await update_voice_session(db_session, voice_session, is_hidden=True)
        assert updated.is_hidden is True

    async def test_update_owner_id(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """owner_id だけ更新（譲渡）できる。"""
        new_owner = snowflake()
        updated = await update_voice_session(
            db_session, voice_session, owner_id=new_owner
        )
        assert updated.owner_id == new_owner

    async def test_update_multiple_fields(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """複数フィールド同時更新。"""
        new_name = fake.word()
        new_owner = snowflake()
        updated = await update_voice_session(
            db_session,
            voice_session,
            name=new_name,
            is_locked=True,
            is_hidden=True,
            owner_id=new_owner,
        )
        assert updated.name == new_name
        assert updated.is_locked is True
        assert updated.is_hidden is True
        assert updated.owner_id == new_owner

    async def test_update_no_params_unchanged(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """パラメータなしなら変更なし。"""
        original_name = voice_session.name
        original_owner = voice_session.owner_id
        updated = await update_voice_session(db_session, voice_session)
        assert updated.name == original_name
        assert updated.owner_id == original_owner


class TestDeleteVoiceSession:
    """delete_voice_session のテスト。"""

    async def test_delete_existing(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """存在するセッションを削除できる。"""
        ch_id = voice_session.channel_id
        assert await delete_voice_session(db_session, ch_id) is True
        assert await get_voice_session(db_session, ch_id) is None

    async def test_delete_nonexistent(self, db_session: AsyncSession) -> None:
        """存在しない channel_id の削除は False。"""
        assert await delete_voice_session(db_session, snowflake()) is False

    async def test_delete_does_not_affect_others(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """1つ削除しても他のセッションに影響しない。"""
        ch_keep = snowflake()
        ch_delete = snowflake()
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_keep,
            owner_id=snowflake(),
            name="keep",
        )
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_delete,
            owner_id=snowflake(),
            name="delete",
        )

        await delete_voice_session(db_session, ch_delete)

        kept = await get_voice_session(db_session, ch_keep)
        assert kept is not None
        assert kept.name == "keep"


# ===========================================================================
# エッジケース — FK 違反・重複・ロールバック
# ===========================================================================


class TestServiceEdgeCases:
    """サービス関数のエッジケーステスト。"""

    async def test_create_lobby_duplicate_channel_id(
        self, db_session: AsyncSession
    ) -> None:
        """同じ lobby_channel_id で create_lobby を2回呼ぶと IntegrityError。"""
        cid = snowflake()
        await create_lobby(db_session, guild_id=snowflake(), lobby_channel_id=cid)
        with pytest.raises(IntegrityError):
            await create_lobby(db_session, guild_id=snowflake(), lobby_channel_id=cid)

    async def test_create_voice_session_duplicate_channel_id(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """同じ channel_id で create_voice_session を2回呼ぶと IntegrityError。"""
        cid = snowflake()
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=cid,
            owner_id=snowflake(),
            name=fake.word(),
        )
        with pytest.raises(IntegrityError):
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=cid,
                owner_id=snowflake(),
                name=fake.word(),
            )

    async def test_create_voice_session_invalid_lobby_id(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない lobby_id で create_voice_session は IntegrityError。"""
        with pytest.raises(IntegrityError):
            await create_voice_session(
                db_session,
                lobby_id=999999,
                channel_id=snowflake(),
                owner_id=snowflake(),
                name="orphan",
            )

    async def test_get_lobby_by_channel_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない channel_id は None を返す。"""
        result = await get_lobby_by_channel_id(db_session, snowflake())
        assert result is None

    async def test_get_voice_session_not_found(self, db_session: AsyncSession) -> None:
        """存在しない channel_id は None を返す。"""
        result = await get_voice_session(db_session, snowflake())
        assert result is None

    async def test_delete_lobby_returns_false_for_missing(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない lobby_id の delete_lobby は False。"""
        assert await delete_lobby(db_session, 0) is False

    async def test_update_voice_session_preserves_unmodified(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """name だけ更新すると他のフィールドは変わらない。"""
        original_owner = voice_session.owner_id
        original_limit = voice_session.user_limit
        original_locked = voice_session.is_locked
        original_hidden = voice_session.is_hidden

        await update_voice_session(db_session, voice_session, name="changed")

        assert voice_session.name == "changed"
        assert voice_session.owner_id == original_owner
        assert voice_session.user_limit == original_limit
        assert voice_session.is_locked == original_locked
        assert voice_session.is_hidden == original_hidden

    async def test_create_and_immediately_delete_lobby(
        self, db_session: AsyncSession
    ) -> None:
        """作成直後に削除できる。"""
        lobby = await create_lobby(
            db_session, guild_id=snowflake(), lobby_channel_id=snowflake()
        )
        assert await delete_lobby(db_session, lobby.id) is True
        assert await delete_lobby(db_session, lobby.id) is False

    async def test_create_and_immediately_delete_session(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """作成直後にセッション削除できる。"""
        cid = snowflake()
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=cid,
            owner_id=snowflake(),
            name=fake.word(),
        )
        assert await delete_voice_session(db_session, cid) is True
        assert await delete_voice_session(db_session, cid) is False

    async def test_get_lobbies_by_guild_isolation(
        self, db_session: AsyncSession
    ) -> None:
        """異なるギルドのロビーは混在しない。"""
        g1, g2 = snowflake(), snowflake()
        await create_lobby(db_session, guild_id=g1, lobby_channel_id=snowflake())
        await create_lobby(db_session, guild_id=g1, lobby_channel_id=snowflake())
        await create_lobby(db_session, guild_id=g2, lobby_channel_id=snowflake())

        assert len(await get_lobbies_by_guild(db_session, g1)) == 2
        assert len(await get_lobbies_by_guild(db_session, g2)) == 1
        assert len(await get_lobbies_by_guild(db_session, snowflake())) == 0

    async def test_delete_lobby_cascades_multiple_sessions(
        self, db_session: AsyncSession
    ) -> None:
        """複数セッションを持つロビーを削除するとすべてカスケード削除。"""
        lobby = await create_lobby(
            db_session, guild_id=snowflake(), lobby_channel_id=snowflake()
        )
        channels = []
        for _ in range(5):
            cid = snowflake()
            channels.append(cid)
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=cid,
                owner_id=snowflake(),
                name=fake.word(),
            )

        assert await delete_lobby(db_session, lobby.id) is True

        for cid in channels:
            assert await get_voice_session(db_session, cid) is None

    async def test_update_session_back_to_defaults(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """フィールドを変更後、デフォルト値に戻せる。"""
        await update_voice_session(
            db_session,
            voice_session,
            is_locked=True,
            is_hidden=True,
            user_limit=50,
        )
        assert voice_session.is_locked is True

        await update_voice_session(
            db_session,
            voice_session,
            is_locked=False,
            is_hidden=False,
            user_limit=0,
        )
        assert voice_session.is_locked is False
        assert voice_session.is_hidden is False
        assert voice_session.user_limit == 0
