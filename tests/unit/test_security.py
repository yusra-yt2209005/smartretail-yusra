"""
Unit tests for app/core/security.py.

These tests focus only on password hashing and JWT behavior.
No HTTP requests and no database are needed.
"""

from jose import JWTError
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_does_not_store_plaintext():
    """
    A password hash must not equal the original plaintext password.
    """

    password = "password123"

    hashed = hash_password(password)

    assert hashed != password


def test_verify_password_accepts_correct_password():
    """
    A correct plaintext password should match its bcrypt hash.
    """

    password = "password123"

    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_rejects_wrong_password():
    """
    A wrong password must not match the stored hash.
    """

    hashed = hash_password("password123")

    assert verify_password("wrong-password", hashed) is False


def test_access_token_contains_subject_and_role():
    """
    After creating a JWT, decoding it should recover the claims we put
    into it.
    """

    token = create_access_token(
        subject="12345678-1234-5678-1234-567812345678",
        role="merchant",
    )

    payload = decode_access_token(token)

    assert payload["sub"] == "12345678-1234-5678-1234-567812345678"
    assert payload["role"] == "merchant"

    # create_access_token() also adds an expiration claim.
    assert "exp" in payload


def test_invalid_token_is_rejected():
    """
    Tampered/malformed tokens should cause python-jose to raise JWTError.
    """

    with pytest.raises(JWTError):
        decode_access_token("this-is-not-a-valid-jwt")


# bcrypt hashing ✓
# correct password ✓
# wrong password rejected ✓
# JWT creation ✓
# JWT decoding ✓
# bad JWT rejected ✓

        