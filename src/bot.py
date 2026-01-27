"""Discord bot class definition."""

import discord
from discord.ext import commands

from src.database.engine import async_session, init_db
from src.services.db_service import get_all_voice_sessions
from src.ui.control_panel import ControlPanelView


class EphemeralVCBot(commands.Bot):
    """Main bot class for Ephemeral VC."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

    async def setup_hook(self) -> None:
        """Setup hook called before the bot starts."""
        # Initialize database
        await init_db()

        # Load cogs
        await self.load_extension("src.cogs.voice")
        await self.load_extension("src.cogs.admin")
        await self.load_extension("src.cogs.health")

        # Restore persistent views for existing sessions
        async with async_session() as session:
            sessions = await get_all_voice_sessions(session)
            for voice_session in sessions:
                view = ControlPanelView(
                    voice_session.id,
                    voice_session.is_locked,
                    voice_session.is_hidden,
                )
                self.add_view(view)

        # Sync slash commands
        await self.tree.sync()

    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        # Set bot status
        activity = discord.Game(name="お菓子を食べています")
        await self.change_presence(activity=activity)

        if self.user:
            print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")
