"""Tests for VoiceCog join tracking helpers and event listeners."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from src.cogs.voice import VoiceCog

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog() -> VoiceCog:
    """Create a VoiceCog instance with a mock bot."""
    bot = MagicMock(spec=discord.ext.commands.Bot)
    bot.user = MagicMock(spec=discord.User)
    bot.user.id = 9999
    return VoiceCog(bot)


def _make_member(user_id: int, *, bot: bool = False) -> MagicMock:
    """Create a mock discord.Member."""
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = bot
    member.display_name = f"User{user_id}"
    member.mention = f"<@{user_id}>"
    return member


def _make_channel(channel_id: int, members: list[MagicMock] | None = None) -> MagicMock:
    """Create a mock discord.VoiceChannel."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = channel_id
    channel.members = members or []
    return channel


def _make_voice_session(
    *,
    channel_id: str = "100",
    owner_id: str = "1",
    is_locked: bool = False,
    is_hidden: bool = False,
) -> MagicMock:
    """Create a mock VoiceSession DB object."""
    vs = MagicMock()
    vs.id = 1
    vs.channel_id = channel_id
    vs.owner_id = owner_id
    vs.name = "Test channel"
    vs.user_limit = 0
    vs.is_locked = is_locked
    vs.is_hidden = is_hidden
    return vs


def _mock_async_session() -> tuple[MagicMock, AsyncMock]:
    """Create mock for async_session context manager.

    Returns:
        (mock_session_factory, mock_session)
    """
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_factory, mock_session


class TestRecordJoinCache:
    """Tests for _record_join_cache."""

    def test_new_member(self) -> None:
        """Test recording a new member join."""
        cog = _make_cog()
        cog._record_join_cache(100, 1)
        assert 1 in cog._join_times[100]

    def test_no_overwrite(self) -> None:
        """Test that existing join time is not overwritten."""
        cog = _make_cog()
        cog._record_join_cache(100, 1)
        first_time = cog._join_times[100][1]
        cog._record_join_cache(100, 1)
        assert cog._join_times[100][1] == first_time

    def test_multiple_members(self) -> None:
        """Test recording multiple members in the same channel."""
        cog = _make_cog()
        cog._record_join_cache(100, 1)
        cog._record_join_cache(100, 2)
        assert len(cog._join_times[100]) == 2

    def test_multiple_channels(self) -> None:
        """Test recording joins across different channels."""
        cog = _make_cog()
        cog._record_join_cache(100, 1)
        cog._record_join_cache(200, 2)
        assert 100 in cog._join_times
        assert 200 in cog._join_times


class TestRemoveJoinCache:
    """Tests for _remove_join_cache."""

    def test_existing_member(self) -> None:
        """Test removing an existing member's join record."""
        cog = _make_cog()
        cog._record_join_cache(100, 1)
        cog._remove_join_cache(100, 1)
        assert 1 not in cog._join_times[100]

    def test_missing_channel(self) -> None:
        """Test removing from a non-existent channel does not raise."""
        cog = _make_cog()
        cog._remove_join_cache(999, 1)  # Should not raise

    def test_missing_member(self) -> None:
        """Test removing a non-existent member does not raise."""
        cog = _make_cog()
        cog._record_join_cache(100, 1)
        cog._remove_join_cache(100, 999)  # Should not raise
        assert 1 in cog._join_times[100]


class TestCleanupChannelCache:
    """Tests for _cleanup_channel_cache."""

    def test_removes_records(self) -> None:
        """Test that cleanup removes all records for a channel."""
        cog = _make_cog()
        cog._record_join_cache(100, 1)
        cog._record_join_cache(100, 2)
        cog._cleanup_channel_cache(100)
        assert 100 not in cog._join_times

    def test_missing_channel(self) -> None:
        """Test cleaning up a non-existent channel does not raise."""
        cog = _make_cog()
        cog._cleanup_channel_cache(999)  # Should not raise


class TestGetLongestMember:
    """Tests for _get_longest_member (async, DB-based)."""

    async def test_uses_db_order(self) -> None:
        """DB から参加順に取得してメンバーを返す。"""
        cog = _make_cog()
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2])
        # guild.get_member のモック
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: m1 if uid == 1 else m2

        voice_session = _make_voice_session()

        # DB から m1, m2 の順で返す
        mock_db_member1 = MagicMock()
        mock_db_member1.user_id = "1"
        mock_db_member2 = MagicMock()
        mock_db_member2.user_id = "2"

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.get_voice_session_members_ordered",
            new_callable=AsyncMock,
            return_value=[mock_db_member1, mock_db_member2],
        ):
            result = await cog._get_longest_member(
                mock_session, voice_session, channel, exclude_id=999
            )
            assert result is m1

    async def test_excludes_specified(self) -> None:
        """除外指定されたメンバーは返さない。"""
        cog = _make_cog()
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2])
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: m1 if uid == 1 else m2

        voice_session = _make_voice_session()

        mock_db_member1 = MagicMock()
        mock_db_member1.user_id = "1"
        mock_db_member2 = MagicMock()
        mock_db_member2.user_id = "2"

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.get_voice_session_members_ordered",
            new_callable=AsyncMock,
            return_value=[mock_db_member1, mock_db_member2],
        ):
            # m1 を除外 → m2 が返る
            result = await cog._get_longest_member(
                mock_session, voice_session, channel, exclude_id=1
            )
            assert result is m2

    async def test_none_remaining(self) -> None:
        """メンバーがいなければ None を返す。"""
        cog = _make_cog()
        m1 = _make_member(1)
        channel = _make_channel(100, [m1])
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: m1 if uid == 1 else None

        voice_session = _make_voice_session()

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.get_voice_session_members_ordered",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await cog._get_longest_member(
                mock_session, voice_session, channel, exclude_id=1
            )
            assert result is None

    async def test_empty_channel(self) -> None:
        """空のチャンネルでは None を返す。"""
        cog = _make_cog()
        channel = _make_channel(100, [])
        channel.guild = MagicMock()
        channel.guild.get_member = lambda _uid: None

        voice_session = _make_voice_session()

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.get_voice_session_members_ordered",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await cog._get_longest_member(
                mock_session, voice_session, channel, exclude_id=1
            )
            assert result is None

    async def test_fallback_to_cache_without_db_records(self) -> None:
        """DB に記録がない場合はキャッシュにフォールバック。"""
        cog = _make_cog()
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2])
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: m1 if uid == 1 else m2

        voice_session = _make_voice_session()

        # キャッシュに記録
        cog._join_times[100] = {1: 10.0, 2: 20.0}

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.get_voice_session_members_ordered",
            new_callable=AsyncMock,
            return_value=[],  # DB に記録なし
        ):
            result = await cog._get_longest_member(
                mock_session, voice_session, channel, exclude_id=999
            )
            assert result is m1  # キャッシュから m1 が選ばれる

    async def test_tiebreaker_by_member_id(self) -> None:
        """キャッシュで同じ join_time の場合、member.id が小さい方が選ばれる。"""
        cog = _make_cog()
        m1 = _make_member(100)  # 大きい ID
        m2 = _make_member(50)  # 小さい ID
        channel = _make_channel(100, [m1, m2])
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: m1 if uid == 100 else m2

        voice_session = _make_voice_session()

        # キャッシュで同じ join_time
        cog._join_times[100] = {100: 10.0, 50: 10.0}

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.get_voice_session_members_ordered",
            new_callable=AsyncMock,
            return_value=[],  # DB に記録なし → キャッシュを使用
        ):
            result = await cog._get_longest_member(
                mock_session, voice_session, channel, exclude_id=999
            )
            assert result is m2  # ID が小さい m2 が選ばれる


