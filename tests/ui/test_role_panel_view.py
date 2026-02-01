"""Tests for role panel UI components."""

from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from src.ui.role_panel_view import (
    RoleButton,
    RolePanelCreateModal,
    RolePanelView,
    create_role_panel_embed,
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
