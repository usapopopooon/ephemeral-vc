"""SQLAlchemy database models.

データベースのテーブル構造を Python クラスで定義する。
SQLAlchemy の ORM (Object Relational Mapper) を使い、
Python オブジェクトとしてデータベースの行を操作できる。

テーブル構成:
    - admin_users: Web 管理画面のログインユーザー
    - lobbies: ロビーVC の設定 (どのチャンネルがロビーか)
    - voice_sessions: 現在アクティブな一時 VC のセッション情報
    - voice_session_members: 一時 VC の参加メンバー
    - bump_reminders: bump リマインダー
    - bump_configs: bump 監視の設定 (ギルドごと)
    - sticky_messages: sticky メッセージの設定 (チャンネルごと)

Examples:
    モデルの使用例::

        from src.database.models import Lobby, VoiceSession

        # ロビーを作成
        lobby = Lobby(
            guild_id="123456789",
            lobby_channel_id="987654321",
        )

        # セッションを作成
        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="111222333",
            owner_id="444555666",
            name="ゲーム部屋",
        )

See Also:
    - :mod:`src.services.db_service`: CRUD 操作関数
    - :mod:`src.database.engine`: データベース接続設定
    - SQLAlchemy ORM: https://docs.sqlalchemy.org/en/20/orm/
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """全モデルの基底クラス。

    SQLAlchemy の DeclarativeBase を継承する。全てのテーブルクラスは
    この Base を継承することで、SQLAlchemy に「これはテーブル定義だよ」
    と認識される。

    Notes:
        - この Base.metadata を使用してテーブルを作成・削除する
        - Alembic マイグレーションもこの Base を参照する

    Examples:
        モデルクラスの定義::

            class MyTable(Base):
                __tablename__ = "my_table"

                id: Mapped[int] = mapped_column(Integer, primary_key=True)
                name: Mapped[str] = mapped_column(String, nullable=False)

    See Also:
        - :func:`src.database.engine.init_db`: テーブル初期化関数
        - SQLAlchemy DeclarativeBase: https://docs.sqlalchemy.org/en/20/orm/mapping_api.html
    """

    pass


class AdminUser(Base):
    """Web 管理画面のログインユーザーテーブル。

    管理画面へのログインに使用する認証情報を保存する。
    パスワードは bcrypt でハッシュ化して保存する。

    Attributes:
        id (int): 自動採番の主キー。
        email (str): ログイン用メールアドレス (ユニーク)。
        password_hash (str): bcrypt でハッシュ化されたパスワード。
        created_at (datetime): ユーザー作成日時 (UTC)。
        updated_at (datetime): 最終更新日時 (UTC)。
        password_changed_at (datetime | None): パスワード変更日時。
            None なら初期パスワードのまま。
        reset_token (str | None): パスワードリセット用トークン。
        reset_token_expires_at (datetime | None): リセットトークンの有効期限。
        pending_email (str | None): 確認待ちの新しいメールアドレス。
        email_change_token (str | None): メールアドレス変更確認用トークン。
        email_change_token_expires_at (datetime | None): メール変更トークンの有効期限。
        email_verified (bool): メールアドレスが確認済みかどうか。

    Notes:
        - テーブル名: ``admin_users``
        - email はユニーク制約あり
        - パスワードは平文で保存せず、必ずハッシュ化する

    Examples:
        新規ユーザー作成::

            import bcrypt

            user = AdminUser(
                email="admin@example.com",
                password_hash=bcrypt.hashpw(b"password", bcrypt.gensalt()).decode(),
            )

    See Also:
        - :mod:`src.web.auth`: 認証ロジック
    """

    __tablename__ = "admin_users"

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # email: ログイン用メールアドレス (ユニーク)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    # password_hash: bcrypt でハッシュ化されたパスワード
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    # created_at: ユーザー作成日時 (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # updated_at: 最終更新日時 (UTC)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # password_changed_at: パスワード変更日時 (None なら初期パスワードのまま)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # reset_token: パスワードリセット用トークン
    reset_token: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    # reset_token_expires_at: リセットトークンの有効期限
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # pending_email: 確認待ちの新しいメールアドレス
    pending_email: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )

    # email_change_token: メールアドレス変更確認用トークン
    email_change_token: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )

    # email_change_token_expires_at: メール変更トークンの有効期限
    email_change_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # email_verified: メールアドレスが確認済みかどうか (初回セットアップ用)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return f"<AdminUser(id={self.id}, email={self.email})>"


class Lobby(Base):
    """ロビーVC の設定テーブル。

    ロビーVC = ユーザーが参加すると一時 VC が自動作成されるチャンネル。
    1つのサーバー (guild) に複数のロビーを設定できる。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        lobby_channel_id (str): ロビーとして使う VC の ID。
            ユニーク制約あり。
        category_id (str | None): 作成された一時 VC を配置するカテゴリの ID。
            None の場合はロビーと同じカテゴリに配置。
        default_user_limit (int): 一時 VC のデフォルト人数制限。0 = 無制限。
        sessions (list[VoiceSession]): このロビーから作成された VC セッション一覧。

    Notes:
        - テーブル名: ``lobbies``
        - lobby_channel_id はユニーク (同じチャンネルを重複登録不可)
        - sessions はカスケード削除設定 (ロビー削除時にセッションも削除)

    Examples:
        ロビー作成::

            lobby = Lobby(
                guild_id="123456789",
                lobby_channel_id="987654321",
                default_user_limit=10,
            )

    See Also:
        - :class:`VoiceSession`: 一時 VC セッション
        - :func:`src.services.db_service.create_lobby`: ロビー作成関数
    """

    __tablename__ = "lobbies"

    # id: 自動採番の主キー。SQLAlchemy が自動で管理する
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # guild_id: Discord サーバーの ID。index=True で検索を高速化
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # lobby_channel_id: ロビーとして使う VC の ID。
    # unique=True で同じチャンネルを重複登録できないようにする
    lobby_channel_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )

    # category_id: 作成された一時 VC を配置するカテゴリの ID (任意)
    # None の場合はロビーと同じカテゴリに配置される
    category_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # default_user_limit: 一時 VC のデフォルト人数制限。0 = 無制限
    default_user_limit: Mapped[int] = mapped_column(Integer, default=0)

    # --- リレーション ---
    # このロビーから作成された VoiceSession の一覧。
    # cascade="all, delete-orphan" → ロビーを削除すると関連セッションも削除される
    sessions: Mapped[list["VoiceSession"]] = relationship(
        "VoiceSession", back_populates="lobby", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。print() や logger で表示される。"""
        return (
            f"<Lobby(id={self.id}, guild_id={self.guild_id}, "
            f"channel_id={self.lobby_channel_id})>"
        )