class TestOnGuildChannelDelete:
    """Tests for on_guild_channel_delete listener."""

    async def test_deletes_voice_session_for_known_channel(self) -> None:
        """Test that DB record is deleted when a voice channel is deleted."""
        cog = _make_cog()
        cog._record_join_cache(100, 1)
        channel = _make_channel(100)

        mock_factory, mock_session = _mock_async_session()
        with (
            patch(
                "src.cogs.voice.delete_voice_session", new_callable=AsyncMock
            ) as mock_delete,
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_guild_channel_delete(channel)

            mock_delete.assert_awaited_once_with(mock_session, "100")
        # メモリ上の参加記録もクリーンアップされる
        assert 100 not in cog._join_times

    async def test_ignores_non_voice_channel(self) -> None:
        """Test that text channel deletion is ignored."""
        cog = _make_cog()
        text_channel = MagicMock(spec=discord.TextChannel)
        text_channel.id = 200

        with patch(
            "src.cogs.voice.delete_voice_session", new_callable=AsyncMock
        ) as mock_delete:
            await cog.on_guild_channel_delete(text_channel)
            mock_delete.assert_not_awaited()

    async def test_no_error_when_no_session_exists(self) -> None:
        """Test that no error occurs when channel has no DB record."""
        cog = _make_cog()
        channel = _make_channel(300)

        mock_factory, mock_session = _mock_async_session()
        with (
            patch(
                "src.cogs.voice.delete_voice_session", new_callable=AsyncMock
            ) as mock_delete,
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            # Should not raise even if no session exists
            await cog.on_guild_channel_delete(channel)
            mock_delete.assert_awaited_once_with(mock_session, "300")

    async def test_deletes_lobby_record_on_channel_delete(self) -> None:
        """ロビー VC を削除すると DB の lobby レコードも削除される。"""
        cog = _make_cog()
        channel = _make_channel(100)

        lobby = MagicMock()
        lobby.id = 42

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.delete_voice_session", new_callable=AsyncMock),
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=lobby,
            ),
            patch(
                "src.cogs.voice.delete_lobby",
                new_callable=AsyncMock,
            ) as mock_delete_lobby,
        ):
            await cog.on_guild_channel_delete(channel)

            mock_delete_lobby.assert_awaited_once_with(mock_session, 42)

    async def test_no_lobby_delete_when_not_lobby(self) -> None:
        """ロビーでないチャンネル削除時は lobby レコード削除が呼ばれない。"""
        cog = _make_cog()
        channel = _make_channel(100)

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.delete_voice_session", new_callable=AsyncMock),
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.cogs.voice.delete_lobby",
                new_callable=AsyncMock,
            ) as mock_delete_lobby,
        ):
            await cog.on_guild_channel_delete(channel)

            mock_delete_lobby.assert_not_awaited()


# ===========================================================================
# _handle_lobby_join テスト
# ===========================================================================


