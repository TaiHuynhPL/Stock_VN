# ---- Build stage ----
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir .

# ---- Runtime stage ----
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Disable IPv6 to avoid connection issues
RUN echo "net.ipv6.conf.all.disable_ipv6=1" >> /etc/sysctl.conf && \
    echo "net.ipv6.conf.default.disable_ipv6=1" >> /etc/sysctl.conf && \
    echo "net.ipv6.conf.lo.disable_ipv6=1" >> /etc/sysctl.conf || true

# Set PostgreSQL connection to SSL disable for simpler connections
ENV PGSSLMODE=disable

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/stock-collector /usr/local/bin/stock-collector

# Copy app source and config
COPY src/ src/
COPY config.yaml .

# Create logs directory
RUN mkdir -p logs

ENTRYPOINT ["stock-collector"]
