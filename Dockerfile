# Dockerfile for prediction-data ingestion container
# Runs on ECS Fargate for scheduled Bronze layer data ingestion

FROM --platform=linux/amd64 python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir hatchling

# Copy package files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Build wheel
RUN pip wheel --no-deps --wheel-dir /build/wheels .


FROM --platform=linux/amd64 python:3.11-slim

# Security: run as non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --shell /bin/bash appuser

WORKDIR /app

# Install the wheel from builder stage with backfill dependencies (pyarrow, etc.)
COPY --from=builder /build/wheels/*.whl /tmp/
RUN WHEEL=$(ls /tmp/prediction_data-*.whl) && \
    pip install --no-cache-dir "${WHEEL}[backfill]" && \
    rm /tmp/*.whl

# Switch to non-root user
USER appuser

# Health check: verify CLI is installed and responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD prediction-data --version || exit 1

# Default entrypoint - override with ECS task definition
ENTRYPOINT ["prediction-data"]
CMD ["--help"]
