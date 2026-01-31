"""Email service for sending password reset and email verification emails.

パスワードリセットやメールアドレス変更時の確認メールを送信する。

Notes:
    Linux 環境での SMTP 接続について:

    - SMTP 接続にはタイムアウトを設定する (ハングアップ防止)
    - ポート 465 (SMTPS) は SMTP_SSL を使用 (暗黙的 TLS)
    - ポート 587 は SMTP + STARTTLS を使用 (明示的 TLS)

See Also:
    - :data:`src.constants.SMTP_TIMEOUT_SECONDS`: 接続タイムアウト
    - :data:`src.constants.SMTP_SSL_PORT`: SMTPS ポート番号
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import settings
from src.constants import SMTP_SSL_PORT, SMTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


def _send_email(msg: MIMEMultipart) -> bool:
    """SMTPサーバー経由でメールを送信する (内部ヘルパー関数)。

    ポート番号に応じて適切な接続方式を選択する:
    - ポート 465: SMTP_SSL (暗黙的 TLS / SMTPS)
    - その他: SMTP + STARTTLS (明示的 TLS)

    Args:
        msg: 送信するメッセージ (MIMEMultipart)

    Returns:
        True if successful, False otherwise

    Notes:
        Linux 環境でハングアップを防ぐため、タイムアウトを設定している。
        Ubuntu/CentOS 等で DNS 解決やネットワーク接続に問題がある場合、
        タイムアウトがないと無限に待機してしまう。
    """
    try:
        # ポート 465 (SMTPS) は暗黙的 TLS を使用
        if settings.smtp_port == SMTP_SSL_PORT:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=SMTP_TIMEOUT_SECONDS,
            ) as server:
                if settings.smtp_auth_required:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            # ポート 587 等は STARTTLS を使用
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=SMTP_TIMEOUT_SECONDS,
            ) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_auth_required:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        return True
    except TimeoutError:
        logger.error(
            "SMTP connection timed out after %d seconds to %s:%d",
            SMTP_TIMEOUT_SECONDS,
            settings.smtp_host,
            settings.smtp_port,
        )
        return False
    except (smtplib.SMTPException, OSError) as e:
        logger.error("SMTP error: %s", e)
        return False


def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    """Send a password reset email.

    Args:
        to_email: Recipient email address
        reset_token: Password reset token

    Returns:
        True if email was sent successfully, False otherwise
    """
    if not settings.smtp_enabled:
        logger.warning(
            "SMTP is not configured. Password reset email not sent. "
            "Set SMTP_HOST environment variable to enable email sending."
        )
        return False

    reset_url = f"{settings.app_url}/reset-password?token={reset_token}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Password Reset Request"
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = to_email

    # プレーンテキスト版
    text = f"""Password Reset Request

You requested to reset your password.

Click the link below to reset your password:
{reset_url}

This link will expire in 1 hour.

If you did not request this, please ignore this email.
"""

    # HTML 版
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #333;">Password Reset Request</h2>
    <p>You requested to reset your password.</p>
    <p>Click the button below to reset your password:</p>
    <p style="margin: 30px 0;">
        <a href="{reset_url}"
           style="background-color: #4CAF50; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 4px; display: inline-block;">
            Reset Password
        </a>
    </p>
    <p style="color: #666; font-size: 14px;">
        Or copy and paste this link into your browser:<br>
        <a href="{reset_url}" style="color: #1a73e8;">{reset_url}</a>
    </p>
    <p style="color: #666; font-size: 14px;">This link will expire in 1 hour.</p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
    <p style="color: #999; font-size: 12px;">
        If you did not request this password reset, please ignore this email.
    </p>
</body>
</html>
"""

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    if _send_email(msg):
        logger.info("Password reset email sent to %s", to_email)
        return True
    else:
        logger.error("Failed to send password reset email to %s", to_email)
        return False


def send_email_change_verification(to_email: str, token: str) -> bool:
    """Send an email change verification email.

    Args:
        to_email: New email address to verify
        token: Email change verification token

    Returns:
        True if email was sent successfully, False otherwise
    """
    if not settings.smtp_enabled:
        logger.warning(
            "SMTP is not configured. Email verification not sent. "
            "Set SMTP_HOST environment variable to enable email sending."
        )
        return False

    confirm_url = f"{settings.app_url}/confirm-email?token={token}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Confirm Your Email Address"
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = to_email

    # プレーンテキスト版
    text = f"""Confirm Your Email Address

You requested to change your email address to this address.

Click the link below to confirm this change:
{confirm_url}

This link will expire in 1 hour.

If you did not request this, please ignore this email.
"""

    # HTML 版
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #333;">Confirm Your Email Address</h2>
    <p>You requested to change your email address to this address.</p>
    <p>Click the button below to confirm this change:</p>
    <p style="margin: 30px 0;">
        <a href="{confirm_url}"
           style="background-color: #4CAF50; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 4px; display: inline-block;">
            Confirm Email
        </a>
    </p>
    <p style="color: #666; font-size: 14px;">
        Or copy and paste this link into your browser:<br>
        <a href="{confirm_url}" style="color: #1a73e8;">{confirm_url}</a>
    </p>
    <p style="color: #666; font-size: 14px;">This link will expire in 1 hour.</p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
    <p style="color: #999; font-size: 12px;">
        If you did not request this email change, please ignore this email.
    </p>
</body>
</html>
"""

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    if _send_email(msg):
        logger.info("Email verification sent to %s", to_email)
        return True
    else:
        logger.error("Failed to send email verification to %s", to_email)
        return False
