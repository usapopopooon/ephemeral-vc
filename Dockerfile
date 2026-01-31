FROM python:3.12-slim AS base

WORKDIR /app

# Install tini for proper signal handling
# PID 1 in containers doesn't forward signals properly without an init process
RUN apt-get update && apt-get install -y --no-install-recommends tini curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy source code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Create data directory
RUN mkdir -p data

# Health check for bot (checks if process is running)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD pgrep -f "python -m src.main" || exit 1

# Use tini as init process for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Run the bot
CMD ["python", "-m", "src.main"]

# Development image with dev dependencies
FROM base AS dev

RUN pip install --no-cache-dir -e ".[dev]"
COPY tests/ tests/
