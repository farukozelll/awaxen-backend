#!/bin/bash
# ============================================
# AWAXEN BACKEND - SERVER INITIAL SETUP
# İlk kurulum için çalıştır (sadece 1 kez)
# ============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           🌞 AWAXEN SERVER INITIAL SETUP                     ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"

# 1. Sistem güncellemesi
echo -e "\n${YELLOW}[1/7] 📦 Updating system packages...${NC}"
apt-get update && apt-get upgrade -y

# 2. Docker kurulumu (eğer yoksa)
if ! command -v docker &> /dev/null; then
    echo -e "\n${YELLOW}[2/7] 🐳 Installing Docker...${NC}"
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
else
    echo -e "\n${GREEN}[2/7] ✅ Docker already installed${NC}"
fi

# 3. Docker Compose kurulumu (eğer yoksa)
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "\n${YELLOW}[3/7] 🐳 Installing Docker Compose...${NC}"
    apt-get install -y docker-compose-plugin
else
    echo -e "\n${GREEN}[3/7] ✅ Docker Compose already installed${NC}"
fi

# 4. Git kurulumu
if ! command -v git &> /dev/null; then
    echo -e "\n${YELLOW}[4/7] 📥 Installing Git...${NC}"
    apt-get install -y git
else
    echo -e "\n${GREEN}[4/7] ✅ Git already installed${NC}"
fi

# 5. Make kurulumu
if ! command -v make &> /dev/null; then
    echo -e "\n${YELLOW}[5/7] 🔧 Installing Make...${NC}"
    apt-get install -y make
else
    echo -e "\n${GREEN}[5/7] ✅ Make already installed${NC}"
fi

# 6. Proje dizini oluştur
PROJECT_DIR="/opt/awaxen"
echo -e "\n${YELLOW}[6/7] 📁 Setting up project directory...${NC}"

if [ ! -d "$PROJECT_DIR" ]; then
    mkdir -p $PROJECT_DIR
    cd $PROJECT_DIR
    git clone https://github.com/farukozelll/awaxen-backend.git .
    echo -e "${GREEN}✅ Repository cloned${NC}"
else
    echo -e "${GREEN}✅ Project directory exists${NC}"
    cd $PROJECT_DIR
    git pull origin master
fi

# 7. .env dosyası kontrolü
echo -e "\n${YELLOW}[7/7] 🔐 Checking environment file...${NC}"
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found!${NC}"
    echo -e "${YELLOW}   Copying from .env.example...${NC}"
    cp $PROJECT_DIR/.env.example $PROJECT_DIR/.env
    echo -e "${RED}❗ IMPORTANT: Edit .env file with your production values!${NC}"
    echo -e "${RED}   nano $PROJECT_DIR/.env${NC}"
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

# Config dizinleri oluştur
mkdir -p $PROJECT_DIR/config/nginx/conf.d
mkdir -p $PROJECT_DIR/config/nginx/ssl
mkdir -p $PROJECT_DIR/config/mosquitto

# Mosquitto config
if [ ! -f "$PROJECT_DIR/config/mosquitto/mosquitto.conf" ]; then
    cat > $PROJECT_DIR/config/mosquitto/mosquitto.conf << 'EOF'
listener 1883
allow_anonymous false
password_file /mosquitto/config/password.txt

listener 9001
protocol websockets
EOF
    touch $PROJECT_DIR/config/mosquitto/password.txt
    echo -e "${GREEN}✅ Mosquitto config created${NC}"
fi

echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✅ SERVER SETUP COMPLETED!                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"

echo -e "\n${BLUE}📝 Next Steps:${NC}"
echo -e "   1. Edit .env file: ${YELLOW}nano $PROJECT_DIR/.env${NC}"
echo -e "   2. Run deployment: ${YELLOW}cd $PROJECT_DIR && make deploy${NC}"
echo -e ""
echo -e "${BLUE}🔐 Required .env variables:${NC}"
echo -e "   - DB_PASSWORD"
echo -e "   - SECRET_KEY"
echo -e "   - AUTH0_DOMAIN"
echo -e "   - AUTH0_AUDIENCE"
echo -e "   - AUTH0_CLIENT_ID"
