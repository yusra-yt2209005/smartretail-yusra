from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import auth, categories, health, products
from app.core.exceptions import AppError

app = FastAPI(title="SmartRetail API", version="0.1.0")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(products.router)


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError):
    """
    This is the one place that turns a domain exception into an HTTP
    response. Because every service function raises AppError subclasses
    (NotFoundError, ForbiddenError, ...) instead of HTTPException, EVERY
    endpoint gets the same JSON error shape for free, without each router
    function needing its own try/except.
    """
    body = {"error_code": exc.error_code, "message": exc.message}
    if hasattr(exc, "errors"):
        body["details"] = exc.errors
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError):
    """
    FastAPI/Pydantic raise this automatically when the request body
    doesn't match a schema (e.g. price sent as a string, missing
    required field) -- before our code ever runs. We catch it here so
    even THOSE errors come back in our shape instead of FastAPI's
    default `{"detail": [...]}` format.
    """
    details = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "validation_failed",
            "message": "Request validation failed",
            "details": details,
        },
    )


@app.exception_handler(StarletteHTTPException)
def handle_http_exception(request: Request, exc: StarletteHTTPException):
    """
    Safety net for HTTP errors that come from Starlette/FastAPI itself
    rather than our own code — e.g. hitting a route that doesn't exist
    (404) or the wrong HTTP method (405). Without this, those would come
    back as `{"detail": "..."}` instead of our `{"error_code",
    "message"}` shape.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "http_error", "message": str(exc.detail)},
    )


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, exc: Exception):
    """
    Last-resort catch-all. Without this, an unhandled bug (a typo, a
    None where an object was expected) would leak a raw Python
    traceback to the client -- exposing internals and violating "no
    stack traces leaked to clients" (spec §3.7). We log it fully
    server-side (Week 3 wires this into structured JSON logging) and
    return a generic, safe message to the client.
    """
    return JSONResponse(
        status_code=500,
        content={"error_code": "internal_error", "message": "An unexpected error occurred"},
    )
