"""Tests for AdminCog (/lobby command)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.cogs.admin import AdminCog

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog() -> AdminCog:
    """Create an AdminCog instance with a mock bot."""
    bot = MagicMock(spec=discord.ext.commands.Bot)
    return AdminCog(bot)


def _make_interaction(
    *,
    guild: MagicMock | None = "default",
    guild_id: int = 1000,
) -> MagicMock:
    """Create a mock discord.Interaction for /lobby command.

    Args:
        guild: Guild mock. Pass None for DM context. "default" creates a
               standard guild mock.
        guild_id: The guild ID to set on the interaction.
    """
    interaction = MagicMock(spec=discord.Interaction)
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


def _mock_async_session() -> tuple[MagicMock, AsyncMock]:
    """Create mock for async_session context manager."""
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(
        return_value=mock_session
    )
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_factory, mock_session


# ---------------------------------------------------------------------------
# /lobby コマンドテスト
# ---------------------------------------------------------------------------


class TestLobbyAdd:
    """Tests for /lobby slash command."""

    async def test_creates_lobby_successfully(self) -> None:
        """正常系: VC を作成し DB に登録して完了メッセージを返す。"""
        cog = _make_cog()
        interaction = _make_interaction()

        lobby_channel = MagicMock(spec=discord.VoiceChannel)
        lobby_channel.id = 500
        lobby_channel.name = "参加して作成"
        interaction.guild.create_voice_channel = AsyncMock(
            return_value=lobby_channel
        )

        mock_factory, mock_session = _mock_async_session()
        with patch("src.cogs.admin.async_session", mock_factory), patch(
            "src.cogs.admin.get_lobbies_by_guild",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "src.cogs.admin.create_lobby", new_callable=AsyncMock
        ) as mock_create:
            await cog.lobby_add.callback(cog, interaction)

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
        interaction = _make_interaction(guild=None)

        await cog.lobby_add.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "サーバー内" in msg
        assert interaction.response.send_message.call_args[1]["ephemeral"] is True

    async def test_handles_http_exception(self) -> None:
        """Discord API エラー時にエラーメッセージを返す。"""
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild.create_voice_channel = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=403), "Missing Permissions"
            )
        )

        mock_factory, _mock_session = _mock_async_session()
        with patch("src.cogs.admin.async_session", mock_factory), patch(
            "src.cogs.admin.get_lobbies_by_guild",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await cog.lobby_add.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "失敗" in msg
        assert interaction.response.send_message.call_args[1]["ephemeral"] is True

    async def test_no_db_call_on_vc_creation_failure(self) -> None:
        """VC 作成失敗時は DB 登録が呼ばれない。"""
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild.create_voice_channel = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=500), "Internal Error"
            )
        )

        mock_factory, _mock_session = _mock_async_session()
        with patch("src.cogs.admin.async_session", mock_factory), patch(
            "src.cogs.admin.get_lobbies_by_guild",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "src.cogs.admin.create_lobby", new_callable=AsyncMock
        ) as mock_create:
            await cog.lobby_add.callback(cog, interaction)
            mock_create.assert_not_awaited()

    async def test_rejects_duplicate_lobby(self) -> None:
        """既にロビーが存在するサーバーでは作成を拒否する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        existing_lobby = MagicMock()
        existing_lobby.id = 1

        mock_factory, _mock_session = _mock_async_session()
        with patch("src.cogs.admin.async_session", mock_factory), patch(
            "src.cogs.admin.get_lobbies_by_guild",
            new_callable=AsyncMock,
            return_value=[existing_lobby],
        ), patch(
            "src.cogs.admin.create_lobby", new_callable=AsyncMock
        ) as mock_create:
            await cog.lobby_add.callback(cog, interaction)

            # VC は作成されない
            interaction.guild.create_voice_channel.assert_not_awaited()
            # DB 登録も呼ばれない
            mock_create.assert_not_awaited()
            # エラーメッセージ
            interaction.response.send_message.assert_awaited_once()
            msg = interaction.response.send_message.call_args[0][0]
            assert "既に" in msg
            assert interaction.response.send_message.call_args[1]["ephemeral"] is True
