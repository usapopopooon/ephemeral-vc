"""Tests for HTML templates."""

from __future__ import annotations

import pytest

from src.web.templates import (
    _base,
    _nav,
    bump_list_page,
    dashboard_page,
    lobbies_list_page,
    login_page,
    settings_page,
    sticky_list_page,
)

# ===========================================================================
# Base テンプレート
# ===========================================================================


class TestBaseTemplate:
    """_base テンプレートのテスト。"""

    def test_contains_html_structure(self) -> None:
        """HTML の基本構造を含む。"""
        result = _base("Test", "<p>Content</p>")
        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "</html>" in result
        assert "<head>" in result
        assert "<body" in result

    def test_title_is_escaped(self) -> None:
        """タイトルがエスケープされる。"""
        result = _base("<script>alert('xss')</script>", "content")
        assert "&lt;script&gt;" in result
        assert "<script>alert" not in result

    def test_includes_tailwind(self) -> None:
        """Tailwind CDN が含まれる。"""
        result = _base("Test", "content")
        assert "tailwindcss" in result

    def test_content_is_included(self) -> None:
        """コンテンツが含まれる。"""
        result = _base("Test", "<div>Test Content</div>")
        assert "<div>Test Content</div>" in result


# ===========================================================================
# ナビゲーションコンポーネント
# ===========================================================================


class TestNavComponent:
    """_nav コンポーネントのテスト。"""

    def test_contains_title(self) -> None:
        """タイトルが含まれる。"""
        result = _nav("Test Title")
        assert "Test Title" in result

    def test_contains_dashboard_link(self) -> None:
        """Dashboard リンクが含まれる。"""
        result = _nav("Test")
        assert "/dashboard" in result

    def test_contains_logout_link(self) -> None:
        """Logout リンクが含まれる。"""
        result = _nav("Test")
        assert "/logout" in result

    def test_title_is_escaped(self) -> None:
        """タイトルがエスケープされる。"""
        result = _nav("<script>xss</script>")
        assert "&lt;script&gt;" in result


# ===========================================================================
# ログインページ
# ===========================================================================


class TestLoginPage:
    """login_page テンプレートのテスト。"""

    def test_contains_form(self) -> None:
        """ログインフォームが含まれる。"""
        result = login_page()
        assert "<form" in result
        assert 'action="/login"' in result
        assert 'method="POST"' in result

    def test_contains_email_field(self) -> None:
        """メールフィールドが含まれる。"""
        result = login_page()
        assert 'name="email"' in result
        assert 'type="email"' in result

    def test_contains_password_field(self) -> None:
        """パスワードフィールドが含まれる。"""
        result = login_page()
        assert 'name="password"' in result
        assert 'type="password"' in result

    def test_error_is_displayed(self) -> None:
        """エラーメッセージが表示される。"""
        result = login_page(error="Test error message")
        assert "Test error message" in result

    def test_error_is_escaped(self) -> None:
        """エラーメッセージがエスケープされる。"""
        result = login_page(error="<script>xss</script>")
        assert "&lt;script&gt;" in result


# ===========================================================================
# ダッシュボードページ
# ===========================================================================


class TestDashboardPage:
    """dashboard_page テンプレートのテスト。"""

    def test_contains_welcome_message(self) -> None:
        """ウェルカムメッセージが含まれる。"""
        result = dashboard_page(email="test@example.com")
        assert "Welcome, test@example.com" in result

    def test_contains_lobbies_link(self) -> None:
        """Lobbies リンクが含まれる。"""
        result = dashboard_page()
        assert "/lobbies" in result

    def test_contains_sticky_link(self) -> None:
        """Sticky リンクが含まれる。"""
        result = dashboard_page()
        assert "/sticky" in result

    def test_contains_bump_link(self) -> None:
        """Bump リンクが含まれる。"""
        result = dashboard_page()
        assert "/bump" in result

    def test_contains_settings_link(self) -> None:
        """Settings リンクが含まれる。"""
        result = dashboard_page()
        assert "/settings" in result

    def test_email_is_escaped(self) -> None:
        """メールアドレスがエスケープされる。"""
        result = dashboard_page(email="<script>xss</script>")
        assert "&lt;script&gt;" in result


# ===========================================================================
# 設定ページ
# ===========================================================================


