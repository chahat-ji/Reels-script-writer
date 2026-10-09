"""
tests/test_security.py
Unit tests for password hashing and JWT token issuance in app/core/security.py.
Strictly offline, 0 external network calls.
"""

from datetime import timedelta
import pytest
import jwt

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing_and_verification():
    raw = "SuperSecret123!"
    hashed = hash_password(raw)

    assert hashed != raw
    assert hashed.startswith("$2b$")
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password("", hashed) is False


def test_jwt_token_roundtrip():
    payload = {
        "sub": "usr_test123",
        "username": "rosh",
        "role": "admin",
    }
    token = create_access_token(payload, expires_delta=timedelta(minutes=30))
    decoded = decode_access_token(token)

    assert decoded["sub"] == "usr_test123"
    assert decoded["username"] == "rosh"
    assert decoded["role"] == "admin"
    assert "exp" in decoded


def test_jwt_expired_token():
    payload = {"sub": "usr_expired", "role": "user"}
    token = create_access_token(payload, expires_delta=timedelta(seconds=-10))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_jwt_invalid_token():
    with pytest.raises(jwt.DecodeError):
        decode_access_token("not.a.valid.jwt.token")