class VoiceSession(Base):
    """現在アクティブな一時 VC のセッション情報テーブル。

    ユーザーがロビーに参加するとレコードが作成され、
    全員が退出するとレコードが削除される。
    ロック状態や非表示状態などの設定もここに保存する。

    Attributes:
        id (int): 自動採番の主キー。
        lobby_id (int): 親ロビーへの外部キー。
        channel_id (str): 作成された一時 VC の Discord チャンネル ID。
            ユニーク制約あり。
        owner_id (str): チャンネルオーナーの Discord ユーザー ID。
        name (str): チャンネル名。
        user_limit (int): VC の人数制限。0 = 無制限。
        is_locked (bool): True ならチャンネルがロック (@everyone の接続拒否)。
        is_hidden (bool): True ならチャンネルが非表示 (@everyone のチャンネル表示拒否)。
        created_at (datetime): レコード作成日時 (UTC)。
        lobby (Lobby): この VC セッションが属する親ロビー。

    Notes:
        - テーブル名: ``voice_sessions``
        - channel_id はユニーク (同じチャンネルの重複レコード防止)
        - オーナーだけがコントロールパネルを操作可能
        - 全員退出時に自動削除される

    Examples:
        セッション作成::

            session = VoiceSession(
                lobby_id=1,
                channel_id="111222333",
                owner_id="444555666",
                name="ゲーム部屋",
                user_limit=5,
            )

    See Also:
        - :class:`Lobby`: 親ロビー
        - :class:`VoiceSessionMember`: 参加メンバー
        - :func:`src.services.db_service.create_voice_session`: 作成関数
    """

    __tablename__ = "voice_sessions"

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # lobby_id: 親ロビーへの外部キー。
    # ForeignKey("lobbies.id") で lobbies テーブルの id カラムを参照
    lobby_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lobbies.id"), nullable=False
    )

    # channel_id: 作成された一時 VC の Discord チャンネル ID
    # unique=True で同じチャンネルの重複レコードを防ぐ
    channel_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )

    # owner_id: チャンネルオーナーの Discord ユーザー ID
    # オーナーだけがコントロールパネルを操作できる
    owner_id: Mapped[str] = mapped_column(String, nullable=False)

    # name: チャンネル名 (例: "ユーザー名's channel")
    name: Mapped[str] = mapped_column(String, nullable=False)

    # user_limit: VC の人数制限。0 = 無制限
    user_limit: Mapped[int] = mapped_column(Integer, default=0)

    # is_locked: True ならチャンネルがロックされている (@everyone の接続を拒否)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    # is_hidden: True ならチャンネルが非表示 (@everyone のチャンネル表示を拒否)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    # created_at: レコード作成日時 (UTC)。自動で現在時刻がセットされる
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # --- リレーション ---
    # この VC セッションが属する親ロビー。lobby.sessions の逆方向
    lobby: Mapped["Lobby"] = relationship("Lobby", back_populates="sessions")

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<VoiceSession(id={self.id}, channel_id={self.channel_id}, "
            f"owner_id={self.owner_id})>"
        )


