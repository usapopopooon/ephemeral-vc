"""Tests for EphemeralVCBot."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord

from src.bot import EphemeralVCBot

# ===========================================================================
# __init__ テスト
# ===========================================================================


class TestBotInit:
    """Tests for EphemeralVCBot constructor."""

    @patch("src.bot.init_db", new_callable=AsyncMock)
    def test_intents_voice_states(self, _: AsyncMock) -> None:
        """voice_states Intent が有効。"""
        bot = EphemeralVCBot()
        assert bot.intents.voice_states is True

    @patch("src.bot.init_db", new_callable=AsyncMock)
    def test_intents_guilds(self, _: AsyncMock) -> None:
        """guilds Intent が有効。"""
        bot = EphemeralVCBot()
        assert bot.intents.guilds is True

    @patch("src.bot.init_db", new_callable=AsyncMock)
    def test_intents_members(self, _: AsyncMock) -> None:
        """members Intent が有効。"""
        bot = EphemeralVCBot()
        assert bot.intents.members is True

    @patch("src.bot.init_db", new_callable=AsyncMock)
    def test_command_prefix(self, _: AsyncMock) -> None:
        """コマンドプレフィックスが ! に設定されている。"""
        bot = EphemeralVCBot()
        assert bot.command_prefix == "!"


# ===========================================================================
# setup_hook テスト
# ===========================================================================


class TestSetupHook:
    """Tests for EphemeralVCBot.setup_hook."""

    def _make_bot(self) -> EphemeralVCBot:
        """setup_hook テスト用のモック済み Bot を作成する。"""
        bot = EphemeralVCBot()
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]
        bot.add_view = MagicMock()  # type: ignore[method-assign]
        return bot

    def _mock_session_factory(self) -> MagicMock:
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        return mock_factory

    @patch("src.bot.async_session")
    @patch("src.bot.init_db", new_callable=AsyncMock)
    async def test_initializes_db(
        self, mock_init_db: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """DB が初期化される。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        bot = self._make_bot()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with patch.object(
            type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
        ), patch(
            "src.bot.get_all_voice_sessions",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await bot.setup_hook()

        mock_init_db.assert_awaited_once()

    @patch("src.bot.async_session")
    @patch("src.bot.init_db", new_callable=AsyncMock)
    async def test_loads_all_cogs(
        self, _init_db: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """4つの Cog がすべて読み込まれる。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        bot = self._make_bot()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with patch.object(
            type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
        ), patch(
            "src.bot.get_all_voice_sessions",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await bot.setup_hook()

        assert bot.load_extension.await_count == 4
        bot.load_extension.assert_any_await("src.cogs.voice")
        bot.load_extension.assert_any_await("src.cogs.admin")
        bot.load_extension.assert_any_await("src.cogs.health")
        bot.load_extension.assert_any_await("src.cogs.bump")

    @patch("src.bot.async_session")
    @patch("src.bot.init_db", new_callable=AsyncMock)
    async def test_syncs_commands(
        self, _init_db: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """スラッシュコマンドが Discord に同期される。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        bot = self._make_bot()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with patch.object(
            type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
        ), patch(
            "src.bot.get_all_voice_sessions",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await bot.setup_hook()

        mock_tree.sync.assert_awaited_once()

    @patch("src.bot.async_session")
    @patch("src.bot.init_db", new_callable=AsyncMock)
    async def test_restores_views(
        self, _init_db: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """DB のセッションから View が復元される。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        vs1 = MagicMock()
        vs1.id = 1
        vs1.channel_id = "100"
        vs1.is_locked = False
        vs1.is_hidden = False
        vs2 = MagicMock()
        vs2.id = 2
        vs2.channel_id = "200"
        vs2.is_locked = True
        vs2.is_hidden = True

        bot = self._make_bot()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with patch.object(
            type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
        ), patch(
            "src.bot.get_all_voice_sessions",
            new_callable=AsyncMock,
            return_value=[vs1, vs2],
        ):
            await bot.setup_hook()

        assert bot.add_view.call_count == 2

    @patch("src.bot.async_session")
    @patch("src.bot.init_db", new_callable=AsyncMock)
    async def test_restores_views_with_nsfw_channel(
        self, _init_db: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """NSFW チャンネルの場合、is_nsfw=True で View が復元される。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        vs = MagicMock()
        vs.id = 1
        vs.channel_id = "100"
        vs.is_locked = False
        vs.is_hidden = False

        # NSFW チャンネルをモック
        nsfw_channel = MagicMock(spec=discord.VoiceChannel)
        nsfw_channel.nsfw = True

        bot = self._make_bot()
        bot.get_channel = MagicMock(return_value=nsfw_channel)
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with patch.object(
            type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
        ), patch(
            "src.bot.get_all_voice_sessions",
            new_callable=AsyncMock,
            return_value=[vs],
        ), patch(
            "src.bot.ControlPanelView"
        ) as mock_view_class:
            await bot.setup_hook()

        # is_nsfw=True で View が作成されることを確認
        mock_view_class.assert_called_once_with(1, False, False, True)
        bot.get_channel.assert_called_once_with(100)

    @patch("src.bot.async_session")
    @patch("src.bot.init_db", new_callable=AsyncMock)
    async def test_no_views_when_no_sessions(
        self, _init_db: AsyncMock, mock_session_factory: MagicMock
    ) -> None:
        """セッションがない場合、View は登録されない。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        bot = self._make_bot()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with patch.object(
            type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
        ), patch(
            "src.bot.get_all_voice_sessions",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await bot.setup_hook()

        bot.add_view.assert_not_called()


# ===========================================================================
# on_ready テスト
# ===========================================================================


class TestOnReady:
    """Tests for EphemeralVCBot.on_ready."""

    @patch("src.bot.init_db", new_callable=AsyncMock)
    async def test_sets_activity(self, _: AsyncMock) -> None:
        """ステータスが設定される。"""
        bot = EphemeralVCBot()
        bot.change_presence = AsyncMock()  # type: ignore[method-assign]

        mock_user = MagicMock()
        mock_user.id = 12345

        with patch.object(
            type(bot), "user", new_callable=PropertyMock, return_value=mock_user
        ):
            await bot.on_ready()

        bot.change_presence.assert_awaited_once()
        activity = bot.change_presence.call_args[1]["activity"]
        assert isinstance(activity, discord.Game)
        assert "お菓子" in activity.name

    @patch("src.bot.init_db", new_callable=AsyncMock)
    async def test_handles_no_user(self, _: AsyncMock) -> None:
        """self.user が None でもエラーにならない。"""
        bot = EphemeralVCBot()
        bot.change_presence = AsyncMock()  # type: ignore[method-assign]

        with patch.object(
            type(bot), "user", new_callable=PropertyMock, return_value=None
        ):
            await bot.on_ready()

        bot.change_presence.assert_awaited_once()
