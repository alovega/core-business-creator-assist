Build a stable, practical, revenue-generating MVP focused on helping African SMEs automate communication, customer engagement, bookings, and payment workflows primarily through WhatsApp.

## Running locally

All development tasks are run from the **repository root** with `make`. Run `make help` anytime to see available commands.

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- `make`

### First-time setup

```bash
make setup
```

This creates the virtualenv, installs dependencies, copies `backend/.env` from the example, starts PostgreSQL and Redis, creates the test database, and applies migrations.

### Day-to-day workflow

**Start the API** (choose one)

Run on the host (virtualenv):

```bash
make run
```

Or run in Docker (Gunicorn, migrations on startup):

```bash
make up-api
```

The server listens on [http://127.0.0.1:5000](http://127.0.0.1:5000).

**Check health** (in another terminal)

```bash
make health
```

**Run tests**

```bash
make test
```

**Run the Celery worker** (optional, separate terminal)

```bash
make celery
```

**Stop infrastructure when finished**

```bash
make down
```

### Commands

| Command | Description |
|---------|-------------|
| `make help` | List all commands |
| `make setup` | First-time bootstrap (install, env, up, migrate) |
| `make install` | Create `.venv` and install dependencies |
| `make env` | Copy `backend/.env.example` → `backend/.env` |
| `make up` | Start PostgreSQL and Redis |
| `make build` | Build the API Docker image |
| `make up-api` | Start PostgreSQL, Redis, and the Flask API in Docker |
| `make down` | Stop PostgreSQL and Redis |
| `make migrate` | Apply database migrations |
| `make migrate-create MSG="..."` | Generate a new migration after model changes |
| `make test` | Run pytest |
| `make run` | Start the Flask API |
| `make celery` | Start the Celery worker |
| `make health` | Call `GET /health` |
| `make logs` | Follow Docker Compose logs |

### Common tasks

**After pulling schema changes**

```bash
make migrate
```

**After editing SQLAlchemy models**

```bash
make migrate-create MSG="add bookings table"
make migrate
```

**Reset only Docker services** (data volumes are kept unless you remove them manually)

```bash
make down
make up
```

### Configuration

Environment variables live in `backend/.env`. `make env` creates it from `backend/.env.example` on first run. Edit `.env` if your database or Redis URLs differ from the defaults.

Application logs are written to `logs/` at the repo root (sibling of `backend/`, gitignored):

- **`info.log`** — successful HTTP responses (status &lt; 400), `request_started`, and general INFO logs
- **`error.log`** — HTTP error responses (4xx, 5xx), unhandled exceptions, and other ERROR+ logs

Routing is based on the **response status code**: `200` → `info.log` only; `401`, `404`, `500`, etc. → `error.log` only. File logs are JSON; the console uses `LOG_JSON` from `.env`. Set `LOG_DIR` to change the directory.

**See HTTP request logs**

```bash
# Successful responses
grep request_completed logs/info.log

# Failed responses (4xx / 5xx)
grep request_completed logs/error.log

tail -f logs/info.log
tail -f logs/error.log

# Docker / Gunicorn access lines
docker compose logs -f api
```

Each request writes `request_started` to `info.log`, then `request_completed` to `info.log` or `error.log` depending on status. Restart the API after logging changes (`make run` or `make up-api --build`).
