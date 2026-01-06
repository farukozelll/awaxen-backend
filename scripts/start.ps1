# ============================================
# AWAXEN BACKEND STARTUP SCRIPT (PowerShell)
# ============================================

Write-Host "🚀 Starting Awaxen Backend..." -ForegroundColor Cyan

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "⚠️  .env file not found. Copying from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "✅ .env created. Please update with your credentials." -ForegroundColor Green
}

# Create necessary directories
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
New-Item -ItemType Directory -Force -Path "config/ssl" | Out-Null

# Check Docker
try {
    docker --version | Out-Null
} catch {
    Write-Host "❌ Docker is not installed. Please install Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Build and start services
Write-Host "📦 Building Docker images..." -ForegroundColor Cyan
docker compose build

Write-Host "🐳 Starting services..." -ForegroundColor Cyan
docker compose up -d

# Wait for database to be ready
Write-Host "⏳ Waiting for database to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# Run migrations
Write-Host "📊 Running database migrations..." -ForegroundColor Cyan
try {
    docker compose exec -T backend alembic upgrade head
} catch {
    Write-Host "⚠️  Migration failed or already up to date" -ForegroundColor Yellow
}

# Create TimescaleDB hypertable
Write-Host "⏰ Setting up TimescaleDB hypertable..." -ForegroundColor Cyan
try {
    docker compose exec -T db psql -U awaxen_user -d awaxen_core -c "SELECT create_hypertable('telemetry_data', 'timestamp', if_not_exists => TRUE);"
} catch {
    Write-Host "⚠️  Hypertable already exists or table not created yet" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "✅ Awaxen Backend is running!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "📍 Services:" -ForegroundColor Cyan
Write-Host "   - API:          http://localhost:8000"
Write-Host "   - API Docs:     http://localhost:8000/docs"
Write-Host "   - PgAdmin:      http://localhost:5050"
Write-Host "   - Flower:       http://localhost:5555"
Write-Host "   - MinIO:        http://localhost:9001"
Write-Host ""
Write-Host "📝 Useful commands:" -ForegroundColor Cyan
Write-Host "   - View logs:    docker compose logs -f"
Write-Host "   - Stop:         docker compose down"
Write-Host "   - Restart:      docker compose restart"
Write-Host ""
