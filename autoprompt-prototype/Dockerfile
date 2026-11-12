# ==============================================================================
# AutoPrompt Frontend Lightweight Container (Phase 8.2)
# High-performance static asset server using Alpine Nginx
# ==============================================================================

FROM nginx:alpine-slim

LABEL maintainer="AutoPrompt Engineering Team" \
      version="1.0.0" \
      description="Static frontend asset server for AutoPrompt SPA"

# Remove default Nginx welcome page
RUN rm -rf /usr/share/nginx/html/*

# Copy static frontend assets into web root
COPY index.html /usr/share/nginx/html/
COPY css/ /usr/share/nginx/html/css/
COPY js/ /usr/share/nginx/html/js/
COPY assets/ /usr/share/nginx/html/assets/

# Configure Nginx for static delivery with gzip compression
RUN cat <<'EOF' > /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    # Gzip Compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml application/json application/javascript application/xml+rss application/atom+xml image/svg+xml;

    # Browser Caching
    location ~* \.(css|js|svg|png|jpg|ico)$ {
        expires 1y;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    # SPA Routing / Root
    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }

    # Security Headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
EOF

# Expose HTTP port
EXPOSE 80

# Health check using built-in wget in Alpine
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

# Start Nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
