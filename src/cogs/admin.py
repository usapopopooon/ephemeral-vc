"""Admin slash commands for lobby management."""

import discord
from discord import app_commands
from discord.ext import commands

from src.database.engine import async_session
from src.services.db_service import create_lobby


class AdminCog(commands.Cog):
    """Cog for admin commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="lobby", description="ロビーVCを作成します")
    @app_commands.default_permissions(administrator=True)
    async def lobby_add(self, interaction: discord.Interaction) -> None:
        """Create a new lobby voice channel."""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        # Create the lobby voice channel
        try:
            lobby_channel = await interaction.guild.create_voice_channel(
                name="参加して作成",
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"VCの作成に失敗しました: {e}", ephemeral=True
            )
            return

        # Register in database
        async with async_session() as session:
            await create_lobby(
                session,
                guild_id=str(interaction.guild_id),
                lobby_channel_id=str(lobby_channel.id),
                category_id=None,
                default_user_limit=0,
            )

        await interaction.response.send_message(
            f"ロビー **{lobby_channel.name}** を作成しました！\n"
            f"お好みのカテゴリに手動で移動してください。",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Setup function for loading the cog."""
    await bot.add_cog(AdminCog(bot))
