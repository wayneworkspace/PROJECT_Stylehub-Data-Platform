# Airflow image; the pipeline runs in its own venv, /opt/venv/stylehub.
# Code and DAGs are copied in, so the laptop runs the image CI tested.
# Build: docker compose --env-file secrets/.env --profile airflow build
# Base image pinned by digest (read 2026-10-17): docker buildx imagetools inspect apache/airflow:3.3.2-python3.13
FROM apache/airflow:3.3.2-python3.13@sha256:e9982ad3f49a60418622e1baf80c34b0daf3fa5091a336cb5ee61f0cdd189371

ARG UV_VERSION=0.12.13

USER root
RUN mkdir -p /opt/venv /opt/stylehub && chown -R airflow /opt/venv /opt/stylehub
USER airflow

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

# Pipeline packages first, so this layer is reused until uv.lock changes. The
# package list is made from uv.lock here, so the lock file is the only source.
COPY --chown=airflow pyproject.toml uv.lock /opt/stylehub/
RUN cd /opt/stylehub \
    && uv export --frozen --no-hashes --no-dev --extra dbt --no-emit-project -o requirements.txt \
    && uv venv /opt/venv/stylehub --python /usr/local/bin/python \
    && uv pip install --no-cache --python /opt/venv/stylehub/bin/python -r requirements.txt

COPY --chown=airflow src /opt/stylehub/src
COPY --chown=airflow include /opt/stylehub/include
COPY --chown=airflow dbt_project /opt/stylehub/dbt_project
# Packages from package-lock.yml (dbt_utils); deps needs no warehouse connection.
RUN GCP_PROJECT_ID=build /opt/venv/stylehub/bin/dbt deps --project-dir /opt/stylehub/dbt_project \
    --profiles-dir /opt/stylehub/dbt_project --log-path /tmp/dbt-logs
COPY --chown=airflow dags /opt/airflow/dags
COPY --chown=airflow config /opt/airflow/config
