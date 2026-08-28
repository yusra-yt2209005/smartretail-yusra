import random

from app.services import (
    failed_job_service,
    notification_service,
)
from app.workers.celery_app import celery_app

from app.core.correlation import (
    reset_correlation_id,
    set_correlation_id,
)

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
    name="app.workers.tasks.notifications.send_order_notification",
)
def send_order_notification(
    self,
    order_id: str,
    event_type: str,
    correlation_id: str,
) -> dict:
    token = set_correlation_id(
        correlation_id
    )

    try:
        notification = (
            notification_service
            .create_order_notification(
                order_id,
                event_type,
            )
        )

        logger.info(
            "Notification created for order %s (%s)",
            order_id,
            event_type,
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

        logger.warning(
            "Notification task failed for order %s "
            "on attempt %s: %s",
            order_id,
            attempt_number,
            exc,
        )

        if (
            self.request.retries
            >= self.max_retries
        ):
            failed_job_service.record_failure(
                task_name="send_order_notification",
                task_id=self.request.id,
                payload={
                    "order_id": order_id,
                    "event_type": event_type,
                    "correlation_id": correlation_id,
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

    finally:
        reset_correlation_id(
            token
        )