"""Tests for email service module."""

from __future__ import annotations

import smtplib
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from src.constants import SMTP_SSL_PORT, SMTP_TIMEOUT_SECONDS

if TYPE_CHECKING:
    pass


class TestSendPasswordResetEmail:
    """send_password_reset_email 関数のテスト。"""

    def test_returns_false_when_smtp_not_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SMTP が設定されていない場合は False を返す。"""
        from src.config import settings

        # SMTP を無効化
        monkeypatch.setattr(settings, "smtp_host", "")

        from src.web.email_service import send_password_reset_email

        result = send_password_reset_email("test@example.com", "token123")
        assert result is False

    def test_returns_true_on_successful_send(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """メール送信成功時は True を返す。"""
        from src.config import settings

        # SMTP を有効化
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 587)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", True)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # SMTP をモック
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            from src.web.email_service import send_password_reset_email

            result = send_password_reset_email("test@example.com", "token123")
            assert result is True

        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@example.com", "password")
        mock_smtp.send_message.assert_called_once()

    def test_returns_true_on_successful_send_without_tls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TLS なしでのメール送信成功時は True を返す。"""
        from src.config import settings

        # SMTP を有効化 (TLS なし、認証あり)
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 25)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "")  # from_email なし
        monkeypatch.setattr(settings, "smtp_use_tls", False)  # TLS なし
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # SMTP をモック
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            from src.web.email_service import send_password_reset_email

            result = send_password_reset_email("test@example.com", "token123")
            assert result is True

        # TLS なしなので starttls は呼ばれない
        mock_smtp.starttls.assert_not_called()
        mock_smtp.login.assert_called_once_with("user@example.com", "password")
        mock_smtp.send_message.assert_called_once()

    def test_returns_true_on_successful_send_without_auth(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """認証なしでのメール送信成功時は True を返す。"""
        from src.config import settings

        # SMTP を有効化 (認証なし - Mailpit のような場合)
        monkeypatch.setattr(settings, "smtp_host", "localhost")
        monkeypatch.setattr(settings, "smtp_port", 1025)
        monkeypatch.setattr(settings, "smtp_user", "")
        monkeypatch.setattr(settings, "smtp_password", "")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", False)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # SMTP をモック
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            from src.web.email_service import send_password_reset_email

            result = send_password_reset_email("test@example.com", "token123")
            assert result is True

        # 認証なしなので login は呼ばれない
        mock_smtp.starttls.assert_not_called()
        mock_smtp.login.assert_not_called()
        mock_smtp.send_message.assert_called_once()

    def test_returns_false_on_smtp_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SMTP エラー時は False を返す。"""
        import smtplib

        from src.config import settings

        # SMTP を有効化
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 587)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", True)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # SMTP 接続エラーをシミュレート
        smtp_error = smtplib.SMTPException("Connection failed")
        with patch("smtplib.SMTP", side_effect=smtp_error):
            from src.web.email_service import send_password_reset_email

            result = send_password_reset_email("test@example.com", "token123")
            assert result is False

    def test_returns_false_on_os_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OSError 時は False を返す。"""
        from src.config import settings

        # SMTP を有効化
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 587)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", True)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # OSError をシミュレート
        with patch("smtplib.SMTP", side_effect=OSError("Network unreachable")):
            from src.web.email_service import send_password_reset_email

            result = send_password_reset_email("test@example.com", "token123")
            assert result is False


