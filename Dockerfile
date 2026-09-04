FROM python:3.11.16-slim as builder

WORKDIR /app

# Install dependencies
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11.16-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Upgrade setuptools/wheel to pick up fixes for CVEs in their vendored
# copies of jaraco.context / wheel bundled with the base image, then remove
# pip itself (not needed at runtime) since it vendors an old msgpack/setuptools
# snapshot internally that otherwise shows up as unfixable image CVEs.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
  && python -m pip uninstall -y pip \
  && rm -rf /usr/local/lib/python3.11/site-packages/pip* \
            /usr/local/bin/pip*

# Copy application code
COPY app/ ./app/
COPY config/ ./config/

# Create data directory for SQLite and a non-root user to run as
RUN mkdir -p /app/data \
  && groupadd --system --gid 1000 app \
  && useradd --system --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app \
  && chown -R app:app /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8787/health').raise_for_status()"

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]