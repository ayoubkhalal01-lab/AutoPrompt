#!/bin/sh
# ==============================================================================
# AutoPrompt SSL Initialization & Certificate Bootstrap Script (Phase 8.3)
# Creates temporary self-signed certificates so Nginx can start before Let's Encrypt
# ==============================================================================

set -e

DOMAIN="${1:-localhost}"
EMAIL="${2:-admin@example.com}"
CERT_DIR="./certbot/conf/live/autoprompt"

echo "[*] AutoPrompt SSL Bootstrap for domain: $DOMAIN"

if [ -f "$CERT_DIR/fullchain.pem" ] && [ -f "$CERT_DIR/privkey.pem" ]; then
    echo "[+] Existing certificates found in $CERT_DIR. Skipping self-signed bootstrap."
    exit 0
fi

echo "[*] Creating temporary self-signed certificate for initial Nginx startup..."
mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out "$CERT_DIR/fullchain.pem" \
    -subj "/CN=$DOMAIN/O=AutoPrompt/C=US"

echo "[+] Temporary self-signed certificate created."
echo "[*] Once Nginx is running, run Certbot to request real Let's Encrypt certificates:"
echo "    docker compose -f docker-compose.prod.yml run --rm certbot certonly --webroot -w /var/www/certbot -d $DOMAIN --email $EMAIL --agree-tos --no-eff-email"
echo "[*] Then reload Nginx:"
echo "    docker compose -f docker-compose.prod.yml exec nginx nginx -s reload"
