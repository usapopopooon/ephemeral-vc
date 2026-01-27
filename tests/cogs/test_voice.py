"""Tests for VoiceCog join tracking helpers and event listeners."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
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


def _make_channel(
    channel_id: int, members: list[MagicMock] | None = None
) -> MagicMock:
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
    mock_factory.return_value.__aenter__ = AsyncMock(
        return_value=mock_session
    )
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_factory, mock_session


class TestRecordJoin:
    """Tests for _record_join."""

    def test_new_member(self) -> None:
        """Test recording a new member join."""
        cog = _make_cog()
        cog._record_join(100, 1)
        assert 1 in cog._join_times[100]

    def test_no_overwrite(self) -> None:
        """Test that existing join time is not overwritten."""
        cog = _make_cog()
        cog._record_join(100, 1)
        first_time = cog._join_times[100][1]
        cog._record_join(100, 1)
        assert cog._join_times[100][1] == first_time

    def test_multiple_members(self) -> None:
        """Test recording multiple members in the same channel."""
        cog = _make_cog()
        cog._record_join(100, 1)
        cog._record_join(100, 2)
        assert len(cog._join_times[100]) == 2

    def test_multiple_channels(self) -> None:
        """Test recording joins across different channels."""
        cog = _make_cog()
        cog._record_join(100, 1)
        cog._record_join(200, 2)
        assert 100 in cog._join_times
        assert 200 in cog._join_times


class TestRemoveJoin:
    """Tests for _remove_join."""

    def test_existing_member(self) -> None:
        """Test removing an existing member's join record."""
        cog = _make_cog()
        cog._record_join(100, 1)
        cog._remove_join(100, 1)
        assert 1 not in cog._join_times[100]

    def test_missing_channel(self) -> None:
        """Test removing from a non-existent channel does not raise."""
        cog = _make_cog()
        cog._remove_join(999, 1)  # Should not raise

    def test_missing_member(self) -> None:
        """Test removing a non-existent member does not raise."""
        cog = _make_cog()
        cog._record_join(100, 1)
        cog._remove_join(100, 999)  # Should not raise
        assert 1 in cog._join_times[100]


class TestCleanupChannel:
    """Tests for _cleanup_channel."""

    def test_removes_records(self) -> None:
        """Test that cleanup removes all records for a channel."""
        cog = _make_cog()
        cog._record_join(100, 1)
        cog._record_join(100, 2)
        cog._cleanup_channel(100)
        assert 100 not in cog._join_times

    def test_missing_channel(self) -> None:
        """Test cleaning up a non-existent channel does not raise."""
        cog = _make_cog()
        cog._cleanup_channel(999)  # Should not raise


class TestGetLongestMember:
    """Tests for _get_longest_member."""

    def test_longest_staying(self) -> None:
        """Test that the member with the earliest join time is returned."""
        cog = _make_cog()
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2])

        cog._join_times[100] = {1: 10.0, 2: 20.0}
        result = cog._get_longest_member(channel, exclude_id=999)
        assert result is m1

    def test_excludes_specified(self) -> None:
        """Test that the excluded member is not returned."""
        cog = _make_cog()
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2])

        cog._join_times[100] = {1: 10.0, 2: 20.0}
        result = cog._get_longest_member(channel, exclude_id=1)
        assert result is m2

    def test_none_remaining(self) -> None:
        """Test that None is returned when no members remain."""
        cog = _make_cog()
        m1 = _make_member(1)
        channel = _make_channel(100, [m1])

        result = cog._get_longest_member(channel, exclude_id=1)
        assert result is None

    def test_empty_channel(self) -> None:
        """Test that None is returned for an empty channel."""
        cog = _make_cog()
        channel = _make_channel(100, [])

        result = cog._get_longest_member(channel, exclude_id=1)
        assert result is None

    def test_fallback_without_records(self) -> None:
        """Test fallback when no join records exist."""
        cog = _make_cog()
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2])

        # No join records - should still return a member
        result = cog._get_longest_member(channel, exclude_id=999)
        assert result is not None


