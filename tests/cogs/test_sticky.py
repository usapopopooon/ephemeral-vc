"""Tests for StickyCog (sticky message feature)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands
from faker import Faker

from src.cogs.sticky import (
    DEFAULT_COLOR,
    StickyCog,
    StickyEmbedModal,
    StickySetModal,
    StickyTextModal,
    StickyTypeSelect,
    StickyTypeView,
)

fake = Faker("ja_JP")

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog(bot_user_id: int = 99999) -> StickyCog:
    """Create a StickyCog with a mock bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = bot_user_id
    return StickyCog(bot)


def _make_message(
    *,
    author_id: int = 12345,
    channel_id: int = 456,
    guild_id: int = 789,
    is_bot: bool = False,
) -> MagicMock:
    """Create a mock Discord message."""
    message = MagicMock(spec=discord.Message)
    message.author = MagicMock()
    message.author.id = author_id
    message.author.bot = is_bot
    message.channel = MagicMock()
    message.channel.id = channel_id
    message.channel.send = AsyncMock()
    message.channel.fetch_message = AsyncMock()
    message.guild = MagicMock()
    message.guild.id = guild_id
    return message


def _make_sticky(
    *,
    channel_id: str = "456",
    guild_id: str = "789",
    message_id: str | None = "999",
    title: str = "Test Title",
    description: str = "Test Description",
    color: int | None = 0xFF0000,
    cooldown_seconds: int = 5,
    last_posted_at: datetime | None = None,
    message_type: str = "embed",
) -> MagicMock:
    """Create a mock StickyMessage."""
    sticky = MagicMock()
    sticky.channel_id = channel_id
    sticky.guild_id = guild_id
    sticky.message_id = message_id
    sticky.title = title
    sticky.description = description
    sticky.color = color
    sticky.cooldown_seconds = cooldown_seconds
    sticky.last_posted_at = last_posted_at
    sticky.message_type = message_type
    return sticky


