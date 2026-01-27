#!/bin/bash
# Production Server Setup Script for Awaxen Backend
# Run this once on the production server

set -e

# Configuration
PROJECT_DIR="/opt/awaxen"
REPO_URL="https://github.com/farukozelll/awaxen-backend.git"
NGINX_CONFIG_DIR="$PROJECT_DIR/config/nginx"
SSL_DIR="$PROJECT_DIR/config/ssl"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "Please run as root or with sudo"
    exit 1
fi

log "Starting production server setup..."

# Update system
log "Updating system packages..."
apt update && apt upgrade -y

# Install Docker
log "Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
systemctl enable docker
systemctl start docker

# Install Docker Compose
log "Installing Docker Compose..."
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Install additional tools
log "Installing additional tools..."
apt install -y git curl nginx htop

# Create project directory
log "Creating project directory..."
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

# Clone repository
log "Cloning repository..."
git clone $REPO_URL .

# Create necessary directories
log "Creating directories..."
mkdir -p {config/nginx,config/ssl,logs,backup}
mkdir -p config/nginx/conf.d

# Create nginx configuration
log "Setting up Nginx configuration..."
cat > config/nginx/nginx.conf << 'EOF'
user nginx;
worker_processes auto;
pid /run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                   '$status $body_bytes_sent "$http_referer" '
                   '"$http_user_agent" "$http_x_forwarded_for"';
    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

    # Upstream backend
    upstream backend {
        server backend:8000;
    }

    # Include site configurations
    include /etc/nginx/conf.d/*.conf;
}
EOF

# Create site configuration
cat > config/nginx/conf.d/awaxen.conf << 'EOF'
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL configuration
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    # API routes
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check
    location /health {
        proxy_pass http://backend;
        access_log off;
    }

    # Static files (if needed)
    location /static/ {
        alias /var/www/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# Create environment file template
log "Creating environment file template..."
cat > .env.example << 'EOF'
# Database Configuration
DB_USER=awaxen_user
DB_PASSWORD=your_secure_password
DB_NAME=awaxen_db
DB_PORT=5432

# Redis Configuration
REDIS_PASSWORD=your_redis_password

# MinIO Configuration
MINIO_ROOT_USER=awaxen_minio
MINIO_ROOT_PASSWORD=your_minio_password

# Auth0 Configuration
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_AUDIENCE=https://your-api
AUTH0_CLIENT_ID=your-client-id

# Application Configuration
SECRET_KEY=your-super-secret-key-here
ENVIRONMENT=production
DEBUG=false

# Email Configuration
RESEND_API_KEY=your-resend-api-key
EOF

# Set permissions
log "Setting permissions..."
chown -R root:root $PROJECT_DIR
chmod +x scripts/*.sh

# Create systemd service for auto-start
log "Creating systemd service..."
cat > /etc/systemd/system/awaxen.service << 'EOF'
[Unit]
Description=Awaxen Backend
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/awaxen
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable service
systemctl enable awaxen.service

# Create log rotation
log "Setting up log rotation..."
cat > /etc/logrotate.d/awaxen << 'EOF'
/opt/awaxen/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 root root
    postrotate
        docker-compose -f /opt/awaxen/docker-compose.yml restart nginx
    endscript
}
EOF

# Setup firewall
log "Configuring firewall..."
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Print next steps
log "Setup completed successfully!"
log ""
log "Next steps:"
log "1. Copy your SSL certificates to $SSL_DIR/"
log "2. Copy .env.example to .env and fill in your values"
log "3. Update your-domain.com in config/nginx/conf.d/awaxen.conf"
log "4. Run: docker-compose -f docker-compose.prod.yml up -d"
log "5. Run: docker-compose exec backend alembic upgrade head"
log ""
log "The project is now ready at $PROJECT_DIR"
