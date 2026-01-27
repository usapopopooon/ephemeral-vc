"""Control panel UI components for voice channels.

一時 VC のコントロールパネル UI。
オーナーがチャンネルの設定を変更するためのボタン・モーダル・セレクトメニューを提供する。

UI の構成:
  - ControlPanelView: メインのボタン群 (永続 View)
  - Modal: テキスト入力フォーム (名前変更、人数制限)
  - SelectView: ドロップダウン選択 (譲渡、キック、ブロック、許可等)

discord.py の UI コンポーネント:
  - View: ボタンやセレクトメニューをまとめるコンテナ
  - Button: クリック可能なボタン
  - Modal: ポップアップのテキスト入力フォーム
  - Select: ドロップダウンメニュー
  - interaction.response: ユーザーの操作に対する応答
  - ephemeral=True: 操作者にだけ見えるメッセージ
"""

from typing import Any

import discord

from src.core.permissions import is_owner
from src.core.validators import validate_channel_name, validate_user_limit
from src.database.engine import async_session
from src.database.models import VoiceSession
from src.services.db_service import get_voice_session, update_voice_session


def create_control_panel_embed(
    session: VoiceSession, owner: discord.Member
) -> discord.Embed:
    """コントロールパネルの Embed (情報表示部分) を作成する。

    チャンネルに送信される情報カードで、オーナー名とチャンネルの状態を表示する。

    Args:
        session: DB の VoiceSession オブジェクト
        owner: チャンネルオーナーの Discord メンバー

    Returns:
        組み立てた Embed オブジェクト
    """
    embed = discord.Embed(
        title="ボイスチャンネル設定",
        # owner.mention → @ユーザー名 のメンション形式 (クリックでプロフィール表示)
        description=f"オーナー: {owner.mention}",
        color=discord.Color.blue(),
    )

    lock_status = "ロック中" if session.is_locked else "未ロック"
    limit_status = str(session.user_limit) if session.user_limit > 0 else "無制限"

    embed.add_field(name="状態", value=lock_status, inline=True)
    embed.add_field(name="人数制限", value=limit_status, inline=True)

    return embed


# =============================================================================
# Modals (ポップアップ入力フォーム)
# =============================================================================


class RenameModal(discord.ui.Modal, title="チャンネル名変更"):
    """チャンネル名を変更するモーダル (ポップアップ入力フォーム)。

    discord.ui.Modal を継承して作る。
    title= でモーダルのタイトルを設定する。
    """

    # TextInput: テキスト入力フィールド。クラス変数として定義する。
    name: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="新しいチャンネル名",
        placeholder="チャンネル名を入力...",  # 未入力時のヒントテキスト
        min_length=1,
        max_length=100,  # Discord のチャンネル名上限
    )

    def __init__(self, session_id: int) -> None:
        super().__init__()
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """モーダルの送信ボタンが押されたときの処理。

        1. 入力値のバリデーション
        2. オーナー権限チェック
        3. Discord API でチャンネル名を変更
        4. DB を更新
        """
        new_name = str(self.name.value)

        if not validate_channel_name(new_name):
            await interaction.response.send_message(
                "無効なチャンネル名です。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.send_message(
                    "セッションが見つかりません。", ephemeral=True
                )
                return

            if not is_owner(voice_session.owner_id, interaction.user.id):
                await interaction.response.send_message(
                    "オーナーのみチャンネル名を変更できます。", ephemeral=True
                )
                return

            # Discord API でチャンネル名を変更
            channel = interaction.channel
            if isinstance(channel, discord.VoiceChannel):
                await channel.edit(name=new_name)

            # DB のチャンネル名も更新
            await update_voice_session(db_session, voice_session, name=new_name)

        await interaction.response.send_message(
            f"チャンネル名を **{new_name}** に変更しました。", ephemeral=True
        )


