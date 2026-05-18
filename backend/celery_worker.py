from app import create_app
from app.extensions import celery
import app.tasks  # noqa: F401

flask_app = create_app()
flask_app.app_context().push()
