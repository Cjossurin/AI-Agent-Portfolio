"""
api/auth_routes.py — Signup, Login, Logout for Alita client portal.
Uses JWT tokens stored in httpOnly cookies. No technical knowledge required from clients.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
import uuid
import hashlib
import secrets as _secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import (
    User, ClientProfile, OnboardingStatus, PasswordResetToken,
    TwoFactorOTP, TrustedDevice, WebAuthnCredential,
    EmailVerificationToken,
)

router = APIRouter(prefix="/account", tags=["auth"])

# ─── Base URL helper ───────────────────────────────────────────────
def _app_base_url(request=None) -> str:
    """Return the public base URL.
    Priority: APP_BASE_URL env → X-Forwarded-Host header → RAILWAY_PUBLIC_DOMAIN → localhost."""
    base = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if base:
        return base
    # Use X-Forwarded-Host which Railway/proxies set to the public-facing hostname
    if request is not None:
        fwd_host = request.headers.get("x-forwarded-host", "").strip()
        if fwd_host:
            proto = request.headers.get("x-forwarded-proto", "https").strip()
            return f"{proto}://{fwd_host}"
        # Last resort: derive from request.base_url and upgrade scheme
        raw = str(request.base_url).rstrip("/")
        if raw.startswith("http://") and request.headers.get("x-forwarded-proto") == "https":
            raw = "https://" + raw[len("http://"):]
        return raw
    # Railway auto-injected env vars (no request object available)
    for env_key in ("RAILWAY_PUBLIC_DOMAIN", "RAILWAY_STATIC_URL"):
        domain = os.getenv(env_key, "").strip()
        if domain:
            domain = domain.removeprefix("https://").removeprefix("http://")
            return f"https://{domain}"
    return "http://localhost:8000"

# ─── Security config ───────────────────────────────────────────────
SECRET_KEY = os.getenv("TOKEN_ENCRYPTION_KEY", "fallback-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 1  # 1 hour hard ceiling — sliding refresh extends active sessions
_COOKIE_MAX_AGE = 60 * 60  # 1 hour (matches JWT lifetime)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Helpers ───────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": user_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """FastAPI dependency — returns the logged-in User or None.

    Also implements sliding token refresh: if the JWT is valid but
    more than halfway through its lifetime, a fresh token is issued
    and attached to the response so active users stay logged in.
    """
    token = request.cookies.get("alita_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        return None

    # ── Sliding token refresh ────────────────────────────────────────────
    # If token has < 30 min left, issue a new one.
    # This means: active user -> token keeps getting extended.
    # Idle user -> token expires after 1 hour, JS kicks them at 30 min.
    try:
        exp = payload.get("exp", 0)
        remaining = exp - datetime.utcnow().timestamp()
        if remaining < 30 * 60:  # less than 30 min left
            request.state._refresh_token = create_access_token(user_id)
    except Exception:
        pass

    return user

def require_auth(request: Request, db: Session = Depends(get_db)) -> User:
    """FastAPI dependency — redirects to login if not authenticated."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/account/login?next=" + str(request.url.path)},
        )
    return user

def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = require_auth(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def migrate_mfa_columns(engine_):
    """Safe one-time migration: add MFA + email_verified columns and create related tables."""
    from sqlalchemy import inspect, text
    from database.db import Base
    from database.models import TwoFactorOTP, TrustedDevice, WebAuthnCredential, EmailVerificationToken  # noqa

    try:
        inspector = inspect(engine_)
        tables = inspector.get_table_names()

        if "users" in tables:
            user_cols = [c["name"] for c in inspector.get_columns("users")]
            new_cols = {
                "mfa_enabled":       "BOOLEAN DEFAULT 0",
                "mfa_method":        "VARCHAR(20)",
                "mfa_secret":        "VARCHAR(100)",
                "phone_number":      "VARCHAR(30)",
                "email_verified":    "BOOLEAN DEFAULT 0",
                "oauth_provider":    "VARCHAR(30)",
                "oauth_provider_id": "VARCHAR(128)",
            }
            with engine_.connect() as conn:
                for col, typedef in new_cols.items():
                    if col not in user_cols:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {typedef}"))
                        print(f"[migration] Added column: users.{col}")
                conn.commit()

        # Create all auth-related tables if they don't exist
        Base.metadata.create_all(engine_, tables=[
            TwoFactorOTP.__table__,
            TrustedDevice.__table__,
            WebAuthnCredential.__table__,
            EmailVerificationToken.__table__,
        ])
        print("[migration] Auth tables ready (2FA OTPs, trusted devices, WebAuthn, email verification)")
    except Exception as e:
        print(f"[migration] Warning: {e}")

def _set_auth_cookie(response, token: str):
    response.set_cookie(
        key="alita_token",
        value=token,
        httponly=True,
        max_age=_COOKIE_MAX_AGE,  # 1 hour — sliding refresh extends active sessions
        samesite="lax",
        secure=os.getenv("ENV", "development") == "production",
    )


# ─── 2FA helpers ───────────────────────────────────────────────────

# In-memory pending 2FA sessions: {tmp_token: user_id}
# Stored in a short-lived signed cookie ("alita_2fa_pending")
_MFA_COOKIE = "alita_2fa_pending"
_MFA_EXPIRE_MINUTES = 10

# Trusted device cookie (skip 2FA on recognized devices)
_TRUSTED_DEVICE_COOKIE   = "alita_trusted"
_TRUSTED_DEVICE_DAYS     = 30

# WebAuthn challenge cookie (holds challenge during register/auth ceremony)
_WA_CHALLENGE_COOKIE     = "alita_wa_ch"
_WA_CHALLENGE_MINUTES    = 5


def _create_mfa_pending_token(user_id: str) -> str:
    """Short-lived token that proves password was correct, 2FA still needed."""
    expire = datetime.utcnow() + timedelta(minutes=_MFA_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "exp": expire, "mfa": True}, SECRET_KEY, algorithm=ALGORITHM)


def _decode_mfa_pending_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("mfa"):
            return None
        return payload.get("sub")
    except JWTError:
        return None


def _generate_totp_secret() -> str:
    import pyotp
    return pyotp.random_base32()


def _get_totp_uri(secret: str, user_email: str) -> str:
    import pyotp
    return pyotp.TOTP(secret).provisioning_uri(name=user_email, issuer_name="Alita AI")


def _verify_totp(secret: str, code: str) -> bool:
    try:
        import pyotp
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


def _generate_otp_code() -> str:
    import secrets
    return str(secrets.randbelow(900000) + 100000)  # 6-digit


def _store_otp(db, user_id: str, code: str, purpose: str = "login"):
    from datetime import timedelta
    # Expire any previous unused codes for this user+purpose
    db.query(TwoFactorOTP).filter(
        TwoFactorOTP.user_id == user_id,
        TwoFactorOTP.purpose == purpose,
        TwoFactorOTP.used == False,
    ).delete()
    db.flush()
    expire = datetime.utcnow() + timedelta(minutes=_MFA_EXPIRE_MINUTES)
    db.add(TwoFactorOTP(
        id=str(uuid.uuid4()),
        user_id=user_id,
        code=code,
        purpose=purpose,
        expires_at=expire,
    ))
    db.commit()


def _check_otp(db, user_id: str, code: str, purpose: str = "login") -> bool:
    record = db.query(TwoFactorOTP).filter(
        TwoFactorOTP.user_id == user_id,
        TwoFactorOTP.code == code,
        TwoFactorOTP.purpose == purpose,
        TwoFactorOTP.used == False,
    ).first()
    if not record or record.expires_at < datetime.utcnow():
        return False
    record.used = True
    db.commit()
    return True


def _get_resend_sender() -> tuple[str, str]:
    """Return (from_name, from_email) using env vars with safe fallback."""
    from_name = os.getenv("EMAIL_FROM_NAME", "Alita AI").strip() or "Alita AI"
    from_email = (
        os.getenv("EMAIL_FROM_ADDRESS", "").strip()
        or os.getenv("NOTIFICATION_EMAIL_FROM", "").strip()
        or "onboarding@resend.dev"
    )
    return from_name, from_email


