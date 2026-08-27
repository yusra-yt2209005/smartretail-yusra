from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.user import TokenResponse, UserLogin, UserOut, UserRegister
from app.services import auth_service

from app.core.dependencies import get_current_user, require_role
from app.models.user import User, UserRole

#routes:
# POST /auth/register
# POST /auth/login
# GET  /auth/me

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: UserRegister,
    db: Session = Depends(get_db),
):
    """
    Register a new customer or merchant account.

    FastAPI validates the request body into UserRegister before this
    function runs. The router delegates business logic to auth_service.

    response_model=UserOut ensures only fields defined by UserOut are
    serialized in the response, so password_hash is never exposed.
    """
    return auth_service.register_user(db, data)


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: UserLogin,
    db: Session = Depends(get_db),
):
    """
    Authenticate a user and return a JWT access token.
    """
    token = auth_service.login_user(db, data)

    return TokenResponse(
        access_token=token,
    )


@router.get("/me", response_model=UserOut)
def me(
    current_user: User = Depends(get_current_user),
):
    """
    Return the currently authenticated user.

    If the bearer token is missing, invalid, expired, or belongs to an
    inactive/nonexistent user, get_current_user raises UnauthorizedError
    before this endpoint body runs.
    """
    return current_user



@router.get("/merchant-only", response_model=UserOut)
def merchant_only(
    current_user: User = Depends(
        require_role(UserRole.MERCHANT)
    ),
):
    """
    Test endpoint for role authorization.

    Only authenticated merchants can access this route.
    """
    return current_user