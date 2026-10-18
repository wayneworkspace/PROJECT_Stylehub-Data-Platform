# Airflow image; the pipeline runs in its own venv, /opt/venv/stylehub.
# Code and DAGs are copied in, so laptop and VM run the same image.
# Build: docker compose --env-file secrets/.env --profile airflow build
# Base image pinned by digest (read 2026-10-17): docker buildx imagetools inspect apache/airflow:3.3.2-python3.13
FROM apache/airflow:3.3.2-python3.13@sha256:e9982ad3f49a60418622e1baf80c34b0daf3fa5091a336cb5ee61f0cdd189371

ARG UV_VERSION=0.12.13

USER root
RUN mkdir -p /opt/venv /opt/stylehub && chown -R airflow /opt/venv /opt/stylehub
USER airflow

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

# Pipeline packages first, so this layer is reused until requirements.txt changes.
COPY --chown=airflow requirements.txt /opt/stylehub/
RUN uv venv /opt/venv/stylehub --python /usr/local/bin/python \
    && uv pip install --no-cache --python /opt/venv/stylehub/bin/python -r /opt/stylehub/requirements.txt

COPY --chown=airflow src /opt/stylehub/src
COPY --chown=airflow include /opt/stylehub/include
COPY --chown=airflow dbt_project /opt/stylehub/dbt_project
COPY --chown=airflow dags /opt/airflow/dags
COPY --chown=airflow config /opt/airflow/config
