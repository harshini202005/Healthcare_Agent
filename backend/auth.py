"""
IAM helpers: password hashing (bcrypt), JWT creation/verification, FastAPI dependency.
"""
import os
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Header, HTTPException
from typing import Optional

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
