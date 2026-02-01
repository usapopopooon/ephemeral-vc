"""FastAPI web admin application."""

import logging
import os
import re
import secrets
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

import bcrypt
from fastapi import Cookie, Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.constants import (
    BCRYPT_MAX_PASSWORD_BYTES,
    EMAIL_CHANGE_TOKEN_EXPIRY_SECONDS,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_SECONDS,
    PASSWORD_MIN_LENGTH,
    RATE_LIMIT_CLEANUP_INTERVAL_SECONDS,
    # RESET_TOKEN_EXPIRY_SECONDS,  # SMTP 未設定のため未使用
    SESSION_MAX_AGE_SECONDS,
    TOKEN_BYTE_LENGTH,
)
from src.database.engine import async_session, check_database_connection
from src.database.models import (
    AdminUser,
    BumpConfig,
    BumpReminder,
    Lobby,
    RolePanel,
    RolePanelItem,
    StickyMessage,
)
from src.web.email_service import (
    send_email_change_verification,  # noqa: F401  # SMTP 設定時に使用
    # send_password_reset_email,  # SMTP 未設定のため未使用
)
from src.web.templates import (
    bump_list_page,
    dashboard_page,
    email_change_page,
    email_verification_pending_page,
    forgot_password_page,
    initial_setup_page,
    lobbies_list_page,
    login_page,
    password_change_page,
    reset_password_page,
    role_panel_create_page,
    role_panels_list_page,
    settings_page,
    sticky_list_page,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan handler for startup/shutdown events."""
    # Startup: データベース接続をチェック
    logger.info("Starting web admin application...")
    if not await check_database_connection():
        logger.error(
            "Database connection failed. "
            "Check DATABASE_URL and ensure the database is running."
        )
        # Web アプリはデータベースがなくても起動を許可する (ヘルスチェック用)
        # ただし、機能は制限される
    else:
        logger.info("Database connection successful")
    yield
    # シャットダウン
    logger.info("Shutting down web admin application...")


app = FastAPI(title="Bot Admin", docs_url=None, redoc_url=None, lifespan=lifespan)

# セッション設定
_session_secret_from_env = os.environ.get("SESSION_SECRET_KEY", "").strip()
if not _session_secret_from_env:
    logger.warning(
        "SESSION_SECRET_KEY is not set. Using a random key. "
        "Sessions will be invalidated on restart. "
        "Set SESSION_SECRET_KEY environment variable for persistent sessions."
    )
    SECRET_KEY = secrets.token_hex(TOKEN_BYTE_LENGTH)
else:
    SECRET_KEY = _session_secret_from_env

# config.py の設定を使用して一貫性を保つ
# 空白のみのパスワードは空として扱う
INIT_ADMIN_EMAIL = settings.admin_email.strip()
INIT_ADMIN_PASSWORD = settings.admin_password.strip() if settings.admin_password else ""
SECURE_COOKIE = os.environ.get("SECURE_COOKIE", "true").lower() == "true"

# レート制限 (インメモリ、再起動時にリセット)
LOGIN_ATTEMPTS: dict[str, list[float]] = {}

# メールアドレス検証パターン
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

serializer = URLSafeTimedSerializer(SECRET_KEY)


# =============================================================================
# パスワードユーティリティ
# =============================================================================


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Note: bcrypt 4.x は72バイトを超えるパスワードで ValueError を発生させる。
    入力検証で長いパスワードを事前に拒否することを推奨。
    """
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        # bcrypt 4.x は72バイトを超えるパスワードでエラーを発生させる
        # 手動で切り詰めてハッシュ化 (セキュリティ上の考慮が必要)
        logger.warning(
            "Password exceeds %d bytes, truncating",
            BCRYPT_MAX_PASSWORD_BYTES,
        )
        password_bytes = password_bytes[:BCRYPT_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # 無効なハッシュ形式の場合
        return False


# =============================================================================
# データベースユーティリティ
# =============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency."""
    async with async_session() as session:
        yield session


async def get_or_create_admin(db: AsyncSession) -> AdminUser | None:
    """Get admin user, create from env vars if not exists."""
    result = await db.execute(select(AdminUser).limit(1))
    admin = result.scalar_one_or_none()

    if admin is None and INIT_ADMIN_PASSWORD:
        # 環境変数から初期管理者を作成（認証済みとして設定）
        admin = AdminUser(
            email=INIT_ADMIN_EMAIL,
            password_hash=hash_password(INIT_ADMIN_PASSWORD),
            email_verified=True,
            password_changed_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

    return admin


# =============================================================================
# レート制限
# =============================================================================

# メモリリーク防止: 古いエントリを定期的にクリーンアップ
_last_cleanup_time: float = 0.0


def _cleanup_old_rate_limit_entries() -> None:
    """古いレート制限エントリをクリーンアップする。"""
    global _last_cleanup_time
    now = time.time()

    if now - _last_cleanup_time < RATE_LIMIT_CLEANUP_INTERVAL_SECONDS:
        return

    _last_cleanup_time = now
    # 期限切れのIPアドレスを削除
    ips_to_remove = []
    for ip, attempts in LOGIN_ATTEMPTS.items():
        valid_attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
        if not valid_attempts:
            ips_to_remove.append(ip)
        else:
            LOGIN_ATTEMPTS[ip] = valid_attempts

    for ip in ips_to_remove:
        del LOGIN_ATTEMPTS[ip]


def is_rate_limited(ip: str) -> bool:
    """Check if IP is rate limited."""
    _cleanup_old_rate_limit_entries()

    now = time.time()
    attempts = LOGIN_ATTEMPTS.get(ip, [])
    attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
    LOGIN_ATTEMPTS[ip] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


def record_failed_attempt(ip: str) -> None:
    """Record a failed login attempt."""
    if not ip:
        return
    now = time.time()
    if ip not in LOGIN_ATTEMPTS:
        LOGIN_ATTEMPTS[ip] = []
    LOGIN_ATTEMPTS[ip].append(now)


# =============================================================================
# セッションユーティリティ
# =============================================================================


def create_session_token(email: str) -> str:
    """Create a signed session token."""
    return serializer.dumps({"authenticated": True, "email": email})


def verify_session_token(token: str) -> dict[str, Any] | None:
    """Verify a session token and return data."""
    if not token or not token.strip():
        return None
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        if data.get("authenticated"):
            return cast(dict[str, Any], data)
        return None
    except (BadSignature, TypeError, ValueError):
        # BadSignature: 無効な署名またはトークンの改ざん
        # TypeError: トークンのデシリアライズ失敗
        # ValueError: 不正なトークン形式
        return None


def get_current_user(
    session: Annotated[str | None, Cookie(alias="session")] = None,
) -> dict[str, Any] | None:
    """Check if user is authenticated, return session data."""
    if not session:
        return None
    return verify_session_token(session)


# =============================================================================
# 認証ルート
# =============================================================================


@app.get("/health", response_model=None)
async def health_check() -> Response:
    """Health check endpoint for Docker/load balancer health checks.

    Returns 200 if the application is running and can connect to the database.
    Returns 503 if the database connection fails.
    """
    if await check_database_connection():
        return Response(content="ok", media_type="text/plain", status_code=200)
    return Response(
        content="database unavailable", media_type="text/plain", status_code=503
    )


@app.get("/", response_model=None)
async def index(
    user: dict[str, Any] | None = Depends(get_current_user),
) -> Response:
    """Redirect to dashboard or login."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_model=None)
async def login_get(
    user: dict[str, Any] | None = Depends(get_current_user),
) -> Response:
    """Show login page."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return HTMLResponse(content=login_page())


@app.post("/login", response_model=None)
async def login_post(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Process login form."""
    client_ip = request.client.host if request.client else "unknown"

    # メールアドレスは前後の空白をトリムする (パスワードはトリムしない)
    email = email.strip() if email else ""

    if is_rate_limited(client_ip):
        return HTMLResponse(
            content=login_page(error="Too many attempts. Try again later."),
            status_code=429,
        )

    # 管理者ユーザーを取得または作成
    admin = await get_or_create_admin(db)
    if admin is None:
        return HTMLResponse(
            content=login_page(error="ADMIN_PASSWORD not configured"),
            status_code=500,
        )

    # 認証情報を検証 (メールアドレスは大文字小文字を区別)
    if admin.email != email or not verify_password(password, admin.password_hash):
        record_failed_attempt(client_ip)
        return HTMLResponse(
            content=login_page(error="Invalid email or password"),
            status_code=401,
        )

    # セットアップ状況に応じてリダイレクト先を決定
    if admin.password_changed_at is None:
        # 初期セットアップが必要 (メールアドレス + パスワード)
        redirect_url = "/initial-setup"
    elif not admin.email_verified:
        # メールアドレス認証が必要
        redirect_url = "/verify-email"
    else:
        redirect_url = "/dashboard"

    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key="session",
        value=create_session_token(email),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=SECURE_COOKIE,
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout() -> RedirectResponse:
    """Logout and clear session."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="session")
    return response


# =============================================================================
# 初期セットアップルート
# =============================================================================


@app.get("/initial-setup", response_model=None)
async def initial_setup_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show initial setup page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # セットアップ済み
    if admin.password_changed_at is not None:
        if not admin.email_verified:
            return RedirectResponse(url="/verify-email", status_code=302)
        return RedirectResponse(url="/dashboard", status_code=302)

    return HTMLResponse(content=initial_setup_page(current_email=admin.email))


@app.post("/initial-setup", response_model=None)
async def initial_setup_post(
    user: dict[str, Any] | None = Depends(get_current_user),
    new_email: Annotated[str, Form()] = "",
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Process initial setup form."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 入力値のトリム (パスワードはトリムしない)
    new_email = new_email.strip() if new_email else ""

    # メールアドレスのバリデーション
    if not new_email:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Email address is required",
            )
        )

    if not EMAIL_PATTERN.match(new_email):
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Invalid email format",
            )
        )

    # パスワードのバリデーション
    if not new_password:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Password is required",
            )
        )

    if new_password != confirm_password:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Passwords do not match",
            )
        )

    if len(new_password) < PASSWORD_MIN_LENGTH:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error=f"Password must be at least {PASSWORD_MIN_LENGTH} characters",
            )
        )

    # bcrypt の制限を超えるパスワードは警告を表示
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error=f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes",
            )
        )

    # パスワードを更新
    admin.password_hash = hash_password(new_password)
    admin.password_changed_at = datetime.now(UTC)

    # メールアドレスを直接更新（SMTP 未設定のため認証スキップ）
    admin.email = new_email
    admin.email_verified = True
    admin.pending_email = None
    admin.email_change_token = None
    admin.email_change_token_expires_at = None

    # # 保留中のメールアドレスを設定し、認証トークンを生成
    # token = secrets.token_urlsafe(TOKEN_BYTE_LENGTH)
    # admin.pending_email = new_email
    # admin.email_change_token = token
    # admin.email_change_token_expires_at = datetime.now(UTC) + timedelta(
    #     seconds=EMAIL_CHANGE_TOKEN_EXPIRY_SECONDS
    # )

    await db.commit()

    # # 認証メールを送信
    # email_sent = send_email_change_verification(new_email, token)
    #
    # # メール送信失敗時は警告付きで認証待ちページにリダイレクト
    # if not email_sent:
    #     return HTMLResponse(
    #         content=email_verification_pending_page(
    #             pending_email=new_email,
    #             error="Failed to send verification email. Check SMTP configuration.",
    #         )
    #     )
    #
    # return RedirectResponse(url="/verify-email", status_code=302)

    # セッションを更新してダッシュボードにリダイレクト
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="session",
        value=create_session_token(new_email),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=SECURE_COOKIE,
        samesite="lax",
    )
    return response