class TestSettingsPage:
    """settings_page テンプレートのテスト。"""

    def test_contains_email_change_link(self) -> None:
        """メール変更リンクが含まれる。"""
        result = settings_page(current_email="admin@example.com")
        assert 'href="/settings/email"' in result
        assert "Change Email" in result

    def test_contains_password_change_link(self) -> None:
        """パスワード変更リンクが含まれる。"""
        result = settings_page(current_email="admin@example.com")
        assert 'href="/settings/password"' in result
        assert "Change Password" in result

    def test_current_email_displayed(self) -> None:
        """現在のメールアドレスが表示される。"""
        result = settings_page(current_email="test@example.com")
        assert "test@example.com" in result

    def test_pending_email_displayed(self) -> None:
        """保留中のメールアドレスが表示される。"""
        result = settings_page(
            current_email="admin@example.com", pending_email="pending@example.com"
        )
        assert "pending@example.com" in result
        assert "Pending email change" in result


# ===========================================================================
# ロビー一覧ページ
# ===========================================================================


class TestLobbiesListPage:
    """lobbies_list_page テンプレートのテスト。"""

    def test_empty_list_message(self) -> None:
        """空リストの場合はメッセージが表示される。"""
        result = lobbies_list_page([])
        assert "No lobbies configured" in result

    def test_contains_table_headers(self) -> None:
        """テーブルヘッダーが含まれる。"""
        result = lobbies_list_page([])
        assert "Guild ID" in result
        assert "Channel ID" in result
        assert "User Limit" in result


# ===========================================================================
# Sticky 一覧ページ
# ===========================================================================


class TestStickyListPage:
    """sticky_list_page テンプレートのテスト。"""

    def test_empty_list_message(self) -> None:
        """空リストの場合はメッセージが表示される。"""
        result = sticky_list_page([])
        assert "No sticky messages configured" in result

    def test_contains_table_headers(self) -> None:
        """テーブルヘッダーが含まれる。"""
        result = sticky_list_page([])
        assert "Guild ID" in result
        assert "Channel ID" in result
        assert "Title" in result
        assert "Type" in result


# ===========================================================================
# Bump 一覧ページ
# ===========================================================================


class TestBumpListPage:
    """bump_list_page テンプレートのテスト。"""

    def test_empty_configs_message(self) -> None:
        """Config が空の場合はメッセージが表示される。"""
        result = bump_list_page([], [])
        assert "No bump configs" in result

    def test_empty_reminders_message(self) -> None:
        """Reminder が空の場合はメッセージが表示される。"""
        result = bump_list_page([], [])
        assert "No bump reminders" in result

    def test_contains_config_headers(self) -> None:
        """Config テーブルヘッダーが含まれる。"""
        result = bump_list_page([], [])
        assert "Bump Configs" in result

    def test_contains_reminder_headers(self) -> None:
        """Reminder テーブルヘッダーが含まれる。"""
        result = bump_list_page([], [])
        assert "Bump Reminders" in result
        assert "Service" in result
        assert "Status" in result


# ===========================================================================
# XSS 対策
# ===========================================================================


class TestXSSProtection:
    """XSS 対策のテスト。"""

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "<script>alert('xss')</script>",
            '"><script>alert("xss")</script>',
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
        ],
    )
    def test_login_error_escapes_xss(self, malicious_input: str) -> None:
        """ログインエラーで XSS がエスケープされる。"""
        result = login_page(error=malicious_input)
        # HTML tags should be escaped (< and > become &lt; and &gt;)
        assert "<script>" not in result
        assert "<img " not in result

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "<script>alert('xss')</script>",
            '"><script>alert("xss")</script>',
        ],
    )
    def test_dashboard_email_escapes_xss(self, malicious_input: str) -> None:
        """ダッシュボードのメールアドレスで XSS がエスケープされる。"""
        result = dashboard_page(email=malicious_input)
        assert "<script>" not in result

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "<script>alert('xss')</script>",
            '"><script>alert("xss")</script>',
        ],
    )
    def test_settings_email_escapes_xss(self, malicious_input: str) -> None:
        """設定ページのメールアドレスで XSS がエスケープされる。"""
        result = settings_page(current_email=malicious_input)
        assert "<script>" not in result
