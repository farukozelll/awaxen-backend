# Awaxen Backend

Modern FastAPI backend boilerplate with async SQLAlchemy, Postgres, Docker, and testing tools.

## Features

## Architecture

```
src/
├── core/                    # Core infrastructure
│   ├── config.py           # pydantic-settings configuration
│   ├── database.py         # Async SQLAlchemy session
│   ├── security.py         # JWT & password hashing
│   ├── exceptions.py       # Global exception handlers
│   ├── logging.py          # Structlog configuration
│   └── models.py           # Base SQLAlchemy model (UUID, timestamps)
│
├── modules/                 # Domain modules (DDD)
│   ├── auth/               # Authentication & Multi-tenancy
│   │   ├── models.py       # User, Organization, Role, OrganizationUser
│   │   ├── schemas.py      # Pydantic DTOs
│   │   ├── service.py      # Business logic
│   │   ├── dependencies.py # FastAPI dependencies
│   │   └── router.py       # API endpoints
│   │
│   ├── real_estate/        # PropTech module
│   │   └── ...             # Asset hierarchy (Site→Block→Floor→Unit), Leases
│   │
│   ├── iot/                # EnergyTech/IoT module
│   │   ├── models.py       # Device, Gateway, TelemetryData (Hypertable)
│   │   ├── mqtt_ingestion.py # MQTT async client with batch insert
│   │   └── ...
│   │
│   └── billing/            # Billing module
│       └── ...             # Wallet, Transaction, Invoice
│
├── tasks/                   # Celery background tasks
├── worker.py               # Celery configuration
└── main.py                 # FastAPI application factory
```

## Technology Stack

| Component | Technology |
|-----------|------------|
| **Framework** | FastAPI + Gunicorn + Uvicorn |
| **Database** | PostgreSQL 16 + TimescaleDB |
| **ORM** | SQLAlchemy 2.0 (Async) + Alembic |
| **Validation** | Pydantic V2 |
| **Task Queue** | Celery + Redis |
| **IoT Protocol** | MQTT (Mosquitto) + aiomqtt |
| **Storage** | MinIO (S3 Compatible) |
| **JSON** | orjson (10x faster) |
| **Logging** | Structlog |

## Key Features & Optimizations

- **ORJSONResponse**: 10x faster JSON serialization
- **Connection Pooling**: `pool_size=20`, `max_overflow=10`
- **Batch Inserts**: IoT telemetry buffered and batch inserted
- **TimescaleDB Hypertable**: Optimized time-series storage
- **Multi-tenant**: Organization-based data isolation
- **RBAC**: Role-based access control
- **Async-first**: Full async/await support

## Quick Start with Docker

```bash
# Clone and setup
cp .env.example .env

# Start all services
docker-compose up -d

# Run migrations
docker-compose exec backend alembic upgrade head

# Create TimescaleDB hypertable (after migrations)
docker-compose exec db psql -U awaxen -d awaxen -c \
  "SELECT create_hypertable('telemetry_data', 'timestamp', if_not_exists => TRUE);"
```

**Services:**
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- MinIO Console: http://localhost:9001
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- MQTT: localhost:1883

## Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -e ".[dev]"

# Setup environment
cp .env.example .env

# Run migrations
alembic upgrade head

# Start development server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Start Celery worker (separate terminal)
celery -A src.worker.celery_app worker --loglevel=info
```

## API Endpoints

| Module | Prefix | Description |
|--------|--------|-------------|
| Auth | `/api/v1/auth` | Login, Register, Users, Organizations, Roles |
| Real Estate | `/api/v1/real-estate` | Assets (hierarchy), Leases |
| IoT | `/api/v1/iot` | Gateways, Devices, Telemetry |
| Billing | `/api/v1/billing` | Wallets, Transactions, Invoices |

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Lint
ruff check .
ruff format .

# Type check
mypy src
```

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Security Notes

- **Never** commit `.env` file
- Change `SECRET_KEY` in production
- Use strong passwords for all services
- Enable MQTT authentication in production
- Configure proper CORS origins

## License

MIT
