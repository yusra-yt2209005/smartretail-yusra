"""
Security primitives for password hashing and JWT handling.

This module deliberately has no database or FastAPI dependencies.
It only knows how to:

1. Hash and verify passwords.
2. Create and verify JWT access tokens.

Database lookups and HTTP errors belong in higher-level modules such as
dependencies.py and auth_service.py.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings


# Configure Passlib to use bcrypt for password hashing.
#
# bcrypt generates a random salt for every hash, so the same plaintext
# password does not normally produce the same stored hash.
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    Only the resulting hash should ever be stored in the database.
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Return True if the plaintext password matches the stored hash.
    """
    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


def create_access_token(subject: str, role: str) -> str:
    """
    Create and sign a JWT access token.

    Claims:
    - sub: identifies the user (their UUID as a string)
    - role: records the user's role when the token was issued
    - exp: defines when the token expires

    The current database user should still be loaded for protected
    requests so account status and authorization can use current data.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )

    payload = {
        "sub": subject,
        "role": role,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Verify and decode a JWT access token.

    python-jose validates the token signature and its `exp` claim.

    Invalid, malformed, tampered-with, or expired tokens raise JWTError.
    The caller is responsible for translating that into an HTTP response.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )