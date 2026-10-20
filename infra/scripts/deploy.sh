#!/bin/bash
# Terraform plan or apply; colored console, plain copies in logs/infra/.
# Usage: TF_STATE_BUCKET=<bucket> [TF_ENV=dev] infra/scripts/deploy.sh plan|apply
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO] $(date +'%Y-%m-%d %H:%M:%S') - $1${NC}"; }
log_warn()  { echo -e "${YELLOW}[WARN] $(date +'%Y-%m-%d %H:%M:%S') - $1${NC}"; }
log_error() { echo -e "${RED}[ERROR] $(date +'%Y-%m-%d %H:%M:%S') - $1${NC}"; }
log_debug() { echo -e "${CYAN}[DEBUG] $(date +'%Y-%m-%d %H:%M:%S') - $1${NC}"; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# prod is the main root; other environments live in infra/terraform/envs/<name>.
TF_ENV="${TF_ENV:-prod}"
if [[ "$TF_ENV" == "prod" ]]; then TF_DIR="$ROOT/infra/terraform"; else TF_DIR="$ROOT/infra/terraform/envs/$TF_ENV"; fi
LOG_DIR="$ROOT/logs/infra"
STAMP="$(date +'%Y%m%d_%H%M%S')"
ACTION="${1:-plan}"
mkdir -p "$LOG_DIR"

: "${TF_STATE_BUCKET:?set TF_STATE_BUCKET to the Terraform state bucket}"

strip_colors() { sed -r 's/\x1b\[[0-9;]*m//g'; }

log_info "terraform init ($TF_ENV, state bucket $TF_STATE_BUCKET)"
terraform -chdir="$TF_DIR" init -input=false -backend-config="bucket=$TF_STATE_BUCKET" \
    | tee >(strip_colors > "$LOG_DIR/init_$STAMP.log")

case "$ACTION" in
    plan)
        log_info "terraform plan"
        terraform -chdir="$TF_DIR" plan -input=false -out=tfplan || {
            log_error "terraform plan failed; see the output above."
            exit 1
        }
        terraform -chdir="$TF_DIR" show -no-color tfplan > "$LOG_DIR/plan_$STAMP.log"
        log_info "Plan saved to logs/infra/plan_$STAMP.log"
        ;;
    apply)
        if [[ "${CI:-}" == "true" ]]; then
            # CD only: the plan was reviewed in the pull request.
            log_warn "Applying with -auto-approve (CI)"
            terraform -chdir="$TF_DIR" apply -input=false -auto-approve \
                | tee >(strip_colors > "$LOG_DIR/apply_$STAMP.log") || {
                log_error "terraform apply failed; check the GCP permissions of the apply account."
                exit 1
            }
        else
            log_debug "Manual run: Terraform asks before it changes anything."
            terraform -chdir="$TF_DIR" apply -input=true
        fi
        log_info "Infrastructure is up to date."
        ;;
    *)
        log_error "Unknown action '$ACTION'; use plan or apply."
        exit 1
        ;;
esac
