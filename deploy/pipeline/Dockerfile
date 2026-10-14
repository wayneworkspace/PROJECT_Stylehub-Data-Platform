# Runs the pipeline in a clean, repeatable environment.
# Build (from the project folder):  docker build -f deploy/pipeline/Dockerfile -t stylehub-pipeline .
# Run:    docker run --rm stylehub-pipeline python -m orchestration.run_daily --help
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install dependencies first. Docker reuses this layer until pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra dbt --no-install-project

COPY src/python ./src/python
COPY src/sql ./src/sql
COPY dbt ./dbt

# Do not run as root.
RUN useradd --create-home app && chown -R app /app
USER app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src/python"

# Secrets are never baked into the image. Pass them as environment variables or mount a key file.
CMD ["python", "-m", "orchestration.run_daily", "--help"]