class VoiceSessionMember(Base):
    """一時 VC に参加しているメンバーの情報テーブル。

    各メンバーの参加時刻を記録し、オーナー引き継ぎ時の優先順位を決定する。
    Bot 再起動後も参加順序が保持される。

    Attributes:
        id (int): 自動採番の主キー。
        voice_session_id (int): 親 VoiceSession への外部キー。
            カスケード削除設定。
        user_id (str): メンバーの Discord ユーザー ID。インデックス付き。
        joined_at (datetime): メンバーがこの VC に参加した日時 (UTC)。

    Notes:
        - テーブル名: ``voice_session_members``
        - (voice_session_id, user_id) でユニーク制約
        - オーナー退出時、最も古い joined_at のメンバーが次のオーナーになる
        - VoiceSession 削除時に自動削除 (CASCADE)

    Examples:
        メンバー追加::

            member = VoiceSessionMember(
                voice_session_id=1,
                user_id="123456789",
            )

    See Also:
        - :class:`VoiceSession`: 親セッション
        - :func:`src.services.db_service.add_voice_session_member`: 追加関数
        - :func:`src.services.db_service.get_voice_session_members_ordered`: 参加順取得
    """

    __tablename__ = "voice_session_members"
    __table_args__ = (
        # 同じ VC セッションに同じユーザーは 1 回だけ
        UniqueConstraint("voice_session_id", "user_id", name="uq_session_user"),
    )

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # voice_session_id: 親 VoiceSession への外部キー
    voice_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("voice_sessions.id", ondelete="CASCADE"), nullable=False
    )

    # user_id: メンバーの Discord ユーザー ID
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # joined_at: メンバーがこの VC に参加した日時 (UTC)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<VoiceSessionMember(id={self.id}, session_id={self.voice_session_id}, "
            f"user_id={self.user_id}, joined_at={self.joined_at})>"
        )


