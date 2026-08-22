#!/usr/bin/env bash
# BMS 开发服务器每日备份总控（部署于 mjbk ~/deploy/backup/）
# 组件：MySQL 全量（含 zentao/kiwi/bms_dev）、PostgreSQL 全量、达梦 DM8 dexp、GitLab
# 禅道细粒度备份由既有 backup_zentao.sh 承担（cron 02:00），本脚本不重复
# 凭据：读 ~/deploy/.env；落位 /mnt/data/backup/<组件>/；保留 7 天
# 用法：bash backup_daily.sh；cron 02:30 每日
set -uo pipefail

BASE_DIR=/mnt/data/backup
ENV_FILE="$HOME/deploy/.env"
TS="$(date +%F_%H%M%S)"
KEEP_DAYS=7
DM_HOME=/opt/dmdbms

get_env() { grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2-; }

mkdir -p "$BASE_DIR"/{mysql,postgres,dameng,gitlab}
STATUS=()

run_step() { # run_step <名称> <命令...>
  local name="$1"; shift
  if "$@" >>"$BASE_DIR/cron.log" 2>&1; then
    STATUS+=("$name:OK")
  else
    STATUS+=("$name:FAIL")
  fi
}

dump_mysql() {
  local pwd; pwd="$(get_env MYSQL_ROOT_PASSWORD)"
  docker exec -e MYSQL_PWD="$pwd" bms-mysql mysqldump --user=root \
    --single-transaction --all-databases --routines --triggers --events \
    --no-tablespaces --default-character-set=utf8mb4 \
    | gzip > "$BASE_DIR/mysql/all_${TS}.sql.gz"
  [ -s "$BASE_DIR/mysql/all_${TS}.sql.gz" ]
}

dump_postgres() {
  # 单库 pg_dump（bms_dev）：恢复时可干净导入任意临时库，无 pg_dumpall 的角色冲突与 \connect 直写问题
  local pwd; pwd="$(get_env POSTGRES_PASSWORD)"
  docker exec -e PGPASSWORD="$pwd" bms-postgres \
    pg_dump --username=postgres --dbname=bms_dev \
    | gzip > "$BASE_DIR/postgres/bms_dev_${TS}.sql.gz"
  [ -s "$BASE_DIR/postgres/bms_dev_${TS}.sql.gz" ]
}

dump_dameng() {
  local pwd; pwd="$(get_env DM8_SYSDBA_PASSWORD)"
  "$DM_HOME/bin/dexp" "SYSDBA/${pwd}@localhost:5236" \
    FILE="dexp_all_${TS}.dmp" LOG="dexp_all_${TS}.log" \
    DIRECTORY="$BASE_DIR/dameng" FULL=Y >/dev/null
  [ -s "$BASE_DIR/dameng/dexp_all_${TS}.dmp" ]
}

backup_gitlab() {
  # 1) 容器内 gitlab-backup（产物落挂载盘 /mnt/ssd2t/gitlab/data/backups/）
  docker exec bms-gitlab gitlab-backup create >/dev/null || return 1
  sleep 2
  local latest
  latest="$(docker exec bms-gitlab bash -c 'ls -t /var/opt/gitlab/backups/*_gitlab_backup.tar 2>/dev/null | head -1')"
  [ -n "$latest" ] || return 1
  local fname; fname="$(basename "$latest")"
  docker cp "bms-gitlab:$latest" "$BASE_DIR/gitlab/$fname" || return 1
  docker exec bms-gitlab rm -f "$latest" >/dev/null
  # 2) 配置备份（secrets/ssl/gitlab.rb 不在数据备份内）
  tar czf "$BASE_DIR/gitlab/gitlab-config_${TS}.tar.gz" -C /mnt/ssd2t/gitlab config
  [ -s "$BASE_DIR/gitlab/$fname" ] && [ -s "$BASE_DIR/gitlab/gitlab-config_${TS}.tar.gz" ]
}

run_step mysql    dump_mysql
run_step postgres dump_postgres
run_step dameng   dump_dameng
run_step gitlab   backup_gitlab

# 保留策略：7 天
find "$BASE_DIR/mysql"    -name 'all_*.sql.gz'        -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/postgres" -name 'bms_dev_*.sql.gz'    -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/postgres" -name 'all_*.sql.gz'        -mtime +"$KEEP_DAYS" -delete  # 清理旧 dumpall 格式
find "$BASE_DIR/dameng"   -name 'dexp_all_*.dmp'      -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/dameng"   -name 'dexp_all_*.log'      -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/gitlab"   -name '*_gitlab_backup.tar' -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/gitlab"   -name 'gitlab-config_*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "[$(date '+%F %T')] daily backup: ${STATUS[*]}"
# 任一组件失败以非零退出，便于 cron 日志观察
for s in "${STATUS[@]}"; do [[ "$s" == *:FAIL ]] && exit 1; done
exit 0
