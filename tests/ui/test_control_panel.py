"""Tests for control panel UI components."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.ui.control_panel import (
    AllowSelectView,
    BitrateSelectMenu,
    BitrateSelectView,
    BlockSelectView,
    ControlPanelView,
    KickSelectView,
    RegionSelectMenu,
    RegionSelectView,
    RenameModal,
    TransferSelectMenu,
    TransferSelectView,
    UserLimitModal,
    _find_panel_message,
    create_control_panel_embed,
    repost_panel,
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


class _AsyncIter:
    """AsyncIterator for mocking channel.history()."""

    def __init__(self, items: list[MagicMock]) -> None:
        self._items = iter(items)

    def __aiter__(self) -> _AsyncIter:
        return self

    async def __anext__(self) -> MagicMock:
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration from None


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
            # ephemeral ではなく defer() を呼ぶ
            interaction.response.defer.assert_awaited_once()
            # チャンネルに通知メッセージが送信される
            interaction.channel.send.assert_awaited_once()
            msg = interaction.channel.send.call_args[0][0]
            assert "New Name" in msg

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

    async def test_default_value_set(self) -> None:
        """current_name を渡すとデフォルト値にセットされる。"""
        modal = RenameModal(session_id=1, current_name="My Channel")
        assert modal.name.default == "My Channel"

    async def test_no_default_when_empty(self) -> None:
        """current_name が空の場合、デフォルト値はセットされない。"""
        modal = RenameModal(session_id=1)
        assert modal.name.default is None

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
            # チャンネルに通知メッセージが送信される
            interaction.channel.send.assert_awaited_once()
            msg = interaction.channel.send.call_args[0][0]
            assert "10" in msg

    async def test_default_value_set(self) -> None:
        """current_limit を渡すとデフォルト値にセットされる。"""
        modal = UserLimitModal(session_id=1, current_limit=10)
        assert modal.limit.default == "10"

    async def test_default_value_zero(self) -> None:
        """current_limit が 0 の場合もデフォルト値にセットされる。"""
        modal = UserLimitModal(session_id=1, current_limit=0)
        assert modal.limit.default == "0"

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
            # チャンネルへの通知で「無制限」が含まれる
            msg = interaction.channel.send.call_args[0][0]
            assert "無制限" in msg


# ===========================================================================
# rename_button / limit_button テスト (モーダルにデフォルト値を渡す)
# ===========================================================================


class TestRenameButton:
    """Tests for ControlPanelView.rename_button passing current values."""

    async def test_passes_current_channel_name(self) -> None:
        """ボタン押下時に現在のチャンネル名がモーダルに渡される。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        interaction.channel.name = "Current Name"

        await view.rename_button.callback(interaction)

        interaction.response.send_modal.assert_awaited_once()
        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, RenameModal)
        assert modal.name.default == "Current Name"

    async def test_no_name_for_non_voice_channel(self) -> None:
        """VoiceChannel でない場合はデフォルト値なし。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1, is_voice=False)

        await view.rename_button.callback(interaction)

        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, RenameModal)
        assert modal.name.default is None


class TestLimitButton:
    """Tests for ControlPanelView.limit_button passing current values."""

    async def test_passes_current_user_limit(self) -> None:
        """ボタン押下時に現在の人数制限がモーダルに渡される。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        interaction.channel.user_limit = 5

        await view.limit_button.callback(interaction)

        interaction.response.send_modal.assert_awaited_once()
        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, UserLimitModal)
        assert modal.limit.default == "5"

    async def test_passes_zero_limit(self) -> None:
        """人数制限 0 (無制限) もモーダルに渡される。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        interaction.channel.user_limit = 0

        await view.limit_button.callback(interaction)

        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, UserLimitModal)
        assert modal.limit.default == "0"

    async def test_no_limit_for_non_voice_channel(self) -> None:
        """VoiceChannel でない場合はデフォルト値 0。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1, is_voice=False)

        await view.limit_button.callback(interaction)

        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, UserLimitModal)
        assert modal.limit.default == "0"


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
            # チャンネルに通知メッセージが送信される
            interaction.channel.send.assert_awaited_once()
            msg = interaction.channel.send.call_args[0][0]
            assert "ロック" in msg

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
            # チャンネルに通知メッセージが送信される
            interaction.channel.send.assert_awaited_once()
            msg = interaction.channel.send.call_args[0][0]
            assert "ロック解除" in msg


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
            # チャンネルに通知メッセージが送信される
            interaction.channel.send.assert_awaited_once()
            msg = interaction.channel.send.call_args[0][0]
            assert "非表示" in msg

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
            # チャンネルに通知メッセージが送信される
            interaction.channel.send.assert_awaited_once()
            msg = interaction.channel.send.call_args[0][0]
            assert "表示" in msg


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
        ) as mock_update, patch(
            "src.ui.control_panel.repost_panel",
            new_callable=AsyncMock,
        ) as mock_repost:
            await menu.callback(interaction)

            mock_update.assert_awaited_once()
            assert mock_update.call_args[1]["owner_id"] == "2"
            interaction.response.edit_message.assert_awaited_once()
            # チャンネルに譲渡メッセージが送信される
            interaction.channel.send.assert_awaited_once()
            msg = interaction.channel.send.call_args[0][0]
            assert "<@2>" in msg
            assert "譲渡" in msg
            # パネルが再投稿される
            mock_repost.assert_awaited_once_with(
                interaction.channel, interaction.client
            )

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


