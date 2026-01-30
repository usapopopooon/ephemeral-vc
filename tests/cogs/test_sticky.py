"""Tests for StickyCog (sticky message feature)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands

from src.cogs.sticky import DEFAULT_COLOR, StickyCog

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog() -> StickyCog:
    """Create a StickyCog with a mock bot."""
    bot = MagicMock(spec=commands.Bot)
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

    async def test_ignores_bot_messages(self) -> None:
        """Bot のメッセージは無視する。"""
        cog = _make_cog()
        message = _make_message(is_bot=True)

        with patch("src.cogs.sticky.get_sticky_message") as mock_get:
            await cog.on_message(message)

        mock_get.assert_not_called()

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

        message.channel.send.assert_not_called()

    async def test_respects_cooldown(self) -> None:
        """cooldown 中は再投稿しない。"""
        cog = _make_cog()
        message = _make_message()

        # 2秒前に投稿済み、cooldown は 5秒
        sticky = _make_sticky(
            last_posted_at=datetime.now(UTC) - timedelta(seconds=2),
            cooldown_seconds=5,
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
        ):
            await cog.on_message(message)

        # cooldown 中なので送信しない
        message.channel.send.assert_not_called()

    async def test_reposts_after_cooldown(self) -> None:
        """cooldown 経過後は再投稿する。"""
        cog = _make_cog()
        message = _make_message()

        # 10秒前に投稿済み、cooldown は 5秒
        sticky = _make_sticky(
            last_posted_at=datetime.now(UTC) - timedelta(seconds=10),
            cooldown_seconds=5,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # 新しいメッセージの mock
        new_message = MagicMock()
        new_message.id = 1234567890
        message.channel.send = AsyncMock(return_value=new_message)

        # 古いメッセージの削除用 mock
        old_message = MagicMock()
        old_message.delete = AsyncMock()
        message.channel.fetch_message = AsyncMock(return_value=old_message)

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
        ):
            await cog.on_message(message)

        # 古いメッセージを削除
        old_message.delete.assert_called_once()
        # 新しいメッセージを送信
        message.channel.send.assert_called_once()

    async def test_posts_when_no_previous_message(self) -> None:
        """message_id がない場合も投稿する。"""
        cog = _make_cog()
        message = _make_message()

        sticky = _make_sticky(
            message_id=None,
            last_posted_at=None,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        message.channel.send = AsyncMock(return_value=new_message)

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
        ):
            await cog.on_message(message)

        message.channel.send.assert_called_once()


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

        await cog.sticky_set.callback(cog, interaction, "Title", "Description")

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_creates_sticky_message(self) -> None:
        """sticky メッセージを作成する。"""
        cog = _make_cog()
        interaction = _make_interaction()

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
            await cog.sticky_set.callback(cog, interaction, "Title", "Description")

        mock_create.assert_called_once()
        interaction.response.send_message.assert_called_once()

    async def test_parses_hex_color(self) -> None:
        """16進数の色をパースする。"""
        cog = _make_cog()
        interaction = _make_interaction()

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
            await cog.sticky_set.callback(
                cog, interaction, "Title", "Description", color="FF0000"
            )

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["color"] == 0xFF0000

    async def test_rejects_invalid_color(self) -> None:
        """無効な色形式はエラーを返す。"""
        cog = _make_cog()
        interaction = _make_interaction()

        await cog.sticky_set.callback(
            cog, interaction, "Title", "Description", color="invalid"
        )

        call_args = interaction.response.send_message.call_args
        assert "無効な色形式" in call_args[0][0]


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
