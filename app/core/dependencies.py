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


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """
    Optional authentication for public endpoints.

    If no bearer token is provided:
        return None

    If a valid token is provided:
        return the corresponding active User

    If the token is invalid/expired or the user does not exist/is inactive:
        return None

    This is useful for endpoints like GET /products, where anonymous users
    are allowed to browse, but logged-in merchants/admins may see more.
    """

    # No Authorization header at all.
    # Public access is allowed, so we simply represent the viewer as None.
    if token is None:
        return None

    try:
        # Verify signature + expiration and decode the JWT.
        payload = decode_access_token(token)

        # JWT "sub" stores our user's UUID as a string.
        subject = payload.get("sub")

        # A valid user token must contain a string subject.
        if not isinstance(subject, str):
            return None

        # Convert the UUID string from the token into a Python UUID object.
        user_id = uuid.UUID(subject)

    # JWTError:
    #   invalid signature, expired token, malformed JWT, etc.
    #
    # ValueError:
    #   `sub` existed but was not a valid UUID.
    except (JWTError, ValueError):
        return None

    # Load the CURRENT database user rather than trusting only the JWT.
    user = db.get(User, user_id)

    # Treat nonexistent/deactivated users like anonymous visitors for this
    # optional dependency.
    if user is None or not user.is_active:
        return None

    return user