def _send_resend_email(to_email: str, subject: str, html: str, text: str = "") -> bool:
    """Send an email via Resend using configured sender identity."""
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return False

    try:
        import resend

        resend.api_key = api_key
        from_name, from_email = _get_resend_sender()
        payload = {
            "from": f"{from_name} <{from_email}>",
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
        if text:
            payload["text"] = text
        resend.Emails.send(payload)
        return True
    except Exception as e:
        print(f"[Email] Resend send error: {e}")
        return False


def _send_otp_email(to_email: str, code: str, full_name: str = "") -> bool:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print(f"[2FA] No RESEND_API_KEY — OTP code: {code}")
        return False

    success = _send_resend_email(
        to_email=to_email,
        subject=f"Your Alita AI verification code: {code}",
        html=f"""
            <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;background:#fff">
              <h1 style="font-size:1.5rem;font-weight:800;color:#5c6ac4;margin-bottom:4px">Alita AI</h1>
              <p style="color:#666;font-size:.9rem;margin-bottom:24px">Security verification</p>
              <h2 style="font-size:1.1rem;font-weight:700;color:#1a1a2e;margin-bottom:12px">Your sign-in code</h2>
              <div style="background:#f4f4ff;border:2px solid #6366f1;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
                <span style="font-size:2.4rem;font-weight:800;letter-spacing:10px;color:#4338ca">{code}</span>
              </div>
              <p style="color:#666;font-size:.85rem">This code expires in <strong>{_MFA_EXPIRE_MINUTES} minutes</strong>. Don't share it with anyone.</p>
              <p style="color:#999;font-size:.78rem;margin-top:16px">If you didn't try to sign in, please change your password immediately.</p>
            </div>""",
        text=f"Your Alita AI verification code is {code}. It expires in {_MFA_EXPIRE_MINUTES} minutes.",
    )
    if not success:
        print("[2FA] Failed to send OTP email via Resend")
    return success


# ─── Email Verification helpers ────────────────────────────────────

_VERIFY_EXPIRE_HOURS = 24


def _issue_and_send_verification_email(db, user_id: str, to_email: str, full_name: str, base_url: str) -> bool:
    """Create a fresh verification token in the DB and send the e-mail with the link."""
    import secrets as _secrets_mod
    from datetime import timedelta
    # Expire any previous unused tokens for this user
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user_id,
        EmailVerificationToken.used == False,
    ).delete()
    db.flush()

    token = _secrets_mod.token_urlsafe(48)
    db.add(EmailVerificationToken(
        id=str(uuid.uuid4()),
        user_id=user_id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=_VERIFY_EXPIRE_HOURS),
    ))
    db.commit()

    verify_url = f"{base_url.rstrip('/')}/account/verify-email?token={token}"
    first_name = (full_name or "there").split()[0]
    return _send_resend_email(
        to_email=to_email,
        subject="Verify your Alita AI email address",
        html=f"""
        <div style="font-family:sans-serif;max-width:540px;margin:0 auto;padding:32px 24px;background:#fff">
          <h1 style="font-size:1.5rem;font-weight:800;color:#5c6ac4;margin-bottom:8px">Alita AI</h1>
          <h2 style="font-size:1.1rem;font-weight:700;color:#111827;margin:0 0 12px">Welcome, {first_name}!</h2>
          <p style="color:#374151;line-height:1.6;margin:0 0 20px">
            Please confirm your email address to finish setting up your account.
          </p>
          <a href="{verify_url}"
             style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);
                    color:#fff;padding:14px 28px;border-radius:10px;text-decoration:none;
                    font-weight:700;font-size:1rem">Verify Email Address</a>
          <p style="color:#9ca3af;font-size:.8rem;margin-top:24px">
            This link expires in {_VERIFY_EXPIRE_HOURS} hours.
            If you didn't create this account, you can safely ignore this email.
          </p>
        </div>""",
        text=f"Verify your Alita AI email address: {verify_url}  (link expires in {_VERIFY_EXPIRE_HOURS} hours)",
    )


def _send_password_changed_email(to_email: str) -> bool:
    return _send_resend_email(
        to_email=to_email,
        subject="Your Alita AI password was changed",
        html="""
        <div style="font-family:sans-serif;max-width:540px;margin:0 auto;padding:32px 24px;background:#fff">
          <h1 style="font-size:1.5rem;font-weight:800;color:#5c6ac4;margin-bottom:8px">Alita AI</h1>
          <h2 style="font-size:1.1rem;font-weight:700;color:#111827;margin:0 0 12px">Password updated</h2>
          <p style="color:#374151;line-height:1.6;margin:0 0 16px">
            This is a confirmation that your account password was changed.
          </p>
          <p style="color:#6b7280;font-size:.88rem;line-height:1.6;margin:0">
            If this wasn't you, reset your password immediately and contact support.
          </p>
        </div>
        """,
        text="Your Alita AI password was changed. If this wasn't you, reset it immediately.",
    )