def _make_interaction(
    *,
    guild_id: int = 789,
    channel_id: int = 456,
) -> MagicMock:
    """Create a mock Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock()
    interaction.guild.id = guild_id
    interaction.channel = MagicMock()
    interaction.channel.id = channel_id
    interaction.channel.send = AsyncMock()
    interaction.channel_id = channel_id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    return interaction


# ---------------------------------------------------------------------------
# _build_embed テスト
# ---------------------------------------------------------------------------


class TestBuildEmbed:
    """Tests for _build_embed method."""

    def test_builds_embed_with_all_params(self) -> None:
        """全てのパラメータを指定して embed を作成する。"""
        cog = _make_cog()
        embed = cog._build_embed("Title", "Description", 0xFF0000)

        assert embed.title == "Title"
        assert embed.description == "Description"
        assert embed.color == discord.Color(0xFF0000)

    def test_uses_default_color_when_none(self) -> None:
        """色が None の場合はデフォルト色を使用する。"""
        cog = _make_cog()
        embed = cog._build_embed("Title", "Description", None)

        assert embed.color == discord.Color(DEFAULT_COLOR)


# ---------------------------------------------------------------------------
# on_message テスト
# ---------------------------------------------------------------------------


class TestOnMessage:
    """Tests for on_message listener."""

    async def test_ignores_own_bot_messages(self) -> None:
        """自分自身の Bot メッセージは無視する（無限ループ防止）。"""
        bot_user_id = 99999
        cog = _make_cog(bot_user_id=bot_user_id)
        # メッセージの author.id を bot.user.id と同じにする
        message = _make_message(author_id=bot_user_id, is_bot=True)

        with patch("src.cogs.sticky.get_sticky_message") as mock_get:
            await cog.on_message(message)

        mock_get.assert_not_called()

    async def test_triggers_on_other_bot_messages(self) -> None:
        """他の Bot のメッセージでも sticky を再投稿する。"""
        cog = _make_cog(bot_user_id=99999)
        # 別の bot からのメッセージ
        message = _make_message(author_id=88888, is_bot=True)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        sticky = _make_sticky()

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.get_sticky_message", return_value=sticky),
        ):
            await cog.on_message(message)

        # タスクがスケジュールされていることを確認
        channel_id = str(message.channel.id)
        assert channel_id in cog._pending_tasks

    async def test_triggers_on_bot_embed_messages(self) -> None:
        """他の Bot の embed メッセージでも sticky を再投稿する。"""
        cog = _make_cog(bot_user_id=99999)
        # 別の bot からの embed 付きメッセージ
        message = _make_message(author_id=88888, is_bot=True)
        message.embeds = [MagicMock()]  # embed が含まれている

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        sticky = _make_sticky()

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.get_sticky_message", return_value=sticky),
        ):
            await cog.on_message(message)

        # タスクがスケジュールされていることを確認
        channel_id = str(message.channel.id)
        assert channel_id in cog._pending_tasks

    async def test_handles_bot_user_none(self) -> None:
        """bot.user が None の場合でもエラーにならない。"""
        cog = _make_cog()
        cog.bot.user = None  # bot.user を None に設定
        message = _make_message(is_bot=True)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        sticky = _make_sticky()

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.get_sticky_message", return_value=sticky),
        ):
            # エラーなく実行される
            await cog.on_message(message)

        # bot.user が None の場合、全てのメッセージが処理される
        channel_id = str(message.channel.id)
        assert channel_id in cog._pending_tasks

    async def test_ignores_dm_messages(self) -> None:
        """DM メッセージは無視する。"""
        cog = _make_cog()
        message = _make_message()
        message.guild = None

        with patch("src.cogs.sticky.get_sticky_message") as mock_get:
            await cog.on_message(message)

        mock_get.assert_not_called()

    async def test_ignores_when_no_sticky_configured(self) -> None:
        """sticky 設定がない場合は無視する。"""
        cog = _make_cog()
        message = _make_message()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_message(message)

        # タスクがスケジュールされていない
        assert len(cog._pending_tasks) == 0

    async def test_schedules_delayed_repost(self) -> None:
        """メッセージが来たら遅延再投稿をスケジュールする。"""
        cog = _make_cog()
        message = _make_message()

        sticky = _make_sticky(cooldown_seconds=5)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            await cog.on_message(message)

        # タスクがスケジュールされている
        assert "456" in cog._pending_tasks
        # クリーンアップ
        cog._pending_tasks["456"].cancel()

    async def test_cancels_existing_task_on_new_message(self) -> None:
        """新しいメッセージが来たら既存のタスクをキャンセルする（デバウンス）。"""
        cog = _make_cog()
        message = _make_message()

        sticky = _make_sticky(cooldown_seconds=5)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            # 1回目のメッセージ
            await cog.on_message(message)
            first_task = cog._pending_tasks["456"]

            # 2回目のメッセージ
            await cog.on_message(message)
            second_task = cog._pending_tasks["456"]

        # 1回目のタスクはキャンセルされている
        assert first_task.cancelled()
        # 2回目のタスクが新しく設定されている
        assert first_task is not second_task
        # クリーンアップ
        second_task.cancel()


class TestDelayedRepost:
    """Tests for _delayed_repost method."""

    async def test_reposts_after_delay(self) -> None:
        """遅延後に再投稿する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=1234567890))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        sticky = _make_sticky()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await cog._delayed_repost(channel, "456", 5)

        mock_sleep.assert_called_once_with(5)
        channel.send.assert_called_once()

    async def test_deletes_old_message_before_repost(self) -> None:
        """再投稿前に古いメッセージを削除する。"""
        cog = _make_cog()
        channel = MagicMock()
        new_msg = MagicMock(id=1234567890)
        channel.send = AsyncMock(return_value=new_msg)

        old_msg = MagicMock()
        old_msg.delete = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=old_msg)

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        old_msg.delete.assert_called_once()
        channel.send.assert_called_once()

    async def test_does_nothing_if_cancelled(self) -> None:
        """キャンセルされた場合は何もしない。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()

        with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
            await cog._delayed_repost(channel, "456", 5)

        channel.send.assert_not_called()

    async def test_does_nothing_if_sticky_deleted(self) -> None:
        """sticky が削除されていた場合は何もしない。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        channel.send.assert_not_called()

    async def test_skips_repost_when_message_not_found(self) -> None:
        """メッセージが既に削除されていた場合は再投稿せず、DB から削除する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # NotFound の場合、再投稿しない
        channel.send.assert_not_called()
        # DB から削除される
        mock_delete.assert_called_once()

    async def test_skips_repost_when_no_message_id(self) -> None:
        """message_id がない場合は再投稿せず、DB から削除する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()

        sticky = _make_sticky(message_id=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # message_id がない場合、再投稿しない
        channel.send.assert_not_called()
        # DB から削除される
        mock_delete.assert_called_once()

    async def test_skips_repost_on_http_exception(self) -> None:
        """HTTP エラーが発生した場合は再投稿せず、DB から削除する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()
        channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "")
        )

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # HTTPException の場合も再投稿しない
        channel.send.assert_not_called()
        # DB から削除される
        mock_delete.assert_called_once()

    async def test_updates_db_after_successful_repost(self) -> None:
        """再投稿成功後に DB を更新する。"""
        cog = _make_cog()
        channel = MagicMock()
        new_msg = MagicMock(id=1234567890)
        channel.send = AsyncMock(return_value=new_msg)

        old_msg = MagicMock()
        old_msg.delete = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=old_msg)

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ) as mock_update,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # DB が新しいメッセージ ID で更新される
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][1] == "456"  # channel_id
        assert call_args[0][2] == "1234567890"  # new message_id

    async def test_handles_send_failure(self) -> None:
        """メッセージ送信に失敗しても例外を投げない。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))

        old_msg = MagicMock()
        old_msg.delete = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=old_msg)

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ) as mock_update,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            # 例外が発生しないことを確認
            await cog._delayed_repost(channel, "456", 5)

        # 送信失敗時は DB 更新されない
        mock_update.assert_not_called()

    async def test_removes_task_from_pending_after_completion(self) -> None:
        """完了後に _pending_tasks からタスクが削除される。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=123))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        sticky = _make_sticky()

        # タスクを事前に登録
        cog._pending_tasks["456"] = MagicMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # タスクが削除されている
        assert "456" not in cog._pending_tasks

    async def test_removes_task_from_pending_on_cancel(self) -> None:
        """キャンセル時にも _pending_tasks からタスクが削除される。"""
        cog = _make_cog()
        channel = MagicMock()

        # タスクを事前に登録
        cog._pending_tasks["456"] = MagicMock()

        with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
            await cog._delayed_repost(channel, "456", 5)

        # タスクが削除されている
        assert "456" not in cog._pending_tasks


class TestCogUnload:
    """Tests for cog_unload method."""

    async def test_cancels_pending_tasks(self) -> None:
        """アンロード時に保留中のタスクをキャンセルする。"""
        cog = _make_cog()

        # ダミーのタスクを追加
        async def dummy() -> None:
            await asyncio.sleep(100)

        task = asyncio.create_task(dummy())
        cog._pending_tasks["456"] = task

        await cog.cog_unload()

        # タスクがキャンセル中または完了していることを確認
        assert task.cancelling() > 0 or task.cancelled()
        assert len(cog._pending_tasks) == 0


# ---------------------------------------------------------------------------
# スラッシュコマンドテスト
# ---------------------------------------------------------------------------


class TestStickySetCommand:
    """Tests for /sticky set command."""

    async def test_requires_guild(self) -> None:
        """ギルド外では使用できない。"""
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild = None

        await cog.sticky_set.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_shows_type_selector(self) -> None:
        """ギルド内でタイプセレクターを表示する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        await cog.sticky_set.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_kwargs = interaction.response.send_message.call_args[1]
        assert "view" in call_kwargs
        assert call_kwargs["ephemeral"] is True


