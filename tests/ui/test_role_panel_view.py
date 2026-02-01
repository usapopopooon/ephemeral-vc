"""Tests for role panel UI components."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.ui.role_panel_view import (
    RoleButton,
    RolePanelCreateModal,
    RolePanelView,
    create_role_panel_embed,
    handle_role_reaction,
    refresh_role_panel,
)

# ===========================================================================
# Helper Functions
# ===========================================================================


def _make_role_panel(
    *,
    panel_id: int = 1,
    guild_id: str = "123456789",
    channel_id: str = "987654321",
    panel_type: str = "button",
    title: str = "Test Panel",
    description: str | None = None,
    color: int | None = None,
    message_id: str | None = None,
) -> MagicMock:
    """Create a mock RolePanel object."""
    panel = MagicMock()
    panel.id = panel_id
    panel.guild_id = guild_id
    panel.channel_id = channel_id
    panel.panel_type = panel_type
    panel.title = title
    panel.description = description
    panel.color = color
    panel.message_id = message_id
    return panel


def _make_role_panel_item(
    *,
    item_id: int = 1,
    panel_id: int = 1,
    role_id: str = "111222333",
    emoji: str = "🎮",
    label: str | None = "Gamer",
    style: str = "secondary",
    position: int = 0,
) -> MagicMock:
    """Create a mock RolePanelItem object."""
    item = MagicMock()
    item.id = item_id
    item.panel_id = panel_id
    item.role_id = role_id
    item.emoji = emoji
    item.label = label
    item.style = style
    item.position = position
    return item


# ===========================================================================
# RolePanelCreateModal - クラス属性テスト
# ===========================================================================


class TestRolePanelCreateModalClassAttributes:
    """RolePanelCreateModal のクラス属性テスト。

    Modal のインスタンス化はイベントループを必要とするため、
    クラス属性レベルでテストする。
    """

    def test_title_max_length_within_discord_limit(self) -> None:
        """タイトルの max_length が Discord の制限内 (4000)。"""
        # クラス属性として定義された TextInput を取得
        title_input = RolePanelCreateModal.panel_title
        assert title_input.max_length is not None
        assert title_input.max_length <= 4000

    def test_description_max_length_within_discord_limit(self) -> None:
        """説明文の max_length が Discord Modal の制限内 (4000)。

        Discord Modal TextInput の max_length 上限は 4000。
        Embed description の上限 (4096) とは異なる。
        """
        description_input = RolePanelCreateModal.description
        assert description_input.max_length is not None
        assert description_input.max_length <= 4000

    def test_panel_title_is_required(self) -> None:
        """タイトルフィールドは必須。"""
        title_input = RolePanelCreateModal.panel_title
        # TextInput のデフォルトは required=True
        # required が明示的に False でないことを確認
        assert title_input.required is not False
        assert title_input.min_length == 1

    def test_description_is_optional(self) -> None:
        """説明文フィールドは任意。"""
        description_input = RolePanelCreateModal.description
        assert description_input.required is False


# ===========================================================================
# RolePanelView
# ===========================================================================


class TestRolePanelView:
    """RolePanelView のテスト。"""

    @pytest.mark.asyncio
    async def test_view_instantiation(self) -> None:
        """View をインスタンス化できる。"""
        items: list[MagicMock] = []
        view = RolePanelView(panel_id=1, items=items)
        assert view.panel_id == 1
        assert view.timeout is None  # 永続 View

    @pytest.mark.asyncio
    async def test_view_is_persistent(self) -> None:
        """View は永続 (timeout=None)。"""
        view = RolePanelView(panel_id=999, items=[])
        assert view.timeout is None

    @pytest.mark.asyncio
    async def test_view_adds_buttons_for_items(self) -> None:
        """items に対応するボタンが追加される。"""
        items = [
            _make_role_panel_item(item_id=1, emoji="🎮", label="Gamer"),
            _make_role_panel_item(item_id=2, emoji="🎨", label="Artist"),
        ]
        view = RolePanelView(panel_id=1, items=items)
        assert len(view.children) == 2

    @pytest.mark.asyncio
    async def test_view_with_empty_items(self) -> None:
        """items が空でも View を作成できる。"""
        view = RolePanelView(panel_id=1, items=[])
        assert len(view.children) == 0


# ===========================================================================
# RoleButton
# ===========================================================================


class TestRoleButton:
    """RoleButton のテスト。"""

    @pytest.mark.asyncio
    async def test_button_instantiation(self) -> None:
        """ボタンをインスタンス化できる。"""
        item = _make_role_panel_item(
            item_id=2,
            role_id="123456789",
            emoji="🎮",
            label="Test",
            style="success",
        )
        button = RoleButton(panel_id=1, item=item)
        assert button.panel_id == 1
        assert button.role_id == "123456789"
        assert button.label == "Test"

    @pytest.mark.asyncio
    async def test_button_custom_id_format(self) -> None:
        """custom_id のフォーマットが正しい。"""
        item = _make_role_panel_item(item_id=50)
        button = RoleButton(panel_id=100, item=item)
        assert button.custom_id == "role_panel:100:50"

    @pytest.mark.asyncio
    async def test_button_style_mapping(self) -> None:
        """style 文字列が ButtonStyle に変換される。"""
        # primary
        item = _make_role_panel_item(style="primary")
        button = RoleButton(panel_id=1, item=item)
        assert button.style == discord.ButtonStyle.primary

        # success
        item = _make_role_panel_item(style="success")
        button = RoleButton(panel_id=1, item=item)
        assert button.style == discord.ButtonStyle.success

        # danger
        item = _make_role_panel_item(style="danger")
        button = RoleButton(panel_id=1, item=item)
        assert button.style == discord.ButtonStyle.danger

    @pytest.mark.asyncio
    async def test_button_default_style(self) -> None:
        """不明な style は secondary になる。"""
        item = _make_role_panel_item(style="unknown")
        button = RoleButton(panel_id=1, item=item)
        assert button.style == discord.ButtonStyle.secondary


# ===========================================================================
# create_role_panel_embed
# ===========================================================================


class TestCreateRolePanelEmbed:
    """create_role_panel_embed のテスト。"""

    def test_creates_embed_with_title(self) -> None:
        """タイトル付きの Embed を作成できる。"""
        panel = _make_role_panel(title="Test Panel")
        embed = create_role_panel_embed(panel, [])
        assert embed.title == "Test Panel"

    def test_creates_embed_with_description(self) -> None:
        """説明文付きの Embed を作成できる。"""
        panel = _make_role_panel(description="This is a description")
        embed = create_role_panel_embed(panel, [])
        assert embed.description == "This is a description"

    def test_creates_embed_with_custom_color(self) -> None:
        """カスタム色の Embed を作成できる。"""
        panel = _make_role_panel(color=0xFF5733)
        embed = create_role_panel_embed(panel, [])
        assert embed.color is not None
        assert embed.color.value == 0xFF5733

    def test_creates_embed_with_default_color(self) -> None:
        """色未指定時はデフォルト色 (blue) になる。"""
        panel = _make_role_panel(color=None)
        embed = create_role_panel_embed(panel, [])
        assert embed.color == discord.Color.blue()

    def test_creates_embed_without_description(self) -> None:
        """説明文なしの Embed を作成できる。"""
        panel = _make_role_panel(description=None)
        embed = create_role_panel_embed(panel, [])
        # description が None の場合は空文字列になる
        assert embed.description == ""

    def test_reaction_panel_shows_role_list(self) -> None:
        """リアクション式パネルはロール一覧を表示する。"""
        panel = _make_role_panel(panel_type="reaction")
        items = [
            _make_role_panel_item(emoji="🎮", role_id="111"),
            _make_role_panel_item(emoji="🎨", role_id="222"),
        ]
        embed = create_role_panel_embed(panel, items)
        # フィールドが追加されている
        assert len(embed.fields) == 1
        assert embed.fields[0].name == "ロール一覧"
        assert "🎮" in embed.fields[0].value
        assert "🎨" in embed.fields[0].value

    def test_button_panel_no_role_list(self) -> None:
        """ボタン式パネルはロール一覧を表示しない。"""
        panel = _make_role_panel(panel_type="button")
        items = [
            _make_role_panel_item(emoji="🎮", role_id="111"),
        ]
        embed = create_role_panel_embed(panel, items)
        # フィールドなし
        assert len(embed.fields) == 0


# ===========================================================================
# refresh_role_panel
# ===========================================================================


class TestRefreshRolePanel:
    """refresh_role_panel のテスト。"""

    @pytest.mark.asyncio
    async def test_returns_false_if_no_message_id(self) -> None:
        """message_id が None の場合 False を返す。"""
        channel = MagicMock(spec=discord.TextChannel)
        panel = _make_role_panel(message_id=None)
        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, [], bot)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_if_message_not_found(self) -> None:
        """メッセージが見つからない場合 False を返す。"""
        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        panel = _make_role_panel(message_id="123456")
        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, [], bot)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_http_exception(self) -> None:
        """HTTPException 発生時は False を返す。"""
        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )
        panel = _make_role_panel(message_id="123456")
        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, [], bot)
        assert result is False

    @pytest.mark.asyncio
    async def test_updates_button_panel(self) -> None:
        """ボタン式パネルを更新できる。"""
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)

        panel = _make_role_panel(panel_type="button", message_id="123456")
        items = [_make_role_panel_item(emoji="🎮", label="Test")]

        bot = MagicMock(spec=discord.Client)
        bot.add_view = MagicMock()

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        msg.edit.assert_called_once()
        bot.add_view.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_reaction_panel(self) -> None:
        """リアクション式パネルを更新できる。"""
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()
        msg.clear_reactions = AsyncMock()
        msg.add_reaction = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)

        panel = _make_role_panel(panel_type="reaction", message_id="123456")
        items = [
            _make_role_panel_item(emoji="🎮"),
            _make_role_panel_item(emoji="🎨"),
        ]

        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        msg.edit.assert_called_once()
        msg.clear_reactions.assert_called_once()
        assert msg.add_reaction.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_reaction_add_error(self) -> None:
        """リアクション追加失敗時もパネル更新は成功扱い。"""
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()
        msg.clear_reactions = AsyncMock()
        msg.add_reaction = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)

        panel = _make_role_panel(panel_type="reaction", message_id="123456")
        items = [_make_role_panel_item(emoji="🎮")]

        bot = MagicMock(spec=discord.Client)

        # リアクション追加失敗しても True が返る
        result = await refresh_role_panel(channel, panel, items, bot)
        assert result is True


# ===========================================================================
# handle_role_reaction
# ===========================================================================


class TestHandleRoleReaction:
    """handle_role_reaction のテスト。"""

    @pytest.mark.asyncio
    async def test_returns_early_if_member_is_none_on_add(self) -> None:
        """add 時に member が None なら早期リターン。"""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = None

        # 早期リターンするためエラーにならない
        await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_returns_if_panel_not_found(self) -> None:
        """パネルが見つからない場合は何もしない。"""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = MagicMock()
        payload.message_id = 123456
        payload.emoji = MagicMock()

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch("src.ui.role_panel_view.get_role_panel_item_by_emoji"),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=None,
            ):
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_returns_if_panel_is_not_reaction_type(self) -> None:
        """パネルがリアクション式でない場合は何もしない。"""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = MagicMock()
        payload.message_id = 123456
        payload.emoji = MagicMock()

        panel = _make_role_panel(panel_type="button")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch("src.ui.role_panel_view.get_role_panel_item_by_emoji"),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_returns_if_item_not_found(self) -> None:
        """アイテムが見つからない場合は何もしない。"""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = MagicMock()
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_returns_early_on_remove_action(self) -> None:
        """remove アクション時は guild 取得できず早期リターン。"""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = None  # remove 時は member が None
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                # remove action で member が取得できないので早期リターン
                await handle_role_reaction(payload, "remove")

    @pytest.mark.asyncio
    async def test_ignores_bot_member(self) -> None:
        """Bot ユーザーのリアクションは無視する。"""
        member = MagicMock(spec=discord.Member)
        member.bot = True

        guild = MagicMock(spec=discord.Guild)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                # Bot なので処理されない
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_adds_role_on_add_action(self) -> None:
        """add アクションでロールを付与する。"""
        role = MagicMock(spec=discord.Role)

        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.roles = []  # ロールを持っていない
        member.add_roles = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=role)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                await handle_role_reaction(payload, "add")

        member.add_roles.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_add_if_already_has_role(self) -> None:
        """既にロールを持っている場合は追加しない。"""
        role = MagicMock(spec=discord.Role)

        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.roles = [role]  # 既にロールを持っている
        member.add_roles = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=role)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                await handle_role_reaction(payload, "add")

        member.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_role_not_found(self) -> None:
        """ロールが見つからない場合は何もしない。"""
        member = MagicMock(spec=discord.Member)
        member.bot = False

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=None)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                # エラーにならずに処理される
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_handles_forbidden_error(self) -> None:
        """権限不足エラーをハンドルする。"""
        role = MagicMock(spec=discord.Role)
        role.name = "Test Role"

        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.roles = []
        member.add_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "no permission")
        )

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=role)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                # エラーにならずに処理される
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_handles_http_exception(self) -> None:
        """HTTP エラーをハンドルする。"""
        role = MagicMock(spec=discord.Role)
        role.name = "Test Role"

        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.roles = []
        member.add_roles = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=role)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                # エラーにならずに処理される
                await handle_role_reaction(payload, "add")
