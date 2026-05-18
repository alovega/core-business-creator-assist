from dotenv import load_dotenv
from flask import Flask

from app.common import health_bp
from app.common.logging import setup_logging
from app.config import config_by_name, get_config_name
from app.extensions import celery, db, init_celery, init_redis, migrate

load_dotenv()


def register_blueprints(app: Flask) -> None:
    from app.ai import ai_bp
    from app.auth import auth_bp
    from app.automations import automations_bp
    from app.bookings import bookings_bp
    from app.businesses import businesses_bp
    from app.conversations import conversations_bp
    from app.customers import customers_bp
    from app.leads import leads_bp
    from app.messages import messages_bp
    from app.payments import payments_bp
    from app.whatsapp import whatsapp_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(businesses_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(conversations_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(whatsapp_bp)
    app.register_blueprint(leads_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(automations_bp)
    app.register_blueprint(ai_bp)
    from app.users import users_bp

    app.register_blueprint(users_bp)


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = get_config_name()

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    if config_name == "production" and not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL environment variable is required in production")

    setup_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)
    init_redis(app)
    init_celery(app, celery)

    # Import models so Flask-Migrate discovers them.
    from app.users import models as user_models  # noqa: F401

    register_blueprints(app)

    return app
