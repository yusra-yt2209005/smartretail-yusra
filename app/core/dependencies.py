import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# BEARER TOKEN SECURITY SCHEME
# ---------------------------------------------------------------------------

# HTTPBearer tells FastAPI/Swagger that protected endpoints expect:
#
# Authorization: Bearer <token>
#
# This is different from OAuth2PasswordBearer.
#
# OAuth2PasswordBearer made Swagger try to log in using an OAuth2
# username/password form.
#
# Our /auth/login endpoint already accepts JSON and returns a JWT,
# so HTTPBearer is simpler for our API:
#
# 1. Call POST /auth/login
# 2. Copy the returned access_token
# 3. Click "Authorize" in Swagger
# 4. Paste the token
# 5. Swagger automatically sends:
#
#    Authorization: Bearer <token>
#
# auto_error=False means HTTPBearer will NOT automatically raise
# FastAPI's own error when authentication is missing.
#
# Instead, our get_current_user() function handles the error using
# UnauthorizedError so our API keeps the same JSON error structure.
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# AUTHENTICATION
# ---------------------------------------------------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticate the request and return the current User.

    This function answers:

        "WHO is making this request?"

    Steps:
    1. Read the Bearer token from the Authorization header.
    2. Verify and decode the JWT.
    3. Read the user's UUID from the JWT `sub` claim.
    4. Load the user from PostgreSQL.
    5. Verify that the user still exists and is active.
    6. Return the authenticated User object.
    """

    # `credentials` represents the Authorization header.
    #
    # For example:
    #
    # Authorization: Bearer eyJhbGciOi...
    #
    # If the request did not contain a Bearer token,
    # credentials will be None because auto_error=False.
    if credentials is None:
        raise UnauthorizedError("Missing authentication token")

    # HTTPAuthorizationCredentials contains two useful values:
    #
    # credentials.scheme
    #     -> "Bearer"
    #
    # credentials.credentials
    #     -> the actual JWT, such as "eyJhbGciOi..."
    #
    # We only need the JWT itself.
    token = credentials.credentials

    try:
        # Verify the JWT signature and expiration time,
        # then return the decoded JWT payload.
        #
        # Example payload:
        #
        # {
        #     "sub": "user-uuid",
        #     "role": "merchant",
        #     "exp": ...
        # }
        payload = decode_access_token(token)

        # The `sub` (subject) claim stores the user's UUID
        # as a string.
        subject = payload.get("sub")

        # Make sure the JWT actually contains a valid string subject.
        if not isinstance(subject, str):
            raise UnauthorizedError("Token is invalid or expired")

        # Convert:
        #
        # "3fd96512-6915-458e-82c8-67c8eaf5e5f8"
        #
        # into a Python UUID object that SQLAlchemy can use.
        user_id = uuid.UUID(subject)

    # JWTError can happen when:
    # - token signature is invalid
    # - token is expired
    # - token is malformed
    #
    # ValueError can happen when:
    # - the `sub` value is not a valid UUID
    except (JWTError, ValueError):
        raise UnauthorizedError("Token is invalid or expired")

    # Load the CURRENT user from PostgreSQL.
    #
    # We do not trust only the JWT because the account could have been
    # disabled or deleted after the token was created.
    user = db.get(User, user_id)

    # Reject deleted or inactive users.
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    # Authentication succeeded.
    #
    # FastAPI can now inject this User object into the endpoint
    # or into require_role().
    return user


# ---------------------------------------------------------------------------
# AUTHORIZATION — TASK 1.6
# ---------------------------------------------------------------------------

def require_role(*allowed_roles: UserRole):
    """
    Dependency factory for role-based authorization.

    This function answers:

        "Is this authenticated user ALLOWED to perform this action?"

    Example:

        current_user: User = Depends(
            require_role(UserRole.MERCHANT)
        )

    Flow:

        request
            ↓
        get_current_user()
            ↓
        authenticated User
            ↓
        require_role()
            ↓
        role allowed?
            ├── yes → continue
            └── no  → 403 Forbidden

    Authentication and authorization are intentionally separate:

        get_current_user()
            -> Who are you?

        require_role()
            -> Are you allowed to do this?
    """

    # require_role() returns another function.
    #
    # For example:
    #
    # require_role(UserRole.MERCHANT, UserRole.ADMIN)
    #
    # creates a dependency that allows either merchants or admins.
    def checker(
        # Before this checker runs, FastAPI automatically calls
        # get_current_user().
        #
        # Therefore current_user is already authenticated here.
        current_user: User = Depends(get_current_user),
    ) -> User:

        # Check whether the user's current database role is included
        # in the roles permitted for this endpoint.
        if current_user.role not in allowed_roles:

            # Convert:
            #
            # (UserRole.MERCHANT, UserRole.ADMIN)
            #
            # into:
            #
            # "merchant, admin"
            #
            # for a readable error message.
            allowed = ", ".join(
                role.value for role in allowed_roles
            )

            # The user IS authenticated, but does not have permission.
            #
            # Therefore this is:
            #
            # 403 Forbidden
            #
            # NOT 401 Unauthorized.
            raise ForbiddenError(
                f"This action requires one of these roles: {allowed}"
            )

        # Role check passed.
        #
        # Return the same User so the endpoint/service can use it
        # for ownership checks and other business logic.
        return current_user

    return checker


# ---------------------------------------------------------------------------
# OPTIONAL AUTHENTICATION
# ---------------------------------------------------------------------------

def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """
    Optional authentication for public endpoints.

    This is used for endpoints such as:

        GET /products

    because everyone is allowed to browse products, but the results
    can depend on WHO is viewing them.

    Examples:

    Anonymous visitor:
        -> no token
        -> return None
        -> see public published/in-stock products

    Customer:
        -> valid token
        -> return customer User
        -> see public products

    Merchant:
        -> valid token
        -> return merchant User
        -> may also see their own draft/inactive products

    Admin:
        -> valid token
        -> return admin User
        -> may see all products

    If authentication is missing or invalid here, we return None
    because authentication is OPTIONAL for this endpoint.
    """

    # No Authorization header was provided.
    #
    # This is allowed for public endpoints.
    if credentials is None:
        return None

    # Extract only the actual JWT from:
    #
    # Authorization: Bearer <JWT>
    token = credentials.credentials

    try:
        # Verify the JWT and decode its claims.
        payload = decode_access_token(token)

        # Get the user UUID stored in the JWT's `sub` claim.
        subject = payload.get("sub")

        # If `sub` is missing or not a string,
        # treat this visitor as anonymous.
        if not isinstance(subject, str):
            return None

        # Convert the UUID string into a UUID object.
        user_id = uuid.UUID(subject)

    # Invalid, expired, malformed JWT
    # or invalid UUID:
    #
    # treat as anonymous for this OPTIONAL dependency.
    except (JWTError, ValueError):
        return None

    # Load the current user from PostgreSQL.
    user = db.get(User, user_id)

    # If the account has been deleted or deactivated,
    # treat the viewer as anonymous.
    if user is None or not user.is_active:
        return None

    # Valid authenticated user.
    return user