class TestOnGuildChannelDelete:
    """Tests for on_guild_channel_delete listener."""

    async def test_deletes_voice_session_for_known_channel(self) -> None:
        """Test that DB record is deleted when a voice channel is deleted."""
        cog = _make_cog()
        cog._record_join(100, 1)
        channel = _make_channel(100)

        with patch(
            "src.cogs.voice.delete_voice_session", new_callable=AsyncMock
        ) as mock_delete, patch(
            "src.cogs.voice.async_session"
        ) as mock_session_factory:
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

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

        with patch(
            "src.cogs.voice.delete_voice_session", new_callable=AsyncMock
        ) as mock_delete, patch(
            "src.cogs.voice.async_session"
        ) as mock_session_factory:
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            # Should not raise even if no session exists
            await cog.on_guild_channel_delete(channel)
            mock_delete.assert_awaited_once_with(mock_session, "300")


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
        with patch("src.cogs.voice.async_session", mock_factory), patch(
            "src.cogs.voice.get_lobby_by_channel_id",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "src.cogs.voice.create_voice_session",
            new_callable=AsyncMock,
        ) as mock_create:
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
        with patch("src.cogs.voice.async_session", mock_factory), patch(
            "src.cogs.voice.get_lobby_by_channel_id",
            new_callable=AsyncMock,
            return_value=lobby,
        ), patch(
            "src.cogs.voice.create_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ) as mock_create, patch(
            "src.cogs.voice.create_control_panel_embed",
            return_value=MagicMock(),
        ), patch(
            "src.cogs.voice.ControlPanelView",
            return_value=MagicMock(),
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
            side_effect=discord.HTTPException(
                MagicMock(status=500), "error"
            )
        )
        new_channel.delete = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.create_voice_channel = AsyncMock(return_value=new_channel)
        guild.default_role = MagicMock()
        member.guild = guild
        member.move_to = AsyncMock()

        voice_session = _make_voice_session(channel_id="200")

        mock_factory, mock_session = _mock_async_session()
        with patch("src.cogs.voice.async_session", mock_factory), patch(
            "src.cogs.voice.get_lobby_by_channel_id",
            new_callable=AsyncMock,
            return_value=lobby,
        ), patch(
            "src.cogs.voice.create_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.cogs.voice.delete_voice_session",
            new_callable=AsyncMock,
        ) as mock_delete:
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
        with patch("src.cogs.voice.async_session", mock_factory), patch(
            "src.cogs.voice.get_voice_session",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "src.cogs.voice.delete_voice_session",
            new_callable=AsyncMock,
        ) as mock_delete:
            await cog._handle_channel_leave(member, channel)
            mock_delete.assert_not_awaited()

    async def test_deletes_empty_channel(self) -> None:
        """全員退出時にチャンネルと DB レコードを削除する。"""
        cog = _make_cog()
        cog._record_join(100, 1)
        member = _make_member(1)
        channel = _make_channel(100, [])  # 空のチャンネル
        channel.delete = AsyncMock()

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_factory, mock_session = _mock_async_session()
        with patch("src.cogs.voice.async_session", mock_factory), patch(
            "src.cogs.voice.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.cogs.voice.delete_voice_session",
            new_callable=AsyncMock,
        ) as mock_delete:
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

        voice_session = _make_voice_session(channel_id="100", owner_id="1")
        cog._join_times[100] = {2: 10.0}

        mock_factory, mock_session = _mock_async_session()
        with patch("src.cogs.voice.async_session", mock_factory), patch(
            "src.cogs.voice.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.cogs.voice.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update, patch(
            "src.cogs.voice.create_control_panel_embed",
            return_value=MagicMock(),
        ):
            # _find_panel_message をモック
            cog._find_panel_message = AsyncMock(return_value=None)

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
        with patch("src.cogs.voice.async_session", mock_factory), patch(
            "src.cogs.voice.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.cogs.voice.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update:
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

        cog._join_times[100] = {2: 10.0, 3: 20.0}
        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update, patch(
            "src.cogs.voice.create_control_panel_embed",
            return_value=MagicMock(),
        ):
            cog._find_panel_message = AsyncMock(return_value=None)
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

        cog._join_times[100] = {2: 10.0}
        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.update_voice_session",
            new_callable=AsyncMock,
        ), patch(
            "src.cogs.voice.create_control_panel_embed",
            return_value=MagicMock(),
        ):
            cog._find_panel_message = AsyncMock(return_value=None)
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

    async def test_updates_pinned_embed(self) -> None:
        """ピン留めされたコントロールパネルの Embed が更新される。"""
        cog = _make_cog()
        old_owner = _make_member(1)
        new_owner = _make_member(2)
        channel = _make_channel(100, [new_owner])
        channel.set_permissions = AsyncMock()
        channel.send = AsyncMock()

        cog._join_times[100] = {2: 10.0}
        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        panel_msg = MagicMock()
        panel_msg.edit = AsyncMock()

        mock_session = AsyncMock()
        mock_embed = MagicMock()
        with patch(
            "src.cogs.voice.update_voice_session",
            new_callable=AsyncMock,
        ), patch(
            "src.cogs.voice.create_control_panel_embed",
            return_value=mock_embed,
        ):
            cog._find_panel_message = AsyncMock(return_value=panel_msg)
            await cog._transfer_ownership(
                mock_session, voice_session, old_owner, channel
            )

            panel_msg.edit.assert_awaited_once_with(embed=mock_embed)

    async def test_sends_notification(self) -> None:
        """引き継ぎ通知がチャンネルに送信される。"""
        cog = _make_cog()
        old_owner = _make_member(1)
        new_owner = _make_member(2)
        channel = _make_channel(100, [new_owner])
        channel.set_permissions = AsyncMock()
        channel.send = AsyncMock()

        cog._join_times[100] = {2: 10.0}
        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.update_voice_session",
            new_callable=AsyncMock,
        ), patch(
            "src.cogs.voice.create_control_panel_embed",
            return_value=MagicMock(),
        ):
            cog._find_panel_message = AsyncMock(return_value=None)
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

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_session = AsyncMock()
        with patch(
            "src.cogs.voice.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update:
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

        await cog.on_voice_state_update(member, before, after)

        cog._handle_lobby_join.assert_awaited_once_with(member, after.channel)
        assert 1 in cog._join_times[100]

    async def test_leave_calls_handle_channel_leave(self) -> None:
        """VC 退出時に _handle_channel_leave が呼ばれる。"""
        cog = _make_cog()
        cog._record_join(100, 1)
        member = _make_member(1)

        before = MagicMock(spec=discord.VoiceState)
        before.channel = _make_channel(100)

        after = MagicMock(spec=discord.VoiceState)
        after.channel = None

        cog._handle_channel_leave = AsyncMock()  # type: ignore[method-assign]

        await cog.on_voice_state_update(member, before, after)

        cog._handle_channel_leave.assert_awaited_once_with(
            member, before.channel
        )
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
# /panel コマンドテスト
# ===========================================================================


def _make_interaction(
    user_id: int,
    channel: MagicMock | None = None,
) -> MagicMock:
    """Create a mock discord.Interaction for slash commands."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = _make_member(user_id)
    interaction.channel = channel
    interaction.channel_id = channel.id if channel else None
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    return interaction


class TestPanelCommand:
    """Tests for /panel slash command."""

    async def test_panel_reposts_control_panel(self) -> None:
        """正常系: 旧パネル削除 + 新パネル送信 + ピン留め。"""
        cog = _make_cog()
        channel = _make_channel(100)
        channel.send = AsyncMock(return_value=MagicMock(pin=AsyncMock()))
        interaction = _make_interaction(1, channel)

        voice_session = _make_voice_session(channel_id="100", owner_id="1")
        old_panel = MagicMock()
        old_panel.delete = AsyncMock()

        mock_factory, mock_session = _mock_async_session()
        with patch("src.cogs.voice.async_session", mock_factory), patch(
            "src.cogs.voice.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.cogs.voice.is_owner",
            return_value=True,
        ), patch(
            "src.cogs.voice.create_control_panel_embed",
            return_value=MagicMock(),
        ), patch(
            "src.cogs.voice.ControlPanelView",
            return_value=MagicMock(),
        ):
            cog._find_panel_message = AsyncMock(return_value=old_panel)
            await cog.panel.callback(cog, interaction)

            # 旧パネルが削除される
            old_panel.delete.assert_awaited_once()
            # 新パネルが送信される
            channel.send.assert_awaited_once()
            # 新パネルがピン留めされる
            channel.send.return_value.pin.assert_awaited_once()
            # ephemeral で応答
            interaction.response.send_message.assert_awaited_once()
            call_kwargs = interaction.response.send_message.call_args[1]
            assert call_kwargs["ephemeral"] is True

    async def test_panel_rejects_non_owner(self) -> None:
        """オーナー以外は拒否される。"""
        cog = _make_cog()
        channel = _make_channel(100)
        interaction = _make_interaction(2, channel)

        voice_session = _make_voice_session(channel_id="100", owner_id="1")

        mock_factory, _mock_session = _mock_async_session()
        with patch("src.cogs.voice.async_session", mock_factory), patch(
            "src.cogs.voice.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.cogs.voice.is_owner",
            return_value=False,
        ):
            await cog.panel.callback(cog, interaction)

            interaction.response.send_message.assert_awaited_once()
            msg = interaction.response.send_message.call_args[0][0]
            assert "オーナー" in msg

    async def test_panel_rejects_non_voice_channel(self) -> None:
        """VC 外で使用すると拒否される。"""
        cog = _make_cog()
        # TextChannel (VoiceChannel ではない)
        text_channel = MagicMock(spec=discord.TextChannel)
        text_channel.id = 100
        interaction = _make_interaction(1, text_channel)

        await cog.panel.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "一時 VC" in msg

    async def test_panel_rejects_no_session(self) -> None:
        """セッションが見つからない場合は拒否される。"""
        cog = _make_cog()
        channel = _make_channel(100)
        interaction = _make_interaction(1, channel)

        mock_factory, _mock_session = _mock_async_session()
        with patch("src.cogs.voice.async_session", mock_factory), patch(
            "src.cogs.voice.get_voice_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await cog.panel.callback(cog, interaction)

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

        error = app_commands.CommandOnCooldown(
            app_commands.Cooldown(1, 30), 15.0
        )
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
