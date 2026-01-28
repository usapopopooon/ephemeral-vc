"""Database service functions with side effects.

データベースの CRUD (Create, Read, Update, Delete) 操作を提供する。
各関数は AsyncSession を受け取り、SQL クエリを実行する。

使い方:
    async with async_session() as session:
        lobby = await get_lobby_by_channel_id(session, "123456")
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    BumpConfig,
    BumpReminder,
    Lobby,
    VoiceSession,
    VoiceSessionMember,
)

# =============================================================================
# Lobby (ロビー) 操作
# =============================================================================


async def get_lobby_by_channel_id(
    session: AsyncSession, channel_id: str
) -> Lobby | None:
    """チャンネル ID からロビーを取得する。

    ユーザーが VC に参加したとき、そのチャンネルがロビーかどうかを
    判定するために使う。

    Args:
        session: DB セッション
        channel_id: 調べたい Discord チャンネルの ID (文字列)

    Returns:
        ロビーが見つかれば Lobby オブジェクト、なければ None
    """
    # select(Lobby) → SELECT * FROM lobbies
    # .where(...) → WHERE lobby_channel_id = :channel_id
    result = await session.execute(
        select(Lobby).where(Lobby.lobby_channel_id == channel_id)
    )
    # scalar_one_or_none: 結果が1行なら返す、0行なら None、2行以上ならエラー
    return result.scalar_one_or_none()


async def get_lobbies_by_guild(session: AsyncSession, guild_id: str) -> list[Lobby]:
    """サーバー (guild) に属する全ロビーを取得する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        ロビーのリスト (0件なら空リスト)
    """
    result = await session.execute(select(Lobby).where(Lobby.guild_id == guild_id))
    # scalars().all() で全行を取得し、list() でリストに変換
    return list(result.scalars().all())


async def create_lobby(
    session: AsyncSession,
    guild_id: str,
    lobby_channel_id: str,
    category_id: str | None = None,
    default_user_limit: int = 0,
) -> Lobby:
    """新しいロビーを DB に登録する。

    /lobby コマンドで VC を作成した後に呼ばれる。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        lobby_channel_id: ロビーとして登録する VC の ID
        category_id: 一時 VC を配置するカテゴリの ID (None なら同カテゴリ)
        default_user_limit: デフォルトの人数制限 (0 = 無制限)

    Returns:
        作成された Lobby オブジェクト (id が自動採番される)
    """
    lobby = Lobby(
        guild_id=guild_id,
        lobby_channel_id=lobby_channel_id,
        category_id=category_id,
        default_user_limit=default_user_limit,
    )
    # session.add(): セッションにオブジェクトを追加 (INSERT 予約)
    session.add(lobby)
    # commit(): 実際に DB に書き込む (INSERT 実行)
    await session.commit()
    # refresh(): DB から最新の値を読み直す (自動採番された id を取得)
    await session.refresh(lobby)
    return lobby


async def delete_lobby(session: AsyncSession, lobby_id: int) -> bool:
    """ロビーを削除する。

    Args:
        session: DB セッション
        lobby_id: 削除するロビーの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(select(Lobby).where(Lobby.id == lobby_id))
    lobby = result.scalar_one_or_none()
    if lobby:
        # session.delete() + commit() で DELETE 文を実行
        await session.delete(lobby)
        await session.commit()
        return True
    return False


# =============================================================================
# VoiceSession (一時 VC セッション) 操作
# =============================================================================


async def get_voice_session(
    session: AsyncSession, channel_id: str
) -> VoiceSession | None:
    """チャンネル ID から VC セッションを取得する。

    チャンネルが一時 VC かどうかの判定や、オーナー情報の取得に使う。

    Args:
        session: DB セッション
        channel_id: Discord VC のチャンネル ID

    Returns:
        セッションが見つかれば VoiceSession、なければ None
    """
    result = await session.execute(
        select(VoiceSession).where(VoiceSession.channel_id == channel_id)
    )
    return result.scalar_one_or_none()


async def get_all_voice_sessions(session: AsyncSession) -> list[VoiceSession]:
    """全てのアクティブな VC セッションを取得する。

    Bot 起動時に永続 View を復元するために使う。

    Args:
        session: DB セッション

    Returns:
        全 VoiceSession のリスト
    """
    result = await session.execute(select(VoiceSession))
    return list(result.scalars().all())


async def create_voice_session(
    session: AsyncSession,
    lobby_id: int,
    channel_id: str,
    owner_id: str,
    name: str,
    user_limit: int = 0,
) -> VoiceSession:
    """新しい VC セッションを DB に登録する。

    ユーザーがロビーに参加し、一時 VC が作成された直後に呼ばれる。

    Args:
        session: DB セッション
        lobby_id: 親ロビーの ID
        channel_id: 作成された一時 VC の ID
        owner_id: チャンネルオーナーの Discord ユーザー ID
        name: チャンネル名
        user_limit: 人数制限 (0 = 無制限)

    Returns:
        作成された VoiceSession オブジェクト
    """
    voice_session = VoiceSession(
        lobby_id=lobby_id,
        channel_id=channel_id,
        owner_id=owner_id,
        name=name,
        user_limit=user_limit,
    )
    session.add(voice_session)
    await session.commit()
    await session.refresh(voice_session)
    return voice_session


