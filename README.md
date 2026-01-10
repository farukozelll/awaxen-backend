# Awaxen Backend

FastAPI based backend application for energy management and IoT platform.

## Features

- **Authentication**: Auth0 integration with JWT tokens
- **Authorization**: Role-based access control (RBAC)
- **Organizations**: Multi-tenant architecture
- **Energy Management**: EPİAŞ integration, recommendations
- **IoT**: Device management and telemetry
- **Billing**: Wallet and transaction management
- **Notifications**: Push, Telegram, Email notifications
- **Compliance**: KVKK/GDPR compliance and audit logs

## Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL + TimescaleDB
- **Cache**: Redis
- **Message Queue**: Celery with Redis
- **MQTT**: Mosquitto for IoT devices
- **Storage**: MinIO (S3 compatible)
- **Monitoring**: Prometheus + Grafana
- **Reverse Proxy**: Nginx

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Environment variables configured in `.env`

### Development Setup

```bash
# Copy environment file
cp .env.example .env

# Edit environment variables
nano .env

# Start all services
docker-compose up -d

# Run database migrations
docker-compose --profile migrate up migrate

# View logs
docker-compose logs -f backend
```

### API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health

### Services

| Service | Port | Description |
|---------|------|-------------|
| Backend API | 8000 | FastAPI application |
| Nginx | 80, 443 | Reverse proxy |
| PostgreSQL | 5432 | Main database |
| Redis (Broker) | 6379 | Celery message broker |
| Redis (Cache) | 6380 | API cache |
| MQTT | 1883 | IoT message broker |
| MinIO | 9000, 9001 | Object storage |
| PgAdmin | 5050 | Database UI |
| Flower | 5555 | Celery monitoring |

## Environment Variables

See `.env.example` for all available environment variables.

Key variables:
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis broker URL
- `AUTH0_DOMAIN`: Auth0 domain
- `AUTH0_AUDIENCE`: Auth0 API audience
- `AUTH0_CLIENT_ID`: Auth0 client ID

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Downgrade migration
alembic downgrade -1
```

## Development

### Code Structure

```
src/
├── core/           # Core utilities and configuration
├── modules/        # Feature modules
│   ├── auth/       # Authentication & authorization
│   ├── billing/    # Billing and wallet
│   ├── energy/     # Energy management
│   ├── iot/        # IoT devices
│   └── ...
├── tasks/          # Celery tasks
└── main.py         # Application entry point
```

### Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test
pytest tests/test_auth.py
```

### Logging

Logs are stored in:
- Application logs: `./logs/`
- Docker logs: `docker-compose logs`

## Deployment

### Production Deployment

```bash
# Build and deploy
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scale workers
docker-compose up -d --scale worker=4
```

### Monitoring

- Application metrics: http://localhost:8000/metrics
- Flower (Celery): http://localhost:5555
- MinIO Console: http://localhost:9001

## Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Add tests
5. Submit pull request

## License

MIT License
