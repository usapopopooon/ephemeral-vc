"""Tests for control panel UI components."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.ui.control_panel import (
    ControlPanelView,
    RenameModal,
    TransferSelectMenu,
    UserLimitModal,
    create_control_panel_embed,
)

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_voice_session(
    *,
    session_id: int = 1,
    channel_id: str = "100",
    owner_id: str = "1",
    name: str = "Test channel",
    user_limit: int = 0,
    is_locked: bool = False,
    is_hidden: bool = False,
) -> MagicMock:
    """Create a mock VoiceSession DB object."""
    vs = MagicMock()
    vs.id = session_id
    vs.channel_id = channel_id
    vs.owner_id = owner_id
    vs.name = name
    vs.user_limit = user_limit
    vs.is_locked = is_locked
    vs.is_hidden = is_hidden
    return vs


def _make_interaction(
    *,
    user_id: int = 1,
    channel_id: int = 100,
    is_voice: bool = True,
) -> MagicMock:
    """Create a mock discord.Interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id

    interaction.channel_id = channel_id
    if is_voice:
        interaction.channel = MagicMock(spec=discord.VoiceChannel)
        interaction.channel.id = channel_id
        interaction.channel.members = []
    else:
        interaction.channel = MagicMock(spec=discord.TextChannel)

    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.default_role = MagicMock()

    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

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


# ===========================================================================
# create_control_panel_embed テスト
# ===========================================================================


class TestCreateControlPanelEmbed:
    """Tests for create_control_panel_embed."""

    def test_basic_embed(self) -> None:
        """基本的な Embed が正しく生成される。"""
        session = _make_voice_session()
        owner = MagicMock(spec=discord.Member)
        owner.mention = "<@1>"

        embed = create_control_panel_embed(session, owner)

        assert embed.title == "ボイスチャンネル設定"
        assert "<@1>" in (embed.description or "")
        assert embed.color == discord.Color.blue()

    def test_locked_status(self) -> None:
        """ロック中の状態表示。"""
        session = _make_voice_session(is_locked=True)
        owner = MagicMock(spec=discord.Member)
        owner.mention = "<@1>"

        embed = create_control_panel_embed(session, owner)

        field_values = [f.value for f in embed.fields]
        assert "ロック中" in field_values

    def test_unlocked_status(self) -> None:
        """未ロックの状態表示。"""
        session = _make_voice_session(is_locked=False)
        owner = MagicMock(spec=discord.Member)
        owner.mention = "<@1>"

        embed = create_control_panel_embed(session, owner)

        field_values = [f.value for f in embed.fields]
        assert "未ロック" in field_values

    def test_user_limit_display(self) -> None:
        """人数制限の表示 (制限あり)。"""
        session = _make_voice_session(user_limit=10)
        owner = MagicMock(spec=discord.Member)
        owner.mention = "<@1>"

        embed = create_control_panel_embed(session, owner)

        field_values = [f.value for f in embed.fields]
        assert "10" in field_values

    def test_unlimited_display(self) -> None:
        """人数制限の表示 (無制限)。"""
        session = _make_voice_session(user_limit=0)
        owner = MagicMock(spec=discord.Member)
        owner.mention = "<@1>"

        embed = create_control_panel_embed(session, owner)

        field_values = [f.value for f in embed.fields]
        assert "無制限" in field_values


# ===========================================================================
# interaction_check テスト
# ===========================================================================