class TestStickySetModal:
    """Tests for StickySetModal."""

    def _make_modal(self) -> StickySetModal:
        """Create a StickySetModal with a mock cog."""
        cog = _make_cog()
        modal = StickySetModal(cog)
        return modal

    async def test_requires_guild(self) -> None:
        """ギルド外では使用できない。"""
        modal = self._make_modal()
        interaction = _make_interaction()
        interaction.guild = None

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5"

        await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_creates_sticky_message(self) -> None:
        """sticky メッセージを作成する。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        mock_create.assert_called_once()
        interaction.response.send_message.assert_called_once()

    async def test_parses_hex_color(self) -> None:
        """16進数の色をパースする。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = "FF0000"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["color"] == 0xFF0000

    async def test_rejects_invalid_color(self) -> None:
        """無効な色形式はエラーを返す。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = "invalid"
        modal.delay._value = "5"

        await modal.on_submit(interaction)

        call_args = interaction.response.send_message.call_args
        assert "無効な色形式" in call_args[0][0]

    async def test_uses_delay_parameter(self) -> None:
        """delay パラメータを使用する。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "10"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 10

    async def test_rejects_invalid_delay(self) -> None:
        """無効な遅延値はエラーを返す。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "abc"

        await modal.on_submit(interaction)

        call_args = interaction.response.send_message.call_args
        assert "無効な遅延値" in call_args[0][0]

    async def test_multiline_description(self) -> None:
        """改行を含む説明文を処理できる。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with multiline description
        modal.sticky_title._value = "Title"
        modal.description._value = "Line 1\nLine 2\nLine 3"
        modal.color._value = ""
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["description"] == "Line 1\nLine 2\nLine 3"

    async def test_delay_minimum_boundary(self) -> None:
        """遅延の最小値は1秒に制限される。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with delay below minimum
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "0"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 1

    async def test_delay_maximum_boundary(self) -> None:
        """遅延の最大値は3600秒に制限される。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with delay above maximum
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "9999"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 3600

    async def test_color_with_hash_prefix(self) -> None:
        """# プレフィックス付きの色をパースする。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = "#00FF00"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["color"] == 0x00FF00

    async def test_handles_send_failure(self) -> None:
        """メッセージ送信に失敗しても例外を投げない。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # send が例外を投げる
        interaction.channel.send = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "")
        )

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            # 例外が発生しないことを確認
            await modal.on_submit(interaction)

        # 送信失敗時は DB 更新されない
        mock_update.assert_not_called()

    async def test_empty_delay_defaults_to_five(self) -> None:
        """空の遅延値はデフォルト5秒になる。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with empty delay
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = ""

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 5


class TestStickyRemoveCommand:
    """Tests for /sticky remove command."""

    async def test_requires_guild(self) -> None:
        """ギルド外では使用できない。"""
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild = None

        await cog.sticky_remove.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_shows_error_when_not_configured(self) -> None:
        """設定がない場合はエラーを表示する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.sticky_remove.callback(cog, interaction)

        call_args = interaction.response.send_message.call_args
        assert "設定されていません" in call_args[0][0]

    async def test_removes_sticky_message(self) -> None:
        """sticky メッセージを削除する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        sticky = _make_sticky()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        old_message = MagicMock()
        old_message.delete = AsyncMock()
        interaction.channel.fetch_message = AsyncMock(return_value=old_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            await cog.sticky_remove.callback(cog, interaction)

        mock_delete.assert_called_once()
        old_message.delete.assert_called_once()

    async def test_cancels_pending_task(self) -> None:
        """保留中のタスクをキャンセルする。"""
        cog = _make_cog()
        interaction = _make_interaction()

        # ダミーのタスクを追加
        async def dummy() -> None:
            await asyncio.sleep(100)

        task = asyncio.create_task(dummy())
        cog._pending_tasks["456"] = task

        sticky = _make_sticky()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        old_message = MagicMock()
        old_message.delete = AsyncMock()
        interaction.channel.fetch_message = AsyncMock(return_value=old_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ),
        ):
            await cog.sticky_remove.callback(cog, interaction)

        # タスクがキャンセル中または完了していることを確認
        assert task.cancelling() > 0 or task.cancelled()
        assert "456" not in cog._pending_tasks


class TestStickyStatusCommand:
    """Tests for /sticky status command."""

    async def test_requires_guild(self) -> None:
        """ギルド外では使用できない。"""
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild = None

        await cog.sticky_status.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_shows_not_configured(self) -> None:
        """設定がない場合は未設定と表示する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.sticky_status.callback(cog, interaction)

        call_args = interaction.response.send_message.call_args
        assert "設定されていません" in call_args[0][0]

    async def test_shows_configuration(self) -> None:
        """設定がある場合は詳細を表示する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        sticky = _make_sticky()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            await cog.sticky_status.callback(cog, interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        assert embed.title == "📌 Sticky メッセージ設定"

    async def test_shows_text_type(self) -> None:
        """テキストタイプの設定を表示する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        sticky = _make_sticky(message_type="text", title="", color=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            await cog.sticky_status.callback(cog, interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        # 種類フィールドがテキストになっている
        type_field = next(f for f in embed.fields if f.name == "種類")
        assert type_field.value == "テキスト"


# ---------------------------------------------------------------------------
# StickyTextModal テスト
# ---------------------------------------------------------------------------


class TestStickyTextModal:
    """Tests for StickyTextModal."""

    def _make_modal(self) -> StickyTextModal:
        """Create a StickyTextModal with a mock cog."""
        cog = _make_cog()
        modal = StickyTextModal(cog)
        return modal

    async def test_requires_guild(self) -> None:
        """ギルド外では使用できない。"""
        modal = self._make_modal()
        interaction = _make_interaction()
        interaction.guild = None

        # Set modal values
        modal.content._value = "Test content"
        modal.delay._value = "5"

        await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_creates_sticky_message(self) -> None:
        """テキスト sticky メッセージを作成する。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.content._value = "Test content"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["message_type"] == "text"
        assert call_kwargs["title"] == ""
        assert call_kwargs["description"] == "Test content"
        interaction.response.send_message.assert_called_once()

    async def test_uses_delay_parameter(self) -> None:
        """delay パラメータを使用する。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.content._value = "Test content"
        modal.delay._value = "10"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 10

    async def test_rejects_invalid_delay(self) -> None:
        """無効な遅延値はエラーを返す。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.content._value = "Test content"
        modal.delay._value = "abc"

        await modal.on_submit(interaction)

        call_args = interaction.response.send_message.call_args
        assert "無効な遅延値" in call_args[0][0]

    async def test_multiline_content(self) -> None:
        """改行を含むコンテンツを処理できる。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with multiline content
        modal.content._value = "Line 1\nLine 2\nLine 3"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["description"] == "Line 1\nLine 2\nLine 3"

    async def test_delay_minimum_boundary(self) -> None:
        """遅延の最小値は1秒に制限される。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with delay below minimum
        modal.content._value = "Test content"
        modal.delay._value = "0"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 1

    async def test_delay_maximum_boundary(self) -> None:
        """遅延の最大値は3600秒に制限される。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with delay above maximum
        modal.content._value = "Test content"
        modal.delay._value = "9999"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 3600

    async def test_handles_send_failure(self) -> None:
        """メッセージ送信に失敗しても例外を投げない。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.content._value = "Test content"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # send が例外を投げる
        interaction.channel.send = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "")
        )

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            # 例外が発生しないことを確認
            await modal.on_submit(interaction)

        # 送信失敗時は DB 更新されない
        mock_update.assert_not_called()

    async def test_empty_delay_defaults_to_five(self) -> None:
        """空の遅延値はデフォルト5秒になる。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with empty delay
        modal.content._value = "Test content"
        modal.delay._value = ""

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 5


# ---------------------------------------------------------------------------
# StickyTypeSelect テスト
# ---------------------------------------------------------------------------


class TestStickyTypeSelect:
    """Tests for StickyTypeSelect."""

    async def test_select_embed_opens_embed_modal(self) -> None:
        """Embed を選択すると StickyEmbedModal が開く。"""
        cog = _make_cog()
        select = StickyTypeSelect(cog)
        interaction = _make_interaction()
        interaction.response.send_modal = AsyncMock()

        select._values = ["embed"]

        await select.callback(interaction)

        interaction.response.send_modal.assert_called_once()
        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, StickyEmbedModal)

    async def test_select_text_opens_text_modal(self) -> None:
        """テキストを選択すると StickyTextModal が開く。"""
        cog = _make_cog()
        select = StickyTypeSelect(cog)
        interaction = _make_interaction()
        interaction.response.send_modal = AsyncMock()

        select._values = ["text"]

        await select.callback(interaction)

        interaction.response.send_modal.assert_called_once()
        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, StickyTextModal)


