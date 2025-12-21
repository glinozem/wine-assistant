#!/usr/bin/env bash
set -euo pipefail

CMD="${1:-backup}"

: "${PGHOST:=db}"
: "${PGPORT:=5432}"
: "${PGUSER:=postgres}"
: "${PGDATABASE:=wine_db}"
: "${PGPASSWORD:?PGPASSWORD is required}"

: "${BACKUP_DIR:=/backups}"
: "${RETENTION_LOCAL_DAYS:=14}"
: "${RETENTION_REMOTE_DAYS:=60}"

: "${RCLONE_REMOTE:?RCLONE_REMOTE is required}"   # например: wa_s3
: "${S3_BUCKET:?S3_BUCKET is required}"           # например: my-bucket
: "${S3_PREFIX:=wine-assistant}"                  # например: wine-assistant/dev

DST="${RCLONE_REMOTE}:${S3_BUCKET}/${S3_PREFIX}"

ts_utc() { date -u +"%Y%m%d_%H%M%S"; }

make_backup() {
  local ts fname tmp sha
  ts="$(ts_utc)"
  fname="wine_db_${ts}.dump"
  tmp="/tmp/${fname}"
  sha="/tmp/${fname}.sha256"

  echo "[backup] dumping ${PGDATABASE} -> ${tmp}"
  PGPASSWORD="${PGPASSWORD}" pg_dump -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -Fc -f "${tmp}"

  echo "[backup] quick verify archive (pg_restore -l)"
  pg_restore -l "${tmp}" >/dev/null

  echo "[backup] checksum"
  sha256sum "${tmp}" > "${sha}"

  echo "[backup] move to ${BACKUP_DIR}"
  mkdir -p "${BACKUP_DIR}"
  mv "${tmp}" "${BACKUP_DIR}/${fname}"
  mv "${sha}" "${BACKUP_DIR}/${fname}.sha256"

  echo "[backup] upload to ${DST}"
  rclone copy "${BACKUP_DIR}/${fname}" "${DST}/" --checksum
  rclone copy "${BACKUP_DIR}/${fname}.sha256" "${DST}/" --checksum

  echo "[backup] local retention: > ${RETENTION_LOCAL_DAYS} days"
  find "${BACKUP_DIR}" -type f -name "wine_db_*.dump" -mtime +"${RETENTION_LOCAL_DAYS}" -delete || true
  find "${BACKUP_DIR}" -type f -name "wine_db_*.sha256" -mtime +"${RETENTION_LOCAL_DAYS}" -delete || true

  echo "[backup] remote retention: delete objects older than ${RETENTION_REMOTE_DAYS} days"
  # Важно: это удаление. Сначала можно прогнать с --dry-run
  rclone delete "${DST}/" --min-age "${RETENTION_REMOTE_DAYS}d" --rmdirs || true

  echo "[backup] DONE: ${fname}"
}

restore_test() {
  echo "[restore-test] find latest local dump"
  local latest
  latest="$(ls -1 "${BACKUP_DIR}"/wine_db_*.dump 2>/dev/null | sort | tail -n 1 || true)"
  if [[ -z "${latest}" ]]; then
    echo "[restore-test] no local dumps found in ${BACKUP_DIR}"
    exit 2
  fi

  echo "[restore-test] using ${latest}"
  echo "[restore-test] recreate db wine_db_restore_test"
  PGPASSWORD="${PGPASSWORD}" dropdb   -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" --if-exists wine_db_restore_test
  PGPASSWORD="${PGPASSWORD}" createdb -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" wine_db_restore_test

  echo "[restore-test] restoring..."
  PGPASSWORD="${PGPASSWORD}" pg_restore -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d wine_db_restore_test --clean --if-exists "${latest}"

  echo "[restore-test] basic counts"
  PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d wine_db_restore_test -c "select count(*) products from products;"
  PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d wine_db_restore_test -c "select count(*) price_rows from product_prices;"
  PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d wine_db_restore_test -c "select count(*) inventory_rows from inventory;"

  echo "[restore-test] DONE"
}

case "${CMD}" in
  backup) make_backup ;;
  restore-test) restore_test ;;
  *)
    echo "Usage: backup.sh [backup|restore-test]"
    exit 1
    ;;
esac