class TestInteractionCheck:
    """Tests for ControlPanelView.interaction_check."""

    async def test_owner_allowed(self) -> None:
        """オーナーは操作を許可される。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        voice_session = _make_voice_session(owner_id="1")

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ):
            result = await view.interaction_check(interaction)
            assert result is True

    async def test_non_owner_rejected(self) -> None:
        """オーナー以外は拒否される。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=2)
        voice_session = _make_voice_session(owner_id="1")

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ):
            result = await view.interaction_check(interaction)
            assert result is False
            interaction.response.send_message.assert_awaited_once()

    async def test_no_session_rejected(self) -> None:
        """セッションが存在しない場合は拒否される。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await view.interaction_check(interaction)
            assert result is False


# ===========================================================================
# RenameModal テスト
# ===========================================================================


class TestRenameModal:
    """Tests for RenameModal.on_submit."""

    async def test_rename_success(self) -> None:
        """正常なリネーム処理。"""
        modal = RenameModal(session_id=1)
        modal.name = MagicMock()
        modal.name.value = "New Name"

        interaction = _make_interaction(user_id=1)
        voice_session = _make_voice_session(owner_id="1")

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.ui.control_panel.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update:
            await modal.on_submit(interaction)

            interaction.channel.edit.assert_awaited_once_with(
                name="New Name"
            )
            mock_update.assert_awaited_once()
            interaction.response.send_message.assert_awaited_once()

    async def test_invalid_name_rejected(self) -> None:
        """空のチャンネル名はバリデーションで弾かれる。"""
        modal = RenameModal(session_id=1)
        modal.name = MagicMock()
        modal.name.value = ""

        interaction = _make_interaction(user_id=1)

        await modal.on_submit(interaction)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "無効" in msg

    async def test_non_owner_rejected(self) -> None:
        """オーナー以外はリネームできない。"""
        modal = RenameModal(session_id=1)
        modal.name = MagicMock()
        modal.name.value = "New Name"

        interaction = _make_interaction(user_id=2)
        voice_session = _make_voice_session(owner_id="1")

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ):
            await modal.on_submit(interaction)

            msg = interaction.response.send_message.call_args[0][0]
            assert "オーナーのみ" in msg


# ===========================================================================
# UserLimitModal テスト
# ===========================================================================


class TestUserLimitModal:
    """Tests for UserLimitModal.on_submit."""

    async def test_set_limit_success(self) -> None:
        """正常な人数制限設定。"""
        modal = UserLimitModal(session_id=1)
        modal.limit = MagicMock()
        modal.limit.value = "10"

        interaction = _make_interaction(user_id=1)
        voice_session = _make_voice_session(owner_id="1")

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.ui.control_panel.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update:
            await modal.on_submit(interaction)

            interaction.channel.edit.assert_awaited_once_with(user_limit=10)
            mock_update.assert_awaited_once()

    async def test_non_numeric_rejected(self) -> None:
        """数値でない入力は弾かれる。"""
        modal = UserLimitModal(session_id=1)
        modal.limit = MagicMock()
        modal.limit.value = "abc"

        interaction = _make_interaction(user_id=1)

        await modal.on_submit(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "数字" in msg

    async def test_out_of_range_rejected(self) -> None:
        """0-99 範囲外は弾かれる。"""
        modal = UserLimitModal(session_id=1)
        modal.limit = MagicMock()
        modal.limit.value = "100"

        interaction = _make_interaction(user_id=1)

        await modal.on_submit(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "0〜99" in msg

    async def test_zero_means_unlimited(self) -> None:
        """0 は無制限として設定される。"""
        modal = UserLimitModal(session_id=1)
        modal.limit = MagicMock()
        modal.limit.value = "0"

        interaction = _make_interaction(user_id=1)
        voice_session = _make_voice_session(owner_id="1")

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.ui.control_panel.update_voice_session",
            new_callable=AsyncMock,
        ):
            await modal.on_submit(interaction)

            interaction.channel.edit.assert_awaited_once_with(user_limit=0)
            msg = interaction.response.send_message.call_args[0][0]
            assert "無制限" in msg


# ===========================================================================
# Lock / Hide ボタンテスト
# ===========================================================================


class TestLockButton:
    """Tests for ControlPanelView.lock_button."""

    async def test_lock_channel(self) -> None:
        """未ロック → ロックに切り替え。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        voice_session = _make_voice_session(
            owner_id="1", is_locked=False
        )

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.ui.control_panel.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update:
            button = view.lock_button
            await view.lock_button.callback(interaction)

            # @everyone の connect が拒否される
            interaction.channel.set_permissions.assert_any_await(
                interaction.guild.default_role, connect=False
            )
            # DB に is_locked=True が書き込まれる
            mock_update.assert_awaited_once()
            assert mock_update.call_args[1]["is_locked"] is True
            # ボタンラベルが「解除」に変わる
            assert button.label == "解除"

    async def test_unlock_channel(self) -> None:
        """ロック中 → ロック解除に切り替え。"""
        view = ControlPanelView(session_id=1, is_locked=True)
        interaction = _make_interaction(user_id=1)
        voice_session = _make_voice_session(
            owner_id="1", is_locked=True
        )

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.ui.control_panel.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update:
            button = view.lock_button
            await view.lock_button.callback(interaction)

            # @everyone の権限上書きが削除される
            interaction.channel.set_permissions.assert_any_await(
                interaction.guild.default_role, overwrite=None
            )
            mock_update.assert_awaited_once()
            assert mock_update.call_args[1]["is_locked"] is False
            assert button.label == "ロック"


