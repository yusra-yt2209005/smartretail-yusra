"""
Application-level exceptions.

Services raise these plain Python exceptions instead of FastAPI's
HTTPException. The API layer translates them into consistent HTTP
responses.

This keeps business logic independent from FastAPI-specific request and
response handling while giving the application one consistent error model.
"""


class AppError(Exception):
    """
    Base class for application/domain errors.

    `status_code` defines the HTTP status the API layer should use.
    `error_code` provides a stable machine-readable error identifier.
    """

    status_code = 500
    error_code = "internal_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"

    def __init__(self, resource: str, identifier: object):
        super().__init__(
            f"{resource} with id '{identifier}' was not found"
        )


class UnauthorizedError(AppError):
    """
    Authentication failed or valid credentials were not provided.
    """

    status_code = 401
    error_code = "unauthorized"

    def __init__(
        self,
        message: str = "Invalid or missing credentials",
    ):
        super().__init__(message)


class ForbiddenError(AppError):
    """
    Authentication succeeded, but the user is not allowed to perform
    the requested action.
    """

    status_code = 403
    error_code = "forbidden"

    def __init__(
        self,
        message: str = "You do not have permission to perform this action",
    ):
        super().__init__(message)


class ConflictError(AppError):
    """
    The request conflicts with the application's current state.

    Examples:
    - duplicate email
    - duplicate SKU
    - invalid state transition
    """

    status_code = 409
    error_code = "conflict"


class ValidationFailedError(AppError):
    """
    A business rule failed after normal request validation succeeded.

    This is different from Pydantic validation, which handles malformed
    or invalid request fields before the service is called.
    """

    status_code = 422
    error_code = "validation_failed"

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))