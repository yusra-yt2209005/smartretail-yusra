import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


class UserRegister(BaseModel):
    """
    Request body for POST /auth/register.

    Public registration may create customer or merchant accounts.
    Admin accounts cannot be created through this endpoint.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.CUSTOMER

    @field_validator("role")
    @classmethod
    def prevent_admin_registration(cls, role: UserRole) -> UserRole:
        if role == UserRole.ADMIN:
            raise ValueError("Admin accounts cannot be created through registration")
        return role


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    """
    Public representation of a user.

    password_hash is intentionally absent so it cannot be serialized
    through this response schema.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"