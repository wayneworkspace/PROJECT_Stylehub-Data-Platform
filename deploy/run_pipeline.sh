#!/usr/bin/env bash
# Run a range of pipeline steps inside the Docker image.
# Usage: deploy/run_pipeline.sh <from-step> <to-step> <service-account-key-file>
# The data date is yesterday (UTC). Override it with DATA_DATE=2026-10-01.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <from-step> <to-step> <service-account-key-file>" >&2
  exit 2
fi
from_step="$1"
to_step="$2"
key_file="$3"
data_date="${DATA_DATE:-$(date -u -d yesterday +%F)}"

# Settings come from /etc/stylehub/pipeline.env. The key is mounted read-only, never copied in.
exec docker run --rm \
  --env-file /etc/stylehub/pipeline.env \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp-sa.json \
  -v "${key_file}:/app/secrets/gcp-sa.json:ro" \
  stylehub-pipeline \
  python -m pipeline.run_daily --date "${data_date}" --from-step "${from_step}" --to-step "${to_step}"
