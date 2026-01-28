"""Tests for BumpCog (DISBOARD/ディス速報 bump reminder)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from src.cogs.bump import (
    DISBOARD_BOT_ID,
    DISBOARD_SUCCESS_KEYWORD,
    DISSOKU_BOT_ID,
    DISSOKU_SUCCESS_KEYWORD,
    TARGET_ROLE_NAME,
    BumpCog,
    BumpNotificationView,
)

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog() -> BumpCog:
    """Create a BumpCog with a mock bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.wait_until_ready = AsyncMock()
    bot.get_channel = MagicMock(return_value=None)
    bot.add_view = MagicMock()
    return BumpCog(bot)


def _make_message(
    *,
    author_id: int,
    channel_id: int,
    guild_id: int = 12345,
    embed_description: str | None = None,
    embed_title: str | None = None,
    content: str | None = None,
    interaction_user: discord.Member | None = None,
) -> MagicMock:
    """Create a mock Discord message."""
    message = MagicMock(spec=discord.Message)
    message.author = MagicMock()
    message.author.id = author_id
    message.channel = MagicMock()
    message.channel.id = channel_id
    message.guild = MagicMock()
    message.guild.id = guild_id
    message.guild.get_member = MagicMock(return_value=interaction_user)
    message.content = content

    if embed_description is not None or embed_title is not None:
        embed = MagicMock(spec=discord.Embed)
        embed.description = embed_description
        embed.title = embed_title
        message.embeds = [embed]
    else:
        message.embeds = []

    if interaction_user:
        message.interaction = MagicMock()
        message.interaction.user = interaction_user
    else:
        message.interaction = None

    return message


def _make_member(*, has_target_role: bool = True) -> MagicMock:
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 99999
    member.name = "TestUser"
    member.mention = "<@99999>"

    if has_target_role:
        role = MagicMock()
        role.name = TARGET_ROLE_NAME
        member.roles = [role]
    else:
        member.roles = []

    return member


def _make_reminder(
    *,
    reminder_id: int = 1,
    guild_id: str = "12345",
    channel_id: str = "456",
    service_name: str = "DISBOARD",
    is_enabled: bool = True,
    role_id: str | None = None,
) -> MagicMock:
    """Create a mock BumpReminder."""
    reminder = MagicMock()
    reminder.id = reminder_id
    reminder.guild_id = guild_id
    reminder.channel_id = channel_id
    reminder.service_name = service_name
    reminder.is_enabled = is_enabled
    reminder.role_id = role_id
    return reminder


# ---------------------------------------------------------------------------
# _detect_bump_success テスト
# ---------------------------------------------------------------------------


class TestDetectBumpSuccess:
    """Tests for _detect_bump_success."""

    def test_detects_disboard_success(self) -> None:
        """DISBOARD の bump 成功を検知する。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_description=f"サーバーの{DISBOARD_SUCCESS_KEYWORD}しました！",
        )

        result = cog._detect_bump_success(message)
        assert result == "DISBOARD"

    def test_detects_dissoku_success(self) -> None:
        """ディス速報の bump 成功を検知する (description)。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description=f"サーバーを{DISSOKU_SUCCESS_KEYWORD}しました！",
        )

        result = cog._detect_bump_success(message)
        assert result == "ディス速報"

    def test_detects_dissoku_success_in_title(self) -> None:
        """ディス速報の bump 成功を検知する (title)。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_title=f"サーバー名 を{DISSOKU_SUCCESS_KEYWORD}したよ!",
        )

        result = cog._detect_bump_success(message)
        assert result == "ディス速報"

    def test_detects_dissoku_success_in_content(self) -> None:
        """ディス速報の bump 成功を検知する (message.content)。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            content=f"🍭CHILLカフェ を{DISSOKU_SUCCESS_KEYWORD}したよ!",
        )

        result = cog._detect_bump_success(message)
        assert result == "ディス速報"

    def test_returns_none_for_non_bump_message(self) -> None:
        """bump 成功ではないメッセージは None を返す。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_description="This is not a bump message",
        )

        result = cog._detect_bump_success(message)
        assert result is None

    def test_returns_none_for_no_embeds(self) -> None:
        """Embed がないメッセージは None を返す。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
        )

        result = cog._detect_bump_success(message)
        assert result is None

    def test_returns_none_for_wrong_bot(self) -> None:
        """DISBOARD/ディス速報以外の Bot は None を返す。"""
        cog = _make_cog()
        message = _make_message(
            author_id=12345,  # Wrong bot
            channel_id=456,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
        )

        result = cog._detect_bump_success(message)
        assert result is None


# ---------------------------------------------------------------------------
# _get_bump_user テスト
# ---------------------------------------------------------------------------


