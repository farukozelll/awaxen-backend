#!/bin/bash
# Production Deployment Script for Awaxen Backend
# This script handles zero-downtime deployments

set -e

# Configuration
BACKUP_DIR="/opt/awaxen/backup/$(date +%Y%m%d_%H%M%S)"
COMPOSE_FILE="/opt/awaxen/docker-compose.yml"
LOG_FILE="/var/log/awaxen-deploy.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a $LOG_FILE
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a $LOG_FILE
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}" | tee -a $LOG_FILE
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "Please run as root or with sudo"
    exit 1
fi

# Create backup directory
mkdir -p $BACKUP_DIR

# Function to backup current state
backup() {
    log "Creating backup..."
    
    # Backup docker-compose.yml
    if [ -f $COMPOSE_FILE ]; then
        cp $COMPOSE_FILE $BACKUP_DIR/docker-compose.yml
    fi
    
    # Backup database
    log "Backing up database..."
    docker compose exec -T db pg_dump -U $DB_USER $DB_NAME | gzip > $BACKUP_DIR/database.sql.gz
    
    # Backup environment file
    if [ -f /opt/awaxen/.env ]; then
        cp /opt/awaxen/.env $BACKUP_DIR/.env
    fi
    
    log "Backup completed: $BACKUP_DIR"
}

# Function to update services
update() {
    log "Starting deployment..."
    
    # Pull latest code
    log "Pulling latest code..."
    cd /opt/awaxen
    git pull origin main
    
    # Copy production compose file
    log "Updating docker-compose configuration..."
    cp docker-compose.prod.yml docker-compose.yml
    
    # Login to GitHub Container Registry
    log "Logging into container registry..."
    echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_USERNAME --password-stdin
    
    # Pull new images
    log "Pulling new Docker images..."
    docker compose pull
    
    # Run database migrations
    log "Running database migrations..."
    docker compose run --rm migrate
    
    # Zero downtime deployment
    log "Starting zero-downtime deployment..."
    
    # Scale up backend to 2 instances
    docker compose up -d --scale backend=2 --no-deps backend
    sleep 20
    
    # Update other services
    docker compose up -d --remove-orphans worker beat flower
    
    # Scale down to original
    docker compose up -d --scale backend=1 --no-deps backend
    
    # Wait for health checks
    log "Waiting for services to be healthy..."
    sleep 30
    
    # Verify deployment
    log "Verifying deployment..."
    if curl -f http://localhost:8000/health; then
        log "Health check passed!"
    else
        error "Health check failed!"
        rollback
        exit 1
    fi
    
    # Clean up
    log "Cleaning up old images..."
    docker image prune -f
    
    log "Deployment completed successfully!"
}

# Function to rollback
rollback() {
    error "Initiating rollback..."
    
    if [ -f $BACKUP_DIR/docker-compose.yml ]; then
        log "Restoring docker-compose.yml..."
        cp $BACKUP_DIR/docker-compose.yml $COMPOSE_FILE
        
        log "Restarting services with previous configuration..."
        docker compose up -d --force-recreate
        
        # Restore database if needed
        if [ -f $BACKUP_DIR/database.sql.gz ]; then
            log "Restoring database..."
            docker compose exec -T db dropdb -U $DB_USER $DB_NAME
            docker compose exec -T db createdb -U $DB_USER $DB_NAME
            gunzip -c $BACKUP_DIR/database.sql.gz | docker compose exec -T db psql -U $DB_USER $DB_NAME
        fi
        
        log "Rollback completed!"
    else
        error "No backup found for rollback!"
        exit 1
    fi
}

# Main execution
main() {
    log "Starting production deployment..."
    
    # Create backup
    backup
    
    # Update services
    update
    
    # Show status
    log "Service status:"
    docker compose ps
    
    log "Production deployment completed successfully!"
}

# Trap errors and cleanup
trap 'error "Deployment failed! Check logs at $LOG_FILE"; exit 1' ERR

# Run main function
main