async def update_voice_session(
    session: AsyncSession,
    voice_session: VoiceSession,
    *,
    name: str | None = None,
    user_limit: int | None = None,
    is_locked: bool | None = None,
    is_hidden: bool | None = None,
    owner_id: str | None = None,
) -> VoiceSession:
    """VC セッションの情報を更新する。

    コントロールパネルのボタン操作 (名前変更、ロック、非表示、オーナー譲渡)
    で呼ばれる。None のフィールドは変更しない。

    Args:
        session: DB セッション
        voice_session: 更新対象の VoiceSession オブジェクト
        name: 新しいチャンネル名 (None なら変更しない)
        user_limit: 新しい人数制限 (None なら変更しない)
        is_locked: 新しいロック状態 (None なら変更しない)
        is_hidden: 新しい非表示状態 (None なら変更しない)
        owner_id: 新しいオーナー ID (None なら変更しない)

    Returns:
        更新後の VoiceSession オブジェクト
    """
    # None でないフィールドだけ更新する (部分更新パターン)
    if name is not None:
        voice_session.name = name
    if user_limit is not None:
        voice_session.user_limit = user_limit
    if is_locked is not None:
        voice_session.is_locked = is_locked
    if is_hidden is not None:
        voice_session.is_hidden = is_hidden
    if owner_id is not None:
        voice_session.owner_id = owner_id

    # SQLAlchemy はオブジェクトの変更を自動検知するので、
    # commit() だけで UPDATE 文が実行される
    await session.commit()
    await session.refresh(voice_session)
    return voice_session


