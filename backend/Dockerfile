# ==============================================================================
# AutoPrompt Backend Production Dockerfile (Phase 8.2)
# Multi-stage, non-root, minimal attack surface Python container
# ==============================================================================

# ── Stage 1: Build & Dependency Wheel Cache ──────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Create isolated build virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip to latest secure version
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install dependencies from requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Minimal Production Runtime ──────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

LABEL maintainer="AutoPrompt Engineering Team" \
      version="1.0.0" \
      description="Production container for AutoPrompt FastAPI backend"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    HOST=0.0.0.0 \
    DATABASE_URL="sqlite:////app/data/autoprompt.db"

WORKDIR /app

# Create dedicated non-root application user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -M -d /app appuser

# Copy pre-built virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create persistent storage mount directory with correct ownership
RUN mkdir -p /app/data && \
    chown -R appuser:appgroup /app /app/data && \
    chmod 700 /app/data

# Copy application source code
COPY --chown=appuser:appgroup app/ /app/app/

# Switch to unprivileged non-root user
USER appuser

# Expose internal application port
EXPOSE 8000

# Health check using Python's standard library (no external curl binary needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').getcode() == 200 else 1)"

# Production execution command (2 workers, no development reload)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
