# Airflow image that can also run the StyleHub pipeline.
#
# Airflow and the pipeline need different package versions, so they live in two Python
# environments inside this one image:
#   - Airflow itself uses the image's own Python (do not touch it).
#   - The pipeline (pandas, google-cloud, dbt, ...) lives in /opt/venv/stylehub.
# Each DAG task starts the pipeline with `uv run --no-sync`, which uses that second environment.
#
# Build (from the project folder):  docker compose --env-file secrets/.env --profile airflow build
FROM apache/airflow:2.10.5-python3.12

USER root
RUN mkdir -p /opt/venv /opt/stylehub && chown airflow /opt/venv /opt/stylehub
USER airflow

RUN pip install --no-cache-dir uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv/stylehub \
    UV_LINK_MODE=copy \
    UV_PYTHON=/usr/local/bin/python

# Install the pipeline's packages first. Docker reuses this layer until pyproject.toml or
# uv.lock changes. The project code itself is mounted at /opt/stylehub (see the airflow services in docker-compose.yaml).
COPY --chown=airflow pyproject.toml uv.lock /tmp/stylehub-deps/
RUN cd /tmp/stylehub-deps && uv sync --frozen --no-install-project --extra dbt