@app.get("/verify-email", response_model=None)
async def verify_email_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show email verification pending page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 認証済み
    if admin.email_verified:
        return RedirectResponse(url="/dashboard", status_code=302)

    # 保留中のメールがない (通常は発生しないが、念のため処理)
    if not admin.pending_email:
        return RedirectResponse(url="/dashboard", status_code=302)

    return HTMLResponse(
        content=email_verification_pending_page(pending_email=admin.pending_email)
    )


@app.post("/resend-verification", response_model=None)
async def resend_verification(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Resend verification email."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    if not admin.pending_email:
        return RedirectResponse(url="/dashboard", status_code=302)

    # 新しいトークンを生成
    token = secrets.token_urlsafe(TOKEN_BYTE_LENGTH)
    admin.email_change_token = token
    admin.email_change_token_expires_at = datetime.now(UTC) + timedelta(
        seconds=EMAIL_CHANGE_TOKEN_EXPIRY_SECONDS
    )
    await db.commit()

    # 認証メールを送信
    email_sent = send_email_change_verification(admin.pending_email, token)

    if email_sent:
        return HTMLResponse(
            content=email_verification_pending_page(
                pending_email=admin.pending_email,
                success="Verification email sent.",
            )
        )
    else:
        return HTMLResponse(
            content=email_verification_pending_page(
                pending_email=admin.pending_email,
                error="Failed to send verification email. Check SMTP configuration.",
            )
        )


# =============================================================================
# パスワードリセットルート
# =============================================================================


@app.get("/forgot-password", response_model=None)
async def forgot_password_get() -> Response:
    """Show forgot password page."""
    return HTMLResponse(content=forgot_password_page())


@app.post("/forgot-password", response_model=None)
async def forgot_password_post(
    email: Annotated[str, Form()],
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Process forgot password form."""
    # 入力値のトリム
    email = email.strip() if email else ""

    # # メールアドレスの存在を推測されないよう、常に成功メッセージを表示
    # success_message = (
    #     "If an account exists with that email, a reset link has been sent."
    # )
    #
    # # メールアドレスで管理者を検索
    # result = await db.execute(select(AdminUser).where(AdminUser.email == email))
    # admin = result.scalar_one_or_none()
    #
    # if admin:
    #     # リセットトークンを生成
    #     token = secrets.token_urlsafe(TOKEN_BYTE_LENGTH)
    #     admin.reset_token = token
    #     admin.reset_token_expires_at = datetime.now(UTC) + timedelta(
    #         seconds=RESET_TOKEN_EXPIRY_SECONDS
    #     )
    #     await db.commit()
    #
    #     # メールを送信
    #     send_password_reset_email(admin.email, token)
    #
    # return HTMLResponse(content=forgot_password_page(success=success_message))

    # SMTP 未設定のエラーメッセージを表示
    _ = email, db  # unused variable warning 回避
    return HTMLResponse(
        content=forgot_password_page(
            error="Password reset is not available. SMTP is not configured."
        )
    )


@app.get("/reset-password", response_model=None)
async def reset_password_get(
    token: str = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show reset password page."""
    # トークンのトリム
    token = token.strip() if token else ""

    if not token:
        return HTMLResponse(
            content=forgot_password_page(error="Invalid or missing reset token.")
        )

    # トークンが存在し、有効期限内であることを確認
    result = await db.execute(select(AdminUser).where(AdminUser.reset_token == token))
    admin = result.scalar_one_or_none()

    if not admin or not admin.reset_token_expires_at:
        return HTMLResponse(
            content=forgot_password_page(error="Invalid or expired reset token.")
        )

    if admin.reset_token_expires_at < datetime.now(UTC):
        return HTMLResponse(
            content=forgot_password_page(error="Reset token has expired.")
        )

    return HTMLResponse(content=reset_password_page(token=token))


@app.post("/reset-password", response_model=None)
async def reset_password_post(
    token: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Process reset password form."""
    # パスワードの一致を検証
    if new_password != confirm_password:
        return HTMLResponse(
            content=reset_password_page(token=token, error="Passwords do not match")
        )

    # パスワードの長さを検証
    if len(new_password) < PASSWORD_MIN_LENGTH:
        return HTMLResponse(
            content=reset_password_page(
                token=token,
                error=f"Password must be at least {PASSWORD_MIN_LENGTH} characters",
            )
        )

    # bcrypt の制限を超えるパスワードは拒否
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        error_msg = f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes"
        return HTMLResponse(content=reset_password_page(token=token, error=error_msg))

    # トークンで管理者を検索
    result = await db.execute(select(AdminUser).where(AdminUser.reset_token == token))
    admin = result.scalar_one_or_none()

    if not admin or not admin.reset_token_expires_at:
        return HTMLResponse(
            content=forgot_password_page(error="Invalid or expired reset token.")
        )

    if admin.reset_token_expires_at < datetime.now(UTC):
        return HTMLResponse(
            content=forgot_password_page(error="Reset token has expired.")
        )

    # パスワードを更新し、リセットトークンをクリア
    admin.password_hash = hash_password(new_password)
    admin.password_changed_at = datetime.now(UTC)
    admin.reset_token = None
    admin.reset_token_expires_at = None
    await db.commit()

    return HTMLResponse(
        content=login_page(error=None),
    )


@app.get("/dashboard", response_model=None)
async def dashboard(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show dashboard."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin:
        # パスワードが一度も変更されていない場合は初期セットアップにリダイレクト
        if admin.password_changed_at is None:
            return RedirectResponse(url="/initial-setup", status_code=302)
        # メールアドレス未認証の場合は認証ページにリダイレクト
        if not admin.email_verified:
            return RedirectResponse(url="/verify-email", status_code=302)

    return HTMLResponse(content=dashboard_page(email=user.get("email", "Admin")))


# =============================================================================
# 設定ルート
# =============================================================================


@app.get("/settings", response_model=None)
async def settings_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show settings hub page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # パスワードが一度も変更されていない場合は初期セットアップにリダイレクト
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス未認証の場合は認証ページにリダイレクト
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    return HTMLResponse(
        content=settings_page(
            current_email=admin.email,
            pending_email=admin.pending_email,
        )
    )


@app.get("/settings/email", response_model=None)
async def settings_email_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show email change page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 初期セットアップが先に必要
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス認証が先に必要
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    return HTMLResponse(
        content=email_change_page(
            current_email=admin.email,
            pending_email=admin.pending_email,
        )
    )


@app.post("/settings/email", response_model=None)
async def settings_email_post(
    user: dict[str, Any] | None = Depends(get_current_user),
    new_email: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Update email address."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 入力値のトリム
    new_email = new_email.strip() if new_email else ""

    # バリデーション
    if not new_email:
        return HTMLResponse(
            content=email_change_page(
                current_email=admin.email,
                pending_email=admin.pending_email,
                error="Email address is required",
            )
        )

    if not EMAIL_PATTERN.match(new_email):
        return HTMLResponse(
            content=email_change_page(
                current_email=admin.email,
                pending_email=admin.pending_email,
                error="Invalid email format",
            )
        )

    if new_email == admin.email:
        return HTMLResponse(
            content=email_change_page(
                current_email=admin.email,
                pending_email=admin.pending_email,
                error="New email must be different from current email",
            )
        )

    # メールアドレスを直接更新（SMTP 未設定のため認証スキップ）
    admin.email = new_email
    admin.pending_email = None
    admin.email_change_token = None
    admin.email_change_token_expires_at = None

    # # 認証トークンを生成し、保留中のメールアドレスを保存
    # token = secrets.token_urlsafe(TOKEN_BYTE_LENGTH)
    # admin.pending_email = new_email
    # admin.email_change_token = token
    # admin.email_change_token_expires_at = datetime.now(UTC) + timedelta(
    #     seconds=EMAIL_CHANGE_TOKEN_EXPIRY_SECONDS
    # )

    await db.commit()

    # # 新しいメールアドレスに認証メールを送信
    # email_sent = send_email_change_verification(new_email, token)
    #
    # if email_sent:
    #     return HTMLResponse(
    #         content=email_change_page(
    #             current_email=admin.email,
    #             pending_email=admin.pending_email,
    #             success="Verification email sent. Please check your inbox.",
    #         )
    #     )
    # else:
    #     return HTMLResponse(
    #         content=email_change_page(
    #             current_email=admin.email,
    #             pending_email=admin.pending_email,
    #             error="Failed to send verification email. Check SMTP configuration.",
    #         )
    #     )

    # セッションを更新してリダイレクト
    response = RedirectResponse(url="/settings", status_code=302)
    response.set_cookie(
        key="session",
        value=create_session_token(new_email),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=SECURE_COOKIE,
        samesite="lax",
    )
    return response


@app.get("/settings/password", response_model=None)
async def settings_password_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show password change page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 初期セットアップが先に必要
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス認証が先に必要
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    return HTMLResponse(content=password_change_page())


@app.post("/settings/password", response_model=None)
async def settings_password_post(
    user: dict[str, Any] | None = Depends(get_current_user),
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Update password."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 初期セットアップが先に必要
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス認証が先に必要
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    # バリデーション
    if not new_password:
        return HTMLResponse(content=password_change_page(error="Password is required"))

    if new_password != confirm_password:
        return HTMLResponse(
            content=password_change_page(error="Passwords do not match")
        )

    if len(new_password) < PASSWORD_MIN_LENGTH:
        return HTMLResponse(
            content=password_change_page(
                error=f"Password must be at least {PASSWORD_MIN_LENGTH} characters"
            )
        )

    # bcrypt の制限を超えるパスワードは拒否
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return HTMLResponse(
            content=password_change_page(
                error=f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes"
            )
        )

    # パスワードを更新
    admin.password_hash = hash_password(new_password)
    admin.password_changed_at = datetime.now(UTC)
    await db.commit()

    # パスワード変更後はログアウト
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="session")
    return response


# =============================================================================
# メールアドレス変更確認ルート
# =============================================================================


@app.get("/confirm-email", response_model=None)
async def confirm_email(
    token: str = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Confirm email change."""
    # トークンのトリム
    token = token.strip() if token else ""

    if not token:
        return HTMLResponse(
            content=login_page(error="Invalid or missing confirmation token.")
        )

    # トークンで管理者を検索
    result = await db.execute(
        select(AdminUser).where(AdminUser.email_change_token == token)
    )
    admin = result.scalar_one_or_none()

    if not admin or not admin.email_change_token_expires_at or not admin.pending_email:
        return HTMLResponse(
            content=login_page(error="Invalid or expired confirmation token.")
        )

    if admin.email_change_token_expires_at < datetime.now(UTC):
        return HTMLResponse(content=login_page(error="Confirmation token has expired."))

    # メールアドレスを更新し、認証済みに設定し、保留中フィールドをクリア
    admin.email = admin.pending_email
    admin.email_verified = True
    admin.pending_email = None
    admin.email_change_token = None
    admin.email_change_token_expires_at = None
    await db.commit()

    return HTMLResponse(
        content=login_page(error=None),
    )


# =============================================================================
# ロビールート
# =============================================================================


@app.get("/lobbies", response_model=None)
async def lobbies_list(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """List all lobbies."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(Lobby).options(selectinload(Lobby.sessions)).order_by(Lobby.id)
    )
    lobbies = list(result.scalars().all())
    return HTMLResponse(content=lobbies_list_page(lobbies))


@app.post("/lobbies/{lobby_id}/delete", response_model=None)
async def lobbies_delete(
    lobby_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a lobby."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(Lobby).where(Lobby.id == lobby_id))
    lobby = result.scalar_one_or_none()
    if lobby:
        await db.delete(lobby)
        await db.commit()
    return RedirectResponse(url="/lobbies", status_code=302)


# =============================================================================
# Sticky メッセージルート
# =============================================================================


@app.get("/sticky", response_model=None)
async def sticky_list(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """List all sticky messages."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(StickyMessage).order_by(StickyMessage.created_at))
    stickies = list(result.scalars().all())
    return HTMLResponse(content=sticky_list_page(stickies))


@app.post("/sticky/{channel_id}/delete", response_model=None)
async def sticky_delete(
    channel_id: str,
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a sticky message."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(StickyMessage).where(StickyMessage.channel_id == channel_id)
    )
    sticky = result.scalar_one_or_none()
    if sticky:
        await db.delete(sticky)
        await db.commit()
    return RedirectResponse(url="/sticky", status_code=302)


# =============================================================================
# Bump ルート
# =============================================================================


@app.get("/bump", response_model=None)
async def bump_list(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """List all bump configs and reminders."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    configs_result = await db.execute(select(BumpConfig))
    configs = list(configs_result.scalars().all())

    reminders_result = await db.execute(
        select(BumpReminder).order_by(BumpReminder.guild_id)
    )
    reminders = list(reminders_result.scalars().all())

    return HTMLResponse(content=bump_list_page(configs, reminders))


@app.post("/bump/config/{guild_id}/delete", response_model=None)
async def bump_config_delete(
    guild_id: str,
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a bump config."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(BumpConfig).where(BumpConfig.guild_id == guild_id))
    config = result.scalar_one_or_none()
    if config:
        await db.delete(config)
        await db.commit()
    return RedirectResponse(url="/bump", status_code=302)


@app.post("/bump/reminder/{reminder_id}/delete", response_model=None)
async def bump_reminder_delete(
    reminder_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a bump reminder."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(BumpReminder).where(BumpReminder.id == reminder_id)
    )
    reminder = result.scalar_one_or_none()
    if reminder:
        await db.delete(reminder)
        await db.commit()
    return RedirectResponse(url="/bump", status_code=302)


@app.post("/bump/reminder/{reminder_id}/toggle", response_model=None)
async def bump_reminder_toggle(
    reminder_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Toggle a bump reminder enabled state."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(BumpReminder).where(BumpReminder.id == reminder_id)
    )
    reminder = result.scalar_one_or_none()
    if reminder:
        reminder.is_enabled = not reminder.is_enabled
        await db.commit()
    return RedirectResponse(url="/bump", status_code=302)


# -----------------------------------------------------------------------------
# Role Panels 管理
# -----------------------------------------------------------------------------


@app.get("/rolepanels", response_model=None)
async def rolepanels_list(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """List all role panels."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # パネル一覧を取得 (アイテムも一緒に取得)
    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .order_by(RolePanel.created_at.desc())
    )
    panels = list(result.scalars().all())

    # パネルID -> アイテムリストのマップを作成
    items_by_panel: dict[int, list[RolePanelItem]] = {}
    for panel in panels:
        items_by_panel[panel.id] = sorted(panel.items, key=lambda x: x.position)

    return HTMLResponse(content=role_panels_list_page(panels, items_by_panel))


@app.post("/rolepanels/{panel_id}/delete", response_model=None)
async def rolepanel_delete(
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a role panel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
    panel = result.scalar_one_or_none()
    if panel:
        await db.delete(panel)
        await db.commit()
    return RedirectResponse(url="/rolepanels", status_code=302)


@app.get("/rolepanels/new", response_model=None)
async def rolepanel_create_get(
    user: dict[str, Any] | None = Depends(get_current_user),
) -> Response:
    """Show role panel create form."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse(content=role_panel_create_page())


@app.post("/rolepanels/new", response_model=None)
async def rolepanel_create_post(
    user: dict[str, Any] | None = Depends(get_current_user),
    guild_id: Annotated[str, Form()] = "",
    channel_id: Annotated[str, Form()] = "",
    panel_type: Annotated[str, Form()] = "button",
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Create a new role panel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Trim input values
    guild_id = guild_id.strip()
    channel_id = channel_id.strip()
    panel_type = panel_type.strip()
    title = title.strip()
    description = description.strip()

    # Validation
    if not guild_id:
        return HTMLResponse(
            content=role_panel_create_page(
                error="Guild ID is required",
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type=panel_type,
                title=title,
                description=description,
            )
        )

    if not guild_id.isdigit():
        return HTMLResponse(
            content=role_panel_create_page(
                error="Guild ID must be a number",
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type=panel_type,
                title=title,
                description=description,
            )
        )

    if not channel_id:
        return HTMLResponse(
            content=role_panel_create_page(
                error="Channel ID is required",
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type=panel_type,
                title=title,
                description=description,
            )
        )

    if not channel_id.isdigit():
        return HTMLResponse(
            content=role_panel_create_page(
                error="Channel ID must be a number",
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type=panel_type,
                title=title,
                description=description,
            )
        )

    if panel_type not in ("button", "reaction"):
        return HTMLResponse(
            content=role_panel_create_page(
                error="Invalid panel type",
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type=panel_type,
                title=title,
                description=description,
            )
        )

    if not title:
        return HTMLResponse(
            content=role_panel_create_page(
                error="Title is required",
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type=panel_type,
                title=title,
                description=description,
            )
        )

    if len(title) > 256:
        return HTMLResponse(
            content=role_panel_create_page(
                error="Title must be 256 characters or less",
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type=panel_type,
                title=title,
                description=description,
            )
        )

    if len(description) > 4096:
        return HTMLResponse(
            content=role_panel_create_page(
                error="Description must be 4096 characters or less",
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type=panel_type,
                title=title,
                description=description,
            )
        )

    # Create the role panel
    panel = RolePanel(
        guild_id=guild_id,
        channel_id=channel_id,
        panel_type=panel_type,
        title=title,
        description=description if description else None,
    )
    db.add(panel)
    await db.commit()

    return RedirectResponse(url="/rolepanels", status_code=302)
