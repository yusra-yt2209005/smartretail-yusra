"""
Business logic for user registration and login.

This module contains no FastAPI router logic. It receives a SQLAlchemy
Session and validated Pydantic data, performs business rules/database
operations, and either returns a result or raises an application error.

The API layer is responsible for translating application errors into
HTTP responses.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.user import UserLogin, UserRegister


def register_user(db: Session, data: UserRegister) -> User:
    """
    Create a new user account.

    Raises ConflictError if the email is already registered.
    """

    existing_user = db.scalar(
        select(User).where(User.email == data.email)
    )

    if existing_user is not None:
        raise ConflictError(
            f"A user with email '{data.email}' already exists"
        )

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def login_user(db: Session, data: UserLogin) -> str:
    """
    Validate credentials and return a signed JWT access token.

    A generic UnauthorizedError is used for invalid credentials so the
    endpoint does not reveal whether a particular email is registered.
    """

    user = db.scalar(
        select(User).where(User.email == data.email)
    )

    if user is None or not user.is_active:
        raise UnauthorizedError("Incorrect email or password")

    if not verify_password(data.password, user.password_hash):
        raise UnauthorizedError("Incorrect email or password")

    return create_access_token(
        subject=str(user.id),
        role=user.role.value,
    )