class UserLimitModal(discord.ui.Modal, title="人数制限変更"):
    """人数制限を変更するモーダル。"""

    limit: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="人数制限 (0〜99、0 = 無制限)",
        placeholder="0〜99の数字を入力...",
        min_length=1,
        max_length=2,
    )

    def __init__(self, session_id: int) -> None:
        super().__init__()
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """モーダル送信時の処理。入力値を数値に変換し、バリデーション後に適用する。"""
        # 文字列 → 数値に変換。数値でなければエラー
        try:
            new_limit = int(self.limit.value)
        except ValueError:
            await interaction.response.send_message(
                "有効な数字を入力してください。", ephemeral=True
            )
            return

        # 0〜99 の範囲チェック
        if not validate_user_limit(new_limit):
            await interaction.response.send_message(
                "無効な人数制限です。0〜99の範囲で入力してください。",
                ephemeral=True,
            )
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.send_message(
                    "セッションが見つかりません。", ephemeral=True
                )
                return

            if not is_owner(voice_session.owner_id, interaction.user.id):
                await interaction.response.send_message(
                    "オーナーのみ人数制限を変更できます。", ephemeral=True
                )
                return

            # Discord API で人数制限を変更
            channel = interaction.channel
            if isinstance(channel, discord.VoiceChannel):
                await channel.edit(user_limit=new_limit)

            # DB を更新
            await update_voice_session(db_session, voice_session, user_limit=new_limit)

        limit_text = str(new_limit) if new_limit > 0 else "無制限"
        await interaction.response.send_message(
            f"人数制限を **{limit_text}** に設定しました。", ephemeral=True
        )


# =============================================================================
# Ephemeral Select Views (ボタン押下時に表示されるセレクトメニュー)
# =============================================================================
# ephemeral = 操作者にだけ見えるメッセージとして表示される


class TransferSelectView(discord.ui.View):
    """オーナー譲渡先を選択するセレクトメニュー。

    チャンネル内のメンバー一覧をドロップダウンで表示する。
    timeout=60: 60秒操作がないと自動で無効化される。
    """

    def __init__(
        self, channel: discord.VoiceChannel, owner_id: int
    ) -> None:
        super().__init__(timeout=60)
        # オーナー自身と Bot を除外した候補リストを作成
        members = [
            m for m in channel.members if m.id != owner_id and not m.bot
        ]
        if not members:
            return  # 誰もいなければセレクトメニューを追加しない
        # SelectOption: ドロップダウンの選択肢 (label=表示名, value=内部値)
        # Discord の制限: セレクトの選択肢は最大25個
        options = [
            discord.SelectOption(
                label=m.display_name, value=str(m.id)
            )
            for m in members[:25]
        ]
        self.add_item(TransferSelectMenu(options))


class TransferSelectMenu(discord.ui.Select[Any]):
    """オーナー譲渡のセレクトメニュー本体。"""

    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(
            placeholder="新しいオーナーを選択...", options=options
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """ユーザーが選択したときの処理。

        1. 選択されたメンバーを取得
        2. テキストチャット権限を移行
        3. DB のオーナー ID を更新
        """
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel):
            return

        guild = interaction.guild
        if not guild:
            return

        # self.values[0]: 選択された値 (ユーザー ID の文字列)
        new_owner = guild.get_member(int(self.values[0]))
        if not new_owner:
            await interaction.response.edit_message(
                content="メンバーが見つかりません。", view=None
            )
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.edit_message(
                    content="セッションが見つかりません。", view=None
                )
                return

            # テキストチャット権限の移行
            # 旧オーナー: read_message_history=None (ロール設定に戻す)
            if isinstance(interaction.user, discord.Member):
                await channel.set_permissions(
                    interaction.user,
                    read_message_history=None,
                )
            # 新オーナー: read_message_history=True (閲覧可)
            await channel.set_permissions(
                new_owner, read_message_history=True
            )

            # DB のオーナー ID を更新
            await update_voice_session(
                db_session,
                voice_session,
                owner_id=str(new_owner.id),
            )

        # edit_message: 元のセレクトメニューを完了メッセージに差し替える
        # view=None でセレクトメニューを削除
        await interaction.response.edit_message(
            content=f"{new_owner.mention} にオーナーを譲渡しました。",
            view=None,
        )


class KickSelectView(discord.ui.View):
    """キック対象を選択するユーザーセレクト。

    @discord.ui.select(cls=UserSelect) で Discord 標準のユーザー選択 UI を使う。
    サーバー全メンバーから検索・選択できる。
    """

    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="キックするユーザーを選択...",
    )
    async def select_user(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect[Any]
    ) -> None:
        """ユーザー選択時の処理。VC から切断する (move_to(None))。"""
        user_to_kick = select.values[0]
        channel = interaction.channel

        if not isinstance(channel, discord.VoiceChannel):
            return

        # 選択されたユーザーがこの VC にいるか確認
        if not (
            isinstance(user_to_kick, discord.Member)
            and user_to_kick.voice
            and user_to_kick.voice.channel == channel
        ):
            await interaction.response.edit_message(
                content=f"{user_to_kick.mention} はこのチャンネルにいません。",
                view=None,
            )
            return

        # move_to(None) でユーザーを VC から切断する
        await user_to_kick.move_to(None)
        await interaction.response.edit_message(
            content=f"{user_to_kick.mention} をキックしました。", view=None
        )


class BlockSelectView(discord.ui.View):
    """ブロック対象を選択するユーザーセレクト。

    ブロック = connect=False で接続権限を拒否する。
    既に VC にいる場合はキックもする。
    """

    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.select(
        cls=discord.ui.UserSelect, placeholder="ブロックするユーザーを選択..."
    )
    async def select_user(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect[Any]
    ) -> None:
        """ユーザー選択時の処理。接続権限を拒否し、VC にいればキックする。"""
        user_to_block = select.values[0]
        channel = interaction.channel

        if not isinstance(channel, discord.VoiceChannel):
            return

        if not isinstance(user_to_block, discord.Member):
            return

        # connect=False で接続を拒否
        await channel.set_permissions(user_to_block, connect=False)

        # 既に VC にいる場合はキック
        if (
            isinstance(user_to_block, discord.Member)
            and user_to_block.voice
            and user_to_block.voice.channel == channel
        ):
            await user_to_block.move_to(None)

        await interaction.response.edit_message(
            content=f"{user_to_block.mention} をブロックしました。", view=None
        )


class AllowSelectView(discord.ui.View):
    """許可対象を選択するユーザーセレクト。

    許可 = connect=True で接続権限を許可する。
    ロック状態で特定のユーザーだけ入れるようにする場合に使う。
    """

    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.select(
        cls=discord.ui.UserSelect, placeholder="許可するユーザーを選択..."
    )
    async def select_user(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect[Any]
    ) -> None:
        """ユーザー選択時の処理。接続権限を許可する。"""
        user_to_allow = select.values[0]
        channel = interaction.channel

        if not isinstance(channel, discord.VoiceChannel):
            return

        if not isinstance(user_to_allow, discord.Member):
            return

        # connect=True で接続を許可
        await channel.set_permissions(user_to_allow, connect=True)
        await interaction.response.edit_message(
            content=f"{user_to_allow.mention} を許可しました。", view=None
        )


class BitrateSelectView(discord.ui.View):
    """ビットレートを選択するセレクトメニュー。

    ビットレート = 音声品質。高いほど高音質だが帯域を使う。
    サーバーのブーストレベルで上限が変わる。
    """

    # (表示ラベル, 値) のリスト。値は bps (bits per second) 単位
    BITRATES = [
        ("8 kbps", "8000"),
        ("16 kbps", "16000"),
        ("32 kbps", "32000"),
        ("64 kbps", "64000"),
        ("96 kbps", "96000"),
        ("128 kbps", "128000"),
        ("256 kbps", "256000"),
        ("384 kbps", "384000"),
    ]

    def __init__(self) -> None:
        super().__init__(timeout=60)
        options = [
            discord.SelectOption(label=label, value=value)
            for label, value in self.BITRATES
        ]
        self.add_item(BitrateSelectMenu(options))


