#!/bin/bash
# ============================================
# AWAXEN BACKEND STARTUP SCRIPT
# ============================================

set -e

echo "🚀 Starting Awaxen Backend..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "✅ .env created. Please update with your credentials."
fi

# Create necessary directories
mkdir -p logs config/ssl

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Build and start services
echo "📦 Building Docker images..."
docker compose build

echo "🐳 Starting services..."
docker compose up -d

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 10

# Run migrations
echo "📊 Running database migrations..."
docker compose exec -T backend alembic upgrade head || echo "⚠️  Migration failed or already up to date"

# Create TimescaleDB hypertable
echo "⏰ Setting up TimescaleDB hypertable..."
docker compose exec -T db psql -U awaxen_user -d awaxen_core -c \
    "SELECT create_hypertable('telemetry_data', 'timestamp', if_not_exists => TRUE);" 2>/dev/null || echo "⚠️  Hypertable already exists or table not created yet"

echo ""
echo "============================================"
echo "✅ Awaxen Backend is running!"
echo "============================================"
echo ""
echo "📍 Services:"
echo "   - API:          http://localhost:8000"
echo "   - API Docs:     http://localhost:8000/docs"
echo "   - PgAdmin:      http://localhost:5050"
echo "   - Flower:       http://localhost:5555"
echo "   - MinIO:        http://localhost:9001"
echo ""
echo "📝 Useful commands:"
echo "   - View logs:    docker compose logs -f"
echo "   - Stop:         docker compose down"
echo "   - Restart:      docker compose restart"
echo ""
