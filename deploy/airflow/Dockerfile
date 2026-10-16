# Airflow image that can also run the StyleHub pipeline.
#
# Airflow and the pipeline need different package versions, so they live in two Python
# environments inside this one image:
#   - Airflow itself uses the image's own Python (do not touch it).
#   - The pipeline (pandas, google-cloud, dbt, ...) lives in /opt/venv/stylehub.
# Each DAG task starts the pipeline with `uv run --no-sync`, which uses that second environment.
#
# The project code is COPIED into the image (/opt/stylehub), not mounted from your folder. So the
# image you test on a laptop is the image that runs on the VM. After a code change, rebuild.
#
# Build (from the project folder):  docker compose --env-file secrets/.env --profile airflow build
# Airflow 3.3.2 (the DAG was loaded with exactly this version on 2026-10-16). The base image is
# pinned by digest (the multi-platform index, read on 2026-10-16). To read it again:
#   docker buildx imagetools inspect apache/airflow:3.3.2-python3.12
FROM apache/airflow:3.3.2-python3.12@sha256:9df9c8be4096b9cc626bd7cb1f2b8c712eef66c59c615f8c7e6200871ca10bd1

ARG UV_VERSION=0.12.13

USER root
# logs/ is where pipeline_runs rows wait when BigQuery is down (a volume is mounted on it).
RUN mkdir -p /opt/venv /opt/stylehub/logs && chown -R airflow /opt/venv /opt/stylehub
USER airflow

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

ENV UV_PROJECT_ENVIRONMENT=/opt/venv/stylehub \
    UV_LINK_MODE=copy \
    UV_PYTHON=/usr/local/bin/python

# Install the pipeline's packages first. Docker reuses this layer until pyproject.toml or
# uv.lock changes.
COPY --chown=airflow pyproject.toml uv.lock /opt/stylehub/
RUN cd /opt/stylehub && uv sync --frozen --no-install-project --extra dbt

# The code itself, and the DAG next to it. The DAG is NOT mounted from your folder: DAG and code
# are one image, so they can never be two different versions.
COPY --chown=airflow src/stylehub /opt/stylehub/src/stylehub
COPY --chown=airflow dbt /opt/stylehub/dbt
COPY --chown=airflow deploy/airflow/dags /opt/airflow/dags
