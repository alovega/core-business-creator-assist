import os
from pathlib import Path

from app import create_app
from app.db import db

app = create_app()


@app.shell_context_processor
def make_shell_context():
    return {"db": db}


def _dev_extra_files() -> list[str]:
    """Restart the dev server when local env files change."""
    backend_dir = Path(__file__).resolve().parent
    return [str(path) for path in (backend_dir / ".env", backend_dir / ".env.local") if path.is_file()]


if __name__ == "__main__":
    use_reloader = app.config.get("USE_RELOADER", False)
    app.run(
        host=os.environ.get("FLASK_HOST", "0.0.0.0"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=app.config.get("DEBUG", False),
        use_reloader=use_reloader,
        use_debugger=app.config.get("USE_DEBUGGER", False),
        extra_files=_dev_extra_files() if use_reloader else None,
    )