class TestSendEmailChangeVerification:
    """send_email_change_verification 関数のテスト。"""

    def test_returns_false_when_smtp_not_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SMTP が設定されていない場合は False を返す。"""
        from src.config import settings

        # SMTP を無効化
        monkeypatch.setattr(settings, "smtp_host", "")

        from src.web.email_service import send_email_change_verification

        result = send_email_change_verification("new@example.com", "token123")
        assert result is False

    def test_returns_true_on_successful_send(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """メール送信成功時は True を返す。"""
        from src.config import settings

        # SMTP を有効化
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 587)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", True)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # SMTP をモック
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            from src.web.email_service import send_email_change_verification

            result = send_email_change_verification("new@example.com", "token123")
            assert result is True

        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@example.com", "password")
        mock_smtp.send_message.assert_called_once()

    def test_returns_true_on_successful_send_without_tls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TLS なしでのメール送信成功時は True を返す。"""
        from src.config import settings

        # SMTP を有効化 (TLS なし、認証あり)
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 25)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "")
        monkeypatch.setattr(settings, "smtp_use_tls", False)  # TLS なし
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # SMTP をモック
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            from src.web.email_service import send_email_change_verification

            result = send_email_change_verification("new@example.com", "token123")
            assert result is True

        # TLS なしなので starttls は呼ばれない
        mock_smtp.starttls.assert_not_called()
        mock_smtp.login.assert_called_once_with("user@example.com", "password")
        mock_smtp.send_message.assert_called_once()

    def test_returns_true_on_successful_send_without_auth(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """認証なしでのメール送信成功時は True を返す。"""
        from src.config import settings

        # SMTP を有効化 (認証なし - Mailpit のような場合)
        monkeypatch.setattr(settings, "smtp_host", "localhost")
        monkeypatch.setattr(settings, "smtp_port", 1025)
        monkeypatch.setattr(settings, "smtp_user", "")
        monkeypatch.setattr(settings, "smtp_password", "")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", False)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # SMTP をモック
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            from src.web.email_service import send_email_change_verification

            result = send_email_change_verification("new@example.com", "token123")
            assert result is True

        # 認証なしなので login は呼ばれない
        mock_smtp.starttls.assert_not_called()
        mock_smtp.login.assert_not_called()
        mock_smtp.send_message.assert_called_once()

    def test_returns_false_on_smtp_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SMTP エラー時は False を返す。"""
        from src.config import settings

        # SMTP を有効化
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 587)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", True)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # SMTP 接続エラーをシミュレート
        smtp_error = smtplib.SMTPException("Connection failed")
        with patch("smtplib.SMTP", side_effect=smtp_error):
            from src.web.email_service import send_email_change_verification

            result = send_email_change_verification("new@example.com", "token123")
            assert result is False


# ===========================================================================
# Linux 互換性テスト (ポート465 / SMTPS, タイムアウト)
# ===========================================================================


class TestSmtpSSLPort465:
    """ポート 465 (SMTPS / 暗黙的 TLS) のテスト。"""

    def test_uses_smtp_ssl_for_port_465(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ポート 465 では SMTP_SSL を使用する。"""
        from src.config import settings

        # ポート 465 (SMTPS) を設定
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", SMTP_SSL_PORT)  # 465
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", False)  # SMTPS では不要
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # SMTP_SSL をモック
        mock_smtp_ssl = MagicMock()
        mock_smtp_ssl.__enter__ = MagicMock(return_value=mock_smtp_ssl)
        mock_smtp_ssl.__exit__ = MagicMock(return_value=False)

        ssl_patch = "src.web.email_service.smtplib.SMTP_SSL"
        smtp_patch = "src.web.email_service.smtplib.SMTP"
        with (
            patch(ssl_patch, return_value=mock_smtp_ssl) as mock_ssl_class,
            patch(smtp_patch) as mock_smtp_class,
        ):
            from src.web.email_service import send_password_reset_email

            result = send_password_reset_email("test@example.com", "token123")

            assert result is True
            # SMTP_SSL が呼ばれる (SMTP ではない)
            mock_ssl_class.assert_called_once_with(
                "smtp.example.com",
                SMTP_SSL_PORT,
                timeout=SMTP_TIMEOUT_SECONDS,
            )
            mock_smtp_class.assert_not_called()

    def test_smtp_ssl_with_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ポート 465 で認証が正しく行われる。"""
        from src.config import settings

        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", SMTP_SSL_PORT)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "secret123")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", False)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        mock_smtp_ssl = MagicMock()
        mock_smtp_ssl.__enter__ = MagicMock(return_value=mock_smtp_ssl)
        mock_smtp_ssl.__exit__ = MagicMock(return_value=False)

        ssl_patch = "src.web.email_service.smtplib.SMTP_SSL"
        with patch(ssl_patch, return_value=mock_smtp_ssl):
            from src.web.email_service import send_password_reset_email

            result = send_password_reset_email("test@example.com", "token123")

            assert result is True
            mock_smtp_ssl.login.assert_called_once_with("user@example.com", "secret123")


class TestSmtpTimeout:
    """SMTP タイムアウトのテスト。"""

    def test_smtp_uses_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SMTP 接続にタイムアウトが設定される。"""
        from src.config import settings

        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 587)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", True)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        smtp_patch = "src.web.email_service.smtplib.SMTP"
        with patch(smtp_patch, return_value=mock_smtp) as mock_class:
            from src.web.email_service import send_password_reset_email

            send_password_reset_email("test@example.com", "token123")

            # timeout パラメータが渡される
            mock_class.assert_called_once_with(
                "smtp.example.com",
                587,
                timeout=SMTP_TIMEOUT_SECONDS,
            )

    def test_returns_false_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """タイムアウト時は False を返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 587)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", True)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # TimeoutError をシミュレート
        smtp_patch = "src.web.email_service.smtplib.SMTP"
        timeout_err = TimeoutError("Connection timed out")
        with patch(smtp_patch, side_effect=timeout_err):
            from src.web.email_service import send_password_reset_email

            result = send_password_reset_email("test@example.com", "token123")
            assert result is False

    def test_smtp_ssl_returns_false_on_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SMTP_SSL でタイムアウト時は False を返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", SMTP_SSL_PORT)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", False)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        # TimeoutError をシミュレート
        ssl_patch = "src.web.email_service.smtplib.SMTP_SSL"
        timeout_err = TimeoutError("Connection timed out")
        with patch(ssl_patch, side_effect=timeout_err):
            from src.web.email_service import send_password_reset_email

            result = send_password_reset_email("test@example.com", "token123")
            assert result is False


class TestSendEmailChangeVerificationPort465:
    """send_email_change_verification のポート 465 (SMTPS) テスト。"""

    def test_uses_smtp_ssl_for_port_465(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ポート 465 では SMTP_SSL を使用する。"""
        from src.config import settings

        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", SMTP_SSL_PORT)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", False)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        mock_smtp_ssl = MagicMock()
        mock_smtp_ssl.__enter__ = MagicMock(return_value=mock_smtp_ssl)
        mock_smtp_ssl.__exit__ = MagicMock(return_value=False)

        ssl_patch = "src.web.email_service.smtplib.SMTP_SSL"
        smtp_patch = "src.web.email_service.smtplib.SMTP"
        with (
            patch(ssl_patch, return_value=mock_smtp_ssl) as mock_ssl_class,
            patch(smtp_patch) as mock_smtp_class,
        ):
            from src.web.email_service import send_email_change_verification

            result = send_email_change_verification("new@example.com", "token123")

            assert result is True
            mock_ssl_class.assert_called_once_with(
                "smtp.example.com",
                SMTP_SSL_PORT,
                timeout=SMTP_TIMEOUT_SECONDS,
            )
            mock_smtp_class.assert_not_called()

    def test_returns_false_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SMTP_SSL でタイムアウト時は False を返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", SMTP_SSL_PORT)
        monkeypatch.setattr(settings, "smtp_user", "user@example.com")
        monkeypatch.setattr(settings, "smtp_password", "password")
        monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_use_tls", False)
        monkeypatch.setattr(settings, "app_url", "http://localhost:8000")

        ssl_patch = "src.web.email_service.smtplib.SMTP_SSL"
        timeout_err = TimeoutError("Connection timed out")
        with patch(ssl_patch, side_effect=timeout_err):
            from src.web.email_service import send_email_change_verification

            result = send_email_change_verification("new@example.com", "token123")
            assert result is False