# ---------------------------------------------------------------------------
# StickyTypeView テスト
# ---------------------------------------------------------------------------


class TestStickyTypeView:
    """Tests for StickyTypeView."""

    async def test_view_has_select_item(self) -> None:
        """View に StickyTypeSelect が含まれている。"""
        cog = _make_cog()
        view = StickyTypeView(cog)

        assert len(view.children) == 1
        assert isinstance(view.children[0], StickyTypeSelect)

    async def test_view_timeout(self) -> None:
        """View のタイムアウトが60秒である。"""
        cog = _make_cog()
        view = StickyTypeView(cog)

        assert view.timeout == 60


# ---------------------------------------------------------------------------
# _delayed_repost テキストタイプ テスト
# ---------------------------------------------------------------------------


class TestDelayedRepostTextType:
    """Tests for _delayed_repost with text message type."""

    async def test_reposts_text_message(self) -> None:
        """テキストタイプの場合、テキストメッセージを再投稿する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=1234567890))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        sticky = _make_sticky(message_type="text", description="Test text content")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # テキストとして送信されている（embed ではない）
        channel.send.assert_called_once_with("Test text content")

    async def test_reposts_embed_message(self) -> None:
        """Embed タイプの場合、embed メッセージを再投稿する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=1234567890))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        sticky = _make_sticky(
            message_type="embed",
            title="Test Title",
            description="Test Description",
            color=0xFF0000,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # embed として送信されている
        channel.send.assert_called_once()
        call_kwargs = channel.send.call_args[1]
        assert "embed" in call_kwargs
        assert call_kwargs["embed"].title == "Test Title"
        assert call_kwargs["embed"].description == "Test Description"


# ---------------------------------------------------------------------------
# StickyEmbedModal message_type テスト
# ---------------------------------------------------------------------------


class TestStickyEmbedModalMessageType:
    """Tests for StickyEmbedModal message_type parameter."""

    def _make_modal(self) -> StickyEmbedModal:
        """Create a StickyEmbedModal with a mock cog."""
        cog = _make_cog()
        modal = StickyEmbedModal(cog)
        return modal

    async def test_creates_sticky_with_embed_type(self) -> None:
        """message_type が embed として保存される。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["message_type"] == "embed"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cog() -> StickyCog:
    """StickyCog フィクスチャ。"""
    return _make_cog()


@pytest.fixture
def interaction() -> MagicMock:
    """Interaction フィクスチャ。"""
    return _make_interaction()


@pytest.fixture
def mock_session() -> MagicMock:
    """Mock session フィクスチャ。"""
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


# ---------------------------------------------------------------------------
# Faker を使ったテスト
# ---------------------------------------------------------------------------


class TestStickyWithFaker:
    """Faker を使ったランダムデータでのテスト。"""

    async def test_embed_modal_with_random_data(
        self, cog: StickyCog, interaction: MagicMock, mock_session: MagicMock
    ) -> None:
        """ランダムなデータで embed sticky を作成する。"""
        modal = StickyEmbedModal(cog)

        # Faker でランダムデータ生成
        title = fake.sentence(nb_words=3)
        description = fake.paragraph(nb_sentences=3)
        delay = str(fake.random_int(min=1, max=60))

        modal.sticky_title._value = title
        modal.description._value = description
        modal.color._value = ""
        modal.delay._value = delay

        new_message = MagicMock()
        new_message.id = fake.random_int(min=100000, max=999999)
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["title"] == title
        assert call_kwargs["description"] == description
        assert call_kwargs["cooldown_seconds"] == int(delay)

    async def test_text_modal_with_random_content(
        self, cog: StickyCog, interaction: MagicMock, mock_session: MagicMock
    ) -> None:
        """ランダムなコンテンツでテキスト sticky を作成する。"""
        modal = StickyTextModal(cog)

        # Faker でランダムデータ生成
        content = fake.text(max_nb_chars=500)
        delay = str(fake.random_int(min=1, max=60))

        modal.content._value = content
        modal.delay._value = delay

        new_message = MagicMock()
        new_message.id = fake.random_int(min=100000, max=999999)
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["description"] == content
        assert call_kwargs["message_type"] == "text"

    async def test_delayed_repost_with_random_sticky(
        self, cog: StickyCog, mock_session: MagicMock
    ) -> None:
        """ランダムな sticky データで再投稿をテストする。"""
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=fake.random_int()))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        # ランダムなタイプを選択
        message_type = fake.random_element(elements=("embed", "text"))
        sticky = _make_sticky(
            message_type=message_type,
            title=fake.sentence() if message_type == "embed" else "",
            description=fake.paragraph(),
            color=(
                fake.random_int(min=0, max=0xFFFFFF)
                if message_type == "embed"
                else None
            ),
            cooldown_seconds=fake.random_int(min=1, max=60),
        )

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, str(fake.random_int()), 5)

        channel.send.assert_called_once()

    @pytest.mark.parametrize("message_type", ["embed", "text"])
    async def test_status_shows_correct_type(
        self,
        cog: StickyCog,
        interaction: MagicMock,
        mock_session: MagicMock,
        message_type: str,
    ) -> None:
        """各メッセージタイプのステータス表示をテストする。"""
        sticky = _make_sticky(
            message_type=message_type,
            title=fake.sentence() if message_type == "embed" else "",
            description=fake.paragraph(),
        )

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            await cog.sticky_status.callback(cog, interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        type_field = next(f for f in embed.fields if f.name == "種類")
        expected = "Embed" if message_type == "embed" else "テキスト"
        assert type_field.value == expected


class TestStickyWithParameterize:
    """pytest.mark.parametrize を使ったテスト。"""

    @pytest.mark.parametrize(
        "delay_input,expected_delay",
        [
            ("1", 1),
            ("5", 5),
            ("60", 60),
            ("3600", 3600),
            ("0", 1),  # 最小値に補正
            ("-5", 1),  # 負の値は最小値に補正
            ("9999", 3600),  # 最大値に補正
        ],
    )
    async def test_embed_modal_delay_boundaries(
        self,
        cog: StickyCog,
        interaction: MagicMock,
        mock_session: MagicMock,
        delay_input: str,
        expected_delay: int,
    ) -> None:
        """遅延値の境界値テスト。"""
        modal = StickyEmbedModal(cog)

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = delay_input

        new_message = MagicMock()
        new_message.id = 12345
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == expected_delay

    @pytest.mark.parametrize(
        "color_input,expected_color",
        [
            ("FF0000", 0xFF0000),
            ("00FF00", 0x00FF00),
            ("0000FF", 0x0000FF),
            ("#FF0000", 0xFF0000),
            ("#00ff00", 0x00FF00),
            ("FFFFFF", 0xFFFFFF),
            ("123456", 0x123456),
            ("#ABCDEF", 0xABCDEF),
        ],
    )
    async def test_embed_modal_color_parsing(
        self,
        cog: StickyCog,
        interaction: MagicMock,
        mock_session: MagicMock,
        color_input: str,
        expected_color: int,
    ) -> None:
        """色のパーステスト。"""
        modal = StickyEmbedModal(cog)

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = color_input
        modal.delay._value = "5"

        new_message = MagicMock()
        new_message.id = 12345
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["color"] == expected_color