class TestGetBumpUser:
    """Tests for _get_bump_user."""

    def test_returns_member_from_interaction(self) -> None:
        """interaction.user が Member なら返す。"""
        cog = _make_cog()
        member = _make_member()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            interaction_user=member,
        )

        result = cog._get_bump_user(message)
        assert result == member

    def test_returns_none_without_interaction(self) -> None:
        """interaction がなければ None を返す。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
        )

        result = cog._get_bump_user(message)
        assert result is None


# ---------------------------------------------------------------------------
# _has_target_role テスト
# ---------------------------------------------------------------------------


class TestHasTargetRole:
    """Tests for _has_target_role."""

    def test_returns_true_with_role(self) -> None:
        """Server Bumper ロールを持つメンバーは True。"""
        cog = _make_cog()
        member = _make_member(has_target_role=True)

        result = cog._has_target_role(member)
        assert result is True

    def test_returns_false_without_role(self) -> None:
        """Server Bumper ロールを持たないメンバーは False。"""
        cog = _make_cog()
        member = _make_member(has_target_role=False)

        result = cog._has_target_role(member)
        assert result is False


# ---------------------------------------------------------------------------
# on_message テスト
# ---------------------------------------------------------------------------


def _make_bump_config(*, guild_id: str = "12345", channel_id: str = "456") -> MagicMock:
    """Create a mock BumpConfig."""
    config = MagicMock()
    config.guild_id = guild_id
    config.channel_id = channel_id
    return config


class TestOnMessage:
    """Tests for on_message listener."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Mock database session."""
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    async def test_skips_when_channel_not_configured(self) -> None:
        """bump 監視設定がないギルドは無視。"""
        cog = _make_cog()
        member = _make_member()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=None,  # 設定なし
            ),
            patch("src.cogs.bump.upsert_bump_reminder") as mock_upsert,
        ):
            await cog.on_message(message)

        mock_upsert.assert_not_called()

    async def test_skips_wrong_channel(self) -> None:
        """設定されたチャンネル以外は無視。"""
        cog = _make_cog()
        member = _make_member()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=999,  # 設定と異なるチャンネル
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # 設定は channel_id=456 だが、メッセージは 999
        mock_config = _make_bump_config(channel_id="456")

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch("src.cogs.bump.upsert_bump_reminder") as mock_upsert,
        ):
            await cog.on_message(message)

        mock_upsert.assert_not_called()

    async def test_skips_wrong_bot(self) -> None:
        """DISBOARD/ディス速報以外の Bot は無視。"""
        cog = _make_cog()
        member = _make_member()
        message = _make_message(
            author_id=12345,  # Wrong bot
            channel_id=456,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        # Bot ID が違うので get_bump_config は呼ばれない
        with patch("src.cogs.bump.upsert_bump_reminder") as mock_upsert:
            await cog.on_message(message)

        mock_upsert.assert_not_called()

    async def test_skips_user_without_role(self) -> None:
        """Server Bumper ロールを持たないユーザーは無視。"""
        cog = _make_cog()
        member = _make_member(has_target_role=False)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_config = _make_bump_config(channel_id="456")

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch("src.cogs.bump.upsert_bump_reminder") as mock_upsert,
        ):
            await cog.on_message(message)

        mock_upsert.assert_not_called()

    async def test_creates_reminder_on_valid_bump(
        self, mock_db_session: MagicMock
    ) -> None:
        """有効な bump でリマインダーを作成し、検知 Embed と View を送信。"""
        cog = _make_cog()
        member = _make_member(has_target_role=True)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )
        # チャンネルの send をモック
        message.channel.send = AsyncMock()

        # Mock config and reminder
        mock_config = _make_bump_config(guild_id="12345", channel_id="456")
        mock_reminder = _make_reminder(is_enabled=True)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_db_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.upsert_bump_reminder",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ) as mock_upsert,
        ):
            await cog.on_message(message)

        mock_upsert.assert_awaited_once()
        call_kwargs = mock_upsert.call_args[1]
        assert call_kwargs["guild_id"] == "12345"
        assert call_kwargs["channel_id"] == "456"
        assert call_kwargs["service_name"] == "DISBOARD"

        # 検知 Embed と View が送信されたことを確認
        message.channel.send.assert_awaited_once()
        send_kwargs = message.channel.send.call_args[1]
        assert isinstance(send_kwargs["embed"], discord.Embed)
        assert "Bump 検知" in send_kwargs["embed"].title
        assert isinstance(send_kwargs["view"], BumpNotificationView)

    async def test_creates_reminder_shows_default_role_in_embed(
        self, mock_db_session: MagicMock
    ) -> None:
        """デフォルトロールが Embed に表示される。"""
        cog = _make_cog()
        member = _make_member(has_target_role=True)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )
        message.channel.send = AsyncMock()

        mock_config = _make_bump_config(guild_id="12345", channel_id="456")
        # role_id が None = デフォルトロール
        mock_reminder = _make_reminder(is_enabled=True, role_id=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_db_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.upsert_bump_reminder",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ),
        ):
            await cog.on_message(message)

        send_kwargs = message.channel.send.call_args[1]
        embed = send_kwargs["embed"]
        # デフォルトロール名が表示される
        assert "現在の通知先:" in embed.description
        assert f"@{TARGET_ROLE_NAME}" in embed.description

    async def test_creates_reminder_shows_custom_role_in_embed(
        self, mock_db_session: MagicMock
    ) -> None:
        """カスタムロールが Embed に表示される。"""
        cog = _make_cog()
        member = _make_member(has_target_role=True)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )
        message.channel.send = AsyncMock()

        # カスタムロールを設定
        mock_custom_role = MagicMock()
        mock_custom_role.name = "カスタムロール"
        message.guild.get_role = MagicMock(return_value=mock_custom_role)

        mock_config = _make_bump_config(guild_id="12345", channel_id="456")
        # role_id が設定されている = カスタムロール
        mock_reminder = _make_reminder(is_enabled=True, role_id="999")

        with (
            patch("src.cogs.bump.async_session", return_value=mock_db_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.upsert_bump_reminder",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ),
        ):
            await cog.on_message(message)

        # guild.get_role が呼ばれることを確認
        message.guild.get_role.assert_called_once_with(999)

        send_kwargs = message.channel.send.call_args[1]
        embed = send_kwargs["embed"]
        # カスタムロール名が表示される
        assert "現在の通知先:" in embed.description
        assert "@カスタムロール" in embed.description


# ---------------------------------------------------------------------------
# _reminder_check テスト
# ---------------------------------------------------------------------------


class TestReminderCheck:
    """Tests for _reminder_check loop."""

    async def test_sends_reminder_for_due_reminders(self) -> None:
        """期限が来たリマインダーを Embed と View で送信する。"""
        cog = _make_cog()

        # Mock reminder
        reminder = _make_reminder()

        # Mock channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_channel.guild = MagicMock()
        mock_channel.guild.name = "Test Guild"
        mock_role = MagicMock()
        mock_role.mention = "@ServerVoter"

        with patch("discord.utils.get", return_value=mock_role):
            cog.bot.get_channel = MagicMock(return_value=mock_channel)

            # Mock DB session
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            with (
                patch("src.cogs.bump.async_session", return_value=mock_session),
                patch(
                    "src.cogs.bump.get_due_bump_reminders",
                    new_callable=AsyncMock,
                    return_value=[reminder],
                ),
                patch(
                    "src.cogs.bump.clear_bump_reminder", new_callable=AsyncMock
                ) as mock_clear,
            ):
                await cog._reminder_check()  # type: ignore[misc]

            mock_channel.send.assert_awaited_once()
            send_kwargs = mock_channel.send.call_args[1]
            assert send_kwargs["content"] == "@ServerVoter"
            assert isinstance(send_kwargs["embed"], discord.Embed)
            assert "Bump リマインダー" in send_kwargs["embed"].title
            assert isinstance(send_kwargs["view"], BumpNotificationView)
            mock_clear.assert_awaited_once_with(mock_session, 1)

    async def test_uses_here_when_role_not_found(self) -> None:
        """Server Bumper ロールが見つからない場合は @here を使用。"""
        cog = _make_cog()

        # Mock reminder
        reminder = _make_reminder()

        # Mock channel (no role found)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_channel.guild = MagicMock()
        mock_channel.guild.name = "Test Guild"

        with patch("discord.utils.get", return_value=None):
            cog.bot.get_channel = MagicMock(return_value=mock_channel)

            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            with (
                patch("src.cogs.bump.async_session", return_value=mock_session),
                patch(
                    "src.cogs.bump.get_due_bump_reminders",
                    new_callable=AsyncMock,
                    return_value=[reminder],
                ),
                patch(
                    "src.cogs.bump.clear_bump_reminder", new_callable=AsyncMock
                ),
            ):
                await cog._reminder_check()  # type: ignore[misc]

            send_kwargs = mock_channel.send.call_args[1]
            assert send_kwargs["content"] == "@here"

    async def test_skips_invalid_channel(self) -> None:
        """チャンネルが見つからない場合はスキップ。"""
        cog = _make_cog()

        reminder = _make_reminder()

        # Return None for channel
        cog.bot.get_channel = MagicMock(return_value=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_due_bump_reminders",
                new_callable=AsyncMock,
                return_value=[reminder],
            ),
            patch(
                "src.cogs.bump.clear_bump_reminder", new_callable=AsyncMock
            ) as mock_clear,
        ):
            await cog._reminder_check()  # type: ignore[misc]

        # Should still clear the reminder
        mock_clear.assert_awaited_once()