# ===========================================================================
# TransferSelectView テスト
# ===========================================================================


class TestTransferSelectView:
    """Tests for TransferSelectView member filtering."""

    async def test_excludes_bot_members(self) -> None:
        """Bot ユーザーが候補から除外される。"""
        human = MagicMock(spec=discord.Member)
        human.id = 2
        human.bot = False
        human.display_name = "Human"

        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = 99
        bot_member.bot = True
        bot_member.display_name = "Bot"

        channel = MagicMock(spec=discord.VoiceChannel)
        channel.members = [human, bot_member]

        view = TransferSelectView(channel, owner_id=1)
        # セレクトメニューが1つ追加される (Bot は除外)
        assert len(view.children) == 1
        select_menu = view.children[0]
        assert isinstance(select_menu, TransferSelectMenu)
        # Bot は選択肢に含まれない
        assert len(select_menu.options) == 1
        assert select_menu.options[0].value == "2"

    async def test_excludes_owner(self) -> None:
        """オーナー自身が候補から除外される。"""
        owner = MagicMock(spec=discord.Member)
        owner.id = 1
        owner.bot = False
        owner.display_name = "Owner"

        other = MagicMock(spec=discord.Member)
        other.id = 2
        other.bot = False
        other.display_name = "Other"

        channel = MagicMock(spec=discord.VoiceChannel)
        channel.members = [owner, other]

        view = TransferSelectView(channel, owner_id=1)
        assert len(view.children) == 1
        select_menu = view.children[0]
        assert len(select_menu.options) == 1
        assert select_menu.options[0].value == "2"

    async def test_empty_when_only_bots_and_owner(self) -> None:
        """オーナーと Bot しかいない場合、セレクトメニューは追加されない。"""
        owner = MagicMock(spec=discord.Member)
        owner.id = 1
        owner.bot = False

        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = 99
        bot_member.bot = True

        channel = MagicMock(spec=discord.VoiceChannel)
        channel.members = [owner, bot_member]

        view = TransferSelectView(channel, owner_id=1)
        assert len(view.children) == 0


# ===========================================================================
# NSFW ボタンテスト
# ===========================================================================


class TestNsfwButton:
    """Tests for ControlPanelView.nsfw_button."""

    async def test_enable_nsfw(self) -> None:
        """NSFW を有効化する。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        interaction.channel.nsfw = False

        with patch(
            "src.ui.control_panel.refresh_panel_embed",
            new_callable=AsyncMock,
        ):
            await view.nsfw_button.callback(interaction)

        interaction.channel.edit.assert_awaited_once_with(nsfw=True)
        # ephemeral ではなく defer() を呼ぶ
        interaction.response.defer.assert_awaited_once()
        # チャンネルに通知メッセージが送信される
        msg = interaction.channel.send.call_args[0][0]
        assert "年齢制限を設定" in msg
        assert view.nsfw_button.label == "制限解除"

    async def test_disable_nsfw(self) -> None:
        """NSFW を無効化する。"""
        view = ControlPanelView(session_id=1, is_nsfw=True)
        interaction = _make_interaction(user_id=1)
        interaction.channel.nsfw = True

        with patch(
            "src.ui.control_panel.refresh_panel_embed",
            new_callable=AsyncMock,
        ):
            await view.nsfw_button.callback(interaction)

        interaction.channel.edit.assert_awaited_once_with(nsfw=False)
        # チャンネルに通知メッセージが送信される
        msg = interaction.channel.send.call_args[0][0]
        assert "年齢制限を解除" in msg
        assert view.nsfw_button.label == "年齢制限"

    async def test_nsfw_non_voice_channel_skipped(self) -> None:
        """VoiceChannel でない場合は何もしない。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1, is_voice=False)

        await view.nsfw_button.callback(interaction)

        interaction.response.defer.assert_not_awaited()


# ===========================================================================
# ビットレートボタンテスト
# ===========================================================================


