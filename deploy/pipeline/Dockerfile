# Runs the pipeline in a clean, repeatable environment.
# Build (from the project folder):  docker build -f deploy/pipeline/Dockerfile -t stylehub-pipeline .
# Run:    docker run --rm stylehub-pipeline python -m stylehub.orchestration.run_daily --help
#
# Pins: Python 3.12 (the same version as CI and Airflow), a fixed uv version, a fixed Debian
# release, and the digest of the base image (checked on 2026-10-16, Python 3.12.15). The digest is
# the multi-platform index, so amd64 and arm64 both work. To read the digest of a tag again:
#   docker buildx imagetools inspect python:3.12-slim-bookworm
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ARG UV_VERSION=0.12.13
ARG EXTRAS="--extra dbt"  # the dashboard builds this image with --extra serving

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

# Do not run as root.
RUN useradd --create-home app && chown app:app /app

# Install dependencies first. Docker reuses this layer until pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev ${EXTRAS} --no-install-project

# --chown here, not a recursive chown afterwards: that would copy every file into a new layer.
COPY --chown=app:app src/stylehub ./src/stylehub
COPY --chown=app:app dbt ./dbt
USER app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

# Secrets are never baked into the image. On a GCP VM the container uses the service account
# of the VM. On your laptop, mount a key file or pass environment variables.
CMD ["python", "-m", "stylehub.orchestration.run_daily", "--help"]
