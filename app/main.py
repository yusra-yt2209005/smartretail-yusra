from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.api.v1 import (
    analytics,
    assistant,
    auth,
    categories,
    health,
    orders,
    products,
    search,
)
from app.core.exceptions import AppError
import uuid
from app.core.correlation import (
    reset_correlation_id,
    set_correlation_id,
)
from app.core.logging import (
    configure_logging,
    get_logger,
)
import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from starlette.responses import Response

from app.core.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
)
configure_logging()

logger = get_logger(
    "smartretail.api"
)

app = FastAPI(
    title="SmartRetail API",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(analytics.router)
app.include_router(search.router)
app.include_router(assistant.router)
@app.middleware("http")

async def correlation_id_middleware(
    request: Request,
    call_next,
):
    """
    Reuse X-Request-ID when supplied by the client,
    otherwise generate a new correlation ID.

    The same ID is returned in the response header.
    """

    supplied_id = request.headers.get(
        "X-Request-ID"
    )

    if (
        supplied_id
        and supplied_id.strip()
        and len(supplied_id.strip()) <= 100
    ):
        correlation_id = (
            supplied_id.strip()
        )
    else:
        correlation_id = str(
            uuid.uuid4()
        )

    token = set_correlation_id(
        correlation_id
    )

    try:
        logger.info(
            "%s %s started",
            request.method,
            request.url.path,
        )

        response = await call_next(
            request
        )

        response.headers[
            "X-Request-ID"
        ] = correlation_id

        logger.info(
            "%s %s completed with status %s",
            request.method,
            request.url.path,
            response.status_code,
        )

        return response

    except Exception:
        logger.exception(
            "%s %s failed",
            request.method,
            request.url.path,
        )

        raise

    finally:
        reset_correlation_id(
            token
        )

@app.get(
    "/metrics",
    include_in_schema=True,
)
def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )

@app.exception_handler(AppError)
async def handle_app_error(
    request: Request,
    exc: AppError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
            }
        },
    )





@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = exc.errors()

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": errors,
            }
        },
    )

@app.middleware("http")
async def prometheus_metrics_middleware(
    request: Request,
    call_next,
):
    start = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(
            request
        )

        status_code = response.status_code

        return response

    finally:
        duration = (
            time.perf_counter()
            - start
        )

        route = request.scope.get(
            "route"
        )

        endpoint = (
            route.path
            if route is not None
            and hasattr(route, "path")
            else request.url.path
        )

        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=endpoint,
            status=str(status_code),
        ).inc()

        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)