def _send_otp_sms(phone: str, code: str) -> bool:
    if os.getenv("TWILIO_SMS_ENABLED", "false").lower() != "true":
        print(f"[2FA] Twilio disabled — SMS OTP code: {code}")
        return False
    try:
        from twilio.rest import Client as TwilioClient
        client = TwilioClient(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        client.messages.create(
            body=f"Your Alita AI sign-in code is: {code}. Expires in {_MFA_EXPIRE_MINUTES} minutes.",
            from_=os.getenv("TWILIO_PHONE_NUMBER"),
            to=phone,
        )
        return True
    except Exception as e:
        print(f"[2FA] SMS send error: {e}")
        return False


# ─── Trusted Device helpers ────────────────────────────────────────

def _make_device_token() -> tuple:
    """Returns (raw_token, sha256_hash). Store hash in DB, raw token in cookie."""
    raw = _secrets.token_urlsafe(48)
    hsh = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hsh


def _check_trusted_device(request: Request, db, user_id: str) -> bool:
    """Returns True if the request carries a valid trusted-device cookie for this user."""
    raw = request.cookies.get(_TRUSTED_DEVICE_COOKIE)
    if not raw:
        return False
    hsh = hashlib.sha256(raw.encode()).hexdigest()
    device = db.query(TrustedDevice).filter(
        TrustedDevice.user_id    == user_id,
        TrustedDevice.token_hash == hsh,
        TrustedDevice.expires_at >  datetime.utcnow(),
    ).first()
    if device:
        device.last_used_at = datetime.utcnow()
        db.commit()
        return True
    return False


def _register_trusted_device(db, user_id: str, ua_string: str) -> str:
    """Creates a TrustedDevice record and returns the raw token to store in the cookie."""
    # Housekeeping: remove expired entries for this user
    db.query(TrustedDevice).filter(
        TrustedDevice.user_id    == user_id,
        TrustedDevice.expires_at <  datetime.utcnow(),
    ).delete()
    raw, hsh = _make_device_token()
    db.add(TrustedDevice(
        id          = str(uuid.uuid4()),
        user_id     = user_id,
        token_hash  = hsh,
        device_name = (ua_string or "Unknown Device")[:200],
        expires_at  = datetime.utcnow() + timedelta(days=_TRUSTED_DEVICE_DAYS),
    ))
    db.commit()
    return raw


def _set_trusted_cookie(response, raw_token: str):
    response.set_cookie(
        key      = _TRUSTED_DEVICE_COOKIE,
        value    = raw_token,
        httponly = True,
        max_age  = 60 * 60 * 24 * _TRUSTED_DEVICE_DAYS,
        samesite = "lax",
        secure   = os.getenv("ENV", "development") == "production",
    )


# ─── WebAuthn / Passkey helpers ────────────────────────────────────

def _get_rp_info() -> tuple:
    """Returns (rp_id, expected_origin) from APP_BASE_URL env var."""
    from urllib.parse import urlparse
    base   = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    parsed = urlparse(base)
    rp_id  = parsed.hostname or "localhost"
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return rp_id, origin


def _encode_wa_challenge(challenge: bytes) -> str:
    """Encode the WebAuthn challenge into a short-lived signed JWT for cookie storage."""
    import base64
    b64 = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
    exp = datetime.utcnow() + timedelta(minutes=_WA_CHALLENGE_MINUTES)
    return jwt.encode({"wa_ch": b64, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def _decode_wa_challenge(cookie_val: str) -> Optional[bytes]:
    """Recover challenge bytes from the signed cookie; returns None if invalid/expired."""
    import base64
    try:
        payload = jwt.decode(cookie_val, SECRET_KEY, algorithms=[ALGORITHM])
        b64 = payload.get("wa_ch", "")
        pad = 4 - len(b64) % 4
        if pad != 4:
            b64 += "=" * pad
        return base64.urlsafe_b64decode(b64)
    except Exception:
        return None


# ─── HTML helpers ──────────────────────────────────────────────────

def _page(title: str, body: str, extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Alita AI</title>
{extra_head}
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }}
  .card {{
    background: rgba(255,255,255,0.05);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 20px;
    padding: 48px 40px;
    width: 100%;
    max-width: 460px;
    color: white;
  }}
  .logo {{ text-align: center; margin-bottom: 32px; }}
  .logo h1 {{ font-size: 2rem; font-weight: 800; background: linear-gradient(135deg, #6366f1, #8b5cf6, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
  .logo p {{ color: rgba(255,255,255,0.5); font-size: 0.9rem; margin-top: 6px; }}
  h2 {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 24px; }}
  label {{ display: block; font-size: 0.85rem; color: rgba(255,255,255,0.7); margin-bottom: 6px; margin-top: 16px; }}
  input[type=text], input[type=email], input[type=password] {{
    width: 100%;
    padding: 12px 16px;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 10px;
    color: white;
    font-size: 1rem;
    outline: none;
    transition: border-color 0.2s;
  }}
  input:focus {{ border-color: #6366f1; }}
  input::placeholder {{ color: rgba(255,255,255,0.3); }}
  .btn {{
    display: block;
    width: 100%;
    padding: 14px;
    margin-top: 28px;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: white;
    border: none;
    border-radius: 12px;
    font-size: 1rem;
    font-weight: 700;
    cursor: pointer;
    transition: opacity 0.2s;
    text-align: center;
    text-decoration: none;
  }}
  .btn:hover {{ opacity: 0.9; }}
  .link-row {{ text-align: center; margin-top: 20px; font-size: 0.88rem; color: rgba(255,255,255,0.5); }}
  .link-row a {{ color: #a78bfa; text-decoration: none; font-weight: 600; }}
  .error {{
    background: rgba(239,68,68,0.15);
    border: 1px solid rgba(239,68,68,0.4);
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 0.88rem;
    color: #fca5a5;
    margin-top: 16px;
  }}
  .hint {{ font-size: 0.78rem; color: rgba(255,255,255,0.35); margin-top: 4px; }}
  .pw-wrap {{ position: relative; }}
  .pw-wrap input {{ padding-right: 46px; }}
  .eye-btn {{
    position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
    background: none; border: none; cursor: pointer; padding: 4px;
    color: rgba(255,255,255,0.4); font-size: 1.1rem; line-height:1;
    transition: color 0.2s;
  }}
  .eye-btn:hover {{ color: rgba(255,255,255,0.85); }}
  .social-row {{ display: flex; flex-direction: column; gap: 12px; margin-bottom: 4px; }}
  .btn-social {{
    display: flex; align-items: center; justify-content: center; gap: 10px;
    width: 100%; padding: 12px 16px; border-radius: 12px;
    font-size: 0.95rem; font-weight: 600; cursor: pointer;
    text-decoration: none; transition: opacity 0.2s; border: none;
  }}
  .btn-social:hover {{ opacity: 0.88; }}
  .btn-google {{ background: white; color: #3c4043; }}
  .btn-facebook {{ background: #1877F2; color: white; }}
  .or-divider {{
    display: flex; align-items: center; gap: 12px; margin: 20px 0 8px;
    font-size: 0.82rem; color: rgba(255,255,255,0.35);
  }}
  .or-divider::before, .or-divider::after {{ content: ''; flex: 1; height: 1px; background: rgba(255,255,255,0.12); }}
</style>
</head>
<body>
{body}
<script>
function togglePw(inputId, btn) {{
  var inp = document.getElementById(inputId);
  if (!inp) return;
  if (inp.type === 'password') {{
    inp.type = 'text';
    btn.innerHTML = '&#128584;';
    btn.title = 'Hide password';
  }} else {{
    inp.type = 'password';
    btn.innerHTML = '&#128065;';
    btn.title = 'Show password';
  }}
}}
</script>
</body>
</html>"""


# ─── Routes ────────────────────────────────────────────────────────


def _find_or_create_social_user(
    db: Session, provider: str, provider_id: str, email: str, full_name: str
):
    """Find an existing user by social provider ID or email, or create a new one.

    Returns (user, is_new) tuple.
    - Looks up by (provider, provider_id) first — fastest for returning users.
    - Falls back to email — links social ID to an existing email/password account.
    - Creates a brand-new User + ClientProfile if neither match.
    """
    # 1. Returning social login user
    user = db.query(User).filter(
        User.oauth_provider == provider,
        User.oauth_provider_id == provider_id,
    ).first()
    if user:
        user.last_login = datetime.utcnow()
        db.commit()
        return user, False

    # 2. Existing email/password user — link social ID
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if user:
        if not user.oauth_provider_id:
            user.oauth_provider    = provider
            user.oauth_provider_id = provider_id
        user.last_login = datetime.utcnow()
        db.commit()
        return user, False

    # 3. Brand-new user
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=email,
        password_hash=hash_password(str(uuid.uuid4())),  # random unusable placeholder
        full_name=full_name or email.split("@")[0],
        email_verified=True,   # email already verified by OAuth provider
        oauth_provider=provider,
        oauth_provider_id=provider_id,
    )
    db.add(user)

    raw_name = (full_name or email.split("@")[0]).strip()
    client_id = "".join(c if c.isalnum() else "_" for c in raw_name.lower()).strip("_")
    base = client_id
    counter = 1
    while db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first():
        client_id = f"{base}_{counter}"
        counter += 1

    profile = ClientProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        client_id=client_id,
        business_name=raw_name,
        onboarding_status=OnboardingStatus.pending,
    )
    db.add(profile)
    db.commit()
    return user, True


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(error: str = ""):
    error_html = f'<div class="error">{error}</div>' if error else ""
    body = f"""
    <div class="card">
      <div class="logo">
        <h1>Alita AI</h1>
        <p>Your AI-powered marketing team</p>
      </div>
      <h2>Create your account</h2>
      {error_html}
      <div class="social-row">
        <a href="/account/google" class="btn-social btn-google">
          <svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg"><path fill="#4285F4" d="M44.5 20H24v8.5h11.7C34.3 33.1 29.8 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.7 1.1 7.7 2.9l6.1-6.1C34.4 6.1 29.5 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20c11 0 19.7-8 19.7-20 0-1.3-.1-2.7-.2-4z"/></svg>
          Sign up with Google
        </a>
        <a href="/account/facebook" class="btn-social btn-facebook">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="white" xmlns="http://www.w3.org/2000/svg"><path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/></svg>
          Sign up with Facebook
        </a>
      </div>
      <div class="or-divider"><span>or create account with email</span></div>
      <form method="post" action="/account/signup">
        <label>Full Name</label>
        <input type="text" name="full_name" placeholder="Jane Smith" required autofocus>

        <label>Email Address</label>
        <input type="email" name="email" placeholder="jane@yourbusiness.com" required>

        <label>Password</label>
        <div class="pw-wrap">
          <input type="password" id="signup-pw" name="password" placeholder="At least 8 characters" required minlength="8">
          <button type="button" class="eye-btn" onclick="togglePw('signup-pw', this)" title="Show password">&#128065;</button>
        </div>
        <p class="hint">Minimum 8 characters.</p>

        <label>Business Name</label>
        <input type="text" name="business_name" placeholder="Cool Cruise Co." required>

        <button type="submit" class="btn">Get Started</button>
      </form>
      <div class="link-row">Already have an account? <a href="/account/login">Sign in</a></div>
    </div>"""
    return _page("Create Account", body)


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    db: Session = Depends(get_db),
):
    # Validate
    email = email.strip().lower()
    if len(password) < 8:
        return RedirectResponse("/auth/signup?error=Password+must+be+at+least+8+characters", status_code=303)
    if db.query(User).filter(User.email == email).first():
        return RedirectResponse("/auth/signup?error=An+account+with+this+email+already+exists", status_code=303)

    # Create user
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
    )
    db.add(user)

    # Create client profile
    raw_name = business_name.strip()
    # Generate a clean client_id: "Cool Cruise Co." → "cool_cruise_co"
    client_id = "".join(c if c.isalnum() else "_" for c in raw_name.lower()).strip("_")
    # Ensure uniqueness
    base = client_id
    counter = 1
    while db.query(ClientProfile).filter(ClientProfile.client_id == client_id).first():
        client_id = f"{base}_{counter}"
        counter += 1

    profile = ClientProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        client_id=client_id,
        business_name=raw_name,
        onboarding_status=OnboardingStatus.pending,
        onboarding_step=1,
    )
    db.add(profile)
    db.commit()

    # Best-effort: send verification email (never block signup on email issues)
    base_url = os.getenv("APP_BASE_URL", str(request.base_url).rstrip("/"))
    _issue_and_send_verification_email(db, user_id, user.email, user.full_name, base_url)

    # Log in immediately — redirect to onboarding
    token = create_access_token(user_id)
    response = RedirectResponse("/onboarding", status_code=303)
    _set_auth_cookie(response, token)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(error: str = "", next: str = "/dashboard"):
    error_html = f'<div class="error">{error}</div>' if error else ""
    body = f"""
    <div class="card">
      <div class="logo">
        <h1>Alita AI</h1>
        <p>Your AI-powered marketing team</p>
      </div>
      <h2>Welcome back</h2>
      {error_html}

      <div class="social-row">
        <a href="/account/google" class="btn-social btn-google">
          <svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg"><path fill="#4285F4" d="M44.5 20H24v8.5h11.7C34.3 33.1 29.8 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.7 1.1 7.7 2.9l6.1-6.1C34.4 6.1 29.5 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20c11 0 19.7-8 19.7-20 0-1.3-.1-2.7-.2-4z"/></svg>
          Sign in with Google
        </a>
        <a href="/account/facebook" class="btn-social btn-facebook">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="white" xmlns="http://www.w3.org/2000/svg"><path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/></svg>
          Sign in with Facebook
        </a>
      </div>
      <div class="or-divider"><span>or sign in with email</span></div>
      <form method="post" action="/account/login">
        <input type="hidden" name="next" value="{next}">
        <label>Email Address</label>
        <input type="email" name="email" placeholder="jane@yourbusiness.com" required autofocus>

        <label>Password</label>
        <div class="pw-wrap">
          <input type="password" id="login-pw" name="password" placeholder="Your password" required>
          <button type="button" class="eye-btn" onclick="togglePw('login-pw', this)" title="Show password">&#128065;</button>
        </div>

        <button type="submit" class="btn">Sign In</button>
      </form>
      <div class="link-row" style="margin-top:14px"><a href="/account/forgot-password">Forgot password?</a></div>
      <div class="link-row">Don't have an account? <a href="/account/signup">Get started free</a></div>
    </div>"""
    return _page("Sign In", body)


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email, User.is_active == True).first()

    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse("/account/login?error=Invalid+email+or+password", status_code=303)

    # ── 2FA check ────────────────────────────────────────────────────
    if user.mfa_enabled and user.mfa_method:
        # Trusted device? Skip 2FA entirely
        if _check_trusted_device(request, db, user.id):
            pass  # fall through to normal session grant below
        else:
            # Issue a short-lived pending token, redirect to challenge page
            pending_token = _create_mfa_pending_token(user.id)
            # For email/SMS methods, send the OTP now
            if user.mfa_method in ("email", "sms"):
                code = _generate_otp_code()
                _store_otp(db, user.id, code, purpose="login")
                if user.mfa_method == "email":
                    _send_otp_email(user.email, code, user.full_name)
                else:
                    _send_otp_sms(user.phone_number or "", code)

            from urllib.parse import quote
            redirect_next = quote(next if next.startswith("/") else "/dashboard")
            response = RedirectResponse(
                f"/account/2fa/challenge?next={redirect_next}&method={user.mfa_method}",
                status_code=303,
            )
            response.set_cookie(
                key=_MFA_COOKIE,
                value=pending_token,
                httponly=True,
                max_age=60 * _MFA_EXPIRE_MINUTES,
                samesite="lax",
                secure=os.getenv("ENV", "development") == "production",
            )
            return response
    # ─────────────────────────────────────────────────────────────────

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    # Decide where to send them
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
    step = getattr(profile, "onboarding_step", None)
    if profile and step is not None and 1 <= step <= 6:
        destination = "/onboarding"
    elif profile and profile.onboarding_status != OnboardingStatus.complete:
        destination = "/onboarding"
    else:
        destination = next if next.startswith("/") else "/dashboard"

    token = create_access_token(user.id)
    response = RedirectResponse(destination, status_code=303)
    _set_auth_cookie(response, token)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/account/login", status_code=303)
    response.delete_cookie("alita_token")
    return response


# ─── 2FA Routes ────────────────────────────────────────────────────

@router.get("/2fa/challenge", response_class=HTMLResponse)
async def mfa_challenge_page(request: Request, next: str = "/dashboard", method: str = "totp", error: str = ""):
    pending = request.cookies.get(_MFA_COOKIE)
    if not pending or not _decode_mfa_pending_token(pending):
        return RedirectResponse("/account/login", status_code=303)

    from urllib.parse import quote

    error_html = f'<div class="error">{error}</div>' if error else ""

    # ── Passkey / fingerprint method ─────────────────────────────────
    if method == "passkey":
        body = f"""
    <div class="card" style="max-width:460px">
      <div class="logo"><h1>Alita AI</h1><p>Two-factor authentication</p></div>
      <h2>&#128274; Verify with Fingerprint / Biometric</h2>
      <p style="color:rgba(255,255,255,.6);font-size:.88rem;margin:12px 0 20px;line-height:1.6">
        Use your device fingerprint, Face ID, or Windows Hello to continue.
      </p>
      {error_html}
      <button id="passkey-btn" class="btn" style="width:100%;font-size:1rem;padding:14px;margin-bottom:10px"
              onclick="doPasskeyAuth()">
        &#128274; Use Fingerprint / Biometric
      </button>
      <div id="passkey-status" style="color:rgba(255,255,255,.5);font-size:.82rem;text-align:center;min-height:20px"></div>
      <div class="link-row" style="margin-top:18px"><a href="/account/login">Back to login</a></div>
      <input type="hidden" id="next-val" value="{next}">
    </div>
    <script>
    function b64UrlDecode(s) {{
      s = s.replace(/-/g,'+').replace(/_/g,'/');
      while(s.length%4) s+='=';
      return Uint8Array.from(atob(s), c=>c.charCodeAt(0));
    }}
    function b64UrlEncode(buf) {{
      return btoa(String.fromCharCode(...new Uint8Array(buf)))
             .replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=/g,'');
    }}
    async function doPasskeyAuth() {{
      const btn = document.getElementById('passkey-btn');
      const status = document.getElementById('passkey-status');
      btn.disabled = true;
      status.textContent = 'Waiting for biometric prompt…';
      try {{
        const optResp = await fetch('/account/2fa/passkey/auth-start');
        if(!optResp.ok) throw new Error(await optResp.text());
        const opts = await optResp.json();
        opts.challenge = b64UrlDecode(opts.challenge);
        if(opts.allowCredentials) {{
          opts.allowCredentials = opts.allowCredentials.map(c => ({{...c, id: b64UrlDecode(c.id)}}));
        }}
        const assertion = await navigator.credentials.get({{publicKey: opts}});
        status.textContent = 'Verifying…';
        const body = JSON.stringify({{
          id: assertion.id,
          rawId: b64UrlEncode(assertion.rawId),
          type: assertion.type,
          response: {{
            clientDataJSON:    b64UrlEncode(assertion.response.clientDataJSON),
            authenticatorData: b64UrlEncode(assertion.response.authenticatorData),
            signature:         b64UrlEncode(assertion.response.signature),
            userHandle:        assertion.response.userHandle ? b64UrlEncode(assertion.response.userHandle) : null,
          }},
          next: document.getElementById('next-val').value,
        }});
        const verResp = await fetch('/account/2fa/passkey/auth-finish', {{
          method: 'POST', headers: {{'Content-Type':'application/json'}}, body
        }});
        const result = await verResp.json();
        if(result.ok) {{
          window.location.href = result.redirect || '/dashboard';
        }} else {{
          status.textContent = '';
          btn.disabled = false;
          document.getElementById('passkey-btn').insertAdjacentHTML('beforebegin',
            '<div class="error">' + (result.error || 'Verification failed. Please try again.') + '</div>');
        }}
      }} catch(err) {{
        status.textContent = '';
        btn.disabled = false;
        if(err.name === 'NotAllowedError') {{
          document.getElementById('passkey-btn').insertAdjacentHTML('beforebegin',
            '<div class="error">Biometric cancelled or not allowed. Please try again.</div>');
        }} else {{
          document.getElementById('passkey-btn').insertAdjacentHTML('beforebegin',
            '<div class="error">Error: ' + err.message + '</div>');
        }}
      }}
    }}
    // Auto-trigger on page load
    window.addEventListener('load', () => setTimeout(doPasskeyAuth, 400));
    </script>"""
        return _page("Verify Identity", body)

    # ── Code-entry methods (totp / email / sms) ──────────────────────
    if method == "totp":
        instruction = "Enter the 6-digit code from your authenticator app."
        icon = "&#128241;"
    elif method == "sms":
        instruction = "We sent a 6-digit code to your phone number. Enter it below."
        icon = "&#128244;"
    else:  # email
        instruction = "We sent a 6-digit code to your email address. Enter it below."
        icon = "&#128140;"

    resend_html = ""
    if method in ("email", "sms"):
        resend_html = f'<div class="link-row" style="margin-top:10px"><a href="/account/2fa/resend?next={next}&method={method}">Resend code</a></div>'

    body = f"""
    <div class="card">
      <div class="logo"><h1>Alita AI</h1><p>Two-factor authentication</p></div>
      <h2>{icon} Verify your identity</h2>
      <p style="color:rgba(255,255,255,.6);font-size:.88rem;margin:12px 0 4px">{instruction}</p>
      {error_html}
      <form method="post" action="/account/2fa/challenge">
        <input type="hidden" name="next" value="{next}">
        <input type="hidden" name="method" value="{method}">
        <label>Verification Code</label>
        <input type="text" name="code" placeholder="123456" maxlength="6" inputmode="numeric" pattern="[0-9]{{6}}"
               autocomplete="one-time-code" autofocus style="letter-spacing:8px;font-size:1.3rem;text-align:center">
        <label style="display:flex;align-items:center;gap:10px;cursor:pointer;margin-top:16px;font-size:.85rem;font-weight:400;opacity:.8">
          <input type="checkbox" name="remember_device" value="1" style="width:16px;height:16px;cursor:pointer">
          Trust this device for {_TRUSTED_DEVICE_DAYS} days (skip 2FA on this browser)
        </label>
        <button type="submit" class="btn" style="margin-top:16px">Verify</button>
      </form>
      {resend_html}
      <div class="link-row" style="margin-top:14px"><a href="/account/login">Back to login</a></div>
    </div>"""
    return _page("Verify Identity", body)


@router.post("/2fa/challenge", response_class=HTMLResponse)
async def mfa_challenge_submit(
    request: Request,
    code: str = Form(...),
    next: str = Form("/dashboard"),
    method: str = Form("totp"),
    remember_device: str = Form(""),
    db: Session = Depends(get_db),
):
    from urllib.parse import quote
    pending = request.cookies.get(_MFA_COOKIE)
    user_id = _decode_mfa_pending_token(pending) if pending else None
    if not user_id:
        return RedirectResponse("/account/login?error=Session+expired.+Please+log+in+again.", status_code=303)

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    code = code.strip()
    valid = False
    if method == "totp" and user.mfa_secret:
        valid = _verify_totp(user.mfa_secret, code)
    elif method in ("email", "sms"):
        valid = _check_otp(db, user_id, code, purpose="login")

    if not valid:
        err = quote("Invalid or expired code. Please try again.")
        return RedirectResponse(f"/account/2fa/challenge?next={quote(next)}&method={method}&error={err}", status_code=303)

    # Code correct — finish login
    user.last_login = datetime.utcnow()
    db.commit()

    profile = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
    destination = next if next.startswith("/") else "/dashboard"
    if profile and profile.onboarding_status != OnboardingStatus.complete:
        destination = "/onboarding"

    token = create_access_token(user.id)
    response = RedirectResponse(destination, status_code=303)
    _set_auth_cookie(response, token)
    response.delete_cookie(_MFA_COOKIE)

    # Trust this device if checkbox was checked
    if remember_device == "1":
        ua = request.headers.get("user-agent", "Unknown Device")
        raw = _register_trusted_device(db, user.id, ua)
        _set_trusted_cookie(response, raw)

    return response


@router.get("/2fa/resend")
async def mfa_resend(request: Request, next: str = "/dashboard", method: str = "email", db: Session = Depends(get_db)):
    """Resend email/SMS OTP for the pending 2FA session."""
    from urllib.parse import quote
    pending = request.cookies.get(_MFA_COOKIE)
    user_id = _decode_mfa_pending_token(pending) if pending else None
    if not user_id:
        return RedirectResponse("/account/login", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if user and method in ("email", "sms"):
        code = _generate_otp_code()
        _store_otp(db, user_id, code, purpose="login")
        if method == "email":
            _send_otp_email(user.email, code, user.full_name)
        else:
            _send_otp_sms(user.phone_number or "", code)

    return RedirectResponse(f"/account/2fa/challenge?next={quote(next)}&method={method}", status_code=303)


# ── 2FA Setup (called from /settings/security) ─────────────────────

@router.get("/2fa/setup", response_class=HTMLResponse)
async def mfa_setup_page(request: Request, method: str = "totp", error: str = "", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    if method == "totp":
        # Generate a fresh TOTP secret and render QR code
        secret = _generate_totp_secret()
        uri = _get_totp_uri(secret, user.email)

        # Build QR as inline base64 PNG
        try:
            import qrcode, io
            qr = qrcode.make(uri)
            buf = io.BytesIO()
            qr.save(buf, format="PNG")
            qr_b64 = __import__("base64").b64encode(buf.getvalue()).decode()
            qr_img = f'<img src="data:image/png;base64,{qr_b64}" alt="QR Code" style="width:180px;height:180px;border-radius:8px;border:3px solid rgba(255,255,255,.15)">'
        except ImportError:
            qr_img = f'<p style="color:rgba(255,255,255,.5);font-size:.8rem">Install <code>qrcode[pil]</code> to show QR code.<br>Manual key: <code style="letter-spacing:2px">{secret}</code></p>'

        error_html = f'<div class="error">{error}</div>' if error else ""
        body = f"""
        <div class="card" style="max-width:520px">
          <div class="logo"><h1>Alita AI</h1><p>Set up two-factor authentication</p></div>
          <h2>&#128241; Authenticator App</h2>
          <p style="color:rgba(255,255,255,.6);font-size:.86rem;margin:12px 0 20px;line-height:1.6">
            Scan the QR code with <strong>Google Authenticator</strong>, <strong>Microsoft Authenticator</strong>,
            or any TOTP app. Then enter the 6-digit code to confirm.
          </p>
          {error_html}
          <div style="display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap;margin-bottom:20px">
            <div style="background:rgba(255,255,255,.08);border-radius:12px;padding:16px;text-align:center">
              {qr_img}
            </div>
            <div style="flex:1;min-width:180px">
              <p style="color:rgba(255,255,255,.5);font-size:.78rem;margin-bottom:6px">Or enter key manually:</p>
              <code style="background:rgba(255,255,255,.08);padding:8px 12px;border-radius:6px;font-size:.85rem;letter-spacing:2px;display:block;word-break:break-all">{secret}</code>
            </div>
          </div>
          <form method="post" action="/account/2fa/setup">
            <input type="hidden" name="method" value="totp">
            <input type="hidden" name="secret" value="{secret}">
            <label>Enter the 6-digit code from your app to confirm</label>
            <input type="text" name="code" placeholder="123456" maxlength="6" inputmode="numeric"
                   autocomplete="one-time-code" autofocus style="letter-spacing:8px;font-size:1.3rem;text-align:center">
            <button type="submit" class="btn">Enable 2FA</button>
          </form>
          <div class="link-row" style="margin-top:14px"><a href="/settings/security">Cancel</a></div>
        </div>"""
        return _page("Set Up 2FA", body)

    elif method in ("email", "sms"):
        # Send a test OTP immediately and ask them to verify
        phone_field = ""
        if method == "sms":
            phone_field = """
            <label>Phone Number (with country code)</label>
            <input type="text" name="phone" placeholder="+1 305 555 0100" style="font-size:1rem">"""

        error_html = f'<div class="error">{error}</div>' if error else ""
        icon = "&#128140;" if method == "email" else "&#128244;"
        desc = (
            f"We'll send a 6-digit code to <strong>{user.email}</strong> each time you sign in."
            if method == "email"
            else "We'll send a 6-digit code to your phone number each time you sign in."
        )
        body = f"""
        <div class="card" style="max-width:480px">
          <div class="logo"><h1>Alita AI</h1><p>Set up two-factor authentication</p></div>
          <h2>{icon} {"Email" if method == "email" else "SMS"} Verification</h2>
          <p style="color:rgba(255,255,255,.6);font-size:.86rem;margin:12px 0 20px;line-height:1.6">{desc}</p>
          {error_html}
          <form method="post" action="/account/2fa/setup">
            <input type="hidden" name="method" value="{method}">
            {phone_field}
            <button type="submit" class="btn">Send Verification Code</button>
          </form>
          <div class="link-row" style="margin-top:14px"><a href="/settings/security">Cancel</a></div>
        </div>"""
        return _page("Set Up 2FA", body)

    elif method == "passkey":
        body = """
        <div class="card" style="max-width:500px">
          <div class="logo"><h1>Alita AI</h1><p>Set up two-factor authentication</p></div>
          <h2>&#128274; Fingerprint / Biometric (Passkey)</h2>
          <p style="color:rgba(255,255,255,.6);font-size:.86rem;margin:12px 0 20px;line-height:1.6">
            Use your device's built-in biometric &mdash; <strong>Touch ID, Face ID, fingerprint reader,
            or Windows Hello</strong> &mdash; as a second factor. No code entry needed.
          </p>
          <div id="reg-status" style="color:rgba(255,255,255,.5);font-size:.83rem;margin-bottom:12px;min-height:20px"></div>
          <button id="reg-btn" class="btn" style="width:100%;font-size:1rem;padding:14px"
                  onclick="doRegister()">&#128274; Register Fingerprint / Biometric</button>
          <div class="link-row" style="margin-top:18px"><a href="/settings/security">Cancel</a></div>
        </div>
        <script>
        function b64UrlDecode(s){
          s=s.replace(/-/g,'+').replace(/_/g,'/');
          while(s.length%4)s+='=';
          return Uint8Array.from(atob(s),c=>c.charCodeAt(0));
        }
        function b64UrlEncode(buf){
          return btoa(String.fromCharCode(...new Uint8Array(buf)))
                 .replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=/g,'');
        }
        async function doRegister(){
          const btn=document.getElementById('reg-btn');
          const status=document.getElementById('reg-status');
          btn.disabled=true;
          status.textContent='Starting registration…';
          try{
            const optResp=await fetch('/account/2fa/passkey/register-start');
            if(!optResp.ok) throw new Error(await optResp.text());
            const opts=await optResp.json();
            opts.challenge=b64UrlDecode(opts.challenge);
            opts.user.id=b64UrlDecode(opts.user.id);
            if(opts.excludeCredentials) opts.excludeCredentials=opts.excludeCredentials.map(c=>({...c,id:b64UrlDecode(c.id)}));
            status.textContent='Waiting for biometric prompt…';
            const cred=await navigator.credentials.create({publicKey:opts});
            status.textContent='Verifying…';
            const body=JSON.stringify({
              id:cred.id, rawId:b64UrlEncode(cred.rawId), type:cred.type,
              deviceName: navigator.userAgent.slice(0,80),
              response:{
                clientDataJSON:b64UrlEncode(cred.response.clientDataJSON),
                attestationObject:b64UrlEncode(cred.response.attestationObject),
              }
            });
            const verResp=await fetch('/account/2fa/passkey/register-finish',{
              method:'POST',headers:{'Content-Type':'application/json'},body
            });
            const result=await verResp.json();
            if(result.ok){
              status.style.color='#27ae60';
              status.textContent='\\u2705 Registered! Redirecting…';
              setTimeout(()=>window.location.href=result.redirect||'/settings/security',800);
            } else {
              status.textContent='';
              btn.disabled=false;
              status.insertAdjacentHTML('afterend','<div class="error">'+(result.error||'Registration failed.')+'</div>');
            }
          } catch(err){
            status.textContent='';
            btn.disabled=false;
            if(err.name==='NotAllowedError'){
              status.insertAdjacentHTML('afterend','<div class="error">Biometric was cancelled. Please try again.</div>');
            } else {
              status.insertAdjacentHTML('afterend','<div class="error">Error: '+err.message+'</div>');
            }
          }
        }
        </script>"""
        return _page("Set Up Passkey", body)

    return RedirectResponse("/settings/security", status_code=303)


@router.post("/2fa/setup", response_class=HTMLResponse)
async def mfa_setup_submit(
    request: Request,
    method: str = Form(...),
    secret: str = Form(""),
    code: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    from urllib.parse import quote
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    if method == "totp":
        # Verify the TOTP code against the secret before saving
        if not code.strip() and not secret.strip():
            # First visit — just show the page (shouldn't happen via POST but guard anyway)
            return RedirectResponse("/account/2fa/setup?method=totp", status_code=303)

        if not _verify_totp(secret.strip(), code.strip()):
            err = quote("Incorrect code — please try again.")
            return RedirectResponse(f"/account/2fa/setup?method=totp&error={err}", status_code=303)

        user.mfa_enabled = True
        user.mfa_method = "totp"
        user.mfa_secret = secret.strip()
        db.commit()
        return RedirectResponse("/settings/security?msg=2FA+enabled+with+authenticator+app", status_code=303)

    elif method in ("email", "sms"):
        code = code.strip()
        if not code:
            # Step 1: generate + send OTP, then show verification form
            otp = _generate_otp_code()
            _store_otp(db, user.id, otp, purpose="setup")
            if method == "email":
                _send_otp_email(user.email, otp, user.full_name)
            else:
                p = phone.strip() or user.phone_number or ""
                _send_otp_sms(p, otp)
                if p:
                    user.phone_number = p
                    db.commit()

            # Render code-entry form
            icon = "&#128140;" if method == "email" else "&#128244;"
            dest = user.email if method == "email" else (phone.strip() or user.phone_number or "your phone")
            body = f"""
            <div class="card" style="max-width:480px">
              <div class="logo"><h1>Alita AI</h1><p>Set up two-factor authentication</p></div>
              <h2>{icon} Enter Verification Code</h2>
              <p style="color:rgba(255,255,255,.6);font-size:.86rem;margin:12px 0 20px;line-height:1.6">
                We sent a code to <strong>{dest}</strong>. Enter it below to confirm.
              </p>
              <form method="post" action="/account/2fa/setup">
                <input type="hidden" name="method" value="{method}">
                <input type="hidden" name="phone" value="{phone.strip()}">
                <label>Verification Code</label>
                <input type="text" name="code" placeholder="123456" maxlength="6" inputmode="numeric"
                       autocomplete="one-time-code" autofocus style="letter-spacing:8px;font-size:1.3rem;text-align:center">
                <button type="submit" class="btn">Enable 2FA</button>
              </form>
              <div class="link-row" style="margin-top:14px"><a href="/settings/security">Cancel</a></div>
            </div>"""
            return HTMLResponse(_page("Verify Code", body))
        else:
            # Step 2: verify the OTP
            if not _check_otp(db, user.id, code, purpose="setup"):
                err = quote("Invalid or expired code. Please try again.")
                return RedirectResponse(f"/account/2fa/setup?method={method}&error={err}", status_code=303)

            p = phone.strip()
            if method == "sms" and p:
                user.phone_number = p
            user.mfa_enabled = True
            user.mfa_method = method
            user.mfa_secret = None  # not used for email/SMS
            db.commit()
            label = "email" if method == "email" else "SMS"
            return RedirectResponse(f"/settings/security?msg=2FA+enabled+via+{label}", status_code=303)

    return RedirectResponse("/settings/security", status_code=303)


@router.post("/2fa/disable")
async def mfa_disable(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/account/login", status_code=303)
    user.mfa_enabled = False
    user.mfa_method = None
    user.mfa_secret = None
    db.commit()
    return RedirectResponse("/settings/security?msg=Two-factor+authentication+has+been+disabled", status_code=303)


# ─── WebAuthn / Passkey routes ─────────────────────────────────────

from fastapi.responses import JSONResponse


@router.get("/2fa/passkey/register-start")
async def passkey_register_start(request: Request, db: Session = Depends(get_db)):
    """Return registration options JSON for navigator.credentials.create()."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    try:
        import base64
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria, UserVerificationRequirement,
            ResidentKeyRequirement, AuthenticatorAttachment,
        )
        rp_id, origin = _get_rp_info()

        # Existing passkey credentials to exclude (prevent re-registering same key)
        existing = db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == user.id).all()

        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="Alita AI",
            user_id=user.id.encode(),
            user_name=user.email,
            user_display_name=user.full_name or user.email,
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        challenge_cookie = _encode_wa_challenge(options.challenge)

        import json
        opts_dict = json.loads(options_to_json(options))

        resp = JSONResponse(opts_dict)
        resp.set_cookie(
            key=_WA_CHALLENGE_COOKIE, value=challenge_cookie,
            httponly=True, max_age=60 * _WA_CHALLENGE_MINUTES, samesite="lax",
            secure=os.getenv("ENV", "development") == "production",
        )
        return resp
    except ImportError:
        return JSONResponse({"error": "WebAuthn package not installed. Run: pip install webauthn"}, status_code=503)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/2fa/passkey/register-finish")
async def passkey_register_finish(request: Request, db: Session = Depends(get_db)):
    """Verify registration response and store new WebAuthn credential."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False, "error": "Not authenticated"}, status_code=401)
    try:
        import base64, json
        from webauthn import verify_registration_response
        from webauthn.helpers.structs import RegistrationCredential

        challenge_cookie = request.cookies.get(_WA_CHALLENGE_COOKIE)
        expected_challenge = _decode_wa_challenge(challenge_cookie) if challenge_cookie else None
        if not expected_challenge:
            return JSONResponse({"ok": False, "error": "Challenge expired — please try again."}, status_code=400)

        body = await request.json()
        rp_id, origin = _get_rp_info()

        credential = RegistrationCredential.parse_raw(json.dumps(body))
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )

        cred_id_b64 = base64.urlsafe_b64encode(verification.credential_id).decode().rstrip("=")
        pub_key_b64 = base64.b64encode(verification.credential_public_key).decode()
        device_name = body.get("deviceName") or "Fingerprint / Passkey"

        # Save credential
        db.add(WebAuthnCredential(
            id=str(uuid.uuid4()),
            user_id=user.id,
            credential_id=cred_id_b64,
            public_key=pub_key_b64,
            sign_count=verification.sign_count,
            device_name=device_name[:200],
        ))
        # Enable passkey as MFA method
        user.mfa_enabled = True
        user.mfa_method = "passkey"
        user.mfa_secret = None
        db.commit()

        resp = JSONResponse({"ok": True, "redirect": "/settings/security?msg=Fingerprint+2FA+enabled"})
        resp.delete_cookie(_WA_CHALLENGE_COOKIE)
        return resp
    except ImportError:
        return JSONResponse({"ok": False, "error": "WebAuthn package not installed."}, status_code=503)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@router.get("/2fa/passkey/auth-start")
async def passkey_auth_start(request: Request, db: Session = Depends(get_db)):
    """Return authentication options JSON for navigator.credentials.get()."""
    pending = request.cookies.get(_MFA_COOKIE)
    user_id = _decode_mfa_pending_token(pending) if pending else None
    if not user_id:
        return JSONResponse({"error": "Session expired"}, status_code=401)
    try:
        import base64, json
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import (
            UserVerificationRequirement, PublicKeyCredentialDescriptor,
        )
        rp_id, origin = _get_rp_info()
        creds = db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == user_id).all()
        if not creds:
            return JSONResponse({"error": "No passkeys registered for this account."}, status_code=400)

        allow_creds = [
            PublicKeyCredentialDescriptor(
                id=base64.urlsafe_b64decode(c.credential_id + "=="),
            )
            for c in creds
        ]
        options = generate_authentication_options(
            rp_id=rp_id,
            allow_credentials=allow_creds,
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        challenge_cookie = _encode_wa_challenge(options.challenge)

        opts_dict = json.loads(options_to_json(options))
        resp = JSONResponse(opts_dict)
        resp.set_cookie(
            key=_WA_CHALLENGE_COOKIE, value=challenge_cookie,
            httponly=True, max_age=60 * _WA_CHALLENGE_MINUTES, samesite="lax",
            secure=os.getenv("ENV", "development") == "production",
        )
        return resp
    except ImportError:
        return JSONResponse({"error": "WebAuthn package not installed."}, status_code=503)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/2fa/passkey/auth-finish")
async def passkey_auth_finish(request: Request, db: Session = Depends(get_db)):
    """Verify passkey assertion and grant a full session."""
    pending = request.cookies.get(_MFA_COOKIE)
    user_id = _decode_mfa_pending_token(pending) if pending else None
    if not user_id:
        return JSONResponse({"ok": False, "error": "Session expired. Please log in again."}, status_code=401)
    try:
        import base64, json
        from webauthn import verify_authentication_response
        from webauthn.helpers.structs import AuthenticationCredential

        challenge_cookie = request.cookies.get(_WA_CHALLENGE_COOKIE)
        expected_challenge = _decode_wa_challenge(challenge_cookie) if challenge_cookie else None
        if not expected_challenge:
            return JSONResponse({"ok": False, "error": "Challenge expired. Please try again."}, status_code=400)

        body = await request.json()
        rp_id, origin = _get_rp_info()
        next_url = body.get("next", "/dashboard")

        # Look up the stored credential by credential ID
        cred_id_b64 = body.get("id", "")
        pad = 4 - len(cred_id_b64) % 4
        cred_id_padded = cred_id_b64 + ("=" * pad if pad != 4 else "")
        stored = db.query(WebAuthnCredential).filter(
            WebAuthnCredential.credential_id == cred_id_b64,
            WebAuthnCredential.user_id == user_id,
        ).first()
        if not stored:
            return JSONResponse({"ok": False, "error": "Passkey not recognized."}, status_code=400)

        pub_key_bytes = base64.b64decode(stored.public_key)
        credential = AuthenticationCredential.parse_raw(json.dumps(body))
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=pub_key_bytes,
            credential_current_sign_count=stored.sign_count,
        )

        # Update sign count
        stored.sign_count = verification.new_sign_count
        stored.last_used_at = datetime.utcnow()

        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
        user.last_login = datetime.utcnow()
        db.commit()

        profile = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
        destination = next_url if next_url.startswith("/") else "/dashboard"
        if profile and profile.onboarding_status != OnboardingStatus.complete:
            destination = "/onboarding"

        token = create_access_token(user.id)
        resp = JSONResponse({"ok": True, "redirect": destination})
        _set_auth_cookie(resp, token)
        resp.delete_cookie(_MFA_COOKIE)
        resp.delete_cookie(_WA_CHALLENGE_COOKIE)
        return resp
    except ImportError:
        return JSONResponse({"ok": False, "error": "WebAuthn package not installed."}, status_code=503)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@router.post("/2fa/trusted-devices/{device_id}/revoke")
async def revoke_trusted_device(device_id: str, request: Request, db: Session = Depends(get_db)):
    """Revoke a specific trusted device so it has to complete 2FA again."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/account/login", status_code=303)
    db.query(TrustedDevice).filter(
        TrustedDevice.id == device_id,
        TrustedDevice.user_id == user.id,
    ).delete()
    db.commit()
    return RedirectResponse("/settings/security?msg=Trusted+device+removed", status_code=303)


@router.post("/2fa/trusted-devices/revoke-all")
async def revoke_all_trusted_devices(request: Request, db: Session = Depends(get_db)):
    """Revoke all trusted devices for the current user."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/account/login", status_code=303)
    db.query(TrustedDevice).filter(TrustedDevice.user_id == user.id).delete()
    db.commit()
    return RedirectResponse("/settings/security?msg=All+trusted+devices+removed", status_code=303)


@router.get("/logout")
async def logout():
    response = RedirectResponse("/account/login", status_code=303)
    response.delete_cookie("alita_token")
    return response


# ─── Email Verification ────────────────────────────────────────────

@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email(token: str = "", db: Session = Depends(get_db)):
    if not token:
        return RedirectResponse("/account/login", status_code=303)

    record = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.token == token,
        EmailVerificationToken.used == False,
    ).first()

    if not record:
        body = """
    <div class="card">
      <div class="logo"><h1>Alita AI</h1><p>Your AI-powered marketing team</p></div>
      <h2>Invalid link</h2>
      <p style="color:rgba(255,255,255,.65);margin:14px 0">
        This verification link is invalid or has already been used.
      </p>
      <a href="/account/login" class="btn" style="margin-top:20px">Back to Sign In</a>
    </div>"""
        return HTMLResponse(_page("Invalid Link", body), status_code=400)

    if record.expires_at < datetime.utcnow():
        body = """
    <div class="card">
      <div class="logo"><h1>Alita AI</h1><p>Your AI-powered marketing team</p></div>
      <h2>Link expired</h2>
      <p style="color:rgba(255,255,255,.65);margin:14px 0">
        This verification link has expired. Request a new one from your dashboard.
      </p>
      <a href="/account/resend-verification" class="btn" style="margin-top:20px">Resend Verification Email</a>
    </div>"""
        return HTMLResponse(_page("Link Expired", body), status_code=400)

    user = db.query(User).filter(User.id == record.user_id).first()
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    user.email_verified = True
    record.used = True
    db.commit()

    body = f"""
    <div class="card">
      <div class="logo"><h1>Alita AI</h1><p>Your AI-powered marketing team</p></div>
      <h2>&#10003; Email verified!</h2>
      <p style="color:rgba(255,255,255,.65);margin:14px 0;line-height:1.6">
        Your email address <strong>{user.email}</strong> has been confirmed.
        Your account is fully set up.
      </p>
      <a href="/dashboard" class="btn" style="margin-top:20px">Go to Dashboard</a>
    </div>"""
    return _page("Email Verified", body)


@router.get("/resend-verification", response_class=HTMLResponse)
async def resend_verification(request: Request, db: Session = Depends(get_db)):
    """Resend the verification email for the currently logged-in user."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/account/login?next=/account/resend-verification", status_code=303)

    if user.email_verified:
        return RedirectResponse("/dashboard?msg=Email+already+verified", status_code=303)

    base_url = os.getenv("APP_BASE_URL", str(request.base_url).rstrip("/"))
    _issue_and_send_verification_email(db, user.id, user.email, user.full_name, base_url)

    body = f"""
    <div class="card">
      <div class="logo"><h1>Alita AI</h1><p>Your AI-powered marketing team</p></div>
      <h2>Verification email sent</h2>
      <p style="color:rgba(255,255,255,.65);margin:14px 0;line-height:1.6">
        We've sent a new verification link to <strong>{user.email}</strong>.<br>
        Check your inbox (and spam folder).
      </p>
      <a href="/dashboard" class="btn" style="margin-top:20px">Back to Dashboard</a>
    </div>"""
    return _page("Verification Sent", body)


# ─── Password Reset ────────────────────────────────────────────────

def _send_reset_email(to_email: str, reset_url: str) -> bool:
    """Try to send a reset email via Resend. Returns True on success."""
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return False

    return _send_resend_email(
        to_email=to_email,
        subject="Reset your Alita AI password",
        html=f"""
            <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px">
              <h1 style="font-size:1.6rem;font-weight:800;color:#5c6ac4;margin-bottom:8px">Alita AI</h1>
              <h2 style="font-size:1.2rem;font-weight:700;margin-bottom:16px">Reset your password</h2>
              <p style="color:#444;margin-bottom:24px">Click the button below to set a new password. This link expires in 1 hour.</p>
              <a href="{reset_url}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:14px 28px;border-radius:10px;text-decoration:none;font-weight:700;font-size:1rem">Reset Password</a>
              <p style="color:#999;font-size:.8rem;margin-top:24px">If you didn't request this, you can safely ignore this email.<br>This link expires in 1 hour.</p>
            </div>""",
        text=f"Reset your password using this link (expires in 1 hour): {reset_url}",
    )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(sent: str = "", error: str = ""):
    if sent:
        body = """
    <div class="card">
      <div class="logo"><h1>Alita AI</h1><p>Your AI-powered marketing team</p></div>
      <h2>Check your email</h2>
      <p style="color:rgba(255,255,255,.65);margin-top:12px;line-height:1.6">
        If an account exists for that address, we've sent a password reset link.<br>
        The link expires in <strong>1 hour</strong>.
      </p>
      <a href="/account/login" class="btn" style="margin-top:28px">Back to Sign In</a>
    </div>"""
    else:
        error_html = f'<div class="error">{error}</div>' if error else ""
        body = f"""
    <div class="card">
      <div class="logo"><h1>Alita AI</h1><p>Your AI-powered marketing team</p></div>
      <h2>Forgot password?</h2>
      <p style="color:rgba(255,255,255,.55);font-size:.88rem;margin-top:8px;margin-bottom:4px">
        Enter your email and we'll send a reset link.
      </p>
      {error_html}
      <form method="post" action="/account/forgot-password">
        <label>Email Address</label>
        <input type="email" name="email" placeholder="jane@yourbusiness.com" required autofocus>
        <button type="submit" class="btn">Send Reset Link</button>
      </form>
      <div class="link-row"><a href="/account/login">Back to Sign In</a></div>
    </div>"""
    return _page("Forgot Password", body)


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    import uuid, secrets
    from datetime import timedelta

    email = email.strip().lower()
    user = db.query(User).filter(User.email == email, User.is_active == True).first()

    # Always redirect to "sent" page to avoid email enumeration
    if user:
        # Invalidate any prior unused tokens for this user
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used == False,
        ).delete()
        db.flush()

        token = secrets.token_urlsafe(48)
        expires = datetime.utcnow() + timedelta(hours=1)
        db.add(PasswordResetToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token=token,
            expires_at=expires,
        ))
        db.commit()

        base_url = os.getenv("BASE_URL", str(request.base_url).rstrip("/"))
        reset_url = f"{base_url}/account/reset-password?token={token}"
        _send_reset_email(user.email, reset_url)

    return RedirectResponse("/account/forgot-password?sent=1", status_code=303)


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(token: str = "", error: str = "", success: str = ""):
    if not token and not success:
        return RedirectResponse("/account/forgot-password", status_code=303)

    if success:
        body = """
    <div class="card">
      <div class="logo"><h1>Alita AI</h1><p>Your AI-powered marketing team</p></div>
      <h2>Password updated!</h2>
      <p style="color:rgba(255,255,255,.65);margin-top:12px">Your password has been changed successfully.</p>
      <a href="/account/login" class="btn" style="margin-top:28px">Sign In</a>
    </div>"""
        return _page("Password Updated", body)

    error_html = f'<div class="error">{error}</div>' if error else ""
    body = f"""
    <div class="card">
      <div class="logo"><h1>Alita AI</h1><p>Your AI-powered marketing team</p></div>
      <h2>Set new password</h2>
      {error_html}
      <form method="post" action="/account/reset-password">
        <input type="hidden" name="token" value="{token}">
        <label>New Password</label>
        <div class="pw-wrap">
          <input type="password" id="pw1" name="password" placeholder="At least 8 characters" required minlength="8" autofocus>
          <button type="button" class="eye-btn" onclick="togglePw('pw1',this)" title="Show">&#128065;</button>
        </div>
        <label>Confirm Password</label>
        <div class="pw-wrap">
          <input type="password" id="pw2" name="confirm" placeholder="Repeat password" required minlength="8">
          <button type="button" class="eye-btn" onclick="togglePw('pw2',this)" title="Show">&#128065;</button>
        </div>
        <button type="submit" class="btn">Update Password</button>
      </form>
      <div class="link-row"><a href="/account/login">Back to Sign In</a></div>
    </div>"""
    return _page("Reset Password", body)


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    from urllib.parse import quote

    if len(password) < 8:
        return RedirectResponse(f"/account/reset-password?token={token}&error=Password+must+be+at+least+8+characters", status_code=303)
    if password != confirm:
        return RedirectResponse(f"/account/reset-password?token={token}&error=Passwords+do+not+match", status_code=303)

    record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token,
        PasswordResetToken.used == False,
    ).first()

    if not record:
        return RedirectResponse("/account/forgot-password?error=Invalid+or+expired+reset+link", status_code=303)

    if record.expires_at < datetime.utcnow():
        return RedirectResponse("/account/forgot-password?error=Reset+link+has+expired.+Request+a+new+one.", status_code=303)

    user = db.query(User).filter(User.id == record.user_id).first()
    if not user:
        return RedirectResponse("/account/forgot-password", status_code=303)

    user.password_hash = hash_password(password)
    record.used = True
    db.commit()

    # Best effort: send confirmation that password was changed
    _send_password_changed_email(user.email)

    return RedirectResponse("/account/reset-password?success=1", status_code=303)


# ═══════════════════════════════════════════════════════════════════
# SOCIAL LOGIN — Google & Facebook OAuth
# ═══════════════════════════════════════════════════════════════════


@router.get("/google")
async def google_login(request: Request):
    """Redirect to Google's consent screen for sign-in (scope: openid email profile)."""
    import secrets as _sec
    from urllib.parse import urlencode as _ue

    client_id = os.getenv("GMAIL_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="Google OAuth not configured (GMAIL_CLIENT_ID missing)")

    redirect_uri = os.getenv(
        "GOOGLE_LOGIN_REDIRECT_URI",
        _app_base_url(request) + "/account/google/callback",
    )

    state = _sec.token_urlsafe(24)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
        "prompt": "select_account",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{_ue(params)}"
    state_token = jwt.encode(
        {"state": state, "exp": datetime.utcnow() + timedelta(minutes=10)},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="_g_state", value=state_token, httponly=True, max_age=600,
        samesite="lax", secure=os.getenv("ENV", "development") == "production",
    )
    return response


@router.get("/google/callback", response_class=HTMLResponse)
async def google_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(""),
    db: Session = Depends(get_db),
):
    """Exchange Google auth code, find/create user, and issue an Alita session."""
    import httpx
    from urllib.parse import quote

    # Validate CSRF state
    state_cookie = request.cookies.get("_g_state", "")
    try:
        payload = jwt.decode(state_cookie, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("state") != state:
            raise ValueError("State mismatch")
    except Exception:
        return RedirectResponse("/account/login?error=Login+session+expired.+Please+try+again.", status_code=303)

    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    redirect_uri = os.getenv(
        "GOOGLE_LOGIN_REDIRECT_URI",
        _app_base_url(request) + "/account/google/callback",
    )

    # Exchange code for access token
    async with httpx.AsyncClient() as hc:
        token_resp = await hc.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })

    if token_resp.status_code != 200:
        err = token_resp.json().get("error_description", "Unknown error")
        return RedirectResponse(f"/account/login?error={quote('Google sign-in failed: ' + err)}", status_code=303)

    access_token = token_resp.json().get("access_token", "")

    # Fetch user profile
    async with httpx.AsyncClient() as hc:
        info_resp = await hc.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if info_resp.status_code != 200:
        return RedirectResponse("/account/login?error=Could+not+fetch+Google+account+info.", status_code=303)

    info = info_resp.json()
    google_id = info.get("id", "")
    email     = info.get("email", "").lower().strip()
    full_name = info.get("name", email.split("@")[0])

    if not email:
        return RedirectResponse("/account/login?error=No+email+returned+from+Google.", status_code=303)

    user, is_new = _find_or_create_social_user(db, "google", google_id, email, full_name)

    # Decide destination
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
    if is_new or (profile and profile.onboarding_status != OnboardingStatus.complete):
        destination = "/onboarding"
    else:
        # Ask if they want to use this Gmail for inbox — friendly opt-in
        destination = f"/account/confirm-gmail-inbox?email={quote(email)}"

    token = create_access_token(user.id)
    response = RedirectResponse(destination, status_code=303)
    _set_auth_cookie(response, token)
    response.delete_cookie("_g_state")
    return response


@router.get("/facebook")
async def facebook_login(request: Request):
    """Redirect to Facebook OAuth dialog — includes Meta posting scopes."""
    import secrets as _sec
    from urllib.parse import urlencode as _ue

    app_id = os.getenv("META_APP_ID")
    if not app_id:
        raise HTTPException(status_code=500, detail="Facebook OAuth not configured (META_APP_ID missing)")

    redirect_uri = os.getenv(
        "FACEBOOK_LOGIN_REDIRECT_URI",
        _app_base_url(request) + "/account/facebook/callback",
    )

    state = _sec.token_urlsafe(24)
    params = {
        "client_id":     app_id,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope": (
            "public_profile,email,pages_show_list,instagram_basic,"
            "instagram_manage_comments,pages_manage_posts,pages_read_engagement"
        ),
        "state": state,
    }
    auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?{_ue(params)}"
    state_token = jwt.encode(
        {"state": state, "exp": datetime.utcnow() + timedelta(minutes=10)},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="_fb_state", value=state_token, httponly=True, max_age=600,
        samesite="lax", secure=os.getenv("ENV", "development") == "production",
    )
    return response


@router.get("/facebook/callback", response_class=HTMLResponse)
async def facebook_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(""),
    db: Session = Depends(get_db),
):
    """Exchange Facebook code, auto-connect Meta token, find/create user, set session."""
    import httpx
    from urllib.parse import quote
    from cryptography.fernet import Fernet
    from database.models import MetaOAuthToken

    # Validate CSRF state
    state_cookie = request.cookies.get("_fb_state", "")
    try:
        payload = jwt.decode(state_cookie, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("state") != state:
            raise ValueError("State mismatch")
    except Exception:
        return RedirectResponse("/account/login?error=Login+session+expired.+Please+try+again.", status_code=303)

    app_id     = os.getenv("META_APP_ID")
    app_secret = os.getenv("META_APP_SECRET")
    redirect_uri = os.getenv(
        "FACEBOOK_LOGIN_REDIRECT_URI",
        _app_base_url(request) + "/account/facebook/callback",
    )

    # Exchange code for short-lived token
    async with httpx.AsyncClient() as hc:
        token_resp = await hc.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                "client_id":     app_id,
                "client_secret": app_secret,
                "redirect_uri":  redirect_uri,
                "code":          code,
            },
        )

    if token_resp.status_code != 200:
        err = token_resp.json().get("error", {}).get("message", "Unknown error")
        return RedirectResponse(f"/account/login?error={quote('Facebook sign-in failed: ' + err)}", status_code=303)

    short_token = token_resp.json().get("access_token", "")

    # Upgrade to long-lived token
    long_token = short_token
    async with httpx.AsyncClient() as hc:
        ll_resp = await hc.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                "grant_type":       "fb_exchange_token",
                "client_id":        app_id,
                "client_secret":    app_secret,
                "fb_exchange_token": short_token,
            },
        )
    if ll_resp.status_code == 200:
        long_token = ll_resp.json().get("access_token", short_token)

    # Fetch user profile
    async with httpx.AsyncClient() as hc:
        me_resp = await hc.get(
            "https://graph.facebook.com/me",
            params={"fields": "id,name,email", "access_token": long_token},
        )

    if me_resp.status_code != 200:
        return RedirectResponse("/account/login?error=Could+not+fetch+Facebook+account+info.", status_code=303)

    me       = me_resp.json()
    fb_id    = me.get("id", "")
    email    = me.get("email", "").lower().strip()
    full_name = me.get("name", "")

    if not email:
        return RedirectResponse(
            "/account/login?error=Facebook+didn%27t+share+your+email.+Ensure+your+Facebook+account+has+a+confirmed+email+address.",
            status_code=303,
        )

    user, is_new = _find_or_create_social_user(db, "facebook", fb_id, email, full_name)

    # Auto-store / update the Meta OAuth token for this user's client profile
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
    if profile and long_token:
        _enc_key = os.getenv("TOKEN_ENCRYPTION_KEY", "")
        try:
            _fernet  = Fernet(_enc_key.encode() if isinstance(_enc_key, str) else _enc_key)
            enc_tok  = _fernet.encrypt(long_token.encode()).decode()
        except Exception:
            enc_tok = long_token  # fallback: store plain if key misconfigured

        existing_meta = db.query(MetaOAuthToken).filter(
            MetaOAuthToken.client_profile_id == profile.id
        ).first()
        if existing_meta:
            existing_meta.access_token_enc = enc_tok
            existing_meta.meta_user_id     = fb_id
            existing_meta.updated_at       = datetime.utcnow()
        else:
            db.add(MetaOAuthToken(
                id=str(uuid.uuid4()),
                client_profile_id=profile.id,
                meta_user_id=fb_id,
                access_token_enc=enc_tok,
                scopes=(
                    "public_profile,email,pages_show_list,instagram_basic,"
                    "instagram_manage_comments,pages_manage_posts,pages_read_engagement"
                ),
                is_long_lived=True,
            ))

        profile.meta_user_id      = fb_id
        profile.meta_connected_at = datetime.utcnow()
        db.commit()

    token = create_access_token(user.id)
    if is_new or (profile and profile.onboarding_status != OnboardingStatus.complete):
        destination = "/onboarding"
    else:
        destination = "/dashboard"

    response = RedirectResponse(destination, status_code=303)
    _set_auth_cookie(response, token)
    response.delete_cookie("_fb_state")
    return response