class BumpReminder(Base):
    """bump リマインダーテーブル。

    DISBOARD/ディス速報の bump 後、2時間後にリマインドを送信するための情報を保存。
    同じサーバー・サービスの組み合わせで1件のみ保持 (上書き更新)。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        channel_id (str): bump 通知を送信するチャンネルの ID。
        service_name (str): サービス名 ("DISBOARD" または "ディス速報")。
        remind_at (datetime | None): リマインドを送信する予定時刻 (UTC)。
            None なら未設定。
        is_enabled (bool): 通知が有効かどうか (デフォルト True)。
        role_id (str | None): 通知先ロールの ID。
            None の場合は "Server Bumper" ロールを自動検索。

    Notes:
        - テーブル名: ``bump_reminders``
        - (guild_id, service_name) でユニーク制約
        - bump 検知後、remind_at に 2時間後を設定
        - リマインド送信後、remind_at は None にリセット

    Examples:
        リマインダー作成::

            from datetime import UTC, datetime, timedelta

            reminder = BumpReminder(
                guild_id="123456789",
                channel_id="987654321",
                service_name="DISBOARD",
                remind_at=datetime.now(UTC) + timedelta(hours=2),
            )

    See Also:
        - :class:`BumpConfig`: bump 監視設定
        - :func:`src.services.db_service.upsert_bump_reminder`: 作成/更新関数
        - :mod:`src.cogs.bump`: bump 検知 Cog
    """

    __tablename__ = "bump_reminders"
    __table_args__ = (
        # 同じ guild + service の組み合わせは 1 件のみ
        UniqueConstraint("guild_id", "service_name", name="uq_guild_service"),
    )

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # guild_id: Discord サーバーの ID
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # channel_id: bump 通知を送信するチャンネルの ID
    channel_id: Mapped[str] = mapped_column(String, nullable=False)

    # service_name: サービス名 ("DISBOARD" または "ディス速報")
    service_name: Mapped[str] = mapped_column(String, nullable=False)

    # remind_at: リマインドを送信する予定時刻 (UTC)、None なら未設定
    remind_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # is_enabled: 通知が有効かどうか (デフォルト True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # role_id: 通知先ロールの ID (None の場合はデフォルトの "Server Bumper" ロール)
    role_id: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<BumpReminder(id={self.id}, guild_id={self.guild_id}, "
            f"service={self.service_name}, remind_at={self.remind_at}, "
            f"is_enabled={self.is_enabled}, role_id={self.role_id})>"
        )


class BumpConfig(Base):
    """bump 監視の設定テーブル。

    ギルドごとに bump を監視するチャンネルを設定する。
    管理者が /bump setup コマンドで設定する。

    Attributes:
        guild_id (str): Discord サーバーの ID (主キー、1ギルド1設定)。
        channel_id (str): bump を監視するチャンネルの ID。
            リマインドもここに送信する。
        created_at (datetime): 設定作成日時 (UTC)。

    Notes:
        - テーブル名: ``bump_configs``
        - guild_id が主キー (1ギルドにつき1設定のみ)
        - /bump setup で設定、/bump disable で削除

    Examples:
        設定作成::

            config = BumpConfig(
                guild_id="123456789",
                channel_id="987654321",
            )

    See Also:
        - :class:`BumpReminder`: 個別のリマインダー
        - :func:`src.services.db_service.upsert_bump_config`: 作成/更新関数
    """

    __tablename__ = "bump_configs"

    # guild_id: Discord サーバーの ID (主キー、1ギルド1設定)
    guild_id: Mapped[str] = mapped_column(String, primary_key=True)

    # channel_id: bump を監視するチャンネルの ID (リマインドもここに送信)
    channel_id: Mapped[str] = mapped_column(String, nullable=False)

    # created_at: 設定作成日時 (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return f"<BumpConfig(guild_id={self.guild_id}, channel_id={self.channel_id})>"