# ---------------------------------------------------------------------------
# cog_load / cog_unload テスト
# ---------------------------------------------------------------------------


class TestCogLifecycle:
    """Tests for cog_load and cog_unload."""

    async def test_cog_load_starts_loop(self) -> None:
        """cog_load でループが開始される。"""
        cog = _make_cog()
        with patch.object(cog._reminder_check, "start") as mock_start:
            await cog.cog_load()
            mock_start.assert_called_once()

    async def test_cog_unload_cancels_loop(self) -> None:
        """cog_unload でループが停止される。"""
        cog = _make_cog()
        with (
            patch.object(cog._reminder_check, "is_running", return_value=True),
            patch.object(cog._reminder_check, "cancel") as mock_cancel,
        ):
            await cog.cog_unload()
            mock_cancel.assert_called_once()


# ---------------------------------------------------------------------------
# _before_reminder_check テスト
# ---------------------------------------------------------------------------


class TestBeforeReminderCheck:
    """Tests for _before_reminder_check."""

    async def test_waits_until_ready(self) -> None:
        """ループ開始前に wait_until_ready が呼ばれる。"""
        cog = _make_cog()
        await cog._before_reminder_check()
        cog.bot.wait_until_ready.assert_awaited_once()


# ---------------------------------------------------------------------------
# Embed 生成テスト
# ---------------------------------------------------------------------------