class TestBitrateButton:
    """Tests for ControlPanelView.bitrate_button."""

    async def test_sends_select_view(self) -> None:
        """ビットレートボタンはセレクトメニューを送信する。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)

        await view.bitrate_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args[1]
        assert isinstance(kwargs["view"], BitrateSelectView)
        assert kwargs["ephemeral"] is True


class TestBitrateSelectMenu:
    """Tests for BitrateSelectMenu.callback."""

    async def test_change_bitrate_success(self) -> None:
        """ビットレートを変更する。"""
        options = [discord.SelectOption(label="64 kbps", value="64000")]
        menu = BitrateSelectMenu(options)
        menu._values = ["64000"]

        interaction = _make_interaction(user_id=1)

        await menu.callback(interaction)

        interaction.channel.edit.assert_awaited_once_with(bitrate=64000)
        # セレクトメニューを ✅ に置き換え
        interaction.response.edit_message.assert_awaited_once()
        assert interaction.response.edit_message.call_args[1]["content"] == "✅"
        # チャンネルに通知メッセージが送信される
        msg = interaction.channel.send.call_args[0][0]
        assert "64 kbps" in msg

    async def test_bitrate_http_exception(self) -> None:
        """ブーストレベルが足りない場合のエラー処理。"""
        options = [discord.SelectOption(label="384 kbps", value="384000")]
        menu = BitrateSelectMenu(options)
        menu._values = ["384000"]

        interaction = _make_interaction(user_id=1)
        interaction.channel.edit = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=400), "Premium required"
            )
        )

        await menu.callback(interaction)

        msg = interaction.response.edit_message.call_args[1]["content"]
        assert "ブーストレベル" in msg

    async def test_bitrate_non_voice_channel(self) -> None:
        """VoiceChannel でない場合は edit を呼ばないがセレクトメニューは閉じる。"""
        options = [discord.SelectOption(label="64 kbps", value="64000")]
        menu = BitrateSelectMenu(options)
        menu._values = ["64000"]

        interaction = _make_interaction(user_id=1, is_voice=False)

        await menu.callback(interaction)

        # セレクトメニューを閉じる
        interaction.response.edit_message.assert_awaited_once()
        assert interaction.response.edit_message.call_args[1]["content"] == "✅"
        # チャンネルへの通知は送信されない
        interaction.channel.send.assert_not_awaited()


# ===========================================================================
# リージョンボタンテスト
# ===========================================================================


class TestRegionButton:
    """Tests for ControlPanelView.region_button."""

    async def test_sends_select_view(self) -> None:
        """リージョンボタンはセレクトメニューを送信する。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)

        await view.region_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args[1]
        assert isinstance(kwargs["view"], RegionSelectView)
        assert kwargs["ephemeral"] is True


class TestRegionSelectMenu:
    """Tests for RegionSelectMenu.callback."""

    async def test_change_region_japan(self) -> None:
        """リージョンを日本に変更する。"""
        options = [discord.SelectOption(label="日本", value="japan")]
        menu = RegionSelectMenu(options)
        menu._values = ["japan"]

        interaction = _make_interaction(user_id=1)

        await menu.callback(interaction)

        interaction.channel.edit.assert_awaited_once_with(rtc_region="japan")
        # セレクトメニューを ✅ に置き換え
        assert interaction.response.edit_message.call_args[1]["content"] == "✅"
        # チャンネルに通知メッセージが送信される
        msg = interaction.channel.send.call_args[0][0]
        assert "japan" in msg

    async def test_change_region_auto(self) -> None:
        """自動リージョンは None を渡す。"""
        options = [discord.SelectOption(label="自動", value="auto")]
        menu = RegionSelectMenu(options)
        menu._values = ["auto"]

        interaction = _make_interaction(user_id=1)

        await menu.callback(interaction)

        interaction.channel.edit.assert_awaited_once_with(rtc_region=None)
        # セレクトメニューを ✅ に置き換え
        assert interaction.response.edit_message.call_args[1]["content"] == "✅"
        # チャンネルに通知メッセージが送信される
        msg = interaction.channel.send.call_args[0][0]
        assert "自動" in msg

    async def test_region_notification_sent(self) -> None:
        """リージョン変更後に通知メッセージが送信される。"""
        options = [discord.SelectOption(label="日本", value="japan")]
        menu = RegionSelectMenu(options)
        menu._values = ["japan"]

        interaction = _make_interaction(user_id=1)

        await menu.callback(interaction)

        interaction.channel.send.assert_awaited_once()
        msg = interaction.channel.send.call_args[0][0]
        assert "リージョン" in msg


# ===========================================================================
# 譲渡ボタンテスト (追加)
# ===========================================================================


class TestTransferButton:
    """Tests for ControlPanelView.transfer_button."""

    async def test_sends_select_when_members_exist(self) -> None:
        """メンバーがいる場合、セレクトメニューを送信する。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)

        other = MagicMock(spec=discord.Member)
        other.id = 2
        other.bot = False
        other.display_name = "Other"
        interaction.channel.members = [other]

        await view.transfer_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args[1]
        assert isinstance(kwargs["view"], TransferSelectView)

    async def test_rejects_when_no_members(self) -> None:
        """他にメンバーがいない場合、エラーメッセージを返す。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        interaction.channel.members = []

        await view.transfer_button.callback(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "メンバーがいません" in msg

    async def test_non_voice_channel_skipped(self) -> None:
        """VoiceChannel でない場合は何もしない。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1, is_voice=False)

        await view.transfer_button.callback(interaction)

        interaction.response.send_message.assert_not_awaited()


# ===========================================================================
# キックボタンテスト
# ===========================================================================


class TestKickButton:
    """Tests for ControlPanelView.kick_button."""

    async def test_sends_kick_select(self) -> None:
        """キックボタンはユーザーセレクトを送信する。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)

        await view.kick_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args[1]
        assert isinstance(kwargs["view"], KickSelectView)
        assert kwargs["ephemeral"] is True


# ===========================================================================
# ブロックボタンテスト
# ===========================================================================


class TestBlockButton:
    """Tests for ControlPanelView.block_button."""

    async def test_sends_block_select(self) -> None:
        """ブロックボタンはユーザーセレクトを送信する。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)

        await view.block_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args[1]
        assert isinstance(kwargs["view"], BlockSelectView)
        assert kwargs["ephemeral"] is True


# ===========================================================================
# 許可ボタンテスト
# ===========================================================================


class TestAllowButton:
    """Tests for ControlPanelView.allow_button."""

    async def test_sends_allow_select(self) -> None:
        """許可ボタンはユーザーセレクトを送信する。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)

        await view.allow_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args[1]
        assert isinstance(kwargs["view"], AllowSelectView)
        assert kwargs["ephemeral"] is True


