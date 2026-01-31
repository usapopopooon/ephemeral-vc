"""Web test fixtures."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.constants import DEFAULT_TEST_DATABASE_URL
from src.database.models import AdminUser, Base
from src.web import app as web_app_module
from src.web.app import app, get_db, hash_password

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    DEFAULT_TEST_DATABASE_URL,
)

# テスト用管理者認証情報
TEST_ADMIN_EMAIL = "test@example.com"
TEST_ADMIN_PASSWORD = "testpassword123"


@pytest.fixture(autouse=True)
def clear_rate_limit() -> None:
    """各テスト前にレート制限をクリアする。"""
    web_app_module.LOGIN_ATTEMPTS.clear()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """PostgreSQL テスト DB のセッションを提供する。"""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> AdminUser:
    """テスト用の AdminUser を作成する (パスワード変更済み、メール認証済み)。"""
    admin = AdminUser(
        email=TEST_ADMIN_EMAIL,
        password_hash=hash_password(TEST_ADMIN_PASSWORD),
        password_changed_at=datetime.now(UTC),  # パスワード変更済みとしてマーク
        email_verified=True,  # メール認証済み
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.fixture
async def initial_admin_user(db_session: AsyncSession) -> AdminUser:
    """テスト用の AdminUser を作成する (初回セットアップ状態)。"""
    admin = AdminUser(
        email=TEST_ADMIN_EMAIL,
        password_hash=hash_password(TEST_ADMIN_PASSWORD),
        password_changed_at=None,  # 初回セットアップ
        email_verified=False,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.fixture
async def unverified_admin_user(db_session: AsyncSession) -> AdminUser:
    """テスト用の AdminUser を作成する (パスワード変更済み、メール未認証)。"""
    admin = AdminUser(
        email=TEST_ADMIN_EMAIL,
        password_hash=hash_password(TEST_ADMIN_PASSWORD),
        password_changed_at=datetime.now(UTC),  # パスワード変更済み
        email_verified=False,  # メール未認証
        pending_email="pending@example.com",
        email_change_token="test_verify_token",
        email_change_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI テストクライアントを提供する。"""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_client(
    client: AsyncClient,
    admin_user: AdminUser,
) -> AsyncClient:
    """認証済みのテストクライアントを提供する。"""
    response = await client.post(
        "/login",
        data={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD,
        },
        follow_redirects=False,
    )
    # セッション cookie を取得
    session_cookie = response.cookies.get("session")
    if session_cookie:
        client.cookies.set("session", session_cookie)
    return client


@pytest.fixture(autouse=True)
def mock_email_sending() -> Generator[None, None, None]:
    """全てのテストでメール送信をモックする (常に成功)。"""
    with (
        patch(
            "src.web.app.send_email_change_verification",
            return_value=True,
        ),
        patch(
            "src.web.app.send_password_reset_email",
            return_value=True,
        ),
    ):
        yield