class TestBuildDetectionEmbed:
    """Tests for _build_detection_embed."""

    def test_detection_embed_has_correct_title(self) -> None:
        """検知 Embed のタイトルが正しい。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, True)

        assert embed.title == "Bump 検知"
        assert embed.color == discord.Color.green()

    def test_detection_embed_mentions_user(self) -> None:
        """検知 Embed にユーザーメンションが含まれる。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, True)

        assert member.mention in (embed.description or "")

    def test_detection_embed_contains_service_name(self) -> None:
        """検知 Embed にサービス名が含まれる。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed("ディス速報", member, remind_at, True)

        assert "ディス速報" in (embed.description or "")
        assert embed.footer is not None
        assert "ディス速報" in (embed.footer.text or "")

    def test_detection_embed_shows_disabled_when_disabled(self) -> None:
        """通知無効時は「無効」と表示される。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, False)

        assert "無効" in (embed.description or "")

    def test_detection_embed_shows_default_role(self) -> None:
        """デフォルトロール名が表示される。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, True)

        assert "現在の通知先:" in (embed.description or "")
        assert f"@{TARGET_ROLE_NAME}" in (embed.description or "")

    def test_detection_embed_shows_custom_role(self) -> None:
        """カスタムロール名が表示される。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed(
            "DISBOARD", member, remind_at, True, role_name="カスタムロール"
        )

        assert "現在の通知先:" in (embed.description or "")
        assert "@カスタムロール" in (embed.description or "")

    def test_detection_embed_shows_custom_role_when_disabled(self) -> None:
        """通知無効時でもカスタムロール名が表示される。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed(
            "DISBOARD", member, remind_at, False, role_name="カスタムロール"
        )

        assert "無効" in (embed.description or "")
        assert "現在の通知先:" in (embed.description or "")
        assert "@カスタムロール" in (embed.description or "")


class TestBuildReminderEmbed:
    """Tests for _build_reminder_embed."""

    def test_reminder_embed_has_correct_title(self) -> None:
        """リマインダー Embed のタイトルが正しい。"""
        cog = _make_cog()

        embed = cog._build_reminder_embed("DISBOARD")

        assert embed.title == "Bump リマインダー"
        assert embed.color == discord.Color.blue()

    def test_reminder_embed_contains_service_name(self) -> None:
        """リマインダー Embed にサービス名が含まれる。"""
        cog = _make_cog()

        embed = cog._build_reminder_embed("ディス速報")

        assert "ディス速報" in (embed.description or "")
        assert embed.footer is not None
        assert "ディス速報" in (embed.footer.text or "")


# ---------------------------------------------------------------------------
# BumpNotificationView テスト
# ---------------------------------------------------------------------------


class TestBumpNotificationView:
    """Tests for BumpNotificationView."""

    async def test_view_initializes_with_enabled_state(self) -> None:
        """有効状態で初期化される。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        assert view.guild_id == "12345"
        assert view.service_name == "DISBOARD"
        assert view.toggle_button.label == "通知を無効にする"
        assert view.toggle_button.style == discord.ButtonStyle.secondary

    async def test_view_initializes_with_disabled_state(self) -> None:
        """無効状態で初期化される。"""
        view = BumpNotificationView("12345", "DISBOARD", False)

        assert view.toggle_button.label == "通知を有効にする"
        assert view.toggle_button.style == discord.ButtonStyle.success

    async def test_view_has_correct_custom_id(self) -> None:
        """custom_id が正しい形式。"""
        view = BumpNotificationView("12345", "ディス速報", True)

        assert view.toggle_button.custom_id == "bump_toggle:12345:ディス速報"

    async def test_toggle_button_toggles_state(self) -> None:
        """ボタンクリックで状態が切り替わる。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.edit_message = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.toggle_bump_reminder",
                new_callable=AsyncMock,
                return_value=False,  # Toggled to disabled
            ) as mock_toggle,
        ):
            await view.toggle_button.callback(mock_interaction)

        mock_toggle.assert_awaited_once_with(mock_session, "12345", "DISBOARD")
        mock_interaction.response.edit_message.assert_awaited_once()
        mock_interaction.followup.send.assert_awaited_once()

        # Button should now show "enable"
        assert view.toggle_button.label == "通知を有効にする"
        assert view.toggle_button.style == discord.ButtonStyle.success

    async def test_view_has_role_button(self) -> None:
        """ロール変更ボタンが存在する。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        assert view.role_button.label == "通知ロールを変更"
        assert view.role_button.style == discord.ButtonStyle.primary
        assert view.role_button.custom_id == "bump_role:12345:DISBOARD"


# ---------------------------------------------------------------------------
# カスタムロール使用時のテスト
# ---------------------------------------------------------------------------


class TestReminderWithCustomRole:
    """Tests for reminder sending with custom role."""

    async def test_sends_reminder_with_custom_role(self) -> None:
        """カスタムロールが設定されている場合はそのロールにメンション。"""
        cog = _make_cog()

        # Mock reminder with custom role_id
        reminder = _make_reminder(role_id="999")

        # Mock channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_channel.guild = MagicMock()
        mock_channel.guild.name = "Test Guild"

        # Mock custom role
        mock_custom_role = MagicMock()
        mock_custom_role.mention = "@CustomRole"
        mock_channel.guild.get_role = MagicMock(return_value=mock_custom_role)

        cog.bot.get_channel = MagicMock(return_value=mock_channel)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_due_bump_reminders",
                new_callable=AsyncMock,
                return_value=[reminder],
            ),
            patch("src.cogs.bump.clear_bump_reminder", new_callable=AsyncMock),
        ):
            await cog._reminder_check()  # type: ignore[misc]

        mock_channel.guild.get_role.assert_called_once_with(999)
        send_kwargs = mock_channel.send.call_args[1]
        assert send_kwargs["content"] == "@CustomRole"

    async def test_falls_back_to_default_when_custom_role_not_found(self) -> None:
        """カスタムロールが見つからない場合はデフォルトロールにフォールバック。"""
        cog = _make_cog()

        # Mock reminder with custom role_id that doesn't exist
        reminder = _make_reminder(role_id="999")

        # Mock channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_channel.guild = MagicMock()
        mock_channel.guild.name = "Test Guild"

        # Custom role not found
        mock_channel.guild.get_role = MagicMock(return_value=None)

        # Default role found
        mock_default_role = MagicMock()
        mock_default_role.mention = "@ServerVoter"

        cog.bot.get_channel = MagicMock(return_value=mock_channel)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_due_bump_reminders",
                new_callable=AsyncMock,
                return_value=[reminder],
            ),
            patch("src.cogs.bump.clear_bump_reminder", new_callable=AsyncMock),
            patch("discord.utils.get", return_value=mock_default_role),
        ):
            await cog._reminder_check()  # type: ignore[misc]

        send_kwargs = mock_channel.send.call_args[1]
        assert send_kwargs["content"] == "@ServerVoter"