class TestHideButton:
    """Tests for ControlPanelView.hide_button."""

    async def test_hide_channel(self) -> None:
        """表示中 → 非表示に切り替え。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        voice_session = _make_voice_session(
            owner_id="1", is_hidden=False
        )

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.ui.control_panel.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update:
            button = view.hide_button
            await view.hide_button.callback(interaction)

            interaction.channel.set_permissions.assert_any_await(
                interaction.guild.default_role, view_channel=False
            )
            mock_update.assert_awaited_once()
            assert mock_update.call_args[1]["is_hidden"] is True
            assert button.label == "表示"

    async def test_show_channel(self) -> None:
        """非表示 → 表示に切り替え。"""
        view = ControlPanelView(session_id=1, is_hidden=True)
        interaction = _make_interaction(user_id=1)
        voice_session = _make_voice_session(
            owner_id="1", is_hidden=True
        )

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.ui.control_panel.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update:
            button = view.hide_button
            await view.hide_button.callback(interaction)

            interaction.channel.set_permissions.assert_any_await(
                interaction.guild.default_role, view_channel=None
            )
            mock_update.assert_awaited_once()
            assert mock_update.call_args[1]["is_hidden"] is False
            assert button.label == "非表示"


# ===========================================================================
# TransferSelectMenu テスト
# ===========================================================================


class TestTransferSelectMenu:
    """Tests for TransferSelectMenu.callback."""

    async def test_transfer_success(self) -> None:
        """正常なオーナー譲渡。"""
        options = [discord.SelectOption(label="User2", value="2")]
        menu = TransferSelectMenu(options)
        menu._values = ["2"]  # selected value

        interaction = _make_interaction(user_id=1)
        new_owner = MagicMock(spec=discord.Member)
        new_owner.id = 2
        new_owner.mention = "<@2>"
        interaction.guild.get_member = MagicMock(return_value=new_owner)

        voice_session = _make_voice_session(owner_id="1")

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.ui.control_panel.update_voice_session",
            new_callable=AsyncMock,
        ) as mock_update:
            await menu.callback(interaction)

            mock_update.assert_awaited_once()
            assert mock_update.call_args[1]["owner_id"] == "2"
            interaction.response.edit_message.assert_awaited_once()

    async def test_member_not_found(self) -> None:
        """メンバーが見つからない場合。"""
        options = [discord.SelectOption(label="User2", value="2")]
        menu = TransferSelectMenu(options)
        menu._values = ["2"]

        interaction = _make_interaction(user_id=1)
        interaction.guild.get_member = MagicMock(return_value=None)

        await menu.callback(interaction)

        interaction.response.edit_message.assert_awaited_once()
        msg = interaction.response.edit_message.call_args[1]["content"]
        assert "見つかりません" in msg

    async def test_no_session_found(self) -> None:
        """セッションが見つからない場合。"""
        options = [discord.SelectOption(label="User2", value="2")]
        menu = TransferSelectMenu(options)
        menu._values = ["2"]

        interaction = _make_interaction(user_id=1)
        new_owner = MagicMock(spec=discord.Member)
        new_owner.id = 2
        interaction.guild.get_member = MagicMock(return_value=new_owner)

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await menu.callback(interaction)

            msg = interaction.response.edit_message.call_args[1]["content"]
            assert "セッション" in msg
