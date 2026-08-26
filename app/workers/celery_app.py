from celery import Celery


celery_app = Celery(
    "smartretail",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/1",
)


@celery_app.task
def add(x: int, y: int) -> int:
    return x + y