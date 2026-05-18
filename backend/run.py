import os

from app import create_app
from app.extensions import db

app = create_app()


@app.shell_context_processor
def make_shell_context():
    return {"db": db}


if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "0.0.0.0"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=app.config.get("DEBUG", False),
    )