# ---------------------------------------------------------------------------
# BumpRoleSelectMenu テスト
# ---------------------------------------------------------------------------


class TestBumpRoleSelectMenu:
    """Tests for BumpRoleSelectMenu."""

    async def test_menu_initializes_without_default(self) -> None:
        """デフォルト値なしで初期化。"""
        from src.cogs.bump import BumpRoleSelectMenu

        menu = BumpRoleSelectMenu("12345", "DISBOARD")

        assert menu.guild_id == "12345"
        assert menu.service_name == "DISBOARD"
        assert menu.placeholder == "通知先ロールを選択..."
        assert menu.min_values == 1
        assert menu.max_values == 1
        assert len(menu.default_values) == 0

    async def test_menu_initializes_with_default(self) -> None:
        """デフォルト値ありで初期化。"""
        from src.cogs.bump import BumpRoleSelectMenu

        menu = BumpRoleSelectMenu("12345", "DISBOARD", current_role_id="999")

        assert len(menu.default_values) == 1
        assert menu.default_values[0].id == 999
        assert menu.default_values[0].type == discord.SelectDefaultValueType.role

    async def test_menu_callback_updates_role(self) -> None:
        """ロール選択時にDBが更新される。"""
        from src.cogs.bump import BumpRoleSelectMenu

        menu = BumpRoleSelectMenu("12345", "DISBOARD")

        mock_role = MagicMock()
        mock_role.id = 999
        mock_role.name = "CustomRole"
        menu._values = [mock_role]

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.edit_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.update_bump_reminder_role",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            await menu.callback(mock_interaction)

        mock_update.assert_awaited_once_with(mock_session, "12345", "DISBOARD", "999")
        mock_interaction.response.edit_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.edit_message.call_args[1]
        assert "CustomRole" in call_kwargs["content"]
        assert call_kwargs["view"] is None

    async def test_menu_callback_does_nothing_without_values(self) -> None:
        """選択値がない場合は何もしない。"""
        from src.cogs.bump import BumpRoleSelectMenu

        menu = BumpRoleSelectMenu("12345", "DISBOARD")
        menu._values = []

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.edit_message = AsyncMock()

        await menu.callback(mock_interaction)

        mock_interaction.response.edit_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# BumpRoleSelectView テスト
# ---------------------------------------------------------------------------


class TestBumpRoleSelectView:
    """Tests for BumpRoleSelectView."""

    async def test_view_initializes_with_menu(self) -> None:
        """ロール選択メニューを含む。"""
        from src.cogs.bump import BumpRoleSelectMenu, BumpRoleSelectView

        view = BumpRoleSelectView("12345", "DISBOARD")

        assert view.timeout == 60
        # メニューを探す (順序は実装依存なので型で探す)
        menu = None
        for child in view.children:
            if isinstance(child, BumpRoleSelectMenu):
                menu = child
                break
        assert menu is not None
        assert menu.guild_id == "12345"
        assert menu.service_name == "DISBOARD"

    async def test_view_passes_current_role_to_menu(self) -> None:
        """現在のロールIDをメニューに渡す。"""
        from src.cogs.bump import BumpRoleSelectMenu, BumpRoleSelectView

        view = BumpRoleSelectView("12345", "DISBOARD", current_role_id="999")

        # メニューを探す
        menu = None
        for child in view.children:
            if isinstance(child, BumpRoleSelectMenu):
                menu = child
                break
        assert menu is not None
        assert len(menu.default_values) == 1
        assert menu.default_values[0].id == 999

    async def test_reset_button_resets_role(self) -> None:
        """デフォルトに戻すボタンがロールをリセット。"""
        from src.cogs.bump import BumpRoleSelectMenu, BumpRoleSelectView

        view = BumpRoleSelectView("12345", "DISBOARD")

        # メニューを見つけて service_name を確認するためのモック
        menu = None
        for child in view.children:
            if isinstance(child, BumpRoleSelectMenu):
                menu = child
                break
        assert menu is not None

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild_id = 12345  # int型
        mock_interaction.response = MagicMock()
        mock_interaction.response.edit_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.update_bump_reminder_role",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            await view.reset_button.callback(mock_interaction)

        # role_id=None でリセット (guild_id は str に変換される)
        mock_update.assert_awaited_once_with(
            mock_session, "12345", "DISBOARD", None
        )
        mock_interaction.response.edit_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.edit_message.call_args[1]
        assert "Server Bumper" in call_kwargs["content"]
        assert "デフォルト" in call_kwargs["content"]


# ---------------------------------------------------------------------------
# role_button callback テスト
# ---------------------------------------------------------------------------


