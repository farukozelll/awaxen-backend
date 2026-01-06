#!/bin/bash
# ============================================
# MQTT PASSWORD SETUP SCRIPT
# ============================================

echo "🔐 Setting up MQTT authentication..."

# Create password file for Mosquitto
MQTT_USER="${MQTT_USERNAME:-awaxen_admin}"
MQTT_PASS="${MQTT_PASSWORD:-gizli_sifre_123}"

# Generate password hash
docker compose exec mqtt mosquitto_passwd -b -c /mosquitto/config/password.txt "$MQTT_USER" "$MQTT_PASS"

echo "✅ MQTT user '$MQTT_USER' created"
echo "🔄 Restarting MQTT broker..."

docker compose restart mqtt

echo "✅ MQTT setup complete!"
