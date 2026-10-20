#!/bin/bash
# Back up or restore the Airflow metadata database of the local Docker stack.
# pg_dump gives a consistent copy while Airflow runs; the files go to backups/.
# Usage: infra/scripts/airflow_db_backup.sh backup
#        infra/scripts/airflow_db_backup.sh restore backups/airflow_<stamp>.sql.gz
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO] $(date +'%Y-%m-%d %H:%M:%S') - $1${NC}"; }
log_error() { echo -e "${RED}[ERROR] $(date +'%Y-%m-%d %H:%M:%S') - $1${NC}"; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose --env-file secrets/.env --profile airflow)
mkdir -p backups

case "${1:-}" in
    backup)
        FILE="backups/airflow_$(date +'%Y%m%d_%H%M%S').sql.gz"
        "${COMPOSE[@]}" exec -T airflow-db pg_dump -U airflow --clean --if-exists airflow | gzip > "$FILE"
        log_info "Backup written to $FILE"
        ;;
    restore)
        FILE="${2:?give the backup file to restore}"
        [[ -f "$FILE" ]] || { log_error "No file $FILE"; exit 1; }
        log_info "Stopping Airflow so nothing writes during the restore"
        "${COMPOSE[@]}" stop airflow-scheduler airflow-dag-processor airflow-apiserver
        gunzip -c "$FILE" | "${COMPOSE[@]}" exec -T airflow-db psql -U airflow -d airflow -v ON_ERROR_STOP=1 > /dev/null
        "${COMPOSE[@]}" start airflow-apiserver airflow-dag-processor airflow-scheduler
        log_info "Restored $FILE"
        ;;
    *)
        log_error "Use: backup | restore <file>"
        exit 1
        ;;
esac
