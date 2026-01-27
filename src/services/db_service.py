"""Database service functions with side effects.

データベースの CRUD (Create, Read, Update, Delete) 操作を提供する。
各関数は AsyncSession を受け取り、SQL クエリを実行する。

使い方:
    async with async_session() as session:
        lobby = await get_lobby_by_channel_id(session, "123456")
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Lobby, VoiceSession

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
