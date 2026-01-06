# ============================================
# AWAXEN BACKEND - MAKEFILE
# Hızlı komutlar için kısayollar
# ============================================

.PHONY: help install dev test lint format migrate deploy logs shell db-shell clean

# Varsayılan hedef
help:
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║           🌞 AWAXEN BACKEND - KOMUTLAR                       ║"
	@echo "╠══════════════════════════════════════════════════════════════╣"
	@echo "║  make install    - Bağımlılıkları yükle                      ║"
	@echo "║  make dev        - Development sunucusu başlat               ║"
	@echo "║  make test       - Testleri çalıştır                         ║"
	@echo "║  make lint       - Kod kalitesi kontrolü                     ║"
	@echo "║  make format     - Kodu formatla                             ║"
	@echo "║  make migrate    - Veritabanı migration'ları çalıştır        ║"
	@echo "║  make deploy     - Production'a deploy et                    ║"
	@echo "║  make logs       - Container loglarını izle                  ║"
	@echo "║  make shell      - Backend container'a bağlan                ║"
	@echo "║  make db-shell   - PostgreSQL shell'e bağlan                 ║"
	@echo "║  make clean      - Temizlik yap                              ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"

# ============================================
# DEVELOPMENT
# ============================================

install:
	pip install -e ".[dev]"

dev:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

dev-docker:
	docker compose up -d db redis mqtt
	@echo "⏳ Waiting for services..."
	@sleep 5
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# ============================================
# TESTING
# ============================================

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

test-docker:
	docker compose exec backend pytest tests/ -v --tb=short

# ============================================
# CODE QUALITY
# ============================================

lint:
	ruff check src/ tests/
	mypy src/ --ignore-missing-imports

format:
	ruff format src/ tests/
	ruff check src/ tests/ --fix

# ============================================
# DATABASE
# ============================================

migrate:
	alembic upgrade head

migrate-docker:
	docker compose exec backend alembic upgrade head

migrate-create:
	@read -p "Migration adı: " name; \
	alembic revision --autogenerate -m "$$name"

db-shell:
	docker compose exec db psql -U awaxen_user -d awaxen_core

db-reset:
	docker compose exec db psql -U awaxen_user -d awaxen_core -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	docker compose exec backend alembic upgrade head

# ============================================
# DOCKER
# ============================================

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build --no-cache backend

rebuild:
	docker compose down
	docker compose build --no-cache
	docker compose up -d

logs:
	docker compose logs -f backend

logs-all:
	docker compose logs -f

shell:
	docker compose exec backend /bin/bash

# ============================================
# DEPLOYMENT
# ============================================

deploy:
	@echo "🚀 Deploying to production..."
	git pull origin main
	docker compose down
	docker compose build --no-cache backend
	docker compose up -d
	docker compose exec backend alembic upgrade head
	docker system prune -f
	@echo "✅ Deployment complete!"

deploy-staging:
	@echo "🧪 Deploying to staging..."
	git pull origin develop
	docker compose -f docker-compose.staging.yml down
	docker compose -f docker-compose.staging.yml build --no-cache backend
	docker compose -f docker-compose.staging.yml up -d
	docker compose -f docker-compose.staging.yml exec backend alembic upgrade head
	@echo "✅ Staging deployment complete!"

# ============================================
# CLEANUP
# ============================================

clean:
	docker system prune -f
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "🧹 Cleanup complete!"

clean-all: clean
	docker compose down -v
	@echo "🧹 Full cleanup complete (volumes removed)!"

# ============================================
# UTILITIES
# ============================================

health:
	curl -s http://localhost:8000/health | python -m json.tool

openapi:
	curl -s http://localhost:8000/openapi.json > openapi.json
	@echo "📄 OpenAPI schema saved to openapi.json"

env-check:
	@echo "🔍 Checking environment variables..."
	@test -f .env && echo "✅ .env file exists" || echo "❌ .env file missing"
	@docker compose config --quiet && echo "✅ docker-compose.yml is valid" || echo "❌ docker-compose.yml has errors"

# ============================================
# GIT SHORTCUTS
# ============================================

push:
	git add .
	@read -p "Commit mesajı: " msg; \
	git commit -m "$$msg"
	git push origin $$(git branch --show-current)

pull:
	git pull origin $$(git branch --show-current)
