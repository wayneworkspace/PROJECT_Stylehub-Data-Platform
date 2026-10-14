#!/usr/bin/env bash
# Run a range of pipeline steps inside the Docker image.
# Usage: deploy/run_pipeline.sh <from-step> <to-step> <service-account-key-file>
# The data date is yesterday (UTC). Override it with DATA_DATE=2026-10-01.
#
# Which image runs:
#   - STYLEHUB_IMAGE is set (CD, see docs/CD.md): log in to its registry with the job's own
#     key, pull the image, run it. Pin a version with a tag, for example ...:<git-sha>.
#   - STYLEHUB_IMAGE is empty: run the local image "stylehub-pipeline" built by hand.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <from-step> <to-step> <service-account-key-file>" >&2
  exit 2
fi
from_step="$1"
to_step="$2"
key_file="$3"
data_date="${DATA_DATE:-$(date -u -d yesterday +%F)}"
image="${STYLEHUB_IMAGE:-stylehub-pipeline}"

if [ -n "${STYLEHUB_IMAGE:-}" ]; then
  # Keep the registry login in a temporary folder, so no password stays on the disk.
  DOCKER_CONFIG="$(mktemp -d)"
  export DOCKER_CONFIG
  trap 'rm -rf "${DOCKER_CONFIG}"' EXIT
  docker login -u _json_key --password-stdin "https://${STYLEHUB_IMAGE%%/*}" < "${key_file}"
  docker pull "${image}"
fi

# Settings come from /etc/stylehub/pipeline.env. The key is mounted read-only, never copied in.
docker run --rm \
  --env-file /etc/stylehub/pipeline.env \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp-sa.json \
  -v "${key_file}:/app/secrets/gcp-sa.json:ro" \
  "${image}" \
  python -m pipeline.run_daily --date "${data_date}" --from-step "${from_step}" --to-step "${to_step}"