class StickyMessage(Base):
    """sticky メッセージの設定テーブル。

    チャンネルごとに常に最新位置に表示される embed メッセージを設定する。
    新しいメッセージが投稿されると、古い sticky を削除して再投稿する。

    Attributes:
        channel_id (str): チャンネルの ID (主キー、1チャンネル1設定)。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        message_id (str | None): 現在投稿されている sticky メッセージの ID。
            削除時に使用。
        message_type (str): メッセージの種類 ("embed" または "text")。
        title (str): embed のタイトル (text の場合は空文字)。
        description (str): embed の説明文。
        color (int | None): embed の色 (16進数の整数値、例: 0x00FF00)。
        cooldown_seconds (int): 再投稿までの最小間隔 (秒)。
        last_posted_at (datetime | None): 最後に sticky を投稿した日時。
            cooldown 計算用。
        created_at (datetime): 設定作成日時 (UTC)。

    Notes:
        - テーブル名: ``sticky_messages``
        - channel_id が主キー (1チャンネルにつき1設定のみ)
        - cooldown でスパム防止 (短時間での連続再投稿を防ぐ)
        - message_type で embed/text の切り替えが可能

    Examples:
        sticky メッセージ作成::

            sticky = StickyMessage(
                channel_id="123456789",
                guild_id="987654321",
                title="ルール",
                description="このチャンネルのルールです。",
                color=0x00FF00,
                cooldown_seconds=10,
            )

    See Also:
        - :func:`src.services.db_service.create_sticky_message`: 作成関数
        - :mod:`src.cogs.sticky`: sticky メッセージ Cog
    """

    __tablename__ = "sticky_messages"

    # channel_id: チャンネルの ID (主キー、1チャンネル1設定)
    channel_id: Mapped[str] = mapped_column(String, primary_key=True)

    # guild_id: Discord サーバーの ID
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # message_id: 現在投稿されている sticky メッセージの ID (削除用)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # message_type: メッセージの種類 ("embed" または "text")
    message_type: Mapped[str] = mapped_column(String, default="embed", nullable=False)

    # title: embed のタイトル (text の場合は空文字)
    title: Mapped[str] = mapped_column(String, nullable=False)

    # description: embed の説明文
    description: Mapped[str] = mapped_column(String, nullable=False)

    # color: embed の色 (16進数の整数値、例: 0x00FF00)
    color: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # cooldown_seconds: 再投稿までの最小間隔 (秒)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # last_posted_at: 最後に sticky を投稿した日時 (cooldown 計算用)
    last_posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # created_at: 設定作成日時 (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<StickyMessage(channel_id={self.channel_id}, "
            f"guild_id={self.guild_id}, title={self.title})>"
        )


