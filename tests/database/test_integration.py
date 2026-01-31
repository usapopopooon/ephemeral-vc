"""Integration tests — 複数サービスにまたがる整合性テスト。"""

from __future__ import annotations

from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession

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


class TestLobbySessionLifecycle:
    """ロビー → セッション作成 → 更新 → 削除の一連フローテスト。"""

    async def test_full_lifecycle(self, db_session: AsyncSession) -> None:
        """ロビー作成 → セッション作成 → 更新 → セッション削除 → ロビー削除。"""
        # ロビー作成
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
            default_user_limit=10,
        )
        assert lobby.id is not None

        # セッション作成
        ch_id = snowflake()
        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_id,
            owner_id=snowflake(),
            name="initial",
        )
        assert vs.id is not None
        assert vs.name == "initial"

        # セッション更新
        updated = await update_voice_session(
            db_session, vs, name="renamed", is_locked=True
        )
        assert updated.name == "renamed"
        assert updated.is_locked is True

        # セッション削除
        assert await delete_voice_session(db_session, ch_id) is True
        assert await get_voice_session(db_session, ch_id) is None

        # ロビー削除
        assert await delete_lobby(db_session, lobby.id) is True

    async def test_multiple_lobbies_multiple_sessions(
        self, db_session: AsyncSession
    ) -> None:
        """複数ロビーにそれぞれセッションを作成し、独立して管理できる。"""
        guild_id = snowflake()
        lobbies = []
        for _ in range(3):
            lobby = await create_lobby(
                db_session,
                guild_id=guild_id,
                lobby_channel_id=snowflake(),
            )
            lobbies.append(lobby)

        # 各ロビーに2セッションずつ作成
        all_channels: dict[int, list[str]] = {}
        for lobby in lobbies:
            channels = []
            for _ in range(2):
                cid = snowflake()
                channels.append(cid)
                await create_voice_session(
                    db_session,
                    lobby_id=lobby.id,
                    channel_id=cid,
                    owner_id=snowflake(),
                    name=fake.word(),
                )
            all_channels[lobby.id] = channels

        # 全6セッション存在
        all_sessions = await get_all_voice_sessions(db_session)
        assert len(all_sessions) == 6

        # ロビー1つ削除 → そのセッションのみ消える
        deleted_lobby = lobbies[0]
        await delete_lobby(db_session, deleted_lobby.id)

        remaining = await get_all_voice_sessions(db_session)
        assert len(remaining) == 4

        # 削除されたロビーのセッションは存在しない
        for cid in all_channels[deleted_lobby.id]:
            assert await get_voice_session(db_session, cid) is None

        # 残りのロビーのセッションは存在する
        for lobby in lobbies[1:]:
            for cid in all_channels[lobby.id]:
                assert await get_voice_session(db_session, cid) is not None

    async def test_owner_transfer_and_verify(self, db_session: AsyncSession) -> None:
        """オーナー譲渡後にセッションを再取得して反映を確認。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )
        original_owner = snowflake()
        ch_id = snowflake()
        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_id,
            owner_id=original_owner,
            name="test",
        )

        new_owner = snowflake()
        await update_voice_session(db_session, vs, owner_id=new_owner)

        # DB から再取得して確認
        reloaded = await get_voice_session(db_session, ch_id)
        assert reloaded is not None
        assert reloaded.owner_id == new_owner
        assert reloaded.owner_id != original_owner


class TestDataIsolation:
    """データ分離・整合性テスト。"""

    async def test_guild_lobby_isolation(self, db_session: AsyncSession) -> None:
        """異なるギルドのロビーは完全に分離されている。"""
        g1, g2 = snowflake(), snowflake()
        l1 = await create_lobby(db_session, guild_id=g1, lobby_channel_id=snowflake())
        l2 = await create_lobby(db_session, guild_id=g2, lobby_channel_id=snowflake())

        g1_lobbies = await get_lobbies_by_guild(db_session, g1)
        g2_lobbies = await get_lobbies_by_guild(db_session, g2)

        assert len(g1_lobbies) == 1
        assert g1_lobbies[0].id == l1.id
        assert len(g2_lobbies) == 1
        assert g2_lobbies[0].id == l2.id

    async def test_session_deletion_isolation(self, db_session: AsyncSession) -> None:
        """セッション削除は同じロビーの他セッションに影響しない。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )
        ch1, ch2, ch3 = snowflake(), snowflake(), snowflake()
        for cid in [ch1, ch2, ch3]:
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=cid,
                owner_id=snowflake(),
                name=fake.word(),
            )

        # ch2 だけ削除
        await delete_voice_session(db_session, ch2)

        assert await get_voice_session(db_session, ch1) is not None
        assert await get_voice_session(db_session, ch2) is None
        assert await get_voice_session(db_session, ch3) is not None

    async def test_lobby_lookup_by_channel_id(self, db_session: AsyncSession) -> None:
        """channel_id でロビーを正しく取得できる。"""
        target_cid = snowflake()
        # ダミーロビーを先に作成
        for _ in range(5):
            await create_lobby(
                db_session,
                guild_id=snowflake(),
                lobby_channel_id=snowflake(),
            )
        # ターゲットロビー
        target = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=target_cid,
        )

        found = await get_lobby_by_channel_id(db_session, target_cid)
        assert found is not None
        assert found.id == target.id

    async def test_session_count_after_bulk_operations(
        self, db_session: AsyncSession
    ) -> None:
        """大量の作成・削除後にカウントが正確。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )

        # 10セッション作成
        channels = []
        for _ in range(10):
            cid = snowflake()
            channels.append(cid)
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=cid,
                owner_id=snowflake(),
                name=fake.word(),
            )
        assert len(await get_all_voice_sessions(db_session)) == 10

        # 偶数インデックスの5件削除
        for i in range(0, 10, 2):
            await delete_voice_session(db_session, channels[i])

        remaining = await get_all_voice_sessions(db_session)
        assert len(remaining) == 5

    async def test_update_does_not_create_duplicate(
        self, db_session: AsyncSession
    ) -> None:
        """update はレコードを増やさない。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )
        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name="original",
        )

        assert len(await get_all_voice_sessions(db_session)) == 1

        await update_voice_session(db_session, vs, name="updated")
        assert len(await get_all_voice_sessions(db_session)) == 1

    async def test_lobby_with_category_id(self, db_session: AsyncSession) -> None:
        """category_id 付きロビーの作成と取得。"""
        cat_id = snowflake()
        cid = snowflake()
        await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=cid,
            category_id=cat_id,
            default_user_limit=25,
        )

        found = await get_lobby_by_channel_id(db_session, cid)
        assert found is not None
        assert found.category_id == cat_id
        assert found.default_user_limit == 25
