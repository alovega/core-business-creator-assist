from app.extensions import celery


@celery.task(name="app.tasks.ping")
def ping() -> str:
    return "pong"