@router.get("/confirm-gmail-inbox", response_class=HTMLResponse)
async def confirm_gmail_inbox(request: Request, email: str = ""):
    """Post-Google-login: ask the user if they want to connect this Gmail as their inbox."""
    user = get_current_user(request, db=next(get_db()))
    if not user:
        return RedirectResponse("/account/login", status_code=303)

    display_email = email or user.email
    body = f"""
    <div class="card" style="max-width:520px">
      <div class="logo">
        <h1>Alita AI</h1>
        <p>Your AI-powered marketing team</p>
      </div>
      <h2 style="text-align:center;margin-bottom:16px">Connect your inbox?</h2>
      <p style="text-align:center;color:rgba(255,255,255,0.65);margin-bottom:28px;line-height:1.6">
        You signed in with <strong style="color:white">{display_email}</strong>.<br>
        Would you like Alita to use this Gmail account to read incoming emails
        and send AI-powered replies &amp; campaigns?
      </p>
      <a href="/settings/email/authorize" class="btn" style="margin-bottom:14px">&#128231;&nbsp; Yes, connect my Gmail inbox</a>
      <a href="/dashboard" class="btn" style="background:rgba(255,255,255,0.08);margin-top:0">Skip for now</a>
      <p class="hint" style="text-align:center;margin-top:16px">You can always connect it later in Settings &rarr; Email.</p>
    </div>"""
    return _page("Connect Gmail Inbox", body)