class RolePanel(Base):
    """ロールパネルの設定テーブル。

    ボタンまたはリアクションをクリックしてロールを付与/解除できるパネル。
    1つのパネルに複数のロールボタン/リアクションを設定可能。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        channel_id (str): パネルを送信したチャンネルの ID。
        message_id (str | None): パネルメッセージの ID。
        panel_type (str): パネルの種類 ("button" または "reaction")。
        title (str): パネルのタイトル。
        description (str | None): パネルの説明文。
        color (int | None): Embed の色 (16進数の整数値)。
        remove_reaction (bool): リアクション自動削除フラグ (リアクション式のみ)。
            True の場合、ユーザーがリアクションするとロールをトグルし、
            リアクションを自動削除してカウントを 1 に保つ。
        created_at (datetime): 作成日時 (UTC)。
        items (list[RolePanelItem]): このパネルに設定されたロール一覧。

    Notes:
        - テーブル名: ``role_panels``
        - panel_type で動作が切り替わる (ボタン式/リアクション式)
        - items はカスケード削除設定 (パネル削除時にアイテムも削除)
        - remove_reaction=True: リアクション追加でトグル、リアクション自動削除
        - remove_reaction=False: リアクション追加で付与、削除で解除 (通常動作)

    Examples:
        パネル作成::

            panel = RolePanel(
                guild_id="123456789",
                channel_id="987654321",
                panel_type="button",
                title="ロール選択",
                description="好きなロールを選んでください",
            )

    See Also:
        - :class:`RolePanelItem`: パネルに設定されたロール
        - :mod:`src.cogs.role_panel`: ロールパネル Cog
    """

    __tablename__ = "role_panels"

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # guild_id: Discord サーバーの ID
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # channel_id: パネルを送信したチャンネルの ID
    channel_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # message_id: パネルメッセージの ID (送信後に設定)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # panel_type: パネルの種類 ("button" または "reaction")
    panel_type: Mapped[str] = mapped_column(String, nullable=False)

    # title: パネルのタイトル
    title: Mapped[str] = mapped_column(String, nullable=False)

    # description: パネルの説明文
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # color: Embed の色 (16進数の整数値)
    color: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # remove_reaction: リアクション自動削除フラグ
    # True: リアクション追加でトグル、リアクション自動削除 (カウント常に 1)
    # False: リアクション追加で付与、削除で解除 (通常動作)
    remove_reaction: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # created_at: 作成日時 (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # --- リレーション ---
    # このパネルに設定されたロール一覧
    items: Mapped[list["RolePanelItem"]] = relationship(
        "RolePanelItem", back_populates="panel", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<RolePanel(id={self.id}, guild_id={self.guild_id}, "
            f"title={self.title}, type={self.panel_type})>"
        )


class RolePanelItem(Base):
    """ロールパネルに設定されたロールのテーブル。

    パネルに追加された各ロールの設定を保存する。
    ボタン式の場合はラベルとスタイル、リアクション式の場合は絵文字を使用。

    Attributes:
        id (int): 自動採番の主キー。
        panel_id (int): 親パネルへの外部キー。カスケード削除設定。
        role_id (str): 付与するロールの Discord ID。
        emoji (str): ボタン/リアクションに使用する絵文字。
        label (str | None): ボタンのラベル (ボタン式のみ)。
        style (str): ボタンのスタイル ("primary", "secondary", "success", "danger")。
        position (int): 表示順序。

    Notes:
        - テーブル名: ``role_panel_items``
        - (panel_id, emoji) でユニーク制約 (同じ絵文字の重複防止)
        - RolePanel 削除時に自動削除 (CASCADE)

    Examples:
        ロール追加::

            item = RolePanelItem(
                panel_id=1,
                role_id="111222333",
                emoji="🎮",
                label="ゲーマー",
                style="primary",
                position=0,
            )

    See Also:
        - :class:`RolePanel`: 親パネル
        - :func:`src.services.db_service.add_role_panel_item`: 追加関数
    """

    __tablename__ = "role_panel_items"
    __table_args__ = (
        # 同じパネルに同じ絵文字は 1 回だけ
        UniqueConstraint("panel_id", "emoji", name="uq_panel_emoji"),
    )

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # panel_id: 親パネルへの外部キー
    panel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("role_panels.id", ondelete="CASCADE"), nullable=False
    )

    # role_id: 付与するロールの Discord ID
    role_id: Mapped[str] = mapped_column(String, nullable=False)

    # emoji: ボタン/リアクションに使用する絵文字
    emoji: Mapped[str] = mapped_column(String, nullable=False)

    # label: ボタンのラベル (ボタン式のみ、リアクション式は None)
    label: Mapped[str | None] = mapped_column(String, nullable=True)

    # style: ボタンのスタイル (ボタン式のみ)
    style: Mapped[str] = mapped_column(String, default="secondary", nullable=False)

    # position: 表示順序
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- リレーション ---
    # このアイテムが属する親パネル
    panel: Mapped["RolePanel"] = relationship("RolePanel", back_populates="items")

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<RolePanelItem(id={self.id}, panel_id={self.panel_id}, "
            f"role_id={self.role_id}, emoji={self.emoji})>"
        )