# ===========================================================================
# ControlPanelView 初期化テスト
# ===========================================================================


class TestControlPanelViewInit:
    """Tests for ControlPanelView initial state."""

    async def test_default_labels(self) -> None:
        """デフォルト状態のラベル。"""
        view = ControlPanelView(session_id=1)
        assert view.lock_button.label == "ロック"
        assert view.hide_button.label == "非表示"
        assert view.nsfw_button.label == "年齢制限"

    async def test_locked_labels(self) -> None:
        """ロック状態のラベル。"""
        view = ControlPanelView(session_id=1, is_locked=True)
        assert view.lock_button.label == "解除"
        assert str(view.lock_button.emoji) == "🔓"

    async def test_hidden_labels(self) -> None:
        """非表示状態のラベル。"""
        view = ControlPanelView(session_id=1, is_hidden=True)
        assert view.hide_button.label == "表示"
        assert str(view.hide_button.emoji) == "👁️"

    async def test_nsfw_labels(self) -> None:
        """NSFW 状態のラベル。"""
        view = ControlPanelView(session_id=1, is_nsfw=True)
        assert view.nsfw_button.label == "制限解除"

    async def test_all_flags_combined(self) -> None:
        """全フラグ ON の組み合わせ。"""
        view = ControlPanelView(
            session_id=1, is_locked=True, is_hidden=True, is_nsfw=True
        )
        assert view.lock_button.label == "解除"
        assert view.hide_button.label == "表示"
        assert view.nsfw_button.label == "制限解除"

    async def test_timeout_is_none(self) -> None:
        """永続 View なので timeout=None。"""
        view = ControlPanelView(session_id=1)
        assert view.timeout is None

    async def test_session_id_stored(self) -> None:
        """session_id が保存される。"""
        view = ControlPanelView(session_id=42)
        assert view.session_id == 42


# ===========================================================================
# RenameModal — セッション未発見テスト
# ===========================================================================


