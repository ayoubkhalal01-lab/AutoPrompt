# ==============================================================================
# AutoPrompt Unified Production Nginx Reverse Proxy & Static Web Server
# Alpine-slim base, hardened TLS 1.3, rate-limited upstream proxy
# ==============================================================================

FROM nginx:alpine-slim

LABEL maintainer="AutoPrompt Engineering Team" \
      version="1.0.0" \
      description="Production Nginx reverse proxy with TLS and static SPA hosting"

# Remove default configurations and assets
RUN rm -rf /etc/nginx/conf.d/* /usr/share/nginx/html/*

# Create directory structures
RUN mkdir -p /var/www/html /var/www/certbot /etc/letsencrypt

# Copy main tuned configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/autoprompt-production.conf /etc/nginx/conf.d/autoprompt.conf

# Expose HTTP and HTTPS ports
EXPOSE 80 443

# Health check probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
