"""Tests for web admin application routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    AdminUser,
    BumpConfig,
    BumpReminder,
    Lobby,
    RolePanel,
    RolePanelItem,
    StickyMessage,
)
from src.web.app import hash_password

from .conftest import TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD

# ===========================================================================
# ヘルスチェックルート
# ===========================================================================


class TestHealthCheckRoute:
    """/health ルートのテスト。"""

    async def test_health_check_returns_ok(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """正常時は 200 OK を返す。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # check_database_connection を True を返すようにモック
        monkeypatch.setattr(
            web_app_module,
            "check_database_connection",
            AsyncMock(return_value=True),
        )

        response = await client.get("/health")
        assert response.status_code == 200
        assert response.text == "ok"

    async def test_health_check_returns_503_on_db_failure(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DB 接続失敗時は 503 を返す。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # check_database_connection を False を返すようにモック
        monkeypatch.setattr(
            web_app_module,
            "check_database_connection",
            AsyncMock(return_value=False),
        )

        response = await client.get("/health")
        assert response.status_code == 503
        assert response.text == "database unavailable"

    async def test_health_check_no_auth_required(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """認証なしでアクセスできる (ログイン不要)。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # check_database_connection を True を返すようにモック
        monkeypatch.setattr(
            web_app_module,
            "check_database_connection",
            AsyncMock(return_value=True),
        )

        # 認証なしのクライアントでアクセス
        response = await client.get("/health")
        assert response.status_code == 200
        # リダイレクトではなく直接レスポンスを返す
        assert "session" not in response.request.headers


# ===========================================================================
# インデックスルート
# ===========================================================================


class TestIndexRoute:
    """/ ルートのテスト。"""

    async def test_redirect_to_login_when_not_authenticated(
        self, client: AsyncClient
    ) -> None:
        """未認証時は /login にリダイレクトされる。"""
        response = await client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_redirect_to_dashboard_when_authenticated(
        self, authenticated_client: AsyncClient
    ) -> None:
        """認証済みの場合は /dashboard にリダイレクトされる。"""
        response = await authenticated_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"


# ===========================================================================
# ログインルート
# ===========================================================================


class TestLoginRoutes:
    """ログイン関連ルートのテスト。"""

    async def test_login_page_renders(self, client: AsyncClient) -> None:
        """ログインページが表示される。"""
        response = await client.get("/login")
        assert response.status_code == 200
        assert "Bot Admin" in response.text
        assert "Email" in response.text
        assert "Password" in response.text

    async def test_login_redirects_when_authenticated(
        self, authenticated_client: AsyncClient
    ) -> None:
        """認証済みの場合は /dashboard にリダイレクトされる。"""
        response = await authenticated_client.get("/login", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

    async def test_login_success(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """正しい認証情報でログインできる。"""
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"
        assert "session" in response.cookies

    async def test_login_failure_wrong_password(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """間違ったパスワードでログインに失敗する。"""
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": "wrongpassword",
            },
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.text

    async def test_login_failure_wrong_email(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """間違ったユーザー名でログインに失敗する。"""
        response = await client.post(
            "/login",
            data={
                "email": "wronguser",
                "password": TEST_ADMIN_PASSWORD,
            },
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.text

    async def test_login_with_default_admin(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """デフォルトの AdminUser 認証情報でログインできる。"""
        import src.web.app as web_app_module

        # 既知のテスト認証情報を使用
        monkeypatch.setattr(web_app_module, "INIT_ADMIN_EMAIL", "default@example.com")
        monkeypatch.setattr(web_app_module, "INIT_ADMIN_PASSWORD", "defaultpassword")

        response = await client.post(
            "/login",
            data={
                "email": "default@example.com",
                "password": "defaultpassword",
            },
            follow_redirects=False,
        )
        # 認証済み状態で作成されるため、ダッシュボードへ直接リダイレクト
        assert response.status_code == 302
        assert response.headers.get("location") == "/dashboard"

    async def test_login_auto_creates_admin_from_env(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """INIT_ADMIN_PASSWORD が設定されていれば AdminUser が自動作成される。"""
        import src.web.app as web_app_module

        monkeypatch.setattr(web_app_module, "INIT_ADMIN_EMAIL", "env@example.com")
        monkeypatch.setattr(web_app_module, "INIT_ADMIN_PASSWORD", "envpassword123")

        # 正しい認証情報でログイン
        response = await client.post(
            "/login",
            data={
                "email": "env@example.com",
                "password": "envpassword123",
            },
            follow_redirects=False,
        )
        # 認証済み状態で作成されるため、ダッシュボードへ直接リダイレクト
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"
        assert "session" in response.cookies


# ===========================================================================
# ログアウトルート
# ===========================================================================


class TestLogoutRoute:
    """/logout ルートのテスト。"""

    async def test_logout_clears_session(
        self, authenticated_client: AsyncClient
    ) -> None:
        """ログアウトするとセッションがクリアされる。"""
        response = await authenticated_client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"


# ===========================================================================
# ダッシュボードルート
# ===========================================================================


class TestDashboardRoute:
    """/dashboard ルートのテスト。"""

    async def test_dashboard_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_dashboard_renders(self, authenticated_client: AsyncClient) -> None:
        """認証済みの場合はダッシュボードが表示される。"""
        response = await authenticated_client.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard" in response.text
        assert "Lobbies" in response.text
        assert "Sticky Messages" in response.text
        assert "Bump Reminders" in response.text


# ===========================================================================
# 設定ルート
# ===========================================================================


class TestSettingsRoutes:
    """/settings ルートのテスト。"""

    async def test_settings_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/settings", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_page_renders(
        self, authenticated_client: AsyncClient
    ) -> None:
        """設定ハブページが表示される。"""
        response = await authenticated_client.get("/settings")
        assert response.status_code == 200
        assert "Settings" in response.text
        assert "Change Email" in response.text
        assert "Change Password" in response.text


# ===========================================================================
# ロビールート
# ===========================================================================


class TestLobbiesRoutes:
    """/lobbies ルートのテスト。"""

    async def test_lobbies_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/lobbies", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_lobbies_list_empty(self, authenticated_client: AsyncClient) -> None:
        """ロビーがない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/lobbies")
        assert response.status_code == 200
        assert "No lobbies configured" in response.text

    async def test_lobbies_list_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロビーがある場合は一覧が表示される。"""
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        db_session.add(lobby)
        await db_session.commit()

        response = await authenticated_client.get("/lobbies")
        assert response.status_code == 200
        assert "123456789012345678" in response.text
        assert "987654321098765432" in response.text

    async def test_delete_lobby(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロビーを削除できる。"""
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        db_session.add(lobby)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/lobbies/{lobby.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/lobbies"


# ===========================================================================
# Sticky ルート
# ===========================================================================


class TestStickyRoutes:
    """/sticky ルートのテスト。"""

    async def test_sticky_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/sticky", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_sticky_list_empty(self, authenticated_client: AsyncClient) -> None:
        """Sticky がない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/sticky")
        assert response.status_code == 200
        assert "No sticky messages configured" in response.text

    async def test_sticky_list_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Sticky がある場合は一覧が表示される。"""
        sticky = StickyMessage(
            channel_id="123456789012345678",
            guild_id="987654321098765432",
            title="Test Title",
            description="Test Description",
        )
        db_session.add(sticky)
        await db_session.commit()

        response = await authenticated_client.get("/sticky")
        assert response.status_code == 200
        assert "Test Title" in response.text

    async def test_delete_sticky(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Sticky を削除できる。"""
        sticky = StickyMessage(
            channel_id="123456789012345678",
            guild_id="987654321098765432",
            title="Test",
            description="Test",
        )
        db_session.add(sticky)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/sticky/{sticky.channel_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/sticky"


# ===========================================================================
# Bump ルート
# ===========================================================================


class TestBumpRoutes:
    """/bump ルートのテスト。"""

    async def test_bump_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/bump", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_bump_list_empty(self, authenticated_client: AsyncClient) -> None:
        """Bump 設定がない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "No bump configs" in response.text
        assert "No bump reminders" in response.text

    async def test_bump_list_with_config(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Bump Config がある場合は一覧に表示される。"""
        config = BumpConfig(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
        )
        db_session.add(config)
        await db_session.commit()

        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "123456789012345678" in response.text

    async def test_bump_list_with_reminder(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Bump Reminder がある場合は一覧に表示される。"""
        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()

        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "DISBOARD" in response.text

    async def test_toggle_reminder(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Reminder の有効/無効を切り替えられる。"""
        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            service_name="DISBOARD",
            is_enabled=True,
        )
        db_session.add(reminder)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/bump/reminder/{reminder.id}/toggle",
            follow_redirects=False,
        )
        assert response.status_code == 302

    async def test_delete_config(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Config を削除できる。"""
        config = BumpConfig(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
        )
        db_session.add(config)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/bump/config/{config.guild_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    async def test_delete_reminder(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Reminder を削除できる。"""
        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/bump/reminder/{reminder.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302


# ===========================================================================
# レート制限
# ===========================================================================


class TestRateLimiting:
    """レート制限のテスト。"""

    async def test_rate_limit_after_max_attempts(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """最大試行回数を超えるとレート制限がかかる。"""
        # 5回失敗
        for _ in range(5):
            await client.post(
                "/login",
                data={
                    "email": "wrong",
                    "password": "wrong",
                },
            )

        # 6回目はレート制限
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
        )
        assert response.status_code == 429
        assert "Too many attempts" in response.text


# ===========================================================================
# パスワードハッシュ
# ===========================================================================


class TestPasswordHashing:
    """パスワードハッシュのテスト。"""

    def test_hash_password_creates_hash(self) -> None:
        """hash_password がハッシュを生成する。"""
        password = "testpassword123"
        hashed = hash_password(password)
        assert hashed != password
        assert hashed.startswith("$2b$")

    def test_different_passwords_different_hashes(self) -> None:
        """異なるパスワードは異なるハッシュになる。"""
        hash1 = hash_password("password1")
        hash2 = hash_password("password2")
        assert hash1 != hash2

    def test_same_password_different_hashes(self) -> None:
        """同じパスワードでも毎回異なるハッシュ (salt)。"""
        password = "testpassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2


# ===========================================================================
# パスワード検証
# ===========================================================================


class TestPasswordVerification:
    """verify_password 関数のテスト。"""

    def test_verify_password_correct(self) -> None:
        """正しいパスワードで True を返す。"""
        from src.web.app import verify_password

        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """間違ったパスワードで False を返す。"""
        from src.web.app import verify_password

        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False


# ===========================================================================
# 設定 (変更なし)
# ===========================================================================


# ===========================================================================
# 存在しないアイテムの削除
# ===========================================================================


class TestDeleteNonExistent:
    """存在しないアイテムの削除テスト。"""

    async def test_delete_nonexistent_lobby(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないロビーの削除はリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/lobbies/99999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/lobbies"

    async def test_delete_nonexistent_sticky(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しない Sticky の削除はリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/sticky/999999999999999999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/sticky"

    async def test_delete_nonexistent_bump_config(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しない BumpConfig の削除はリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/bump/config/999999999999999999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/bump"

    async def test_delete_nonexistent_bump_reminder(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しない BumpReminder の削除はリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/bump/reminder/99999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/bump"

    async def test_toggle_nonexistent_bump_reminder(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しない BumpReminder のトグルはリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/bump/reminder/99999/toggle",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/bump"


# ===========================================================================
# セッションユーティリティ
# ===========================================================================


# ===========================================================================
# 未認証の POST リクエスト
# ===========================================================================


class TestUnauthenticatedGetRequests:
    """認証なしの GET リクエストのテスト。"""

    async def test_initial_setup_get_requires_auth(self, client: AsyncClient) -> None:
        """認証なしで初回セットアップGETは /login にリダイレクトされる。"""
        response = await client.get("/initial-setup", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_email_get_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでメール変更GETは /login にリダイレクトされる。"""
        response = await client.get("/settings/email", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_password_get_requires_auth(
        self, client: AsyncClient
    ) -> None:
        """認証なしでパスワード変更GETは /login にリダイレクトされる。"""
        response = await client.get("/settings/password", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"


class TestUnauthenticatedPostRequests:
    """認証なしの POST リクエストのテスト。"""

    async def test_initial_setup_post_requires_auth(self, client: AsyncClient) -> None:
        """認証なしで初回セットアップは /login にリダイレクトされる。"""
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "test@example.com",
                "new_password": "password123",
                "confirm_password": "password123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_email_post_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでメール変更は /login にリダイレクトされる。"""
        response = await client.post(
            "/settings/email",
            data={"new_email": "test@example.com"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_password_post_requires_auth(
        self, client: AsyncClient
    ) -> None:
        """認証なしでパスワード変更は /login にリダイレクトされる。"""
        response = await client.post(
            "/settings/password",
            data={"new_password": "password123", "confirm_password": "password123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_resend_verification_requires_auth(self, client: AsyncClient) -> None:
        """認証なしで確認メール再送は /login にリダイレクトされる。"""
        response = await client.post("/resend-verification", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_lobbies_delete_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでロビー削除は /login にリダイレクトされる。"""
        response = await client.post("/lobbies/1/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_sticky_delete_requires_auth(self, client: AsyncClient) -> None:
        """認証なしで Sticky 削除は /login にリダイレクトされる。"""
        response = await client.post("/sticky/123/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_bump_config_delete_requires_auth(self, client: AsyncClient) -> None:
        """認証なしで BumpConfig 削除は /login にリダイレクトされる。"""
        response = await client.post("/bump/config/123/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_bump_reminder_delete_requires_auth(
        self, client: AsyncClient
    ) -> None:
        """認証なしで BumpReminder 削除は /login にリダイレクトされる。"""
        response = await client.post("/bump/reminder/1/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_bump_reminder_toggle_requires_auth(
        self, client: AsyncClient
    ) -> None:
        """認証なしで BumpReminder トグルは /login にリダイレクトされる。"""
        response = await client.post("/bump/reminder/1/toggle", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"


# ===========================================================================
# 初回セットアップフロー
# ===========================================================================


class TestInitialSetupFlow:
    """初回セットアップフローのテスト。"""

    async def test_login_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回ログイン時は /initial-setup にリダイレクトされる。"""
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_dashboard_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップ時は /dashboard から /initial-setup にリダイレクトされる。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # ダッシュボードにアクセス
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_initial_setup_page_renders(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップページが表示される。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 初回セットアップページにアクセス
        response = await client.get("/initial-setup")
        assert response.status_code == 200
        assert "Initial Setup" in response.text
        assert "Email Address" in response.text
        assert "New Password" in response.text

    async def test_initial_setup_success(
        self,
        client: AsyncClient,
        initial_admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """初回セットアップが成功する。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 初回セットアップを実行
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "newadmin@example.com",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=False,
        )
        # SMTP 未設定のため、ダッシュボードへ直接リダイレクト
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

        # DBが更新されていることを確認
        await db_session.refresh(initial_admin_user)
        # メールアドレスが直接更新される（pending_email ではなく）
        assert initial_admin_user.email == "newadmin@example.com"
        assert initial_admin_user.pending_email is None
        assert initial_admin_user.password_changed_at is not None
        assert initial_admin_user.email_verified is True

    async def test_initial_setup_invalid_email(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップで無効なメールアドレスはエラー。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 無効なメールアドレスで初回セットアップ
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "invalid-email",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )
        assert response.status_code == 200
        assert "Invalid email format" in response.text

    async def test_initial_setup_password_mismatch(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップでパスワード不一致はエラー。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # パスワード不一致で初回セットアップ
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "newadmin@example.com",
                "new_password": "newpassword123",
                "confirm_password": "differentpassword",
            },
        )
        assert response.status_code == 200
        assert "Passwords do not match" in response.text

    async def test_initial_setup_password_too_short(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップでパスワードが短すぎる場合はエラー。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 短すぎるパスワードで初回セットアップ
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "newadmin@example.com",
                "new_password": "short",
                "confirm_password": "short",
            },
        )
        assert response.status_code == 200
        assert "at least 8 characters" in response.text


class TestSessionUtilities:
    """セッションユーティリティのテスト。"""

    def test_create_session_token(self) -> None:
        """create_session_token がトークンを生成する。"""
        from src.web.app import create_session_token

        token = create_session_token("test@example.com")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_session_token_valid(self) -> None:
        """有効なトークンを検証できる。"""
        from src.web.app import create_session_token, verify_session_token

        token = create_session_token("test@example.com")
        data = verify_session_token(token)
        assert data is not None
        assert data["authenticated"] is True
        assert data["email"] == "test@example.com"

    def test_verify_session_token_invalid(self) -> None:
        """無効なトークンは None を返す。"""
        from src.web.app import verify_session_token

        data = verify_session_token("invalid_token")
        assert data is None

    def test_get_current_user_no_session(self) -> None:
        """セッションがない場合は None を返す。"""
        from src.web.app import get_current_user

        user = get_current_user(None)
        assert user is None

    def test_get_current_user_invalid_session(self) -> None:
        """無効なセッションは None を返す。"""
        from src.web.app import get_current_user

        user = get_current_user("invalid_token")
        assert user is None

    def test_get_current_user_valid_session(self) -> None:
        """有効なセッションでユーザー情報を取得できる。"""
        from src.web.app import create_session_token, get_current_user

        token = create_session_token("test@example.com")
        user = get_current_user(token)
        assert user is not None
        assert user["email"] == "test@example.com"

    def test_verify_session_token_not_authenticated(self) -> None:
        """authenticated=False のトークンは None を返す。"""
        from src.web.app import serializer, verify_session_token

        # authenticated=False のトークンを作成
        token = serializer.dumps({"authenticated": False, "email": "test@example.com"})
        data = verify_session_token(token)
        assert data is None


# ===========================================================================
# レート制限ユーティリティ
# ===========================================================================


class TestRateLimitingUtilities:
    """レート制限ユーティリティのテスト。"""

    def test_is_rate_limited_new_ip(self) -> None:
        """新規IPはレート制限されていない。"""
        from src.web.app import is_rate_limited

        result = is_rate_limited("192.168.1.100")
        assert result is False

    def test_record_failed_attempt_new_ip(self) -> None:
        """新規IPの失敗を記録できる。"""
        from src.web.app import LOGIN_ATTEMPTS, record_failed_attempt

        record_failed_attempt("192.168.1.101")
        assert "192.168.1.101" in LOGIN_ATTEMPTS
        assert len(LOGIN_ATTEMPTS["192.168.1.101"]) == 1

    def test_is_rate_limited_after_max_attempts(self) -> None:
        """最大試行回数後はレート制限される。"""
        from src.web.app import is_rate_limited, record_failed_attempt

        ip = "192.168.1.102"
        for _ in range(5):
            record_failed_attempt(ip)

        result = is_rate_limited(ip)
        assert result is True


# ===========================================================================
# パスワードリセットルート
# ===========================================================================


class TestForgotPasswordRoutes:
    """パスワードリセット（forgot-password）ルートのテスト。"""

    async def test_forgot_password_page_renders(self, client: AsyncClient) -> None:
        """パスワードリセットページが表示される。"""
        response = await client.get("/forgot-password")
        assert response.status_code == 200
        assert "Reset Password" in response.text
        assert "Email" in response.text

    async def test_forgot_password_with_valid_email(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """SMTP 未設定のため、パスワードリセットは利用不可。"""
        response = await client.post(
            "/forgot-password",
            data={"email": TEST_ADMIN_EMAIL},
        )
        assert response.status_code == 200
        assert "SMTP is not configured" in response.text

    async def test_forgot_password_with_invalid_email(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """SMTP 未設定のため、どのメールアドレスでも同じエラーが表示される。"""
        response = await client.post(
            "/forgot-password",
            data={"email": "nonexistent@example.com"},
        )
        assert response.status_code == 200
        assert "SMTP is not configured" in response.text

    async def test_forgot_password_sets_reset_token(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """SMTP 未設定のため、リセットトークンは生成されない。"""
        await client.post(
            "/forgot-password",
            data={"email": TEST_ADMIN_EMAIL},
        )
        await db_session.refresh(admin_user)
        # SMTP 未設定のためトークンは設定されない
        assert admin_user.reset_token is None
        assert admin_user.reset_token_expires_at is None


class TestResetPasswordRoutes:
    """パスワードリセット（reset-password）ルートのテスト。"""

    async def test_reset_password_page_without_token(self, client: AsyncClient) -> None:
        """トークンなしでアクセスするとエラー。"""
        response = await client.get("/reset-password")
        assert response.status_code == 200
        assert "Invalid or missing reset token" in response.text

    async def test_reset_password_page_with_invalid_token(
        self, client: AsyncClient
    ) -> None:
        """無効なトークンでアクセスするとエラー。"""
        response = await client.get("/reset-password?token=invalid_token")
        assert response.status_code == 200
        assert "Invalid or expired reset token" in response.text

    async def test_reset_password_page_with_valid_token(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """有効なトークンでパスワードリセットページが表示される。"""
        # トークンを設定
        admin_user.reset_token = "valid_test_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db_session.commit()

        response = await client.get("/reset-password?token=valid_test_token")
        assert response.status_code == 200
        assert "New Password" in response.text

    async def test_reset_password_with_expired_token(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """期限切れのトークンでアクセスするとエラー。"""
        # 期限切れトークンを設定
        admin_user.reset_token = "expired_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db_session.commit()

        response = await client.get("/reset-password?token=expired_token")
        assert response.status_code == 200
        assert "expired" in response.text

    async def test_reset_password_success(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """パスワードリセットが成功する。"""
        # トークンを設定
        admin_user.reset_token = "reset_test_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db_session.commit()

        response = await client.post(
            "/reset-password",
            data={
                "token": "reset_test_token",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )
        assert response.status_code == 200
        # ログインページに戻る
        assert "Bot Admin" in response.text

        # トークンがクリアされている
        await db_session.refresh(admin_user)
        assert admin_user.reset_token is None
        assert admin_user.reset_token_expires_at is None

    async def test_reset_password_mismatch(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """パスワードが一致しない場合はエラー。"""
        admin_user.reset_token = "mismatch_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db_session.commit()

        response = await client.post(
            "/reset-password",
            data={
                "token": "mismatch_token",
                "new_password": "password123",
                "confirm_password": "different123",
            },
        )
        assert response.status_code == 200
        assert "Passwords do not match" in response.text

    async def test_reset_password_too_short(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """パスワードが短すぎる場合はエラー。"""
        admin_user.reset_token = "short_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db_session.commit()

        response = await client.post(
            "/reset-password",
            data={
                "token": "short_token",
                "new_password": "short",
                "confirm_password": "short",
            },
        )
        assert response.status_code == 200
        assert "at least 8 characters" in response.text

    async def test_reset_password_with_expired_token_post(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """期限切れトークンでPOSTするとエラー。"""
        admin_user.reset_token = "expired_post_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db_session.commit()

        response = await client.post(
            "/reset-password",
            data={
                "token": "expired_post_token",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )
        assert response.status_code == 200
        assert "expired" in response.text


# ===========================================================================
# メールアドレス変更検証ルート
# ===========================================================================


class TestEmailChangeVerification:
    """メールアドレス変更検証のテスト。"""

    async def test_settings_email_page_renders(
        self, authenticated_client: AsyncClient
    ) -> None:
        """メールアドレス変更ページが表示される。"""
        response = await authenticated_client.get("/settings/email")
        assert response.status_code == 200
        assert "Change Email" in response.text

    async def test_settings_email_change_sends_verification(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """SMTP 未設定のため、メールアドレスは直接変更される。"""
        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": "newemail@example.com"},
            follow_redirects=False,
        )
        # リダイレクトで設定ページに戻る
        assert response.status_code == 302
        assert response.headers["location"] == "/settings"

    async def test_settings_email_same_email_error(
        self, authenticated_client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """同じメールアドレスを入力するとエラー。"""
        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": admin_user.email},
        )
        assert response.status_code == 200
        assert "different from current" in response.text

    async def test_settings_shows_pending_email(
        self,
        authenticated_client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """保留中のメールアドレス変更が表示される。"""
        # 保留中のメールを設定
        admin_user.pending_email = "pending@example.com"
        admin_user.email_change_token = "test_token"
        admin_user.email_change_token_expires_at = datetime.now(UTC) + timedelta(
            hours=1
        )
        await db_session.commit()

        response = await authenticated_client.get("/settings")
        assert response.status_code == 200
        assert "pending@example.com" in response.text

    async def test_confirm_email_without_token(self, client: AsyncClient) -> None:
        """トークンなしでアクセスするとエラー。"""
        response = await client.get("/confirm-email")
        assert response.status_code == 200
        assert "Invalid or missing confirmation token" in response.text

    async def test_confirm_email_with_invalid_token(self, client: AsyncClient) -> None:
        """無効なトークンでアクセスするとエラー。"""
        response = await client.get("/confirm-email?token=invalid_token")
        assert response.status_code == 200
        assert "Invalid or expired confirmation token" in response.text

    async def test_confirm_email_with_valid_token(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """有効なトークンでメールアドレスが変更される。"""
        # トークンを設定
        admin_user.pending_email = "confirmed@example.com"
        admin_user.email_change_token = "valid_confirm_token"
        admin_user.email_change_token_expires_at = datetime.now(UTC) + timedelta(
            hours=1
        )
        await db_session.commit()

        response = await client.get("/confirm-email?token=valid_confirm_token")
        assert response.status_code == 200

        # メールアドレスが変更され、email_verified が True になっている
        await db_session.refresh(admin_user)
        assert admin_user.email == "confirmed@example.com"
        assert admin_user.email_verified is True
        assert admin_user.pending_email is None
        assert admin_user.email_change_token is None

    async def test_confirm_email_with_expired_token(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """期限切れトークンでアクセスするとエラー。"""
        # 期限切れトークンを設定
        admin_user.pending_email = "expired@example.com"
        admin_user.email_change_token = "expired_confirm_token"
        admin_user.email_change_token_expires_at = datetime.now(UTC) - timedelta(
            hours=1
        )
        await db_session.commit()

        response = await client.get("/confirm-email?token=expired_confirm_token")
        assert response.status_code == 200
        assert "expired" in response.text


class TestEmailVerificationPendingRoutes:
    """メール認証待ちルートのテスト。"""

    async def test_verify_email_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/verify-email", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_verify_email_page_renders(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """メール認証待ちページが表示される。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # メール認証待ちページにアクセス
        response = await client.get("/verify-email")
        assert response.status_code == 200
        assert "Verify Your Email" in response.text
        assert "pending@example.com" in response.text

    async def test_login_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """メール未認証の場合は /verify-email にリダイレクトされる。"""
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_dashboard_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """メール未認証の場合は /dashboard から /verify-email にリダイレクトされる。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # ダッシュボードにアクセス
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_resend_verification_success(
        self,
        client: AsyncClient,
        unverified_admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """確認メール再送が成功する。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 元のトークンを記録
        original_token = unverified_admin_user.email_change_token

        # 確認メール再送
        response = await client.post("/resend-verification")
        assert response.status_code == 200
        assert "Verification email sent" in response.text

        # 新しいトークンが生成されている
        await db_session.refresh(unverified_admin_user)
        assert unverified_admin_user.email_change_token != original_token

    async def test_verify_email_redirects_to_dashboard_when_verified(
        self, authenticated_client: AsyncClient
    ) -> None:
        """既に認証済みの場合は /dashboard にリダイレクトされる。"""
        response = await authenticated_client.get(
            "/verify-email", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"


class TestPasswordChangeRoutes:
    """パスワード変更ルートのテスト。"""

    async def test_password_change_page_renders(
        self, authenticated_client: AsyncClient
    ) -> None:
        """パスワード変更ページが表示される。"""
        response = await authenticated_client.get("/settings/password")
        assert response.status_code == 200
        assert "Change Password" in response.text

    async def test_password_change_success(
        self, authenticated_client: AsyncClient
    ) -> None:
        """パスワード変更が成功する。"""
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_password_change_mismatch(
        self, authenticated_client: AsyncClient
    ) -> None:
        """パスワードが一致しない場合はエラー。"""
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "password123",
                "confirm_password": "different123",
            },
        )
        assert response.status_code == 200
        assert "Passwords do not match" in response.text

    async def test_password_change_too_short(
        self, authenticated_client: AsyncClient
    ) -> None:
        """パスワードが短すぎる場合はエラー。"""
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "short",
                "confirm_password": "short",
            },
        )
        assert response.status_code == 200
        assert "at least 8 characters" in response.text


# ===========================================================================
# Faker を使ったテスト
# ===========================================================================

from faker import Faker  # noqa: E402

fake = Faker()


class TestWebAdminWithFaker:
    """Faker を使ったランダムデータでのテスト。"""

    async def test_login_with_random_credentials_fails(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """ランダムな認証情報ではログインに失敗する。"""
        response = await client.post(
            "/login",
            data={
                "email": fake.email(),
                "password": fake.password(),
            },
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.text

    async def test_change_to_random_email(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Faker で生成したメールアドレスに変更できる（SMTP 未設定のため直接変更）。"""
        new_email = fake.email()
        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": new_email},
            follow_redirects=False,
        )
        # SMTP 未設定のため、リダイレクトで設定ページに戻る
        assert response.status_code == 302
        assert response.headers["location"] == "/settings"

    async def test_change_to_random_password(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Faker で生成したパスワードに変更できる。"""
        new_password = fake.password(length=12)
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": new_password,
                "confirm_password": new_password,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_invalid_random_email_format_rejected(
        self, authenticated_client: AsyncClient
    ) -> None:
        """不正な形式のメールアドレスは拒否される。"""
        invalid_email = fake.user_name()  # @ がないので不正
        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": invalid_email},
        )
        assert response.status_code == 200
        assert "Invalid email format" in response.text

    async def test_short_random_password_rejected(
        self, authenticated_client: AsyncClient
    ) -> None:
        """短すぎるパスワードは拒否される。"""
        short_password = fake.password(length=5)
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": short_password,
                "confirm_password": short_password,
            },
        )
        assert response.status_code == 200
        assert "at least 8 characters" in response.text

    async def test_rate_limiting_with_random_ips(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """ランダムIPでのレート制限テスト。"""
        from src.web.app import LOGIN_ATTEMPTS, is_rate_limited, record_failed_attempt

        random_ip = fake.ipv4()
        assert is_rate_limited(random_ip) is False

        for _ in range(5):
            record_failed_attempt(random_ip)

        assert is_rate_limited(random_ip) is True

        # クリーンアップ
        LOGIN_ATTEMPTS.pop(random_ip, None)


# ===========================================================================
# 初回セットアップのエッジケース
# ===========================================================================


class TestInitialSetupEdgeCases:
    """初回セットアップのエッジケーステスト。"""

    async def test_initial_setup_get_redirects_to_dashboard_when_completed(
        self, authenticated_client: AsyncClient
    ) -> None:
        """セットアップ完了済みの場合は /dashboard にリダイレクトされる。"""
        response = await authenticated_client.get(
            "/initial-setup", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

    async def test_initial_setup_get_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """セットアップ完了済みでメール未認証の場合は /verify-email にリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/initial-setup", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_initial_setup_post_empty_email(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """空のメールアドレスはエラー。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "",
                "new_password": "password123",
                "confirm_password": "password123",
            },
        )
        assert response.status_code == 200
        assert "Email address is required" in response.text

    async def test_initial_setup_post_empty_password(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """空のパスワードはエラー。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "valid@example.com",
                "new_password": "",
                "confirm_password": "",
            },
        )
        assert response.status_code == 200
        assert "Password is required" in response.text


# ===========================================================================
# メール認証待ちのエッジケース
# ===========================================================================


class TestVerifyEmailEdgeCases:
    """メール認証待ちのエッジケーステスト。"""

    async def test_verify_email_no_pending_redirects_to_dashboard(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """pending_email がない場合は /dashboard にリダイレクト。"""
        # email_verified を False にしつつ pending_email を None に
        admin_user.email_verified = False
        admin_user.pending_email = None
        await db_session.commit()

        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/verify-email", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"


# ===========================================================================
# 確認メール再送のエッジケース
# ===========================================================================


class TestResendVerificationEdgeCases:
    """確認メール再送のエッジケーステスト。"""

    async def test_resend_verification_no_pending_redirects_to_dashboard(
        self,
        authenticated_client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """pending_email がない場合は /dashboard にリダイレクト。"""
        # pending_email を None に
        admin_user.pending_email = None
        await db_session.commit()

        response = await authenticated_client.post(
            "/resend-verification", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"


# ===========================================================================
# 初回セットアップが必要な設定ルート
# ===========================================================================


class TestSettingsRequiresInitialSetup:
    """設定ルートで初回セットアップが必要なケースのテスト。"""

    async def test_settings_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """/settings は初回セットアップにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_settings_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """/settings はメール認証待ちにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_settings_email_get_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """/settings/email は初回セットアップにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings/email", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_settings_email_get_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """/settings/email はメール認証待ちにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings/email", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_settings_password_get_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """/settings/password は初回セットアップにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings/password", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_settings_password_get_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """/settings/password はメール認証待ちにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings/password", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_settings_password_post_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """POST /settings/password は初回セットアップにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.post(
            "/settings/password",
            data={
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_settings_password_post_redirects_to_verify_email(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """POST /settings/password はメール認証待ちにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.post(
            "/settings/password",
            data={
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"


# ===========================================================================
# メール変更 POST のエッジケース
# ===========================================================================


class TestSettingsEmailPostEdgeCases:
    """メール変更POSTのエッジケーステスト。"""

    async def test_settings_email_post_empty_email(
        self, authenticated_client: AsyncClient
    ) -> None:
        """空のメールアドレスはエラー。"""
        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": ""},
        )
        assert response.status_code == 200
        assert "Email address is required" in response.text


# ===========================================================================
# パスワード変更 POST のエッジケース
# ===========================================================================


class TestSettingsPasswordPostEdgeCases:
    """パスワード変更POSTのエッジケーステスト。"""

    async def test_settings_password_post_empty_password(
        self, authenticated_client: AsyncClient
    ) -> None:
        """空のパスワードはエラー。"""
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "",
                "confirm_password": "",
            },
        )
        assert response.status_code == 200
        assert "Password is required" in response.text


# ===========================================================================
# パスワードリセット POST のエッジケース
# ===========================================================================


class TestResetPasswordPostEdgeCases:
    """パスワードリセットPOSTのエッジケーステスト。"""

    async def test_reset_password_post_invalid_token(self, client: AsyncClient) -> None:
        """無効なトークンでPOSTするとエラー。"""
        response = await client.post(
            "/reset-password",
            data={
                "token": "invalid_token_for_post",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )
        assert response.status_code == 200
        assert "Invalid or expired reset token" in response.text

    async def test_reset_password_post_password_too_long(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """パスワードが長すぎる場合（72バイト超）はエラー。"""
        admin_user.reset_token = "long_pw_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db_session.commit()

        # 72バイトを超えるパスワード
        long_password = "a" * 80
        response = await client.post(
            "/reset-password",
            data={
                "token": "long_pw_token",
                "new_password": long_password,
                "confirm_password": long_password,
            },
        )
        assert response.status_code == 200
        assert "at most 72 bytes" in response.text


# ===========================================================================
# パスワードが長すぎる場合のテスト
# ===========================================================================


class TestPasswordTooLong:
    """パスワードが72バイトを超える場合のテスト。"""

    async def test_initial_setup_password_too_long(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップでパスワードが72バイトを超えるとエラー。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 72バイトを超えるパスワード
        long_password = "a" * 80
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "newadmin@example.com",
                "new_password": long_password,
                "confirm_password": long_password,
            },
        )
        assert response.status_code == 200
        assert "at most 72 bytes" in response.text

    async def test_settings_password_change_password_too_long(
        self, authenticated_client: AsyncClient
    ) -> None:
        """パスワード変更で72バイトを超えるパスワードはエラー。"""
        long_password = "a" * 80
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": long_password,
                "confirm_password": long_password,
            },
        )
        assert response.status_code == 200
        assert "at most 72 bytes" in response.text


# ===========================================================================
# hash_password の長いパスワードテスト
# ===========================================================================


class TestHashPasswordLong:
    """hash_password で長いパスワードのテスト。"""

    def test_hash_password_truncates_long_password(self) -> None:
        """72バイトを超えるパスワードは切り詰められてハッシュ化される。"""
        from src.web.app import hash_password

        long_password = "a" * 100
        hashed = hash_password(long_password)
        # ハッシュが生成される
        assert hashed.startswith("$2b$")


# ===========================================================================
# verify_password のエッジケース
# ===========================================================================


class TestVerifyPasswordEdgeCases:
    """verify_password のエッジケーステスト。"""

    def test_verify_password_empty_password(self) -> None:
        """空のパスワードは False を返す。"""
        from src.web.app import verify_password

        assert verify_password("", "some_hash") is False

    def test_verify_password_empty_hash(self) -> None:
        """空のハッシュは False を返す。"""
        from src.web.app import verify_password

        assert verify_password("password", "") is False

    def test_verify_password_invalid_hash_format(self) -> None:
        """無効なハッシュ形式は False を返す。"""
        from src.web.app import verify_password

        assert verify_password("password", "not_a_valid_bcrypt_hash") is False


# ===========================================================================
# verify_session_token のエッジケース
# ===========================================================================


class TestVerifySessionTokenEdgeCases:
    """verify_session_token のエッジケーステスト。"""

    def test_verify_session_token_empty_string(self) -> None:
        """空文字列は None を返す。"""
        from src.web.app import verify_session_token

        assert verify_session_token("") is None

    def test_verify_session_token_whitespace(self) -> None:
        """空白のみのトークンは None を返す。"""
        from src.web.app import verify_session_token

        assert verify_session_token("   ") is None


# ===========================================================================
# レート制限クリーンアップのテスト
# ===========================================================================


class TestRateLimitCleanup:
    """レート制限クリーンアップのテスト。"""

    def test_cleanup_removes_old_entries(self) -> None:
        """古いエントリがクリーンアップされる。"""
        import time

        import src.web.app as web_app_module
        from src.web.app import (
            LOGIN_ATTEMPTS,
            _cleanup_old_rate_limit_entries,
        )

        # 古いタイムスタンプを設定（5分以上前）
        old_time = time.time() - 400
        test_ip = "10.0.0.1"
        LOGIN_ATTEMPTS[test_ip] = [old_time]

        # 強制的にクリーンアップを実行
        web_app_module._last_cleanup_time = 0
        _cleanup_old_rate_limit_entries()

        # 古いIPが削除されている
        assert test_ip not in LOGIN_ATTEMPTS

    def test_cleanup_keeps_valid_entries(self) -> None:
        """有効なエントリは保持される。"""
        import time

        import src.web.app as web_app_module
        from src.web.app import (
            LOGIN_ATTEMPTS,
            _cleanup_old_rate_limit_entries,
        )

        # 新しいタイムスタンプを設定
        test_ip = "10.0.0.2"
        LOGIN_ATTEMPTS[test_ip] = [time.time()]

        # 強制的にクリーンアップを実行
        web_app_module._last_cleanup_time = 0
        _cleanup_old_rate_limit_entries()

        # 新しいIPは保持される
        assert test_ip in LOGIN_ATTEMPTS

        # クリーンアップ
        LOGIN_ATTEMPTS.pop(test_ip, None)


# ===========================================================================
# record_failed_attempt のエッジケース
# ===========================================================================


class TestRecordFailedAttemptEdgeCases:
    """record_failed_attempt のエッジケーステスト。"""

    def test_record_failed_attempt_empty_ip(self) -> None:
        """空のIPは記録されない。"""
        from src.web.app import LOGIN_ATTEMPTS, record_failed_attempt

        initial_count = len(LOGIN_ATTEMPTS)
        record_failed_attempt("")
        assert len(LOGIN_ATTEMPTS) == initial_count


# ===========================================================================
# admin が None の場合のテスト
# ===========================================================================


class TestAdminNoneScenarios:
    """admin が None の場合のテスト。"""

    async def test_login_admin_none(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ログイン時に admin が None の場合はエラー。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # get_or_create_admin を None を返すようにモック
        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await client.post(
            "/login",
            data={
                "email": "test@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 500
        assert "ADMIN_PASSWORD not configured" in response.text

    async def test_initial_setup_get_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """初回セットアップGETで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # get_or_create_admin を None を返すようにモック
        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get(
            "/initial-setup", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_initial_setup_post_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """初回セットアップPOSTで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.post(
            "/initial-setup",
            data={
                "new_email": "new@example.com",
                "new_password": "password123",
                "confirm_password": "password123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_verify_email_get_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """verify-email GETで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get(
            "/verify-email", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_resend_verification_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resend-verification で admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.post(
            "/resend-verification", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_get_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings GETで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get("/settings", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_email_get_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings/email GETで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get(
            "/settings/email", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_email_post_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings/email POSTで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": "new@example.com"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_password_get_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings/password GETで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get(
            "/settings/password", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_password_post_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings/password POSTで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"


# ===========================================================================
# resend_verification でメール送信失敗のテスト
# ===========================================================================


class TestDashboardAdminNone:
    """dashboard で admin が None の場合のテスト。"""

    async def test_dashboard_admin_none_shows_page(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ダッシュボードで admin が None の場合でもページが表示される。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # get_or_create_admin を None を返すようにモック
        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard" in response.text


class TestResendVerificationEmailFailure:
    """確認メール再送でメール送信失敗のテスト。"""

    async def test_resend_verification_email_send_fails(
        self,
        client: AsyncClient,
        unverified_admin_user: AdminUser,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """メール送信が失敗した場合はエラーメッセージが表示される。"""
        import src.web.app as web_app_module

        # メール送信を失敗させる
        monkeypatch.setattr(
            web_app_module,
            "send_email_change_verification",
            lambda _email, _token: False,
        )

        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.post("/resend-verification")
        assert response.status_code == 200
        assert "Failed to send verification email" in response.text


# ===========================================================================
# ロールパネルルート
# ===========================================================================


class TestRolePanelsRoutes:
    """/rolepanels ルートのテスト。"""

    async def test_rolepanels_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/rolepanels", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_rolepanels_list_empty(
        self, authenticated_client: AsyncClient
    ) -> None:
        """ロールパネルがない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "No role panels" in response.text

    async def test_rolepanels_list_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールパネルがある場合は一覧が表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Role Panel",
        )
        db_session.add(panel)
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "Test Role Panel" in response.text
        assert "123456789012345678" in response.text

    async def test_rolepanels_list_with_items(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールパネルにアイテムがある場合は表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Panel with Items",
        )
        db_session.add(panel)
        await db_session.flush()

        item = RolePanelItem(
            panel_id=panel.id,
            role_id="111111111111111111",
            emoji="🎮",
            label="Gamer",
            style="primary",
        )
        db_session.add(item)
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "Panel with Items" in response.text
        assert "🎮" in response.text
        assert "Gamer" in response.text

    async def test_delete_rolepanel(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールパネルを削除できる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="To Delete",
        )
        db_session.add(panel)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/rolepanels"

    async def test_delete_nonexistent_rolepanel(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないロールパネルの削除はリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/rolepanels/99999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/rolepanels"

    async def test_rolepanels_delete_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでロールパネル削除は /login にリダイレクトされる。"""
        response = await client.post("/rolepanels/1/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_rolepanels_shows_reaction_type(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """リアクション式パネルのバッジが表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Reaction Panel",
        )
        db_session.add(panel)
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "Reaction Panel" in response.text
        assert "Reaction" in response.text

    async def test_rolepanels_shows_auto_remove_badge(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """リアクション自動削除バッジが表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Auto Remove Panel",
            remove_reaction=True,
        )
        db_session.add(panel)
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "Auto-remove" in response.text

    async def test_rolepanels_list_contains_create_button(
        self, authenticated_client: AsyncClient
    ) -> None:
        """一覧ページに Create ボタンが含まれる。"""
        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "/rolepanels/new" in response.text
        assert "Create Panel" in response.text


# ===========================================================================
# Role Panel Create ルート
# ===========================================================================


class TestRolePanelCreateRoutes:
    """/rolepanels/new ルートのテスト。"""

    async def test_create_page_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/rolepanels/new", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_create_page_shows_form(
        self, authenticated_client: AsyncClient
    ) -> None:
        """認証済みでフォームが表示される。"""
        response = await authenticated_client.get("/rolepanels/new")
        assert response.status_code == 200
        assert 'action="/rolepanels/new"' in response.text
        assert 'name="guild_id"' in response.text
        assert 'name="channel_id"' in response.text
        assert 'name="panel_type"' in response.text
        assert 'name="title"' in response.text

    async def test_create_post_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123",
                "channel_id": "456",
                "panel_type": "button",
                "title": "Test",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_create_success(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """パネルを正常に作成できる。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "New Test Panel",
                "description": "Test description",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/rolepanels"

        # DB にパネルが作成されていることを確認
        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "New Test Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.guild_id == "123456789012345678"
        assert panel.channel_id == "987654321098765432"
        assert panel.panel_type == "button"
        assert panel.description == "Test description"

    async def test_create_reaction_type(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """リアクション式パネルを作成できる。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "reaction",
                "title": "Reaction Panel",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Reaction Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.panel_type == "reaction"

    async def test_create_missing_guild_id(
        self, authenticated_client: AsyncClient
    ) -> None:
        """guild_id が空の場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert "Guild ID is required" in response.text

    async def test_create_invalid_guild_id(
        self, authenticated_client: AsyncClient
    ) -> None:
        """guild_id が数字でない場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "not_a_number",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert "Guild ID must be a number" in response.text

    async def test_create_missing_channel_id(
        self, authenticated_client: AsyncClient
    ) -> None:
        """channel_id が空の場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "",
                "panel_type": "button",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert "Channel ID is required" in response.text

    async def test_create_invalid_channel_id(
        self, authenticated_client: AsyncClient
    ) -> None:
        """channel_id が数字でない場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "not_a_number",
                "panel_type": "button",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert "Channel ID must be a number" in response.text

    async def test_create_invalid_panel_type(
        self, authenticated_client: AsyncClient
    ) -> None:
        """panel_type が不正な場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "invalid",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert "Invalid panel type" in response.text

    async def test_create_missing_title(
        self, authenticated_client: AsyncClient
    ) -> None:
        """title が空の場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "",
            },
        )
        assert response.status_code == 200
        assert "Title is required" in response.text

    async def test_create_title_too_long(
        self, authenticated_client: AsyncClient
    ) -> None:
        """title が長すぎる場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "x" * 257,
            },
        )
        assert response.status_code == 200
        assert "Title must be 256 characters or less" in response.text

    async def test_create_description_too_long(
        self, authenticated_client: AsyncClient
    ) -> None:
        """description が長すぎる場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
                "description": "x" * 4097,
            },
        )
        assert response.status_code == 200
        assert "Description must be 4096 characters or less" in response.text

    async def test_create_preserves_input_on_error(
        self, authenticated_client: AsyncClient
    ) -> None:
        """エラー時に入力値が保持される。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "reaction",
                "title": "",  # Empty title causes error
                "description": "Test desc",
            },
        )
        assert response.status_code == 200
        assert "123456789012345678" in response.text
        assert "987654321098765432" in response.text
        assert "Test desc" in response.text

    async def test_create_without_description(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """description なしでパネルを作成できる。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "No Description Panel",
                "description": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "No Description Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.description is None
