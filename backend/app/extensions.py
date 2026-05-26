from celery import Celery
import redis

celery = Celery("business_creator")
redis_client: redis.Redis | None = None


def init_redis(app) -> redis.Redis:
    global redis_client
    if app.config.get("TESTING"):
        import fakeredis

        redis_client = fakeredis.FakeRedis(decode_responses=True)
    else:
        redis_client = redis.from_url(
            app.config["REDIS_URL"],
            decode_responses=True,
        )
    return redis_client


def init_celery(app, celery_app: Celery) -> Celery:
    celery_app.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
    )

    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return super().__call__(*args, **kwargs)

    celery_app.Task = ContextTask
    celery_app.flask_app = app
    return celery_app