class TestRoleButtonCallback:
    """Tests for role_button callback in BumpNotificationView."""

    async def test_role_button_shows_select_view(self) -> None:
        """ロール変更ボタンがロール選択Viewを表示。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_reminder = MagicMock()
        mock_reminder.role_id = None

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ),
        ):
            await view.role_button.callback(mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        assert call_kwargs["ephemeral"] is True
        assert "DISBOARD" in mock_interaction.response.send_message.call_args[0][0]

    async def test_role_button_passes_current_role(self) -> None:
        """現在のロールIDをViewに渡す。"""
        from src.cogs.bump import BumpRoleSelectMenu, BumpRoleSelectView

        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_reminder = MagicMock()
        mock_reminder.role_id = "999"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ),
        ):
            await view.role_button.callback(mock_interaction)

        # 送信されたViewを確認
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        sent_view = call_kwargs["view"]
        assert isinstance(sent_view, BumpRoleSelectView)

        # メニューにデフォルト値が設定されている (順序は実装依存なので型で探す)
        menu = None
        for child in sent_view.children:
            if isinstance(child, BumpRoleSelectMenu):
                menu = child
                break
        assert menu is not None
        assert len(menu.default_values) == 1
        assert menu.default_values[0].id == 999

    async def test_role_button_handles_no_reminder(self) -> None:
        """リマインダーが存在しない場合もViewを表示。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new_callable=AsyncMock,
                return_value=None,  # リマインダーなし
            ),
        ):
            await view.role_button.callback(mock_interaction)

        # エラーなく実行される
        mock_interaction.response.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# 検知Embed の追加テスト
# ---------------------------------------------------------------------------


class TestBuildDetectionEmbedTimestamp:
    """Tests for detection embed timestamp formatting."""

    async def test_embed_contains_absolute_time(self) -> None:
        """Embedに絶対時刻が含まれる。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        member = MagicMock(spec=discord.Member)
        member.mention = "<@123>"

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, True)

        # タイムスタンプ形式 <t:...:t> が含まれる
        assert "<t:" in (embed.description or "")
        assert ":t>" in (embed.description or "")

    async def test_embed_contains_time_format(self) -> None:
        """Embedに時刻が含まれる。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        member = MagicMock(spec=discord.Member)
        member.mention = "<@123>"

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, True)

        # タイムスタンプ形式 <t:...:t> が含まれる
        assert ":t>" in (embed.description or "")


# ---------------------------------------------------------------------------
# _find_recent_bump テスト
# ---------------------------------------------------------------------------


class TestFindRecentBump:
    """Tests for _find_recent_bump method."""

    async def test_finds_disboard_bump(self) -> None:
        """DISBOARD の bump を検出する。"""
        from datetime import UTC, datetime
        from typing import Any

        cog = _make_cog()

        # Mock message with DISBOARD bump
        mock_message = MagicMock()
        mock_message.author = MagicMock()
        mock_message.author.id = DISBOARD_BOT_ID
        mock_embed = MagicMock()
        mock_embed.description = DISBOARD_SUCCESS_KEYWORD
        mock_message.embeds = [mock_embed]
        mock_message.created_at = datetime.now(UTC)

        # Mock channel history (discord.py uses keyword argument)
        async def mock_history(**_kwargs: Any) -> Any:
            yield mock_message

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is not None
        assert result[0] == "DISBOARD"
        assert result[1] == mock_message.created_at

    async def test_finds_dissoku_bump(self) -> None:
        """ディス速報の bump を検出する。"""
        from datetime import UTC, datetime
        from typing import Any

        cog = _make_cog()

        # Mock message with ディス速報 bump
        mock_message = MagicMock()
        mock_message.author = MagicMock()
        mock_message.author.id = DISSOKU_BOT_ID
        mock_embed = MagicMock()
        mock_embed.description = DISSOKU_SUCCESS_KEYWORD
        mock_message.embeds = [mock_embed]
        mock_message.created_at = datetime.now(UTC)

        async def mock_history(**_kwargs: Any) -> Any:
            yield mock_message

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is not None
        assert result[0] == "ディス速報"
        assert result[1] == mock_message.created_at

    async def test_returns_none_when_no_bump_found(self) -> None:
        """bump が見つからない場合は None を返す。"""
        from typing import Any

        cog = _make_cog()

        # Mock message without bump
        mock_message = MagicMock()
        mock_message.author = MagicMock()
        mock_message.author.id = 12345  # 他の Bot
        mock_message.embeds = []

        async def mock_history(**_kwargs: Any) -> Any:
            yield mock_message

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is None

    async def test_returns_none_on_http_exception(self) -> None:
        """HTTP エラー時は None を返す。"""
        from typing import Any

        cog = _make_cog()

        async def mock_history(**_kwargs: Any) -> Any:
            raise discord.HTTPException(MagicMock(), "Test error")
            yield  # Make it a generator

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is None

    async def test_returns_none_on_empty_history(self) -> None:
        """履歴が空の場合は None を返す。"""
        from typing import Any

        cog = _make_cog()

        async def mock_history(**_kwargs: Any) -> Any:
            # 何も yield しない (空のジェネレータ)
            return
            yield  # Make it a generator

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is None

    async def test_returns_first_bump_found(self) -> None:
        """複数の bump がある場合は最新 (最初に見つかった) ものを返す。"""
        from datetime import UTC, datetime, timedelta
        from typing import Any

        cog = _make_cog()

        # 新しい bump (1時間前)
        newer_message = MagicMock()
        newer_message.author = MagicMock()
        newer_message.author.id = DISBOARD_BOT_ID
        newer_embed = MagicMock()
        newer_embed.description = DISBOARD_SUCCESS_KEYWORD
        newer_message.embeds = [newer_embed]
        newer_message.created_at = datetime.now(UTC) - timedelta(hours=1)

        # 古い bump (5時間前)
        older_message = MagicMock()
        older_message.author = MagicMock()
        older_message.author.id = DISSOKU_BOT_ID
        older_embed = MagicMock()
        older_embed.description = DISSOKU_SUCCESS_KEYWORD
        older_message.embeds = [older_embed]
        older_message.created_at = datetime.now(UTC) - timedelta(hours=5)

        async def mock_history(**_kwargs: Any) -> Any:
            # history は新しい順に返す
            yield newer_message
            yield older_message

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is not None
        # 最初に見つかった (より新しい) DISBOARD の bump が返される
        assert result[0] == "DISBOARD"
        assert result[1] == newer_message.created_at


