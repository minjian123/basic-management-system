#!/usr/bin/env bash
# 禅道备份脚本（在 mjbk 上运行）
# 范围：zentao 库 dump（bms-mysql）+ /data 卷 tar（配置 my.php、license、上传附件、扩展包、内部备份）
# 落位：/mnt/data/backup/zentao/，保留 7 天
# 凭据：读 mjbk ~/deploy/.env 的 ZENTAO_MYSQL_USER/PASSWORD/DB
# 用法：bash backup_zentao.sh；cron 每日 02:00
set -euo pipefail

BACKUP_DIR=/mnt/data/backup/zentao
ENV_FILE="$HOME/deploy/.env"
TS="$(date +%F_%H%M%S)"
KEEP_DAYS=7

get_env() { grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2-; }

ZT_USER="$(get_env ZENTAO_MYSQL_USER)"
ZT_PASS="$(get_env ZENTAO_MYSQL_PASSWORD)"
ZT_DB="$(get_env ZENTAO_MYSQL_DB)"
if [ -z "$ZT_USER" ] || [ -z "$ZT_PASS" ] || [ -z "$ZT_DB" ]; then
  echo "ERROR: $ENV_FILE 缺少 ZENTAO_MYSQL_USER/PASSWORD/DB" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# 1) zentao 库 dump（InnoDB 一致性快照，不锁表）
docker exec -e MYSQL_PWD="$ZT_PASS" bms-mysql \
  mysqldump --user="$ZT_USER" --single-transaction --routines --triggers --no-tablespaces \
  --default-character-set=utf8mb4 "$ZT_DB" \
  | gzip > "$BACKUP_DIR/zentao-db_${TS}.sql.gz"
echo "OK db: zentao-db_${TS}.sql.gz ($(du -h "$BACKUP_DIR/zentao-db_${TS}.sql.gz" | cut -f1))"

# 2) /data 卷（config my.php、license、上传附件、扩展包、内部备份包）
#    该卷为匿名卷，经 --volumes-from 引用，避免 docker volume prune 误删依赖具名
docker run --rm \
  --volumes-from bms-zentao \
  -v "$BACKUP_DIR":/backup \
  alpine:latest tar czf "/backup/zentao-data_${TS}.tar.gz" -C /data .
echo "OK vol: zentao-data_${TS}.tar.gz ($(du -h "$BACKUP_DIR/zentao-data_${TS}.tar.gz" | cut -f1))"

# 3) 保留策略
find "$BACKUP_DIR" -name 'zentao-db_*.sql.gz' -mtime +"$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name 'zentao-data_*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "[$(date '+%F %T')] zentao backup OK -> $BACKUP_DIR"
