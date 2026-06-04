"""
IAM helpers: password hashing (bcrypt), JWT creation/verification, FastAPI dependency, OTP.
"""
import os
import jwt
import bcrypt
import random
from pathlib import Path
from datetime import datetime, timedelta, timezone
from fastapi import Header, HTTPException
from typing import Optional

# Load .env explicitly from the project root so env vars are available
# even when this module is imported before load_dotenv() runs in main.py
from dotenv import load_dotenv as _load_dotenv
_load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

# ── OTP store (in-memory, 10-min TTL) ────────────────────────────────────────
_otp_store: dict = {}  # email → {code, expires_at}


def generate_otp(email: str) -> str:
    code = str(random.randint(100000, 999999))
    _otp_store[email.lower()] = {
        "code": code,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return code


def verify_otp(email: str, code: str) -> bool:
    key = email.lower().strip()
    entry = _otp_store.get(key)
    if not entry:
        return False
    if datetime.now(timezone.utc) > entry["expires_at"]:
        _otp_store.pop(key, None)
        return False
    if entry["code"] != code.strip():
        return False
    _otp_store.pop(key, None)
    return True


def send_otp_email(to_email: str, code: str) -> bool:
    """Send OTP via Resend → SMTP → fallback (returns False so caller shows dev hint)."""
    import logging
    log = logging.getLogger(__name__)

    # Always re-read .env so changes take effect without a server restart
    _load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

    subject = "Your Healthcare Verification Code"
    body = (
        f"Your verification code is: {code}\n\n"
        f"This code expires in 10 minutes.\n"
        f"Do not share this code with anyone."
    )
    resend_key = os.getenv("RESEND_API_KEY")
    smtp_host  = os.getenv("SMTP_HOST")
    log.info(f"Email provider check — RESEND={'SET' if resend_key else 'missing'}, SMTP={'SET' if smtp_host else 'missing'}")

    if resend_key:
        try:
            import httpx
            from_addr = os.getenv("EMAIL_FROM", "Healthcare <onboarding@resend.dev>")
            log.info(f"Sending OTP via Resend from={from_addr!r} to={to_email!r}")
            resp = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                json={"from": from_addr, "to": [to_email], "subject": subject, "text": body},
                timeout=10,
            )
            if resp.status_code in (200, 201):
                log.info(f"Resend OTP email sent to {to_email}")
                return True
            log.error(f"Resend rejected email: {resp.status_code} — {resp.text}")
            return False
        except Exception as e:
            log.error(f"Resend exception: {e}")
            return False
    elif smtp_host:
        try:
            import smtplib
            from email.mime.text import MIMEText
            port      = int(os.getenv("SMTP_PORT", "587"))
            user      = os.getenv("SMTP_USER", "")
            password  = os.getenv("SMTP_PASS", "")
            from_addr = os.getenv("EMAIL_FROM", user)
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"]    = from_addr
            msg["To"]      = to_email
            with smtplib.SMTP(smtp_host, port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                if user and password:
                    smtp.login(user, password)
                smtp.sendmail(from_addr, [to_email], msg.as_string())
            return True
        except Exception:
            return False
    return False

SECRET_KEY  = os.getenv("JWT_SECRET", "hc-super-secret-change-in-prod-2026")
ALGORITHM   = "HS256"
TOKEN_TTL_H = 24


# ── Passwords ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_token(user_id: str, role: str, linked_id: str, username: str) -> str:
    payload = {
        "sub":       user_id,
        "role":      role,
        "linked_id": linked_id or "",
        "username":  username,
        "exp":       datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_H),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Returns decoded token payload: {sub, role, linked_id, username}."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_token(authorization.split(" ", 1)[1])


def require_admin(authorization: Optional[str] = Header(None)) -> dict:
    u = get_current_user(authorization)
    if u["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return u


def require_doctor_or_admin(authorization: Optional[str] = Header(None)) -> dict:
    u = get_current_user(authorization)
    if u["role"] not in ("doctor", "admin"):
        raise HTTPException(status_code=403, detail="Doctor access required")
    return u