async def delete_voice_session(session: AsyncSession, channel_id: str) -> bool:
    """VC セッションを削除する。

    一時 VC から全員が退出したとき、チャンネル削除と一緒に呼ばれる。

    Args:
        session: DB セッション
        channel_id: 削除する VC のチャンネル ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(
        select(VoiceSession).where(VoiceSession.channel_id == channel_id)
    )
    voice_session = result.scalar_one_or_none()
    if voice_session:
        await session.delete(voice_session)
        await session.commit()
        return True
    return False


# =============================================================================
# VoiceSessionMember (VC メンバー) 操作
# =============================================================================


async def add_voice_session_member(
    session: AsyncSession,
    voice_session_id: int,
    user_id: str,
) -> VoiceSessionMember:
    """VC セッションにメンバーを追加する。

    ユーザーが一時 VC に参加したときに呼ばれる。
    既に存在する場合は既存のレコードを返す (参加時刻は更新しない)。

    Args:
        session: DB セッション
        voice_session_id: VC セッションの ID
        user_id: メンバーの Discord ユーザー ID

    Returns:
        作成または既存の VoiceSessionMember オブジェクト
    """
    # 既存のレコードがあるか確認
    result = await session.execute(
        select(VoiceSessionMember).where(
            VoiceSessionMember.voice_session_id == voice_session_id,
            VoiceSessionMember.user_id == user_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # 新規作成
    member = VoiceSessionMember(
        voice_session_id=voice_session_id,
        user_id=user_id,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def remove_voice_session_member(
    session: AsyncSession,
    voice_session_id: int,
    user_id: str,
) -> bool:
    """VC セッションからメンバーを削除する。

    ユーザーが一時 VC から退出したときに呼ばれる。

    Args:
        session: DB セッション
        voice_session_id: VC セッションの ID
        user_id: メンバーの Discord ユーザー ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(
        select(VoiceSessionMember).where(
            VoiceSessionMember.voice_session_id == voice_session_id,
            VoiceSessionMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member:
        await session.delete(member)
        await session.commit()
        return True
    return False


async def get_voice_session_members_ordered(
    session: AsyncSession,
    voice_session_id: int,
) -> list[VoiceSessionMember]:
    """VC セッションのメンバーを参加順 (古い順) で取得する。

    オーナー引き継ぎ時の優先順位を決定するために使う。

    Args:
        session: DB セッション
        voice_session_id: VC セッションの ID

    Returns:
        参加時刻が古い順にソートされた VoiceSessionMember のリスト
    """
    result = await session.execute(
        select(VoiceSessionMember)
        .where(VoiceSessionMember.voice_session_id == voice_session_id)
        .order_by(VoiceSessionMember.joined_at, VoiceSessionMember.user_id)
    )
    return list(result.scalars().all())


# =============================================================================
# BumpReminder (bump リマインダー) 操作
# =============================================================================


async def upsert_bump_reminder(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
    service_name: str,
    remind_at: datetime,
) -> BumpReminder:
    """bump リマインダーを作成または更新する。

    同じ guild_id + service_name の組み合わせが既に存在する場合は上書きする。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        channel_id: リマインド通知を送信するチャンネルの ID
        service_name: サービス名 ("DISBOARD" または "ディス速報")
        remind_at: リマインドを送信する予定時刻 (UTC)

    Returns:
        作成または更新された BumpReminder オブジェクト
    """
    # 既存のレコードを検索
    result = await session.execute(
        select(BumpReminder).where(
            BumpReminder.guild_id == guild_id,
            BumpReminder.service_name == service_name,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # 既存レコードを更新
        existing.channel_id = channel_id
        existing.remind_at = remind_at
        await session.commit()
        await session.refresh(existing)
        return existing

    # 新規作成
    reminder = BumpReminder(
        guild_id=guild_id,
        channel_id=channel_id,
        service_name=service_name,
        remind_at=remind_at,
    )
    session.add(reminder)
    await session.commit()
    await session.refresh(reminder)
    return reminder


async def get_due_bump_reminders(
    session: AsyncSession,
    now: datetime,
) -> list[BumpReminder]:
    """送信予定時刻を過ぎた有効な bump リマインダーを取得する。

    Args:
        session: DB セッション
        now: 現在時刻 (UTC)

    Returns:
        remind_at <= now かつ is_enabled = True の BumpReminder のリスト
    """
    result = await session.execute(
        select(BumpReminder).where(
            BumpReminder.remind_at <= now,
            BumpReminder.remind_at.isnot(None),
            BumpReminder.is_enabled.is_(True),
        )
    )
    return list(result.scalars().all())


async def clear_bump_reminder(session: AsyncSession, reminder_id: int) -> bool:
    """bump リマインダーの remind_at をクリアする。

    リマインド送信後に呼ばれる。レコードは削除せず、remind_at を None にする。

    Args:
        session: DB セッション
        reminder_id: クリアするリマインダーの ID

    Returns:
        クリアできたら True、見つからなければ False
    """
    result = await session.execute(
        select(BumpReminder).where(BumpReminder.id == reminder_id)
    )
    reminder = result.scalar_one_or_none()
    if reminder:
        reminder.remind_at = None
        await session.commit()
        return True
    return False


async def get_bump_reminder(
    session: AsyncSession,
    guild_id: str,
    service_name: str,
) -> BumpReminder | None:
    """guild_id と service_name で bump リマインダーを取得する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        service_name: サービス名 ("DISBOARD" または "ディス速報")

    Returns:
        見つかった BumpReminder、なければ None
    """
    result = await session.execute(
        select(BumpReminder).where(
            BumpReminder.guild_id == guild_id,
            BumpReminder.service_name == service_name,
        )
    )
    return result.scalar_one_or_none()


async def toggle_bump_reminder(
    session: AsyncSession,
    guild_id: str,
    service_name: str,
) -> bool:
    """bump リマインダーの有効/無効を切り替える。

    レコードが存在しない場合は無効状態で新規作成する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        service_name: サービス名 ("DISBOARD" または "ディス速報")

    Returns:
        切り替え後の is_enabled 値
    """
    reminder = await get_bump_reminder(session, guild_id, service_name)

    if reminder:
        reminder.is_enabled = not reminder.is_enabled
        await session.commit()
        return reminder.is_enabled

    # レコードがない場合は無効状態で新規作成
    new_reminder = BumpReminder(
        guild_id=guild_id,
        channel_id="",  # 通知先は bump 検知時に設定される
        service_name=service_name,
        remind_at=None,
        is_enabled=False,
    )
    session.add(new_reminder)
    await session.commit()
    return False


async def update_bump_reminder_role(
    session: AsyncSession,
    guild_id: str,
    service_name: str,
    role_id: str | None,
) -> bool:
    """bump リマインダーの通知ロールを更新する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        service_name: サービス名 ("DISBOARD" または "ディス速報")
        role_id: 新しい通知ロールの ID (None ならデフォルトロールに戻す)

    Returns:
        更新できたら True、レコードが見つからなければ False
    """
    reminder = await get_bump_reminder(session, guild_id, service_name)

    if reminder:
        reminder.role_id = role_id
        await session.commit()
        return True

    return False


# =============================================================================
# BumpConfig (bump 監視設定) 操作
# =============================================================================


async def get_bump_config(
    session: AsyncSession,
    guild_id: str,
) -> BumpConfig | None:
    """ギルドの bump 監視設定を取得する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        見つかった BumpConfig、なければ None
    """
    result = await session.execute(
        select(BumpConfig).where(BumpConfig.guild_id == guild_id)
    )
    return result.scalar_one_or_none()


async def upsert_bump_config(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
) -> BumpConfig:
    """bump 監視設定を作成または更新する。

    既に設定がある場合はチャンネル ID を上書きする。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        channel_id: bump を監視するチャンネルの ID

    Returns:
        作成または更新された BumpConfig オブジェクト
    """
    existing = await get_bump_config(session, guild_id)

    if existing:
        existing.channel_id = channel_id
        await session.commit()
        await session.refresh(existing)
        return existing

    config = BumpConfig(guild_id=guild_id, channel_id=channel_id)
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def delete_bump_config(
    session: AsyncSession,
    guild_id: str,
) -> bool:
    """bump 監視設定を削除する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    config = await get_bump_config(session, guild_id)

    if config:
        await session.delete(config)
        await session.commit()
        return True

    return False
