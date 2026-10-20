#!/bin/bash
# Configure the Airflow VM with Ansible over IAP (enable_airflow_vm = true first).
# Run from Linux, macOS or WSL (Ansible has no Windows control node).
# Usage: GCP_PROJECT_ID=<project> [GCP_LOCATION=asia-southeast1] [VM_ZONE=asia-southeast1-b] infra/scripts/configure_vm.sh
set -euo pipefail

GREEN='\033[0;32m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO] $(date +'%Y-%m-%d %H:%M:%S') - $1${NC}"; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
REGION="${GCP_LOCATION:-asia-southeast1}"
ZONE="${VM_ZONE:-asia-southeast1-b}"
KEY="$HOME/.ssh/google_compute_engine"

# OS Login: register this machine's key once, then sign in as your OS Login user.
[[ -f "$KEY" ]] || ssh-keygen -t ed25519 -f "$KEY" -N "" -q
gcloud compute os-login ssh-keys add --key-file "$KEY.pub" --project "$GCP_PROJECT_ID" > /dev/null
OS_USER="$(gcloud compute os-login describe-profile --format='value(posixAccounts[0].username)')"

log_info "Configuring stylehub-airflow in $ZONE as $OS_USER"
cd "$ROOT/infra/ansible"
ANSIBLE_CONFIG=ansible.cfg uvx --from ansible-core==2.18.6 ansible-playbook airflow_vm.yml \
    -u "$OS_USER" --private-key "$KEY" \
    -e project_id="$GCP_PROJECT_ID" -e region="$REGION" -e vm_zone="$ZONE"
log_info "Airflow VM is up to date."
