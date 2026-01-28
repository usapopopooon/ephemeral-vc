"""SQLAlchemy database models.

データベースのテーブル構造を Python クラスで定義する。
SQLAlchemy の ORM (Object Relational Mapper) を使い、
Python オブジェクトとしてデータベースの行を操作できる。

テーブル構成:
  - lobbies: ロビーVC の設定 (どのチャンネルがロビーか)
  - voice_sessions: 現在アクティブな一時 VC のセッション情報
  - voice_session_members: 一時 VC の参加メンバー
  - bump_reminders: bump リマインダー
  - bump_configs: bump 監視の設定 (ギルドごと)
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """全モデルの基底クラス。

    SQLAlchemy の DeclarativeBase を継承する。
    全てのテーブルクラスはこの Base を継承することで、
    SQLAlchemy に「これはテーブル定義だよ」と認識される。
    """

    pass


class Lobby(Base):
    """ロビーVC の設定テーブル。

    ロビーVC = ユーザーが参加すると一時 VC が自動作成されるチャンネル。
    1つのサーバー (guild) に複数のロビーを設定できる。

    テーブル名: lobbies
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

    テーブル名: voice_sessions
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

    テーブル名: voice_session_members
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

    テーブル名: bump_reminders
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

    テーブル名: bump_configs
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
        return (
            f"<BumpConfig(guild_id={self.guild_id}, channel_id={self.channel_id})>"
        )
