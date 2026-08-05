import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError #1.6
from app.models.user import UserRole


from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User


# Extracts a token from:
#
# Authorization: Bearer <token>
#
# auto_error=False prevents FastAPI from raising its own HTTPException
# when the header is missing. Instead, get_current_user raises our
# UnauthorizedError so all API errors keep the same JSON structure.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False,
)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Verify the bearer token and return the authenticated User.

    Steps:
    1. Make sure a token was provided.
    2. Verify and decode the JWT.
    3. Read the user's UUID from the `sub` claim.
    4. Load that user from PostgreSQL.
    5. Make sure the account still exists and is active.
    """

    if token is None:
        raise UnauthorizedError("Missing authentication token")

    try:
        payload = decode_access_token(token)

        subject = payload.get("sub")

        if not isinstance(subject, str):
            raise UnauthorizedError("Token is invalid or expired")

        user_id = uuid.UUID(subject)

    except (JWTError, ValueError):
        raise UnauthorizedError("Token is invalid or expired")

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return user


#TASK 1.6


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory for role-based authorization.
        current_user: User = Depends(
            require_role(UserRole.MERCHANT)
        )
    The returned dependency first authenticates the user through
    get_current_user(), then checks whether their current database role
    is one of the allowed roles.
    """

    def checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            allowed = ", ".join(
                role.value for role in allowed_roles
            )

            raise ForbiddenError(
                f"This action requires one of these roles: {allowed}"
            )

        return current_user

    return checker