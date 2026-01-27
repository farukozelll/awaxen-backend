# Awaxen Backend Deployment Guide

## Overview

This guide explains how to deploy the Awaxen Backend to production using GitHub Actions and Docker Compose.

## Architecture

- **Local Development**: Use `docker-compose.yml`
- **Production**: Use `docker-compose.prod.yml` with images from GitHub Container Registry
- **CI/CD**: GitHub Actions builds, tests, and deploys automatically

## Prerequisites

### Production Server

- Ubuntu 20.04+ or CentOS 8+
- Docker and Docker Compose installed
- SSH access with sudo privileges
- Domain name pointing to server IP
- SSL certificates (optional but recommended)

### GitHub Repository

- Repository hosted on GitHub
- GitHub Actions enabled
- Container Registry permissions

## Quick Start

### 1. Initial Server Setup

```bash
# SSH into your production server
ssh user@your-server.com

# Download and run setup script
wget https://raw.githubusercontent.com/farukozelll/awaxen-backend/main/scripts/setup-production.sh
chmod +x setup-production.sh
sudo ./setup-production.sh
```

### 2. Configure Environment

```bash
cd /opt/awaxen
cp .env.example .env
nano .env  # Fill in your configuration
```

### 3. Configure Domain and SSL

```bash
# Update domain in nginx config
nano config/nginx/conf.d/awaxen.conf

# Add SSL certificates
cp cert.pem config/ssl/
cp key.pem config/ssl/
```

### 4. First Deployment

```bash
# Start services
docker-compose -f docker-compose.prod.yml up -d

# Run database migrations
docker-compose exec backend alembic upgrade head

# Check status
docker-compose ps
```

## Automated Deployment

### GitHub Actions Workflow

The deployment process is automated through GitHub Actions:

1. **Push to main branch** → Triggers deployment
2. **Build & Test** → Lints, type checks, and runs tests
3. **Build Docker Image** → Pushes to GitHub Container Registry
4. **Deploy to Production** → Updates services on server

### Required GitHub Secrets

Add these secrets to your repository settings:

- `PROD_HOST`: Production server IP/hostname
- `PROD_USER`: SSH username for production server
- `PROD_SSH_KEY`: SSH private key for production server
- `PROD_DOMAIN`: Your domain name (e.g., awaxen.com)
- `SLACK_WEBHOOK`: Slack notification webhook (optional)

### Manual Deployment

To deploy manually:

```bash
# On production server
cd /opt/awaxen
./scripts/deploy-production.sh
```

## Deployment Features

### Zero Downtime

- Services are updated without downtime
- Database migrations run before code deployment
- Health checks ensure services are healthy

### Rollback Capability

If deployment fails:

```bash
# Automatic rollback on failure
# Or manual rollback:
cd /opt/awaxen/backup/20231201_120000  # Latest backup
sudo cp docker-compose.yml /opt/awaxen/
docker-compose up -d --force-recreate
```

### Monitoring

- Health checks at `/health`
- Flower monitoring at `:5555`
- Logs in `/opt/awaxen/logs/`
- Docker logs: `docker-compose logs -f`

## Environment Variables

Key environment variables:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname

# Auth0
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_AUDIENCE=https://your-api
AUTH0_CLIENT_ID=your-client-id

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0

# Application
SECRET_KEY=your-super-secret-key
ENVIRONMENT=production
```

## Troubleshooting

### Common Issues

1. **Build fails**:
   - Check linting: `ruff check src/`
   - Check tests: `pytest tests/`

2. **Deployment fails**:
   - Check logs: `tail -f /var/log/awaxen-deploy.log`
   - Verify SSH keys and secrets

3. **Services not starting**:
   - Check environment variables
   - Verify database connection
   - Check Docker logs: `docker-compose logs service-name`

### Health Checks

```bash
# Check service health
curl https://your-domain.com/health

# Check all services
docker-compose ps

# View logs
docker-compose logs -f backend
```

## Security Best Practices

1. **Use HTTPS** with valid SSL certificates
2. **Rotate secrets** regularly
3. **Use environment variables** for sensitive data
4. **Enable firewall** with only necessary ports
5. **Regular updates** of Docker images and dependencies
6. **Monitor logs** for suspicious activity

## Backup Strategy

Backups are created automatically before each deployment:

- Database dumps: `/opt/awaxen/backup/*/database.sql.gz`
- Configuration files: `/opt/awaxen/backup/*/docker-compose.yml`
- Environment file: `/opt/awaxen/backup/*/.env`

To restore:

```bash
# Find latest backup
ls -la /opt/awaxen/backup/

# Restore database
gunzip -c backup/file/database.sql.gz | docker-compose exec -T db psql -U user dbname
```

## Performance Optimization

1. **Use Redis caching** for API responses
2. **Enable Gzip** compression in Nginx
3. **Configure rate limiting** to prevent abuse
4. **Monitor resource usage** with Docker stats
5. **Use TimescaleDB** for time-series data

## Support

For deployment issues:

1. Check the logs: `/var/log/awaxen-deploy.log`
2. Review GitHub Actions run logs
3. Check Docker service status
4. Verify network connectivity

## Local Development

To run locally:

```bash
# Clone repository
git clone https://github.com/farukozelll/awaxen-backend.git
cd awaxen-backend

# Start services
docker-compose up -d

# Run migrations
docker-compose exec backend alembic upgrade head
```

Access points:
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Flower: http://localhost:5555
- MinIO: http://localhost:9001