# ---------------------------------------------------------------------------
# Cog setup テスト
# ---------------------------------------------------------------------------


class TestBumpCogSetup:
    """Tests for bump cog setup function."""

    async def test_setup_registers_persistent_views(self) -> None:
        """setup が永続 View を登録する。"""
        from src.cogs.bump import setup

        mock_bot = MagicMock(spec=commands.Bot)
        mock_bot.add_view = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        # 2つの永続 View が登録される (DISBOARD と ディス速報)
        assert mock_bot.add_view.call_count == 2
        mock_bot.add_cog.assert_awaited_once()


# ---------------------------------------------------------------------------
# スラッシュコマンド テスト
# ---------------------------------------------------------------------------


class TestBumpSetupCommand:
    """Tests for /bump setup command."""

    async def test_setup_creates_config(self) -> None:
        """設定を作成してメッセージを送信する。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.upsert_bump_config", new_callable=AsyncMock
            ) as mock_upsert,
        ):
            # app_commands のコマンドは .callback でコールバック関数を取得
            await cog.bump_setup.callback(cog, mock_interaction)

        mock_upsert.assert_awaited_once_with(mock_session, "12345", "456")
        mock_interaction.response.send_message.assert_awaited_once()

    async def test_setup_requires_guild(self) -> None:
        """ギルド外では実行できない。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = None
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        await cog.bump_setup.callback(cog, mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "サーバー内" in call_args[0][0]

    async def test_setup_detects_recent_bump_and_creates_reminder(self) -> None:
        """直近の bump を検出してリマインダーを自動作成し、具体的な時刻を表示する。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()

        # 1時間前の bump
        bump_time = datetime.now(UTC) - timedelta(hours=1)
        expected_remind_at = bump_time + timedelta(hours=2)  # 2時間後にリマインド
        expected_ts = int(expected_remind_at.timestamp())

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        # TextChannel をモック
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.upsert_bump_config", new_callable=AsyncMock
            ),
            patch(
                "src.cogs.bump.upsert_bump_reminder", new_callable=AsyncMock
            ) as mock_upsert_reminder,
            patch.object(
                cog, "_find_recent_bump", new_callable=AsyncMock
            ) as mock_find,
        ):
            mock_find.return_value = ("DISBOARD", bump_time)
            await cog.bump_setup.callback(cog, mock_interaction)

        # リマインダーが作成されることを確認
        mock_upsert_reminder.assert_awaited_once()
        call_kwargs = mock_upsert_reminder.call_args[1]
        assert call_kwargs["service_name"] == "DISBOARD"

        # Embed に直近の bump 情報が含まれる
        send_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = send_kwargs["embed"]
        assert "直近の bump を検出" in embed.description
        assert "リマインダーを自動設定しました" in embed.description

        # 具体的な時刻が Discord タイムスタンプ形式で表示される
        assert f"<t:{expected_ts}:t>" in embed.description  # 絶対時刻 (例: 21:30)

        # 相対時刻 (:R>) は含まれない（絶対時刻のみ表示）
        assert ":R>" not in embed.description

        # base_description にも時刻が含まれる
        assert f"<t:{expected_ts}:t> にリマインドを送信します" in embed.description

    async def test_setup_detects_bump_already_available(self) -> None:
        """既に bump 可能な場合はその旨を表示する。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()

        # 3時間前の bump (既に bump 可能)
        bump_time = datetime.now(UTC) - timedelta(hours=3)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        # TextChannel をモック
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.upsert_bump_config", new_callable=AsyncMock
            ),
            patch(
                "src.cogs.bump.upsert_bump_reminder", new_callable=AsyncMock
            ) as mock_upsert_reminder,
            patch.object(
                cog, "_find_recent_bump", new_callable=AsyncMock
            ) as mock_find,
        ):
            mock_find.return_value = ("DISBOARD", bump_time)
            await cog.bump_setup.callback(cog, mock_interaction)

        # リマインダーは作成されない (既に bump 可能なので)
        mock_upsert_reminder.assert_not_awaited()

        # Embed に bump 可能であることが含まれる
        send_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = send_kwargs["embed"]
        assert "直近の bump を検出" in embed.description
        assert "現在 bump 可能です" in embed.description

    async def test_setup_no_recent_bump_found(self) -> None:
        """直近の bump がない場合は bump 情報なしで設定のみ表示する。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # TextChannel をモック
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.upsert_bump_config", new_callable=AsyncMock
            ),
            patch(
                "src.cogs.bump.upsert_bump_reminder", new_callable=AsyncMock
            ) as mock_upsert_reminder,
            patch.object(
                cog, "_find_recent_bump", new_callable=AsyncMock
            ) as mock_find,
        ):
            mock_find.return_value = None  # bump が見つからない
            await cog.bump_setup.callback(cog, mock_interaction)

        # リマインダーは作成されない
        mock_upsert_reminder.assert_not_awaited()

        # Embed に bump 情報が含まれない
        send_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = send_kwargs["embed"]
        assert "直近の bump を検出" not in embed.description
        assert "Bump 監視を開始しました" in embed.title

        # 両方のサービスの通知設定が followup で送信される
        assert mock_interaction.followup.send.await_count == 2

    async def test_setup_skips_history_for_non_text_channel(self) -> None:
        """TextChannel 以外ではチャンネル履歴をスキップする。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # VoiceChannel をモック (TextChannel ではない)
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.upsert_bump_config", new_callable=AsyncMock
            ) as mock_upsert,
            patch.object(
                cog, "_find_recent_bump", new_callable=AsyncMock
            ) as mock_find,
        ):
            await cog.bump_setup.callback(cog, mock_interaction)

        # 設定は作成される
        mock_upsert.assert_awaited_once_with(mock_session, "12345", "456")

        # _find_recent_bump は呼ばれない
        mock_find.assert_not_awaited()

        # Embed に bump 情報が含まれない
        send_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = send_kwargs["embed"]
        assert "直近の bump を検出" not in embed.description

    async def test_setup_shows_notification_role(self) -> None:
        """セットアップ時に通知先ロールが表示される。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # VoiceChannel をモック (TextChannel ではない -> 履歴検索なし)
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.upsert_bump_config", new_callable=AsyncMock
            ),
        ):
            await cog.bump_setup.callback(cog, mock_interaction)

        # Embed に通知先ロールが表示される
        send_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = send_kwargs["embed"]
        assert "現在の通知先:" in embed.description
        assert f"@{TARGET_ROLE_NAME}" in embed.description

    async def test_setup_shows_custom_notification_role(self) -> None:
        """セットアップ時にカスタム通知先ロールが表示される。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()

        # 1時間前の bump
        bump_time = datetime.now(UTC) - timedelta(hours=1)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        # カスタムロールを設定
        mock_custom_role = MagicMock()
        mock_custom_role.name = "カスタムロール"
        mock_interaction.guild.get_role = MagicMock(return_value=mock_custom_role)

        # TextChannel をモック
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # リマインダーにカスタムロールが設定されている
        mock_reminder = _make_reminder(role_id="999")

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.upsert_bump_config", new_callable=AsyncMock
            ),
            patch(
                "src.cogs.bump.upsert_bump_reminder",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ),
            patch.object(
                cog, "_find_recent_bump", new_callable=AsyncMock
            ) as mock_find,
        ):
            mock_find.return_value = ("DISBOARD", bump_time)
            await cog.bump_setup.callback(cog, mock_interaction)

        # Embed にカスタムロール名が表示される
        send_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = send_kwargs["embed"]
        assert "現在の通知先:" in embed.description
        assert "@カスタムロール" in embed.description