class TestRenameModalEdgeCases:
    """RenameModal on_submit edge cases."""

    async def test_no_session_found(self) -> None:
        """セッションが見つからない場合。"""
        modal = RenameModal(session_id=1)
        modal.name = MagicMock()
        modal.name.value = "New Name"

        interaction = _make_interaction(user_id=1)

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await modal.on_submit(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "セッション" in msg


class TestUserLimitModalEdgeCases:
    """UserLimitModal on_submit edge cases."""

    async def test_no_session_found(self) -> None:
        """セッションが見つからない場合。"""
        modal = UserLimitModal(session_id=1)
        modal.limit = MagicMock()
        modal.limit.value = "10"

        interaction = _make_interaction(user_id=1)

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await modal.on_submit(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "セッション" in msg

    async def test_non_owner_rejected(self) -> None:
        """オーナー以外は人数制限を変更できない。"""
        modal = UserLimitModal(session_id=1)
        modal.limit = MagicMock()
        modal.limit.value = "10"

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

    async def test_negative_value_rejected(self) -> None:
        """負の値は弾かれる。"""
        modal = UserLimitModal(session_id=1)
        modal.limit = MagicMock()
        modal.limit.value = "-1"

        interaction = _make_interaction(user_id=1)

        await modal.on_submit(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "0〜99" in msg


# ===========================================================================
# Lock/Hide ボタン — セッション未発見テスト
# ===========================================================================


class TestLockButtonEdgeCases:
    """Lock button edge cases."""

    async def test_no_session_returns_early(self) -> None:
        """セッションが見つからない場合は早期リターン。"""
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
            await view.lock_button.callback(interaction)

        interaction.channel.set_permissions.assert_not_awaited()

    async def test_non_voice_channel_returns_early(self) -> None:
        """VoiceChannel でない場合は早期リターン。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1, is_voice=False)

        await view.lock_button.callback(interaction)

        interaction.response.send_message.assert_not_awaited()

    async def test_no_guild_returns_early(self) -> None:
        """ギルドがない場合は早期リターン。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        interaction.guild = None

        await view.lock_button.callback(interaction)

        interaction.response.send_message.assert_not_awaited()


class TestHideButtonEdgeCases:
    """Hide button edge cases."""

    async def test_no_session_returns_early(self) -> None:
        """セッションが見つからない場合は早期リターン。"""
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
            await view.hide_button.callback(interaction)

        interaction.channel.set_permissions.assert_not_awaited()

    async def test_hide_sets_permissions_for_each_member(self) -> None:
        """非表示時、チャンネル内の各メンバーに view_channel=True を設定。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        voice_session = _make_voice_session(owner_id="1", is_hidden=False)

        # チャンネルにメンバーが2人いる
        m1 = MagicMock(spec=discord.Member)
        m2 = MagicMock(spec=discord.Member)
        interaction.channel.members = [m1, m2]

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
        ), patch(
            "src.ui.control_panel.refresh_panel_embed",
            new_callable=AsyncMock,
        ):
            await view.hide_button.callback(interaction)

        # @everyone + 2メンバー = 3回 set_permissions が呼ばれる
        assert interaction.channel.set_permissions.await_count == 3


# ===========================================================================
# BitrateSelectView / RegionSelectView 構造テスト
# ===========================================================================


class TestBitrateSelectViewStructure:
    """Tests for BitrateSelectView structure."""

    async def test_has_8_options(self) -> None:
        """8つのビットレートオプションがある。"""
        view = BitrateSelectView()
        assert len(view.children) == 1
        menu = view.children[0]
        assert isinstance(menu, BitrateSelectMenu)
        assert len(menu.options) == 8

    async def test_option_values_are_numeric(self) -> None:
        """全オプションの値が数値文字列。"""
        view = BitrateSelectView()
        menu = view.children[0]
        for opt in menu.options:
            assert opt.value.isdigit()


class TestRegionSelectViewStructure:
    """Tests for RegionSelectView structure."""

    async def test_has_14_options(self) -> None:
        """14のリージョンオプションがある。"""
        view = RegionSelectView()
        assert len(view.children) == 1
        menu = view.children[0]
        assert isinstance(menu, RegionSelectMenu)
        assert len(menu.options) == 14

    async def test_auto_option_exists(self) -> None:
        """自動オプションが含まれる。"""
        view = RegionSelectView()
        menu = view.children[0]
        values = [opt.value for opt in menu.options]
        assert "auto" in values

    async def test_japan_option_exists(self) -> None:
        """日本オプションが含まれる。"""
        view = RegionSelectView()
        menu = view.children[0]
        values = [opt.value for opt in menu.options]
        assert "japan" in values


# ===========================================================================
# repost_panel テスト
# ===========================================================================


class TestRepostPanel:
    """Tests for repost_panel function."""

    async def test_deletes_old_and_sends_new(self) -> None:
        """旧パネルを削除し、新パネルを送信する。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 100
        channel.nsfw = False
        channel.guild = MagicMock(spec=discord.Guild)

        owner = MagicMock(spec=discord.Member)
        owner.mention = "<@1>"
        channel.guild.get_member = MagicMock(return_value=owner)

        # 旧パネルメッセージ
        old_msg = MagicMock()
        old_msg.author = channel.guild.me
        old_msg.embeds = [MagicMock(title="ボイスチャンネル設定")]
        old_msg.delete = AsyncMock()
        channel.pins = AsyncMock(return_value=[old_msg])

        # 新パネル送信
        channel.send = AsyncMock(return_value=MagicMock())

        voice_session = _make_voice_session(owner_id="1")
        bot = MagicMock()
        bot.add_view = MagicMock()

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ):
            await repost_panel(channel, bot)

        # 旧パネル削除
        old_msg.delete.assert_awaited_once()
        # 新パネル送信
        channel.send.assert_awaited_once()
        kwargs = channel.send.call_args[1]
        assert "embed" in kwargs
        assert "view" in kwargs
        # View が bot に登録される
        bot.add_view.assert_called_once()

    async def test_skips_when_no_session(self) -> None:
        """セッションがなければ何もしない。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 100
        bot = MagicMock()

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await repost_panel(channel, bot)

        channel.send.assert_not_called()

    async def test_skips_when_no_owner(self) -> None:
        """オーナーが見つからなければ何もしない。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 100
        channel.guild = MagicMock(spec=discord.Guild)
        channel.guild.get_member = MagicMock(return_value=None)
        bot = MagicMock()

        voice_session = _make_voice_session(owner_id="999")

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ):
            await repost_panel(channel, bot)

        channel.send.assert_not_called()

    async def test_works_without_old_panel(self) -> None:
        """旧パネルがなくても新パネルは送信される。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 100
        channel.nsfw = False
        channel.guild = MagicMock(spec=discord.Guild)

        owner = MagicMock(spec=discord.Member)
        channel.guild.get_member = MagicMock(return_value=owner)

        # ピンが空、履歴も空
        channel.pins = AsyncMock(return_value=[])
        channel.history = MagicMock(return_value=_AsyncIter([]))
        channel.send = AsyncMock(return_value=MagicMock())

        voice_session = _make_voice_session(owner_id="1")
        bot = MagicMock()
        bot.add_view = MagicMock()

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ):
            await repost_panel(channel, bot)

        # 新パネルは送信される
        channel.send.assert_awaited_once()

    async def test_suppresses_http_exception_on_find(self) -> None:
        """_find_panel_message で HTTPException が発生しても新パネルは送信される。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 100
        channel.nsfw = False
        channel.guild = MagicMock(spec=discord.Guild)

        owner = MagicMock(spec=discord.Member)
        channel.guild.get_member = MagicMock(return_value=owner)

        channel.send = AsyncMock(return_value=MagicMock())

        voice_session = _make_voice_session(owner_id="1")
        bot = MagicMock()
        bot.add_view = MagicMock()

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.ui.control_panel._find_panel_message",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await repost_panel(channel, bot)

        # 旧パネルが見つからなくても新パネルは送信される
        channel.send.assert_awaited_once()

    async def test_does_not_delete_non_panel_pins(self) -> None:
        """パネル以外のピン留めメッセージは削除されない。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 100
        channel.nsfw = False
        channel.guild = MagicMock(spec=discord.Guild)

        owner = MagicMock(spec=discord.Member)
        channel.guild.get_member = MagicMock(return_value=owner)

        # Bot のメッセージだがタイトルが異なる
        other_bot_msg = MagicMock()
        other_bot_msg.author = channel.guild.me
        other_bot_msg.embeds = [MagicMock(title="別のEmbed")]
        other_bot_msg.delete = AsyncMock()

        # ユーザーのメッセージ
        user_msg = MagicMock()
        user_msg.author = MagicMock()  # guild.me とは異なる
        user_msg.embeds = [MagicMock(title="ボイスチャンネル設定")]
        user_msg.delete = AsyncMock()

        channel.pins = AsyncMock(return_value=[other_bot_msg, user_msg])
        # 履歴にも同じメッセージ (パネルではない)
        channel.history = MagicMock(
            return_value=_AsyncIter([other_bot_msg, user_msg])
        )
        channel.send = AsyncMock(return_value=MagicMock())

        voice_session = _make_voice_session(owner_id="1")
        bot = MagicMock()
        bot.add_view = MagicMock()

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ):
            await repost_panel(channel, bot)

        # どちらも削除されない
        other_bot_msg.delete.assert_not_awaited()
        user_msg.delete.assert_not_awaited()

    async def test_passes_session_flags_to_view(self) -> None:
        """is_locked, is_hidden, nsfw が ControlPanelView に渡される。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 100
        channel.nsfw = True
        channel.guild = MagicMock(spec=discord.Guild)

        owner = MagicMock(spec=discord.Member)
        channel.guild.get_member = MagicMock(return_value=owner)
        channel.pins = AsyncMock(return_value=[])
        channel.history = MagicMock(return_value=_AsyncIter([]))
        channel.send = AsyncMock(return_value=MagicMock())

        voice_session = _make_voice_session(
            owner_id="1", is_locked=True, is_hidden=True
        )
        bot = MagicMock()
        bot.add_view = MagicMock()

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ), patch(
            "src.ui.control_panel.ControlPanelView",
            wraps=ControlPanelView,
        ) as mock_view_cls:
            await repost_panel(channel, bot)

        # ControlPanelView が正しいフラグで呼ばれる
        mock_view_cls.assert_called_once_with(
            voice_session.id, True, True, True
        )

    async def test_deletes_unpinned_panel_from_history(self) -> None:
        """ピン留めされていない旧パネルも履歴から見つけて削除する。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = 100
        channel.nsfw = False
        channel.guild = MagicMock(spec=discord.Guild)

        owner = MagicMock(spec=discord.Member)
        channel.guild.get_member = MagicMock(return_value=owner)

        # ピンにはパネルがない
        channel.pins = AsyncMock(return_value=[])

        # 履歴にパネルがある (ピン留めされていない)
        old_msg = MagicMock()
        old_msg.author = channel.guild.me
        old_msg.embeds = [MagicMock(title="ボイスチャンネル設定")]
        old_msg.delete = AsyncMock()
        channel.history = MagicMock(return_value=_AsyncIter([old_msg]))

        channel.send = AsyncMock(return_value=MagicMock())

        voice_session = _make_voice_session(owner_id="1")
        bot = MagicMock()
        bot.add_view = MagicMock()

        mock_factory, _ = _mock_async_session()
        with patch(
            "src.ui.control_panel.async_session", mock_factory
        ), patch(
            "src.ui.control_panel.get_voice_session",
            new_callable=AsyncMock,
            return_value=voice_session,
        ):
            await repost_panel(channel, bot)

        # 履歴から見つけた旧パネルが削除される
        old_msg.delete.assert_awaited_once()
        # 新パネルも送信される
        channel.send.assert_awaited_once()


# ===========================================================================
# _find_panel_message テスト
# ===========================================================================


class TestFindPanelMessage:
    """Tests for _find_panel_message helper."""

    async def test_finds_panel_in_pins(self) -> None:
        """ピン留めからパネルを見つける。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.guild = MagicMock(spec=discord.Guild)

        panel_msg = MagicMock()
        panel_msg.author = channel.guild.me
        panel_msg.embeds = [MagicMock(title="ボイスチャンネル設定")]
        channel.pins = AsyncMock(return_value=[panel_msg])

        result = await _find_panel_message(channel)
        assert result is panel_msg

    async def test_finds_panel_in_history(self) -> None:
        """ピンになければ履歴からパネルを見つける。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.guild = MagicMock(spec=discord.Guild)

        panel_msg = MagicMock()
        panel_msg.author = channel.guild.me
        panel_msg.embeds = [MagicMock(title="ボイスチャンネル設定")]

        channel.pins = AsyncMock(return_value=[])
        channel.history = MagicMock(return_value=_AsyncIter([panel_msg]))

        result = await _find_panel_message(channel)
        assert result is panel_msg

    async def test_returns_none_when_not_found(self) -> None:
        """パネルが見つからなければ None を返す。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.guild = MagicMock(spec=discord.Guild)

        channel.pins = AsyncMock(return_value=[])
        channel.history = MagicMock(return_value=_AsyncIter([]))

        result = await _find_panel_message(channel)
        assert result is None

    async def test_ignores_non_bot_messages(self) -> None:
        """Bot 以外のメッセージは無視する。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.guild = MagicMock(spec=discord.Guild)

        user_msg = MagicMock()
        user_msg.author = MagicMock()  # guild.me とは異なる
        user_msg.embeds = [MagicMock(title="ボイスチャンネル設定")]

        channel.pins = AsyncMock(return_value=[user_msg])
        channel.history = MagicMock(return_value=_AsyncIter([user_msg]))

        result = await _find_panel_message(channel)
        assert result is None

    async def test_ignores_wrong_title(self) -> None:
        """タイトルが異なる Embed は無視する。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.guild = MagicMock(spec=discord.Guild)

        bot_msg = MagicMock()
        bot_msg.author = channel.guild.me
        bot_msg.embeds = [MagicMock(title="別のEmbed")]

        channel.pins = AsyncMock(return_value=[bot_msg])
        channel.history = MagicMock(return_value=_AsyncIter([bot_msg]))

        result = await _find_panel_message(channel)
        assert result is None

    async def test_suppresses_http_exception_on_pins(self) -> None:
        """pins() で HTTPException が発生しても履歴にフォールバック。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.guild = MagicMock(spec=discord.Guild)

        panel_msg = MagicMock()
        panel_msg.author = channel.guild.me
        panel_msg.embeds = [MagicMock(title="ボイスチャンネル設定")]

        channel.pins = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=500), "error"
            )
        )
        channel.history = MagicMock(return_value=_AsyncIter([panel_msg]))

        result = await _find_panel_message(channel)
        assert result is panel_msg

    async def test_suppresses_http_exception_on_history(self) -> None:
        """history() でも HTTPException が発生すると None を返す。"""
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.guild = MagicMock(spec=discord.Guild)

        channel.pins = AsyncMock(return_value=[])
        channel.history = MagicMock(
            side_effect=discord.HTTPException(
                MagicMock(status=500), "error"
            )
        )

        result = await _find_panel_message(channel)
        assert result is None


# ===========================================================================
# KickSelectView テスト
# ===========================================================================


class TestKickSelectCallback:
    """Tests for KickSelectView.select_user callback."""

    async def test_kick_success(self) -> None:
        """VC 内のメンバーをキックする。"""
        view = KickSelectView()
        select = view.children[0]

        interaction = _make_interaction(user_id=1)
        channel = interaction.channel

        user_to_kick = MagicMock(spec=discord.Member)
        user_to_kick.mention = "<@2>"
        user_to_kick.voice = MagicMock()
        user_to_kick.voice.channel = channel
        user_to_kick.move_to = AsyncMock()

        select._values = [user_to_kick]

        await select.callback(interaction)

        user_to_kick.move_to.assert_awaited_once_with(None)
        # セレクトメニューを ✅ に置き換え
        interaction.response.edit_message.assert_awaited_once()
        assert interaction.response.edit_message.call_args[1]["content"] == "✅"
        # チャンネルに通知メッセージが送信される
        channel.send.assert_awaited_once()
        msg = channel.send.call_args[0][0]
        assert "キック" in msg

    async def test_kick_user_not_in_channel(self) -> None:
        """VC にいないメンバーはキックできない。"""
        view = KickSelectView()
        select = view.children[0]

        interaction = _make_interaction(user_id=1)

        user_to_kick = MagicMock(spec=discord.Member)
        user_to_kick.mention = "<@2>"
        user_to_kick.voice = MagicMock()
        user_to_kick.voice.channel = MagicMock()  # 別のチャンネル

        select._values = [user_to_kick]

        await select.callback(interaction)

        interaction.response.edit_message.assert_awaited_once()
        msg = interaction.response.edit_message.call_args[1]["content"]
        assert "いません" in msg

    async def test_kick_non_voice_channel(self) -> None:
        """VoiceChannel でない場合は何もしない。"""
        view = KickSelectView()
        select = view.children[0]

        interaction = _make_interaction(user_id=1, is_voice=False)

        select._values = [MagicMock()]

        await select.callback(interaction)

        interaction.response.edit_message.assert_not_awaited()


# ===========================================================================
# BlockSelectView テスト
# ===========================================================================


class TestBlockSelectCallback:
    """Tests for BlockSelectView.select_user callback."""

    async def test_block_success(self) -> None:
        """メンバーをブロックする。"""
        view = BlockSelectView()
        select = view.children[0]

        interaction = _make_interaction(user_id=1)
        channel = interaction.channel

        user_to_block = MagicMock(spec=discord.Member)
        user_to_block.mention = "<@2>"
        user_to_block.voice = MagicMock()
        user_to_block.voice.channel = channel
        user_to_block.move_to = AsyncMock()

        select._values = [user_to_block]

        await select.callback(interaction)

        channel.set_permissions.assert_awaited_once_with(
            user_to_block, connect=False
        )
        # VC にいるのでキックもされる
        user_to_block.move_to.assert_awaited_once_with(None)
        # セレクトメニューを ✅ に置き換え
        interaction.response.edit_message.assert_awaited_once()
        assert interaction.response.edit_message.call_args[1]["content"] == "✅"
        # チャンネルに通知メッセージが送信される
        channel.send.assert_awaited_once()
        msg = channel.send.call_args[0][0]
        assert "ブロック" in msg

    async def test_block_user_not_in_vc(self) -> None:
        """VC にいないメンバーをブロック (キックなし)。"""
        view = BlockSelectView()
        select = view.children[0]

        interaction = _make_interaction(user_id=1)
        channel = interaction.channel

        user_to_block = MagicMock(spec=discord.Member)
        user_to_block.mention = "<@2>"
        user_to_block.voice = None  # VC にいない
        user_to_block.move_to = AsyncMock()

        select._values = [user_to_block]

        await select.callback(interaction)

        channel.set_permissions.assert_awaited_once_with(
            user_to_block, connect=False
        )
        # VC にいないのでキックされない
        user_to_block.move_to.assert_not_awaited()
        interaction.response.edit_message.assert_awaited_once()

    async def test_block_non_voice_channel(self) -> None:
        """VoiceChannel でない場合は何もしない。"""
        view = BlockSelectView()
        select = view.children[0]

        interaction = _make_interaction(user_id=1, is_voice=False)

        select._values = [MagicMock(spec=discord.Member)]

        await select.callback(interaction)

        interaction.response.edit_message.assert_not_awaited()

    async def test_block_non_member(self) -> None:
        """Member でない場合は何もしない。"""
        view = BlockSelectView()
        select = view.children[0]

        interaction = _make_interaction(user_id=1)

        # spec=discord.User (Member ではない)
        non_member = MagicMock(spec=discord.User)

        select._values = [non_member]

        await select.callback(interaction)

        interaction.response.edit_message.assert_not_awaited()


# ===========================================================================
# AllowSelectView テスト
# ===========================================================================


class TestAllowSelectCallback:
    """Tests for AllowSelectView.select_user callback."""

    async def test_allow_success(self) -> None:
        """メンバーに接続を許可する。"""
        view = AllowSelectView()
        select = view.children[0]

        interaction = _make_interaction(user_id=1)
        channel = interaction.channel

        user_to_allow = MagicMock(spec=discord.Member)
        user_to_allow.mention = "<@2>"

        select._values = [user_to_allow]

        await select.callback(interaction)

        channel.set_permissions.assert_awaited_once_with(
            user_to_allow, connect=True
        )
        # セレクトメニューを ✅ に置き換え
        interaction.response.edit_message.assert_awaited_once()
        assert interaction.response.edit_message.call_args[1]["content"] == "✅"
        # チャンネルに通知メッセージが送信される
        channel.send.assert_awaited_once()
        msg = channel.send.call_args[0][0]
        assert "許可" in msg

    async def test_allow_non_voice_channel(self) -> None:
        """VoiceChannel でない場合は何もしない。"""
        view = AllowSelectView()
        select = view.children[0]

        interaction = _make_interaction(user_id=1, is_voice=False)

        select._values = [MagicMock(spec=discord.Member)]

        await select.callback(interaction)

        interaction.response.edit_message.assert_not_awaited()

    async def test_allow_non_member(self) -> None:
        """Member でない場合は何もしない。"""
        view = AllowSelectView()
        select = view.children[0]

        interaction = _make_interaction(user_id=1)

        non_member = MagicMock(spec=discord.User)

        select._values = [non_member]

        await select.callback(interaction)

        interaction.response.edit_message.assert_not_awaited()


# ===========================================================================
# TransferSelectMenu 追加エッジケーステスト
# ===========================================================================


class TestTransferSelectMenuEdgeCases:
    """Edge case tests for TransferSelectMenu.callback."""

    async def test_non_voice_channel_returns_early(self) -> None:
        """VoiceChannel でない場合は何もしない。"""
        options = [discord.SelectOption(label="User2", value="2")]
        menu = TransferSelectMenu(options)
        menu._values = ["2"]

        interaction = _make_interaction(user_id=1, is_voice=False)

        await menu.callback(interaction)

        interaction.response.edit_message.assert_not_awaited()

    async def test_no_guild_returns_early(self) -> None:
        """ギルドがない場合は何もしない。"""
        options = [discord.SelectOption(label="User2", value="2")]
        menu = TransferSelectMenu(options)
        menu._values = ["2"]

        interaction = _make_interaction(user_id=1)
        interaction.guild = None

        await menu.callback(interaction)

        interaction.response.edit_message.assert_not_awaited()


# ===========================================================================
# Lock ボタン — オーナー権限付与テスト
# ===========================================================================


class TestLockButtonOwnerPermissions:
    """Tests for lock button granting owner full permissions."""

    async def test_lock_grants_owner_full_permissions(self) -> None:
        """ロック時にオーナーにフル権限が付与される。"""
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
        ):
            await view.lock_button.callback(interaction)

        # オーナーにフル権限が付与される
        interaction.channel.set_permissions.assert_any_await(
            interaction.user,
            connect=True,
            speak=True,
            stream=True,
            move_members=True,
            mute_members=True,
            deafen_members=True,
        )


# ===========================================================================
# Hide ボタン — no-guild テスト
# ===========================================================================


class TestHideButtonNoGuild:
    """Tests for hide button with no guild."""

    async def test_no_guild_returns_early(self) -> None:
        """ギルドがない場合は早期リターン。"""
        view = ControlPanelView(session_id=1)
        interaction = _make_interaction(user_id=1)
        interaction.guild = None

        await view.hide_button.callback(interaction)

        interaction.response.send_message.assert_not_awaited()