class TestHandleLobbyJoin:
    """Tests for _handle_lobby_join."""

    async def test_skips_non_lobby_channel(self) -> None:
        """ロビーではないチャンネルに参加しても何もしない。"""
        cog = _make_cog()
        member = _make_member(1)
        channel = _make_channel(100)

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.cogs.voice.create_voice_session",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog._handle_lobby_join(member, channel)
            mock_create.assert_not_awaited()

    async def test_creates_channel_and_session(self) -> None:
        """ロビー参加時に VC を作成し、DB セッションを記録する。"""
        cog = _make_cog()
        member = _make_member(1)
        channel = _make_channel(100)
        channel.category = MagicMock(spec=discord.CategoryChannel)

        lobby = MagicMock()
        lobby.id = 10
        lobby.category_id = None
        lobby.default_user_limit = 5

        new_channel = _make_channel(200)
        new_channel.send = AsyncMock(return_value=MagicMock(pin=AsyncMock()))
        new_channel.set_permissions = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.create_voice_channel = AsyncMock(return_value=new_channel)
        guild.default_role = MagicMock()
        member.guild = guild
        member.move_to = AsyncMock()

        voice_session = _make_voice_session(channel_id="200", owner_id="1")

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=lobby,
            ),
            patch(
                "src.cogs.voice.create_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ) as mock_create,
            patch(
                "src.cogs.voice.add_voice_session_member",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.create_control_panel_embed",
                return_value=MagicMock(),
            ),
            patch(
                "src.cogs.voice.ControlPanelView",
                return_value=MagicMock(),
            ),
        ):
            await cog._handle_lobby_join(member, channel)

            # VC が作成される
            guild.create_voice_channel.assert_awaited_once()
            # DB セッションが作成される
            mock_create.assert_awaited_once()
            # メンバーが移動される
            member.move_to.assert_awaited_once_with(new_channel)
            # コントロールパネルが送信される
            new_channel.send.assert_awaited_once()

    async def test_cleanup_on_move_failure(self) -> None:
        """move_to 失敗時にチャンネルと DB レコードをクリーンアップする。"""
        cog = _make_cog()
        member = _make_member(1)
        channel = _make_channel(100)
        channel.category = MagicMock(spec=discord.CategoryChannel)

        lobby = MagicMock()
        lobby.id = 10
        lobby.category_id = None
        lobby.default_user_limit = 0

        new_channel = _make_channel(200)
        new_channel.set_permissions = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(status=500), "error")
        )
        new_channel.delete = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.create_voice_channel = AsyncMock(return_value=new_channel)
        guild.default_role = MagicMock()
        member.guild = guild
        member.move_to = AsyncMock()

        voice_session = _make_voice_session(channel_id="200")

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=lobby,
            ),
            patch(
                "src.cogs.voice.create_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
            patch(
                "src.cogs.voice.add_voice_session_member",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.delete_voice_session",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            await cog._handle_lobby_join(member, channel)

            # クリーンアップ: チャンネル削除 + DB レコード削除
            new_channel.delete.assert_awaited_once()
            mock_delete.assert_awaited_once_with(mock_session, "200")


# ===========================================================================
# _handle_channel_leave テスト
# ===========================================================================


class TestHandleChannelLeave:
    """Tests for _handle_channel_leave."""

    async def test_skips_non_session_channel(self) -> None:
        """一時 VC ではないチャンネルからの退出は無視する。"""
        cog = _make_cog()
        member = _make_member(1)
        channel = _make_channel(100)

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.cogs.voice.delete_voice_session",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            await cog._handle_channel_leave(member, channel)
            mock_delete.assert_not_awaited()

    async def test_deletes_empty_channel(self) -> None:
        """全員退出時にチャンネルと DB レコードを削除する。"""
        cog = _make_cog()
        cog._record_join_cache(100, 1)
        member = _make_member(1)
        channel = _make_channel(100, [])  # 空のチャンネル
        channel.delete = AsyncMock()

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
            patch(
                "src.cogs.voice.delete_voice_session",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            await cog._handle_channel_leave(member, channel)

            channel.delete.assert_awaited_once()
            mock_delete.assert_awaited_once_with(mock_session, "100")
            assert 100 not in cog._join_times

    async def test_transfers_ownership_when_owner_leaves(self) -> None:
        """オーナー退出時に引き継ぎ処理が呼ばれる。"""
        cog = _make_cog()
        owner = _make_member(1)
        remaining = _make_member(2)
        channel = _make_channel(100, [remaining])
        channel.set_permissions = AsyncMock()
        channel.send = AsyncMock()
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: remaining if uid == 2 else None

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_db_member2 = MagicMock()
        mock_db_member2.user_id = "2"

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
            patch(
                "src.cogs.voice.update_voice_session",
                new_callable=AsyncMock,
            ) as mock_update,
            patch(
                "src.cogs.voice.repost_panel",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.get_voice_session_members_ordered",
                new_callable=AsyncMock,
                return_value=[mock_db_member2],
            ),
        ):
            await cog._handle_channel_leave(owner, channel)

            # オーナー ID が新オーナーに更新される
            mock_update.assert_awaited_once()
            call_kwargs = mock_update.call_args
            assert call_kwargs[1]["owner_id"] == "2"

    async def test_no_transfer_when_non_owner_leaves(self) -> None:
        """オーナー以外の退出では引き継ぎしない。"""
        cog = _make_cog()
        owner = _make_member(1)
        leaver = _make_member(2)
        channel = _make_channel(100, [owner])

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
            patch(
                "src.cogs.voice.update_voice_session",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            await cog._handle_channel_leave(leaver, channel)
            mock_update.assert_not_awaited()


# ===========================================================================
# _transfer_ownership テスト
# ===========================================================================


class TestTransferOwnership:
    """Tests for _transfer_ownership."""

    async def test_transfers_to_longest_member(self) -> None:
        """最も長く滞在しているメンバーにオーナーが移る。"""
        cog = _make_cog()
        old_owner = _make_member(1)
        m2 = _make_member(2)
        m3 = _make_member(3)
        channel = _make_channel(100, [m2, m3])
        channel.set_permissions = AsyncMock()
        channel.send = AsyncMock()
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: m2 if uid == 2 else m3

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        # DB からの参加順: m2 が先
        mock_db_member2 = MagicMock()
        mock_db_member2.user_id = "2"
        mock_db_member3 = MagicMock()
        mock_db_member3.user_id = "3"

        mock_session = AsyncMock()
        with (
            patch(
                "src.cogs.voice.update_voice_session",
                new_callable=AsyncMock,
            ) as mock_update,
            patch(
                "src.cogs.voice.repost_panel",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.get_voice_session_members_ordered",
                new_callable=AsyncMock,
                return_value=[mock_db_member2, mock_db_member3],
            ),
        ):
            await cog._transfer_ownership(
                mock_session, voice_session, old_owner, channel
            )

            mock_update.assert_awaited_once()
            assert mock_update.call_args[1]["owner_id"] == "2"

    async def test_updates_text_permissions(self) -> None:
        """テキストチャット権限が旧→新オーナーに移行される。"""
        cog = _make_cog()
        old_owner = _make_member(1)
        new_owner = _make_member(2)
        channel = _make_channel(100, [new_owner])
        channel.set_permissions = AsyncMock()
        channel.send = AsyncMock()
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: new_owner if uid == 2 else None

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_db_member2 = MagicMock()
        mock_db_member2.user_id = "2"

        mock_session = AsyncMock()
        with (
            patch(
                "src.cogs.voice.update_voice_session",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.repost_panel",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.get_voice_session_members_ordered",
                new_callable=AsyncMock,
                return_value=[mock_db_member2],
            ),
        ):
            await cog._transfer_ownership(
                mock_session, voice_session, old_owner, channel
            )

            # set_permissions が2回呼ばれる (旧オーナー解除 + 新オーナー付与)
            assert channel.set_permissions.await_count == 2
            calls = channel.set_permissions.call_args_list
            # 旧オーナー: read_message_history=None
            assert calls[0][1]["read_message_history"] is None
            # 新オーナー: read_message_history=True
            assert calls[1][1]["read_message_history"] is True

    async def test_reposts_panel(self) -> None:
        """コントロールパネルが再投稿される。"""
        cog = _make_cog()
        old_owner = _make_member(1)
        new_owner = _make_member(2)
        channel = _make_channel(100, [new_owner])
        channel.set_permissions = AsyncMock()
        channel.send = AsyncMock()
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: new_owner if uid == 2 else None

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_db_member2 = MagicMock()
        mock_db_member2.user_id = "2"

        mock_session = AsyncMock()
        with (
            patch(
                "src.cogs.voice.update_voice_session",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.repost_panel",
                new_callable=AsyncMock,
            ) as mock_repost,
            patch(
                "src.cogs.voice.get_voice_session_members_ordered",
                new_callable=AsyncMock,
                return_value=[mock_db_member2],
            ),
        ):
            await cog._transfer_ownership(
                mock_session, voice_session, old_owner, channel
            )

            mock_repost.assert_awaited_once_with(channel, cog.bot)

    async def test_sends_notification(self) -> None:
        """引き継ぎ通知がチャンネルに送信される。"""
        cog = _make_cog()
        old_owner = _make_member(1)
        new_owner = _make_member(2)
        channel = _make_channel(100, [new_owner])
        channel.set_permissions = AsyncMock()
        channel.send = AsyncMock()
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: new_owner if uid == 2 else None

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_db_member2 = MagicMock()
        mock_db_member2.user_id = "2"

        mock_session = AsyncMock()
        with (
            patch(
                "src.cogs.voice.update_voice_session",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.repost_panel",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.get_voice_session_members_ordered",
                new_callable=AsyncMock,
                return_value=[mock_db_member2],
            ),
        ):
            await cog._transfer_ownership(
                mock_session, voice_session, old_owner, channel
            )

            channel.send.assert_awaited_once()
            msg = channel.send.call_args[0][0]
            assert new_owner.mention in msg

    async def test_no_transfer_when_no_humans(self) -> None:
        """人間のメンバーがいない場合は引き継ぎしない。"""
        cog = _make_cog()
        old_owner = _make_member(1)
        bot_member = _make_member(99, bot=True)
        channel = _make_channel(100, [bot_member])
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: bot_member if uid == 99 else None

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_session = AsyncMock()
        with (
            patch(
                "src.cogs.voice.update_voice_session",
                new_callable=AsyncMock,
            ) as mock_update,
            patch(
                "src.cogs.voice.get_voice_session_members_ordered",
                new_callable=AsyncMock,
                return_value=[],  # DB に記録なし
            ),
        ):
            await cog._transfer_ownership(
                mock_session, voice_session, old_owner, channel
            )
            mock_update.assert_not_awaited()


# ===========================================================================
# _find_panel_message テスト
# ===========================================================================


class TestFindPanelMessage:
    """Tests for _find_panel_message."""

    async def test_finds_pinned_message(self) -> None:
        """ピン留めメッセージから Bot の Embed を見つける。"""
        cog = _make_cog()
        channel = _make_channel(100)

        bot_msg = MagicMock()
        bot_msg.author = cog.bot.user
        bot_msg.embeds = [MagicMock()]

        channel.pins = AsyncMock(return_value=[bot_msg])

        result = await cog._find_panel_message(channel)
        assert result is bot_msg

    async def test_falls_back_to_history(self) -> None:
        """ピンがない場合は履歴から探す。"""
        cog = _make_cog()
        channel = _make_channel(100)

        channel.pins = AsyncMock(return_value=[])

        bot_msg = MagicMock()
        bot_msg.author = cog.bot.user
        bot_msg.embeds = [MagicMock()]

        # AsyncIterator をモック
        async def _history(**_: object) -> AsyncMock:
            """Mock async iterator for channel.history."""

        async def _aiter() -> MagicMock:
            yield bot_msg

        channel.history = MagicMock(return_value=_aiter())

        result = await cog._find_panel_message(channel)
        assert result is bot_msg

    async def test_returns_none_when_not_found(self) -> None:
        """メッセージが見つからない場合は None を返す。"""
        cog = _make_cog()
        channel = _make_channel(100)

        channel.pins = AsyncMock(return_value=[])

        async def _empty_aiter() -> MagicMock:
            return
            yield  # make it an async generator  # noqa: RET504

        channel.history = MagicMock(return_value=_empty_aiter())

        result = await cog._find_panel_message(channel)
        assert result is None

    async def test_skips_non_bot_messages(self) -> None:
        """Bot 以外のメッセージはスキップする。"""
        cog = _make_cog()
        channel = _make_channel(100)

        other_user = MagicMock(spec=discord.User)
        other_user.id = 8888
        non_bot_msg = MagicMock()
        non_bot_msg.author = other_user
        non_bot_msg.embeds = [MagicMock()]

        bot_msg = MagicMock()
        bot_msg.author = cog.bot.user
        bot_msg.embeds = [MagicMock()]

        channel.pins = AsyncMock(return_value=[non_bot_msg, bot_msg])

        result = await cog._find_panel_message(channel)
        assert result is bot_msg


# ===========================================================================
# on_voice_state_update テスト
# ===========================================================================


class TestOnVoiceStateUpdate:
    """Tests for on_voice_state_update event handler."""

    async def test_join_calls_handle_lobby_join(self) -> None:
        """VC 参加時に _handle_lobby_join が呼ばれる。"""
        cog = _make_cog()
        member = _make_member(1)

        before = MagicMock(spec=discord.VoiceState)
        before.channel = None

        after = MagicMock(spec=discord.VoiceState)
        after.channel = _make_channel(100)

        cog._handle_lobby_join = AsyncMock()  # type: ignore[method-assign]
        cog._record_join_to_db = AsyncMock()  # type: ignore[method-assign]

        await cog.on_voice_state_update(member, before, after)

        cog._handle_lobby_join.assert_awaited_once_with(member, after.channel)
        assert 1 in cog._join_times[100]

    async def test_leave_calls_handle_channel_leave(self) -> None:
        """VC 退出時に _handle_channel_leave が呼ばれる。"""
        cog = _make_cog()
        cog._record_join_cache(100, 1)
        member = _make_member(1)

        before = MagicMock(spec=discord.VoiceState)
        before.channel = _make_channel(100)

        after = MagicMock(spec=discord.VoiceState)
        after.channel = None

        cog._handle_channel_leave = AsyncMock()  # type: ignore[method-assign]
        cog._remove_join_from_db = AsyncMock()  # type: ignore[method-assign]

        await cog.on_voice_state_update(member, before, after)

        cog._handle_channel_leave.assert_awaited_once_with(member, before.channel)
        # 参加記録が削除される
        assert 1 not in cog._join_times.get(100, {})

    async def test_same_channel_ignored(self) -> None:
        """同じチャンネル内の状態変化 (ミュート等) は無視される。"""
        cog = _make_cog()
        member = _make_member(1)
        channel = _make_channel(100)

        before = MagicMock(spec=discord.VoiceState)
        before.channel = channel
        after = MagicMock(spec=discord.VoiceState)
        after.channel = channel

        cog._handle_lobby_join = AsyncMock()  # type: ignore[method-assign]
        cog._handle_channel_leave = AsyncMock()  # type: ignore[method-assign]

        await cog.on_voice_state_update(member, before, after)

        cog._handle_lobby_join.assert_not_awaited()
        cog._handle_channel_leave.assert_not_awaited()


# ===========================================================================
# スラッシュコマンドテスト (/vc グループ)
# ===========================================================================


def _make_interaction(
    user_id: int,
    channel: MagicMock | None = None,
    *,
    guild: MagicMock | None = "default",
    guild_id: int = 1000,
) -> MagicMock:
    """Create a mock discord.Interaction for slash commands."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = _make_member(user_id)
    interaction.channel = channel
    interaction.channel_id = channel.id if channel else None
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    if guild == "default":
        g = MagicMock(spec=discord.Guild)
        g.create_voice_channel = AsyncMock()
        interaction.guild = g
    else:
        interaction.guild = guild

    interaction.guild_id = guild_id
    return interaction


# ===========================================================================
# /vc lobby コマンドテスト
# ===========================================================================


class TestVcLobbyCommand:
    """Tests for /vc lobby slash command."""

    async def test_creates_lobby_successfully(self) -> None:
        """正常系: VC を作成し DB に登録して完了メッセージを返す。"""
        cog = _make_cog()
        interaction = _make_interaction(1)

        lobby_channel = MagicMock(spec=discord.VoiceChannel)
        lobby_channel.id = 500
        lobby_channel.name = "参加して作成"
        interaction.guild.create_voice_channel = AsyncMock(return_value=lobby_channel)

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobbies_by_guild",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.cogs.voice.create_lobby", new_callable=AsyncMock) as mock_create,
        ):
            await cog.vc_lobby.callback(cog, interaction)

            # VC が作成される
            interaction.guild.create_voice_channel.assert_awaited_once_with(
                name="参加して作成"
            )
            # DB にロビーとして登録される
            mock_create.assert_awaited_once_with(
                mock_session,
                guild_id=str(interaction.guild_id),
                lobby_channel_id="500",
                category_id=None,
                default_user_limit=0,
            )
            # 完了メッセージ
            interaction.response.send_message.assert_awaited_once()
            msg = interaction.response.send_message.call_args[0][0]
            assert "参加して作成" in msg
            assert interaction.response.send_message.call_args[1]["ephemeral"] is True

    async def test_rejects_dm(self) -> None:
        """DM からの実行は拒否される。"""
        cog = _make_cog()
        interaction = _make_interaction(1, guild=None)

        await cog.vc_lobby.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "サーバー内" in msg
        assert interaction.response.send_message.call_args[1]["ephemeral"] is True

    async def test_handles_http_exception(self) -> None:
        """Discord API エラー時にエラーメッセージを返す。"""
        cog = _make_cog()
        interaction = _make_interaction(1)
        interaction.guild.create_voice_channel = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=403), "Missing Permissions"
            )
        )

        mock_factory, _mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobbies_by_guild",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await cog.vc_lobby.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "失敗" in msg
        assert interaction.response.send_message.call_args[1]["ephemeral"] is True

    async def test_rejects_duplicate_lobby(self) -> None:
        """既にロビーが存在するサーバーでは作成を拒否する。"""
        cog = _make_cog()
        interaction = _make_interaction(1)

        existing_lobby = MagicMock()
        existing_lobby.id = 1

        mock_factory, _mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobbies_by_guild",
                new_callable=AsyncMock,
                return_value=[existing_lobby],
            ),
            patch("src.cogs.voice.create_lobby", new_callable=AsyncMock) as mock_create,
        ):
            await cog.vc_lobby.callback(cog, interaction)

            # VC は作成されない
            interaction.guild.create_voice_channel.assert_not_awaited()
            # DB 登録も呼ばれない
            mock_create.assert_not_awaited()
            # エラーメッセージ
            interaction.response.send_message.assert_awaited_once()
            msg = interaction.response.send_message.call_args[0][0]
            assert "既に" in msg
            assert interaction.response.send_message.call_args[1]["ephemeral"] is True

    async def test_no_db_call_on_vc_creation_failure(self) -> None:
        """VC 作成失敗時は DB 登録が呼ばれない。"""
        cog = _make_cog()
        interaction = _make_interaction(1)
        interaction.guild.create_voice_channel = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(status=500), "Internal Error")
        )

        mock_factory, _mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobbies_by_guild",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.cogs.voice.create_lobby", new_callable=AsyncMock) as mock_create,
        ):
            await cog.vc_lobby.callback(cog, interaction)
            mock_create.assert_not_awaited()

    async def test_lobby_channel_has_correct_name(self) -> None:
        """作成される VC の名前が「参加して作成」。"""
        cog = _make_cog()
        interaction = _make_interaction(1)

        lobby_channel = MagicMock(spec=discord.VoiceChannel)
        lobby_channel.id = 500
        lobby_channel.name = "参加して作成"
        interaction.guild.create_voice_channel = AsyncMock(return_value=lobby_channel)

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobbies_by_guild",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.cogs.voice.create_lobby", new_callable=AsyncMock),
        ):
            await cog.vc_lobby.callback(cog, interaction)

            call_kwargs = interaction.guild.create_voice_channel.call_args[1]
            assert call_kwargs["name"] == "参加して作成"

    async def test_db_registers_correct_guild_id(self) -> None:
        """DB に正しい guild_id が登録される。"""
        cog = _make_cog()
        interaction = _make_interaction(1, guild_id=7777)

        lobby_channel = MagicMock(spec=discord.VoiceChannel)
        lobby_channel.id = 500
        lobby_channel.name = "参加して作成"
        interaction.guild.create_voice_channel = AsyncMock(return_value=lobby_channel)

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobbies_by_guild",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.cogs.voice.create_lobby", new_callable=AsyncMock) as mock_create,
        ):
            await cog.vc_lobby.callback(cog, interaction)

            mock_create.assert_awaited_once()
            assert mock_create.call_args[1]["guild_id"] == "7777"

    async def test_success_message_contains_channel_name(self) -> None:
        """成功メッセージにチャンネル名が含まれる。"""
        cog = _make_cog()
        interaction = _make_interaction(1)

        lobby_channel = MagicMock(spec=discord.VoiceChannel)
        lobby_channel.id = 500
        lobby_channel.name = "参加して作成"
        interaction.guild.create_voice_channel = AsyncMock(return_value=lobby_channel)

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobbies_by_guild",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.cogs.voice.create_lobby", new_callable=AsyncMock),
        ):
            await cog.vc_lobby.callback(cog, interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "参加して作成" in msg
        assert "カテゴリ" in msg

    async def test_error_message_contains_exception_text(self) -> None:
        """エラーメッセージに例外テキストが含まれる。"""
        cog = _make_cog()
        interaction = _make_interaction(1)
        interaction.guild.create_voice_channel = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=403), "Missing Permissions"
            )
        )

        mock_factory, _mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobbies_by_guild",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await cog.vc_lobby.callback(cog, interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "失敗" in msg


# ===========================================================================
# /vc panel コマンドテスト
# ===========================================================================


class TestVcPanelCommand:
    """Tests for /vc panel slash command."""

    async def test_panel_reposts_control_panel(self) -> None:
        """正常系: repost_panel が呼ばれ、ephemeral で応答。"""
        cog = _make_cog()
        channel = _make_channel(100)
        interaction = _make_interaction(1, channel)

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
            patch(
                "src.cogs.voice.repost_panel",
                new_callable=AsyncMock,
            ) as mock_repost,
        ):
            await cog.vc_panel.callback(cog, interaction)

            # repost_panel が呼ばれる
            mock_repost.assert_awaited_once_with(channel, cog.bot)
            # ephemeral で応答
            interaction.response.send_message.assert_awaited_once()
            call_kwargs = interaction.response.send_message.call_args[1]
            assert call_kwargs["ephemeral"] is True

    async def test_panel_allowed_for_non_owner(self) -> None:
        """オーナー以外でも /vc panel を実行できる。"""
        cog = _make_cog()
        channel = _make_channel(100)
        interaction = _make_interaction(2, channel)

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_factory, _mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
            patch(
                "src.cogs.voice.repost_panel",
                new_callable=AsyncMock,
            ) as mock_repost,
        ):
            await cog.vc_panel.callback(cog, interaction)

            mock_repost.assert_awaited_once_with(channel, cog.bot)
            interaction.response.send_message.assert_awaited_once()
            call_kwargs = interaction.response.send_message.call_args[1]
            assert call_kwargs["ephemeral"] is True

    async def test_panel_rejects_non_voice_channel(self) -> None:
        """VC 外で使用すると拒否される。"""
        cog = _make_cog()
        # TextChannel (VoiceChannel ではない)
        text_channel = MagicMock(spec=discord.TextChannel)
        text_channel.id = 100
        interaction = _make_interaction(1, text_channel)

        await cog.vc_panel.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "一時 VC" in msg

    async def test_panel_rejects_no_session(self) -> None:
        """セッションが見つからない場合は拒否される。"""
        cog = _make_cog()
        channel = _make_channel(100)
        interaction = _make_interaction(1, channel)

        mock_factory, _mock_session = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.vc_panel.callback(cog, interaction)

            interaction.response.send_message.assert_awaited_once()
            msg = interaction.response.send_message.call_args[0][0]
            assert "見つかりません" in msg


# ===========================================================================
# cog_app_command_error テスト
# ===========================================================================


class TestCogAppCommandError:
    """Tests for cog_app_command_error handler."""

    async def test_cooldown_sends_message(self) -> None:
        """クールダウン中は残り秒数を通知する。"""
        cog = _make_cog()
        interaction = _make_interaction(1)

        error = app_commands.CommandOnCooldown(app_commands.Cooldown(1, 30), 15.0)
        await cog.cog_app_command_error(interaction, error)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "15" in msg
        assert interaction.response.send_message.call_args[1]["ephemeral"] is True

    async def test_other_error_reraised(self) -> None:
        """クールダウン以外のエラーは再送出される。"""
        cog = _make_cog()
        interaction = _make_interaction(1)

        error = app_commands.AppCommandError("something broke")
        try:
            await cog.cog_app_command_error(interaction, error)
            raised = False
        except app_commands.AppCommandError:
            raised = True

        assert raised
        interaction.response.send_message.assert_not_awaited()


# ===========================================================================
# _handle_lobby_join — カテゴリ解決テスト
# ===========================================================================


class TestHandleLobbyJoinCategory:
    """Tests for _handle_lobby_join category resolution."""

    async def test_uses_lobby_category_id(self) -> None:
        """ロビーに category_id が設定されている場合はそれを使う。"""
        cog = _make_cog()
        member = _make_member(1)
        channel = _make_channel(100)
        channel.category = MagicMock(spec=discord.CategoryChannel)

        custom_category = MagicMock(spec=discord.CategoryChannel)
        lobby = MagicMock()
        lobby.id = 10
        lobby.category_id = "999"
        lobby.default_user_limit = 0

        new_channel = _make_channel(200)
        new_channel.send = AsyncMock(return_value=MagicMock(pin=AsyncMock()))
        new_channel.set_permissions = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.create_voice_channel = AsyncMock(return_value=new_channel)
        guild.default_role = MagicMock()
        guild.get_channel = MagicMock(return_value=custom_category)
        member.guild = guild
        member.move_to = AsyncMock()

        voice_session = _make_voice_session(channel_id="200", owner_id="1")

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=lobby,
            ),
            patch(
                "src.cogs.voice.create_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
            patch(
                "src.cogs.voice.add_voice_session_member",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.create_control_panel_embed",
                return_value=MagicMock(),
            ),
            patch(
                "src.cogs.voice.ControlPanelView",
                return_value=MagicMock(),
            ),
        ):
            await cog._handle_lobby_join(member, channel)

        guild.get_channel.assert_called_once_with(999)
        call_kwargs = guild.create_voice_channel.call_args[1]
        assert call_kwargs["category"] == custom_category

    async def test_falls_back_to_channel_category_when_invalid(self) -> None:
        """category_id のチャンネルが CategoryChannel でない場合はロビーのカテゴリ。"""
        cog = _make_cog()
        member = _make_member(1)
        channel = _make_channel(100)
        lobby_category = MagicMock(spec=discord.CategoryChannel)
        channel.category = lobby_category

        lobby = MagicMock()
        lobby.id = 10
        lobby.category_id = "999"
        lobby.default_user_limit = 0

        new_channel = _make_channel(200)
        new_channel.send = AsyncMock(return_value=MagicMock(pin=AsyncMock()))
        new_channel.set_permissions = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.create_voice_channel = AsyncMock(return_value=new_channel)
        guild.default_role = MagicMock()
        # TextChannel を返す (CategoryChannel ではない)
        guild.get_channel = MagicMock(return_value=MagicMock(spec=discord.TextChannel))
        member.guild = guild
        member.move_to = AsyncMock()

        voice_session = _make_voice_session(channel_id="200", owner_id="1")

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=lobby,
            ),
            patch(
                "src.cogs.voice.create_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
            patch(
                "src.cogs.voice.add_voice_session_member",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.create_control_panel_embed",
                return_value=MagicMock(),
            ),
            patch(
                "src.cogs.voice.ControlPanelView",
                return_value=MagicMock(),
            ),
        ):
            await cog._handle_lobby_join(member, channel)

        call_kwargs = guild.create_voice_channel.call_args[1]
        assert call_kwargs["category"] == lobby_category

    async def test_db_error_deletes_new_channel(self) -> None:
        """DB セッション作成失敗時に VC を削除する。"""
        cog = _make_cog()
        member = _make_member(1)
        channel = _make_channel(100)
        channel.category = MagicMock(spec=discord.CategoryChannel)

        lobby = MagicMock()
        lobby.id = 10
        lobby.category_id = None
        lobby.default_user_limit = 0

        new_channel = _make_channel(200)
        new_channel.delete = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.create_voice_channel = AsyncMock(return_value=new_channel)
        guild.default_role = MagicMock()
        member.guild = guild

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=lobby,
            ),
            patch(
                "src.cogs.voice.create_voice_session",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB error"),
            ),
            contextlib.suppress(RuntimeError),
        ):
            await cog._handle_lobby_join(member, channel)

        new_channel.delete.assert_awaited_once()


# ===========================================================================
# on_voice_state_update — 追加エッジケース
# ===========================================================================


class TestOnVoiceStateUpdateEdgeCases:
    """on_voice_state_update の追加エッジケース。"""

    async def test_move_between_channels(self) -> None:
        """チャンネル間移動では退出と参加の両方が処理される。"""
        cog = _make_cog()
        member = _make_member(1)
        cog._record_join_cache(100, 1)

        old_channel = _make_channel(100)
        new_channel = _make_channel(200)

        before = MagicMock(spec=discord.VoiceState)
        before.channel = old_channel
        after = MagicMock(spec=discord.VoiceState)
        after.channel = new_channel

        cog._handle_lobby_join = AsyncMock()  # type: ignore[method-assign]
        cog._handle_channel_leave = AsyncMock()  # type: ignore[method-assign]
        cog._record_join_to_db = AsyncMock()  # type: ignore[method-assign]
        cog._remove_join_from_db = AsyncMock()  # type: ignore[method-assign]

        await cog.on_voice_state_update(member, before, after)

        # 参加処理
        cog._handle_lobby_join.assert_awaited_once_with(member, new_channel)
        assert 1 in cog._join_times[200]
        # 退出処理
        cog._handle_channel_leave.assert_awaited_once_with(member, old_channel)
        assert 1 not in cog._join_times.get(100, {})

    async def test_non_voice_channel_join_ignored(self) -> None:
        """StageChannel など VoiceChannel でない場合は無視。"""
        cog = _make_cog()
        member = _make_member(1)

        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock(spec=discord.StageChannel)
        after.channel.id = 300

        cog._handle_lobby_join = AsyncMock()  # type: ignore[method-assign]

        await cog.on_voice_state_update(member, before, after)

        cog._handle_lobby_join.assert_not_awaited()

    async def test_non_voice_channel_leave_ignored(self) -> None:
        """VoiceChannel でないチャンネルからの退出は無視。"""
        cog = _make_cog()
        member = _make_member(1)

        before = MagicMock(spec=discord.VoiceState)
        before.channel = MagicMock(spec=discord.StageChannel)
        before.channel.id = 300
        after = MagicMock(spec=discord.VoiceState)
        after.channel = None

        cog._handle_channel_leave = AsyncMock()  # type: ignore[method-assign]

        await cog.on_voice_state_update(member, before, after)

        cog._handle_channel_leave.assert_not_awaited()


# ===========================================================================
# _enforce_channel_restrictions テスト
# ===========================================================================


class TestEnforceChannelRestrictions:
    """Tests for _enforce_channel_restrictions (ロック/人数制限の強制)."""

    async def test_allows_bot_users(self) -> None:
        """Bot ユーザーは常に許可される。"""
        cog = _make_cog()
        member = _make_member(1, bot=True)
        channel = _make_channel(100)

        result = await cog._enforce_channel_restrictions(member, channel)

        assert result is False

    async def test_allows_administrators(self) -> None:
        """Administrator 権限を持つユーザーは常に許可される。"""
        cog = _make_cog()
        member = _make_member(1)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = True
        channel = _make_channel(100)

        voice_session = _make_voice_session(
            channel_id="100", owner_id="999", is_locked=True
        )

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        assert result is False

    async def test_allows_owner(self) -> None:
        """オーナーは常に許可される。"""
        cog = _make_cog()
        member = _make_member(1)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        channel = _make_channel(100)

        voice_session = _make_voice_session(
            channel_id="100", owner_id="1", is_locked=True
        )

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        assert result is False

    async def test_kicks_non_permitted_user_on_locked_channel(self) -> None:
        """ロックされた VC に許可されていないユーザーが入るとキックされる。"""
        cog = _make_cog()
        member = _make_member(2)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        member.move_to = AsyncMock()
        member.send = AsyncMock()  # DM 送信用
        channel = _make_channel(100)
        channel.name = "Test Channel"
        channel.send = AsyncMock()
        # connect 権限が設定されていない
        overwrites = MagicMock()
        overwrites.connect = None
        channel.overwrites_for = MagicMock(return_value=overwrites)

        voice_session = _make_voice_session(
            channel_id="100", owner_id="1", is_locked=True
        )

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        assert result is True
        member.move_to.assert_awaited_once_with(None)
        channel.send.assert_awaited_once()  # チャンネルに通知
        member.send.assert_awaited_once()  # DM で通知

    async def test_allows_permitted_user_on_locked_channel(self) -> None:
        """ロックされた VC でも connect=True が設定されていれば許可される。"""
        cog = _make_cog()
        member = _make_member(2)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        channel = _make_channel(100)
        # connect=True が設定されている
        overwrites = MagicMock()
        overwrites.connect = True
        channel.overwrites_for = MagicMock(return_value=overwrites)

        voice_session = _make_voice_session(
            channel_id="100", owner_id="1", is_locked=True
        )

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        assert result is False

    async def test_kicks_user_exceeding_limit(self) -> None:
        """人数制限を超えた場合、許可されていないユーザーはキックされる。"""
        cog = _make_cog()
        member = _make_member(3)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        member.move_to = AsyncMock()
        member.send = AsyncMock()  # DM 送信用
        # 既に 2 人いる (+ 参加者で 3 人、制限は 2)
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2, member])
        channel.name = "Test Channel"
        channel.send = AsyncMock()
        overwrites = MagicMock()
        overwrites.connect = None
        channel.overwrites_for = MagicMock(return_value=overwrites)

        voice_session = _make_voice_session(channel_id="100", owner_id="1")
        voice_session.user_limit = 2

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        assert result is True
        member.move_to.assert_awaited_once_with(None)
        channel.send.assert_awaited_once()  # チャンネルに通知
        member.send.assert_awaited_once()  # DM で通知

    async def test_allows_permitted_user_exceeding_limit(self) -> None:
        """人数制限を超えていても connect=True が設定されていれば許可される。"""
        cog = _make_cog()
        member = _make_member(3)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2, member])
        # connect=True が設定されている
        overwrites = MagicMock()
        overwrites.connect = True
        channel.overwrites_for = MagicMock(return_value=overwrites)

        voice_session = _make_voice_session(channel_id="100", owner_id="1")
        voice_session.user_limit = 2

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        assert result is False

    async def test_skips_non_voice_session(self) -> None:
        """一時 VC ではないチャンネルは制限チェックをスキップする。"""
        cog = _make_cog()
        member = _make_member(1)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        channel = _make_channel(100)

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        assert result is False

    async def test_kick_succeeds_even_if_dm_fails(self) -> None:
        """DM 送信が失敗してもキックは成功する。"""
        cog = _make_cog()
        member = _make_member(2)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        member.move_to = AsyncMock()
        member.send = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(status=403), "Cannot send DM")
        )
        channel = _make_channel(100)
        channel.name = "Test Channel"
        channel.send = AsyncMock()
        overwrites = MagicMock()
        overwrites.connect = None
        channel.overwrites_for = MagicMock(return_value=overwrites)

        voice_session = _make_voice_session(
            channel_id="100", owner_id="1", is_locked=True
        )

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        # DM が失敗してもキックは成功
        assert result is True
        member.move_to.assert_awaited_once_with(None)
        channel.send.assert_awaited_once()

    async def test_kick_succeeds_even_if_channel_send_fails(self) -> None:
        """チャンネル送信が失敗してもキックは成功する。"""
        cog = _make_cog()
        member = _make_member(2)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        member.move_to = AsyncMock()
        member.send = AsyncMock()
        channel = _make_channel(100)
        channel.name = "Test Channel"
        channel.send = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(status=500), "Server error")
        )
        overwrites = MagicMock()
        overwrites.connect = None
        channel.overwrites_for = MagicMock(return_value=overwrites)

        voice_session = _make_voice_session(
            channel_id="100", owner_id="1", is_locked=True
        )

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        # チャンネル送信が失敗してもキックは成功
        assert result is True
        member.move_to.assert_awaited_once_with(None)


# ===========================================================================
# on_voice_state_update と制限チェックの統合テスト
# ===========================================================================


class TestVoiceStateUpdateWithRestrictions:
    """on_voice_state_update での制限チェック統合テスト。"""

    async def test_skips_join_recording_when_kicked(self) -> None:
        """制限違反でキックされた場合、参加記録がスキップされる。"""
        cog = _make_cog()
        member = _make_member(2)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        member.move_to = AsyncMock()
        member.send = AsyncMock()

        channel = _make_channel(100)
        channel.name = "Test Channel"
        channel.send = AsyncMock()
        overwrites = MagicMock()
        overwrites.connect = None
        channel.overwrites_for = MagicMock(return_value=overwrites)

        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = channel

        voice_session = _make_voice_session(
            channel_id="100", owner_id="1", is_locked=True
        )

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            await cog.on_voice_state_update(member, before, after)

        # キックされたので参加記録がない
        assert 2 not in cog._join_times.get(100, {})
        member.move_to.assert_awaited_once_with(None)


# ===========================================================================
# Faker を使ったランダムデータテスト
# ===========================================================================


from faker import Faker  # noqa: E402

fake = Faker("ja_JP")


def _snowflake() -> str:
    """Discord snowflake 風の ID を生成する。"""
    return str(fake.random_number(digits=18, fix_len=True))


class TestVoiceCogWithFaker:
    """Faker を使ったランダムデータでのテスト。"""

    def test_record_join_cache_with_random_ids(self) -> None:
        """ランダムな ID で参加記録が正しく動作する。"""
        cog = _make_cog()
        channel_id = int(_snowflake())
        user_id = int(_snowflake())

        cog._record_join_cache(channel_id, user_id)

        assert user_id in cog._join_times[channel_id]

    def test_multiple_random_members_in_cache(self) -> None:
        """ランダムな複数メンバーの参加記録が正しく動作する。"""
        cog = _make_cog()
        channel_id = int(_snowflake())
        user_ids = [int(_snowflake()) for _ in range(5)]

        for user_id in user_ids:
            cog._record_join_cache(channel_id, user_id)

        assert len(cog._join_times[channel_id]) == 5
        for user_id in user_ids:
            assert user_id in cog._join_times[channel_id]

    async def test_get_longest_member_with_random_ids(self) -> None:
        """ランダム ID で最古メンバー取得が正しく動作する。"""
        cog = _make_cog()
        user_id_1 = int(_snowflake())
        user_id_2 = int(_snowflake())

        m1 = _make_member(user_id_1)
        m2 = _make_member(user_id_2)
        channel = _make_channel(int(_snowflake()), [m1, m2])
        channel.guild = MagicMock()
        channel.guild.get_member = lambda uid: m1 if uid == user_id_1 else m2

        voice_session = _make_voice_session()

        mock_db_member1 = MagicMock()
        mock_db_member1.user_id = str(user_id_1)
        mock_db_member2 = MagicMock()
        mock_db_member2.user_id = str(user_id_2)

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.get_voice_session_members_ordered",
            new_callable=AsyncMock,
            return_value=[mock_db_member1, mock_db_member2],
        ):
            result = await cog._get_longest_member(
                mock_session, voice_session, channel, exclude_id=999999
            )
            assert result is m1

    async def test_voice_session_with_random_channel_name(self) -> None:
        """ランダムなチャンネル名でセッション作成。"""
        cog = _make_cog()
        member = _make_member(int(_snowflake()))
        channel = _make_channel(int(_snowflake()))
        channel.category = MagicMock(spec=discord.CategoryChannel)

        lobby = MagicMock()
        lobby.id = fake.random_int(min=1, max=1000)
        lobby.category_id = None
        lobby.default_user_limit = fake.random_int(min=0, max=10)

        new_channel_id = int(_snowflake())
        new_channel = _make_channel(new_channel_id)
        new_channel.send = AsyncMock(return_value=MagicMock(pin=AsyncMock()))
        new_channel.set_permissions = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.create_voice_channel = AsyncMock(return_value=new_channel)
        guild.default_role = MagicMock()
        member.guild = guild
        member.move_to = AsyncMock()

        voice_session = _make_voice_session(
            channel_id=str(new_channel_id), owner_id=str(member.id)
        )

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=lobby,
            ),
            patch(
                "src.cogs.voice.create_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
            patch(
                "src.cogs.voice.add_voice_session_member",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.create_control_panel_embed",
                return_value=MagicMock(),
            ),
            patch(
                "src.cogs.voice.ControlPanelView",
                return_value=MagicMock(),
            ),
        ):
            await cog._handle_lobby_join(member, channel)

            guild.create_voice_channel.assert_awaited_once()


class TestVoiceCogWithParametrize:
    """パラメタライズテスト。"""

    @pytest.mark.parametrize(
        "user_limit,member_count,should_kick",
        [
            (0, 5, False),  # 制限なしなら何人でもOK
            (5, 3, False),  # 制限内ならOK
            (5, 5, False),  # ちょうど制限と同じならOK
            (5, 6, True),  # 制限超過でキック
            (2, 10, True),  # 大幅超過でキック
        ],
    )
    async def test_user_limit_enforcement(
        self, user_limit: int, member_count: int, should_kick: bool
    ) -> None:
        """人数制限によるキック判定のパラメタライズテスト。"""
        cog = _make_cog()
        new_member = _make_member(99)
        new_member.guild_permissions = MagicMock()
        new_member.guild_permissions.administrator = False
        new_member.move_to = AsyncMock()
        new_member.send = AsyncMock()

        # member_count 人いる状態 (new_member を含む)
        members = [_make_member(i) for i in range(member_count - 1)] + [new_member]
        channel = _make_channel(100, members)
        channel.name = "Test Channel"
        channel.send = AsyncMock()
        overwrites = MagicMock()
        overwrites.connect = None
        channel.overwrites_for = MagicMock(return_value=overwrites)

        voice_session = _make_voice_session(channel_id="100", owner_id="1")
        voice_session.user_limit = user_limit

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(new_member, channel)

        assert result is should_kick

    @pytest.mark.parametrize(
        "is_locked,has_connect_permission,should_kick",
        [
            (False, None, False),  # ロックなし
            (False, True, False),  # ロックなし、権限あり
            (True, True, False),  # ロックあり、権限あり → OK
            (True, None, True),  # ロックあり、権限なし → キック
            (True, False, True),  # ロックあり、明示的拒否 → キック
        ],
    )
    async def test_lock_enforcement(
        self, is_locked: bool, has_connect_permission: bool | None, should_kick: bool
    ) -> None:
        """ロック状態によるキック判定のパラメタライズテスト。"""
        cog = _make_cog()
        member = _make_member(99)
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        member.move_to = AsyncMock()
        member.send = AsyncMock()

        channel = _make_channel(100, [member])
        channel.name = "Test Channel"
        channel.send = AsyncMock()
        overwrites = MagicMock()
        overwrites.connect = has_connect_permission
        channel.overwrites_for = MagicMock(return_value=overwrites)

        voice_session = _make_voice_session(
            channel_id="100", owner_id="1", is_locked=is_locked
        )

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        assert result is should_kick

    @pytest.mark.parametrize(
        "is_admin,is_owner,is_bot,expected_bypass",
        [
            (True, False, False, True),  # 管理者はバイパス
            (False, True, False, True),  # オーナーはバイパス
            (False, False, True, True),  # Bot はバイパス
            (False, False, False, False),  # 一般ユーザーはバイパスしない
        ],
    )
    async def test_restriction_bypass(
        self, is_admin: bool, is_owner: bool, is_bot: bool, expected_bypass: bool
    ) -> None:
        """制限バイパスのパラメタライズテスト。"""
        cog = _make_cog()
        member = _make_member(99, bot=is_bot)
        if not is_bot:
            member.guild_permissions = MagicMock()
            member.guild_permissions.administrator = is_admin
            member.move_to = AsyncMock()
            member.send = AsyncMock()

        channel = _make_channel(100, [member])
        channel.name = "Test Channel"
        channel.send = AsyncMock()
        overwrites = MagicMock()
        overwrites.connect = None
        channel.overwrites_for = MagicMock(return_value=overwrites)

        owner_id = "99" if is_owner else "1"
        voice_session = _make_voice_session(
            channel_id="100", owner_id=owner_id, is_locked=True
        )

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ),
        ):
            result = await cog._enforce_channel_restrictions(member, channel)

        # バイパスが期待される場合、キックされない (result=False)
        assert result is not expected_bypass

    @pytest.mark.parametrize(
        "default_user_limit",
        [0, 1, 5, 10, 99],
    )
    async def test_lobby_default_user_limit(self, default_user_limit: int) -> None:
        """ロビーのデフォルト人数制限がセッションに反映される。"""
        cog = _make_cog()
        member = _make_member(1)
        channel = _make_channel(100)
        channel.category = MagicMock(spec=discord.CategoryChannel)

        lobby = MagicMock()
        lobby.id = 10
        lobby.category_id = None
        lobby.default_user_limit = default_user_limit

        new_channel = _make_channel(200)
        new_channel.send = AsyncMock(return_value=MagicMock(pin=AsyncMock()))
        new_channel.set_permissions = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.create_voice_channel = AsyncMock(return_value=new_channel)
        guild.default_role = MagicMock()
        member.guild = guild
        member.move_to = AsyncMock()

        voice_session = _make_voice_session(channel_id="200", owner_id="1")

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.voice.async_session", mock_factory),
            patch(
                "src.cogs.voice.get_lobby_by_channel_id",
                new_callable=AsyncMock,
                return_value=lobby,
            ),
            patch(
                "src.cogs.voice.create_voice_session",
                new_callable=AsyncMock,
                return_value=voice_session,
            ) as mock_create,
            patch(
                "src.cogs.voice.add_voice_session_member",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.voice.create_control_panel_embed",
                return_value=MagicMock(),
            ),
            patch(
                "src.cogs.voice.ControlPanelView",
                return_value=MagicMock(),
            ),
        ):
            await cog._handle_lobby_join(member, channel)

            mock_create.assert_awaited_once()
            assert mock_create.call_args[1]["user_limit"] == default_user_limit

    @pytest.mark.parametrize(
        "channel_type,expected_handled",
        [
            (discord.VoiceChannel, True),
            (discord.StageChannel, False),
            (discord.TextChannel, False),
        ],
    )
    async def test_channel_type_filtering(
        self, channel_type: type, expected_handled: bool
    ) -> None:
        """チャンネルタイプによるフィルタリング。"""
        cog = _make_cog()
        member = _make_member(1)

        before = MagicMock(spec=discord.VoiceState)
        before.channel = None

        after_channel = MagicMock(spec=channel_type)
        after_channel.id = 100
        after = MagicMock(spec=discord.VoiceState)
        after.channel = after_channel

        cog._handle_lobby_join = AsyncMock()  # type: ignore[method-assign]
        cog._record_join_to_db = AsyncMock()  # type: ignore[method-assign]
        cog._enforce_channel_restrictions = AsyncMock(  # type: ignore[method-assign]
            return_value=False
        )

        await cog.on_voice_state_update(member, before, after)

        if expected_handled:
            cog._handle_lobby_join.assert_awaited_once()
        else:
            cog._handle_lobby_join.assert_not_awaited()