class TestBumpStatusCommand:
    """Tests for /bump status command."""

    async def test_status_shows_config(self) -> None:
        """設定がある場合は表示する。"""
        from datetime import UTC, datetime

        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.guild.get_role = MagicMock(return_value=None)
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_config = MagicMock()
        mock_config.channel_id = "456"
        mock_config.created_at = datetime.now(UTC)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.bump_status.callback(cog, mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        assert "<#456>" in embed.description

    async def test_status_shows_not_configured(self) -> None:
        """設定がない場合はその旨を表示する。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.bump_status.callback(cog, mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        assert "設定されていません" in embed.description

    async def test_status_shows_notification_roles(self) -> None:
        """通知先ロールが表示される。"""
        from datetime import UTC, datetime

        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        # カスタムロールを設定
        mock_custom_role = MagicMock()
        mock_custom_role.name = "カスタムロール"
        mock_interaction.guild.get_role = MagicMock(return_value=mock_custom_role)

        mock_config = MagicMock()
        mock_config.channel_id = "456"
        mock_config.created_at = datetime.now(UTC)

        # DISBOARD はカスタムロール, ディス速報はデフォルト
        mock_disboard_reminder = _make_reminder(
            service_name="DISBOARD", role_id="999"
        )
        mock_dissoku_reminder = None  # ディス速報はリマインダーなし

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        async def mock_get_reminder(
            _session: MagicMock, _guild_id: str, service_name: str
        ) -> MagicMock | None:
            if service_name == "DISBOARD":
                return mock_disboard_reminder
            return mock_dissoku_reminder

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new=AsyncMock(side_effect=mock_get_reminder),
            ),
        ):
            await cog.bump_status.callback(cog, mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]

        # 通知先ロールが表示される
        assert "通知先ロール" in embed.description
        assert "DISBOARD" in embed.description
        assert "ディス速報" in embed.description
        # カスタムロール名が表示される
        assert "カスタムロール" in embed.description
        # デフォルトロールも表示される
        assert "Server Bumper" in embed.description


class TestBumpDisableCommand:
    """Tests for /bump disable command."""

    async def test_disable_deletes_config(self) -> None:
        """設定を削除する。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.delete_bump_config",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_delete,
        ):
            await cog.bump_disable.callback(cog, mock_interaction)

        mock_delete.assert_awaited_once_with(mock_session, "12345")
        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        assert "停止しました" in embed.title

    async def test_disable_shows_already_disabled(self) -> None:
        """既に無効の場合はその旨を表示する。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.delete_bump_config",
                new_callable=AsyncMock,
                return_value=False,  # 既に無効
            ),
        ):
            await cog.bump_disable.callback(cog, mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        assert "既に無効" in embed.description
