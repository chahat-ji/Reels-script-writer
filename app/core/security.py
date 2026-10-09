"""
app/core/security.py
Cryptographic security, password hashing, and JWT token issuance.

Implements standard OAuth2 Bearer password hashing with bcrypt
and signed stateless JWT tokens with role-based access control.
"""

from datetime import datetime, timedelta, timezone
import os
from typing import Any, Dict, Optional
import bcrypt
import jwt

# Configuration constants
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "scriptwriter-secret-key-change-in-prod-2026")
ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt with auto-generated salt."""
    if not password:
        raise ValueError("Password cannot be empty")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify that a plaintext password matches an existing bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Encode payload into a signed JWT access token.
    Claims typically include 'sub' (user_id), 'username', and 'role'.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": now,
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a signed JWT access token.
    Raises jwt.PyJWTError on invalid signature, expiration, or malformed token.
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