class BitrateSelectMenu(discord.ui.Select[Any]):
    """ビットレートセレクトメニュー本体。"""

    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(
            placeholder="ビットレートを選択...", options=options
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """選択時の処理。Discord API でビットレートを変更する。"""
        bitrate = int(self.values[0])  # bps 単位の値
        channel = interaction.channel

        if isinstance(channel, discord.VoiceChannel):
            try:
                await channel.edit(bitrate=bitrate)
            except discord.HTTPException:
                # サーバーのブーストレベルが足りない場合
                await interaction.response.edit_message(
                    content="このサーバーのブーストレベルでは"
                    "利用できないビットレートです。",
                    view=None,
                )
                return

        label = f"{bitrate // 1000} kbps"
        await interaction.response.edit_message(
            content=f"ビットレートを **{label}** に変更しました。",
            view=None,
        )


class RegionSelectView(discord.ui.View):
    """VC リージョン (サーバー地域) を選択するセレクトメニュー。

    リージョン = 音声サーバーの地理的位置。近い方が低遅延。
    「自動」は Discord が最適なリージョンを選択する。
    """

    # (表示ラベル, Discord API の値) のリスト
    REGIONS = [
        ("自動", "auto"),
        ("日本", "japan"),
        ("シンガポール", "singapore"),
        ("香港", "hongkong"),
        ("シドニー", "sydney"),
        ("インド", "india"),
        ("米国西部", "us-west"),
        ("米国東部", "us-east"),
        ("米国中部", "us-central"),
        ("米国南部", "us-south"),
        ("ヨーロッパ", "europe"),
        ("ブラジル", "brazil"),
        ("南アフリカ", "southafrica"),
        ("ロシア", "russia"),
    ]

    def __init__(self) -> None:
        super().__init__(timeout=60)
        options = [
            discord.SelectOption(label=label, value=value)
            for label, value in self.REGIONS
        ]
        self.add_item(RegionSelectMenu(options))


class RegionSelectMenu(discord.ui.Select[Any]):
    """リージョンセレクトメニュー本体。"""

    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(placeholder="リージョンを選択...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        """選択時の処理。Discord API でリージョンを変更する。"""
        selected = self.values[0]
        # "auto" の場合は None を渡す (Discord が自動選択)
        region = None if selected == "auto" else selected
        channel = interaction.channel

        if isinstance(channel, discord.VoiceChannel):
            await channel.edit(rtc_region=region)

        region_name = selected if selected != "auto" else "自動"
        await interaction.response.edit_message(
            content=f"リージョンを **{region_name}** に変更しました。",
            view=None,
        )


# =============================================================================
# Main Control Panel View (メインのボタン群)
# =============================================================================


class ControlPanelView(discord.ui.View):
    """一時 VC のコントロールパネル。ボタンを5行に配置する。

    discord.py の View は最大5行 (row=0〜4)、各行最大5個のボタンを配置できる。

    ボタン配置:
      Row 0: [名前変更] [人数制限]
      Row 1: [ビットレート] [リージョン]
      Row 2: [ロック] [非表示] [年齢制限]
      Row 3: [譲渡] [キック]
      Row 4: [ブロック] [許可]

    timeout=None: タイムアウトなし (永続 View)。
    custom_id: Bot 再起動後もボタンを識別するための固定 ID。
    """

    def __init__(
        self,
        session_id: int,
        is_locked: bool = False,
        is_hidden: bool = False,
        is_nsfw: bool = False,
    ) -> None:
        # timeout=None で永続 View にする (タイムアウトしない)
        super().__init__(timeout=None)
        self.session_id = session_id

        # 現在の状態に応じてボタンのラベルと絵文字を切り替える
        if is_locked:
            self.lock_button.label = "解除"
            self.lock_button.emoji = "🔓"

        if is_hidden:
            self.hide_button.label = "表示"
            self.hide_button.emoji = "👁️"

        if is_nsfw:
            self.nsfw_button.label = "制限解除"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """全ボタン共通の権限チェック。オーナーのみ操作可能。

        discord.py が各ボタンのコールバック前に自動で呼ぶ。
        False を返すとコールバックが実行されない。
        """
        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.send_message(
                    "セッションが見つかりません。", ephemeral=True
                )
                return False

            if not is_owner(voice_session.owner_id, interaction.user.id):
                await interaction.response.send_message(
                    "チャンネルオーナーのみ操作できます。",
                    ephemeral=True,
                )
                return False

        return True

    # =========================================================================
    # Row 0: チャンネル設定 (名前変更・人数制限)
    # =========================================================================

    @discord.ui.button(
        label="名前変更",
        emoji="🏷️",
        style=discord.ButtonStyle.secondary,  # グレーのボタン
        custom_id="rename_button",  # 永続化用の固定 ID
        row=0,
    )
    async def rename_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """名前変更ボタン。モーダル (入力フォーム) を表示する。"""
        await interaction.response.send_modal(RenameModal(self.session_id))

    @discord.ui.button(
        label="人数制限",
        emoji="👥",
        style=discord.ButtonStyle.secondary,
        custom_id="limit_button",
        row=0,
    )
    async def limit_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """人数制限ボタン。モーダルを表示する。"""
        await interaction.response.send_modal(UserLimitModal(self.session_id))

    # =========================================================================
    # Row 1: チャンネル設定 (ビットレート・リージョン)
    # =========================================================================

    @discord.ui.button(
        label="ビットレート",
        emoji="🔊",
        style=discord.ButtonStyle.secondary,
        custom_id="bitrate_button",
        row=1,
    )
    async def bitrate_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """ビットレートボタン。セレクトメニューを表示する。"""
        await interaction.response.send_message(
            "ビットレートを選択:",
            view=BitrateSelectView(),
            ephemeral=True,
        )

    @discord.ui.button(
        label="リージョン",
        emoji="🌏",
        style=discord.ButtonStyle.secondary,
        custom_id="region_button",
        row=1,
    )
    async def region_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """リージョンボタン。セレクトメニューを表示する。"""
        await interaction.response.send_message(
            "リージョンを選択:", view=RegionSelectView(), ephemeral=True
        )

    # =========================================================================
    # Row 2: 状態トグル (ロック・非表示・年齢制限)
    # =========================================================================

    @discord.ui.button(
        label="ロック",
        emoji="🔒",
        style=discord.ButtonStyle.secondary,
        custom_id="lock_button",
        row=2,
    )
    async def lock_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """ロック/解除トグルボタン。

        ロック時: @everyone の connect を拒否、オーナーにフル権限を付与
        解除時: @everyone の権限上書きを削除 (デフォルトに戻す)
        """
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel) or not interaction.guild:
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                return

            # トグル: 現在の状態を反転
            # 注意: read → toggle → write は非アトミック操作のため、
            # 理論上は同時押しで lost update が発生しうる。
            # ただし interaction_check でオーナーのみに制限しているため、
            # 実際に同時トグルが起きることはない。
            new_locked_state = not voice_session.is_locked

            if new_locked_state:
                # ロック: @everyone の接続を拒否
                await channel.set_permissions(
                    interaction.guild.default_role, connect=False
                )
                # オーナーにフル権限を付与
                if isinstance(interaction.user, discord.Member):
                    await channel.set_permissions(
                        interaction.user,
                        connect=True,
                        speak=True,
                        stream=True,
                        move_members=True,
                        mute_members=True,
                        deafen_members=True,
                    )
                # ボタンの表示を「解除」に変更
                button.label = "解除"
                button.emoji = "🔓"
            else:
                # 解除: @everyone の権限上書きを削除
                # overwrite=None で上書きごと削除 (デフォルトに戻す)
                await channel.set_permissions(
                    interaction.guild.default_role, overwrite=None
                )
                button.label = "ロック"
                button.emoji = "🔒"

            # DB を更新
            await update_voice_session(
                db_session, voice_session, is_locked=new_locked_state
            )

        status = "ロック" if new_locked_state else "ロック解除"
        # edit_message: ボタンの表示を更新 (ラベル変更を反映)
        await interaction.response.edit_message(view=self)
        # followup.send: edit の後に追加メッセージを送る
        await interaction.followup.send(
            f"チャンネルを **{status}** しました。", ephemeral=True
        )

    @discord.ui.button(
        label="非表示",
        emoji="🙈",
        style=discord.ButtonStyle.secondary,
        custom_id="hide_button",
        row=2,
    )
    async def hide_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """非表示/表示トグルボタン。

        非表示時: @everyone の view_channel を拒否、現在のメンバーには許可
        表示時: @everyone の view_channel 上書きを削除
        """
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel) or not interaction.guild:
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                return

            # 注意: lock ボタンと同様、非アトミックなトグル操作。
            # interaction_check のオーナー制限により実害なし。
            new_hidden_state = not voice_session.is_hidden

            if new_hidden_state:
                # 非表示: @everyone のチャンネル表示を拒否
                await channel.set_permissions(
                    interaction.guild.default_role, view_channel=False
                )
                # 現在チャンネルにいるメンバーには表示を許可
                for member in channel.members:
                    await channel.set_permissions(member, view_channel=True)
                button.label = "表示"
                button.emoji = "👁️"
            else:
                # 表示: view_channel の上書きを削除
                # view_channel=None で「上書きなし」にする (ロールの設定に従う)
                await channel.set_permissions(
                    interaction.guild.default_role, view_channel=None
                )
                button.label = "非表示"
                button.emoji = "🙈"

            await update_voice_session(
                db_session, voice_session, is_hidden=new_hidden_state
            )

        status = "非表示" if new_hidden_state else "表示"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"チャンネルを **{status}** にしました。", ephemeral=True
        )

    @discord.ui.button(
        label="年齢制限",
        emoji="🔞",
        style=discord.ButtonStyle.secondary,
        custom_id="nsfw_button",
        row=2,
    )
    async def nsfw_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """年齢制限 (NSFW) トグルボタン。

        Discord の NSFW フラグをトグルする。
        NSFW チャンネルでは年齢確認が必要になる。
        """
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel):
            return

        # 現在の NSFW 状態を反転
        new_nsfw = not channel.nsfw

        # Discord API で NSFW フラグを変更
        await channel.edit(nsfw=new_nsfw)

        if new_nsfw:
            button.label = "制限解除"
        else:
            button.label = "年齢制限"

        await interaction.response.edit_message(view=self)
        status = "年齢制限を設定" if new_nsfw else "年齢制限を解除"
        await interaction.followup.send(
            f"チャンネルの **{status}** しました。", ephemeral=True
        )

    # =========================================================================
    # Row 3: メンバー管理 (譲渡・キック)
    # =========================================================================

    @discord.ui.button(
        label="譲渡",
        emoji="👑",
        style=discord.ButtonStyle.secondary,
        custom_id="transfer_button",
        row=3,
    )
    async def transfer_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """オーナー譲渡ボタン。メンバー選択セレクトを表示する。"""
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel):
            return

        # 譲渡先候補のセレクトメニューを作成
        view = TransferSelectView(channel, interaction.user.id)
        if not view.children:
            # children が空 = メンバーがいない (セレクトが追加されなかった)
            await interaction.response.send_message(
                "他にメンバーがいません。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "新しいオーナーを選択:", view=view, ephemeral=True
        )

    @discord.ui.button(
        label="キック",
        emoji="👟",
        style=discord.ButtonStyle.secondary,
        custom_id="kick_button",
        row=3,
    )
    async def kick_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """キックボタン。ユーザー選択セレクトを表示する。"""
        await interaction.response.send_message(
            "キックするユーザーを選択:", view=KickSelectView(), ephemeral=True
        )

    # =========================================================================
    # Row 4: メンバー管理 (ブロック・許可)
    # =========================================================================

    @discord.ui.button(
        label="ブロック",
        emoji="🚫",
        style=discord.ButtonStyle.secondary,
        custom_id="block_button",
        row=4,
    )
    async def block_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """ブロックボタン。ユーザー選択セレクトを表示する。"""
        await interaction.response.send_message(
            "ブロックするユーザーを選択:", view=BlockSelectView(), ephemeral=True
        )

    @discord.ui.button(
        label="許可",
        emoji="✅",
        style=discord.ButtonStyle.secondary,
        custom_id="allow_button",
        row=4,
    )
    async def allow_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """許可ボタン。ユーザー選択セレクトを表示する。"""
        await interaction.response.send_message(
            "許可するユーザーを選択:", view=AllowSelectView(), ephemeral=True
        )
