#!/usr/bin/env bash
# Run a range of pipeline steps inside the Docker image, on a GCP VM.
# Usage: deploy/pipeline/run_on_vm.sh <from-step> <to-step>
# The data date is yesterday (UTC). Override it with DATA_DATE=2026-10-01.
#
# NO KEY FILE. The VM is created with one service account (see docs/ops/DEPLOY_VM.md), and the
# container gets short-lived tokens for it from the VM's metadata server. There is no JSON key to
# copy, rotate or leak. One VM = one job = one service account.
#
# Which image runs:
#   - STYLEHUB_IMAGE is set (CD, see docs/ops/CD.md): log in to its registry with the VM's own
#     token, pull the image, run it. It must name a version: a git sha tag or a @sha256 digest.
#     ":latest" is refused, so a run can always be traced to one build and rolled back.
#   - STYLEHUB_IMAGE is empty: run the local image "stylehub-pipeline" built by hand.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <from-step> <to-step>" >&2
  exit 2
fi
from_step="$1"
to_step="$2"
data_date="${DATA_DATE:-$(date -u -d yesterday +%F)}"
image="${STYLEHUB_IMAGE:-stylehub-pipeline}"
env_file="${STYLEHUB_ENV_FILE:-/etc/stylehub/pipeline.env}"

if [ -n "${STYLEHUB_IMAGE:-}" ]; then
  case "${image}" in
    *@sha256:*) ;;
    *:latest | *:) echo "STYLEHUB_IMAGE must name a version (a git sha tag or a digest), not :latest" >&2; exit 2 ;;
    *:*) ;;
    *) echo "STYLEHUB_IMAGE has no tag: add :<git-sha> or @sha256:<digest>" >&2; exit 2 ;;
  esac
  # Keep the registry login in a temporary folder, so no token stays on the disk.
  DOCKER_CONFIG="$(mktemp -d)"
  export DOCKER_CONFIG
  trap 'rm -rf "${DOCKER_CONFIG}"' EXIT
  gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin "https://${STYLEHUB_IMAGE%%/*}"
  docker pull "${image}"
fi

# Settings come from the env file. Leave GOOGLE_APPLICATION_CREDENTIALS out of it.
docker run --rm \
  --env-file "${env_file}" \
  "${image}" \
  python -m stylehub.orchestration.run_daily --date "${data_date}" --from-step "${from_step}" --to-step "${to_step}"
