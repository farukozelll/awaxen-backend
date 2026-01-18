#!/bin/bash
# ============================================
# AWAXEN BACKEND - PRODUCTION DEPLOYMENT SCRIPT
# Sunucu: awaxen-core
# ============================================

set -e  # Hata durumunda dur

# Renkli output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           🌞 AWAXEN BACKEND DEPLOYMENT                       ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"

# Proje dizini
PROJECT_DIR="/opt/awaxen"
cd $PROJECT_DIR

echo -e "\n${YELLOW}[1/6] 📥 Pulling latest code from GitHub...${NC}"
git pull origin master

echo -e "\n${YELLOW}[2/6] 🛑 Stopping old containers...${NC}"
docker compose down

echo -e "\n${YELLOW}[3/6] 🏗️  Building new images...${NC}"
docker compose build --no-cache backend

echo -e "\n${YELLOW}[4/6] 🚀 Starting services...${NC}"
docker compose up -d

echo -e "\n${YELLOW}[5/6] ⏳ Waiting for backend to be ready...${NC}"
sleep 10

# Health check
MAX_RETRIES=30
RETRY_COUNT=0
until curl -s http://localhost:8000/health > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo -e "${RED}❌ Backend health check failed after $MAX_RETRIES attempts${NC}"
        docker compose logs backend --tail 50
        exit 1
    fi
    echo "Waiting for backend... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

echo -e "${GREEN}✅ Backend is healthy!${NC}"

echo -e "\n${YELLOW}[6/6] 🗄️  Running database migrations...${NC}"
docker compose exec -T backend alembic upgrade head

echo -e "\n${YELLOW}🧹 Cleaning up old images...${NC}"
docker system prune -f

echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✅ DEPLOYMENT COMPLETED SUCCESSFULLY!              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"

echo -e "\n${BLUE}📊 Service Status:${NC}"
docker compose ps

echo -e "\n${BLUE}🔗 Endpoints:${NC}"
echo -e "   API:     https://api.awaxen.com"
echo -e "   Docs:    https://api.awaxen.com/docs"
echo -e "   Health:  https://api.awaxen.com/health"

echo -e "\n${BLUE}📝 Useful commands:${NC}"
echo -e "   make logs      - View backend logs"
echo -e "   make db-shell  - PostgreSQL shell"
echo -e "   make shell     - Backend container shell"
