"""Admin slash commands for lobby management.

サーバー管理者がロビー VC を作成するためのスラッシュコマンド。
/lobby コマンドで VC を作成し、DB にロビーとして登録する。
"""

import discord
from discord import app_commands
from discord.ext import commands

from src.database.engine import async_session
from src.services.db_service import create_lobby


class AdminCog(commands.Cog):
    """管理者用コマンドの Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="lobby", description="ロビーVCを作成します")
    @app_commands.default_permissions(administrator=True)
    async def lobby_add(self, interaction: discord.Interaction) -> None:
        """ロビー VC を作成するスラッシュコマンド。

        処理の流れ:
          1. サーバー内でのみ実行可能かチェック
          2. 「参加して作成」という名前の VC を新規作成
          3. DB にロビーとして登録
          4. 管理者に完了メッセージを表示

        @app_commands.command: スラッシュコマンドとして登録するデコレータ
        @app_commands.default_permissions: コマンドの実行に必要な権限。
          administrator=True → サーバー管理者のみ実行可能。
          Discord 側で権限チェックされるので、Bot 側でのチェックは不要。
        """
        # DM (ダイレクトメッセージ) からの実行を拒否
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        # --- VC の作成 ---
        # 「参加して作成」という名前のボイスチャンネルを作成する。
        # ユーザーがこの VC に参加すると、voice.py が一時 VC を自動作成する。
        try:
            lobby_channel = await interaction.guild.create_voice_channel(
                name="参加して作成",
            )
        except discord.HTTPException as e:
            # Discord API エラー (権限不足、チャンネル数上限等)
            await interaction.response.send_message(
                f"VCの作成に失敗しました: {e}", ephemeral=True
            )
            return

        # --- DB にロビーとして登録 ---
        async with async_session() as session:
            await create_lobby(
                session,
                guild_id=str(interaction.guild_id),
                lobby_channel_id=str(lobby_channel.id),
                category_id=None,       # カテゴリは手動で移動してもらう
                default_user_limit=0,   # デフォルトは人数制限なし
            )

        # --- 完了メッセージ ---
        # ephemeral=True → コマンド実行者にだけ見えるメッセージ
        await interaction.response.send_message(
            f"ロビー **{lobby_channel.name}** を作成しました！\n"
            f"お好みのカテゴリに手動で移動してください。",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する関数。bot.load_extension() から呼ばれる。"""
    await bot.add_cog(AdminCog(bot))
