import random

from app.services import (
    failed_job_service,
    notification_service,
)
from app.workers.celery_app import celery_app


MAX_RETRIES = 3


def _backoff_seconds(
    attempt: int,
) -> float:
    """
    Exponential backoff with a small random jitter.

    Example:
        attempt 0 -> roughly 1 second
        attempt 1 -> roughly 2 seconds
        attempt 2 -> roughly 4 seconds
    """

    return min(
        2 ** attempt,
        30,
    ) + random.uniform(
        0,
        1,
    )


@celery_app.task(
    bind=True,
    max_retries=MAX_RETRIES,
    name=(
        "app.workers.tasks.notifications."
        "send_order_notification"
    ),
)
def send_order_notification(
    self,
    order_id: str,
    event_type: str,
) -> dict:
    """
    Thin Celery wrapper around notification_service.

    On failure:
        retry with exponential backoff

    After the final allowed retry:
        write the failed task to failed_jobs
    """

    try:
        notification = (
            notification_service
            .create_order_notification(
                order_id,
                event_type,
            )
        )

        return {
            "notification_id": str(
                notification.id
            ),
            "order_id": order_id,
            "event_type": event_type,
        }

    except Exception as exc:

        attempt_number = (
            self.request.retries + 1
        )

        if (
            self.request.retries
            >= self.max_retries
        ):
            failed_job_service.record_failure(
                task_name=(
                    "send_order_notification"
                ),
                task_id=self.request.id,
                payload={
                    "order_id": order_id,
                    "event_type": event_type,
                },
                error=str(exc),
                attempts=attempt_number,
            )

            return {
                "status": "failed",
                "order_id": order_id,
                "attempts": attempt_number,
            }

        raise self.retry(
            exc=exc,
            countdown=_backoff_seconds(
                self.request.retries
            ),
        )