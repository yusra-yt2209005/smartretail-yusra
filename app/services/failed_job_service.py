from app.db.session import SessionLocal
from app.models.failed_job import FailedJob


def record_failure(
    *,
    task_name: str,
    task_id: str | None,
    payload: dict,
    error: str,
    attempts: int,
) -> FailedJob:
    """
    Persist a permanently failed Celery job after retries are exhausted.
    """

    with SessionLocal() as db:
        failed_job = FailedJob(
            task_name=task_name,
            task_id=task_id,
            payload=payload,
            error=error,
            attempts=attempts,
        )

        db.add(failed_job)
        db.commit()
        db.refresh(failed_job)

        return failed_job