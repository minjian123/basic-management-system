#!/usr/bin/env bash
# BMS 开发服务器每日备份总控（部署于 mjbk ~/deploy/backup/）
# 组件：MySQL 全量、PostgreSQL 单库、达梦 DM8 dexp、GitLab、Kiwi TCMS 附件、百度网盘云同步
# 凭据：读 ~/deploy/.env 与 ~/.config/baidunetdisk/Cookies（官方客户端登录态）；不硬编码
# 落位：本地 /mnt/data/backup/<组件>/；云端 /apps/bms-backup/<日期>/（加密 .gpg）
# 用法：bash backup_daily.sh；cron 02:30 每日
set -uo pipefail

BASE_DIR=/mnt/data/backup
ENV_FILE="$HOME/deploy/.env"
TS="$(date +%F_%H%M%S)"
TODAY="$(date +%F)"
KEEP_DAYS=7
CLOUD_KEEP_DAYS=30
DM_HOME=/opt/dmdbms

get_env() { grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2-; }

mkdir -p "$BASE_DIR"/{mysql,postgres,dameng,gitlab,cloud/$TODAY}
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

backup_kiwi_uploads() {
  # Kiwi TCMS 附件卷（compose_kiwi-uploads -> 容器 /Kiwi/uploads）：测试用例附件等文件数据，不在数据库内
  mkdir -p "$BASE_DIR/kiwi"
  docker run --rm --volumes-from bms-kiwi \
    -v "$BASE_DIR/kiwi":/backup \
    alpine:latest tar czf "/backup/kiwi-uploads_${TS}.tar.gz" -C /Kiwi/uploads .
  [ -s "$BASE_DIR/kiwi/kiwi-uploads_${TS}.tar.gz" ]
}

run_step mysql    dump_mysql
run_step postgres dump_postgres
run_step dameng   dump_dameng
run_step gitlab   backup_gitlab
run_step kiwi     backup_kiwi_uploads

# 当日产物清单（含 GitLab 数据包，按 mtime 当日过滤）
mkdir -p "$BASE_DIR/cloud/$TODAY"
find "$BASE_DIR/mysql" "$BASE_DIR/postgres" "$BASE_DIR/dameng" "$BASE_DIR/gitlab" "$BASE_DIR/kiwi" \
  -type f -newermt "$TODAY" \( -name '*.sql.gz' -o -name '*.dmp' -o -name '*.tar' -o -name '*.tar.gz' \) \
  > "$BASE_DIR/cloud/$TODAY/.filelist"

# ---------- 本地保留策略：7 天 ----------
find "$BASE_DIR/mysql"    -name 'all_*.sql.gz'        -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/postgres" -name 'bms_dev_*.sql.gz'    -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/postgres" -name 'all_*.sql.gz'        -mtime +"$KEEP_DAYS" -delete  # 清理旧 dumpall 格式
find "$BASE_DIR/dameng"   -name 'dexp_all_*.dmp'      -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/dameng"   -name 'dexp_all_*.log'      -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/gitlab"   -name '*_gitlab_backup.tar' -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/gitlab"   -name 'gitlab-config_*.tar.gz' -mtime +"$KEEP_DAYS" -delete
find "$BASE_DIR/kiwi"     -name 'kiwi-uploads_*.tar.gz' -mtime +"$KEEP_DAYS" -delete

# ---------- 云同步（百度网盘，加密后单向上传；失败不影响主备份结论）----------
cloud_sync() {
  local pass; pass="$(get_env BACKUP_CRYPT_PASSPHRASE)"
  [ -n "$pass" ] || { echo "cloud: no BACKUP_CRYPT_PASSPHRASE"; return 1; }
  local db="$HOME/.config/baidunetdisk/Cookies"
  [ -f "$db" ] || { echo "cloud: 客户端 Cookies 库不存在"; return 1; }
  gc() { sqlite3 "$db" "SELECT value FROM cookies WHERE name='$1' AND host_key='${2:-.baidu.com}' LIMIT 1"; }
  local ck="BDUSS=$(gc BDUSS .pan.baidu.com); STOKEN=$(gc STOKEN .pan.baidu.com); BAIDUID=$(gc BAIDUID .baidu.com); PTOKEN=$(gc PTOKEN .passport.baidu.com)"
  BaiduPCS-Go login -cookies="$ck" >/dev/null || { echo "cloud: 登录失败"; return 1; }
  # 目标目录：/apps/bms-backup（应用隔离目录，网页端从「我的应用数据」进入查看）
  # 校验目录真实存在（upload 对不存在目录静默失败且返回 0，必须前置 ls 检查防假阳性）
  # 目录策略：mkdir 老 API 已失效（31030）无法自动建目录——若网页端手动建了当月子目录（如 2026-08）则用之，否则平铺根目录
  local dest="/apps/bms-backup"
  local monthly="/apps/bms-backup/$(date +%Y-%m)"
  if BaiduPCS-Go ls "$monthly" >/dev/null 2>&1; then
    dest="$monthly"; echo "cloud: 使用月度目录 $dest"
  else
    echo "cloud: 无月度目录，平铺 $dest（文件名自带日期；如需分目录请在网页端建 $(date +%Y-%m) 文件夹）"
  fi
  if ! BaiduPCS-Go ls "$dest" >/dev/null 2>&1; then
    echo "cloud: 网盘 $dest 不存在（需网页端手动创建），跳过云同步"; return 1
  fi
  # 加密当日清单内全部产物（含 GitLab 数据包）
  local n=0
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    printf '%s' "$pass" | gpg --batch --yes --passphrase-fd 0 --symmetric \
      --cipher-algo AES256 --compress-algo none -o "$BASE_DIR/cloud/$TODAY/$(basename "$f").gpg" "$f"
    n=$((n+1))
  done < "$BASE_DIR/cloud/$TODAY/.filelist"
  echo "cloud: 加密 $n 个产物 -> 上传 $dest/"
  local up_out
  up_out=$(BaiduPCS-Go upload "$BASE_DIR"/cloud/$TODAY/*.gpg "$dest/" 2>&1)
  echo "$up_out" | tail -3
  # 真实性核验：云端按文件名比对
  local missing=0
  for f in "$BASE_DIR"/cloud/$TODAY/*.gpg; do
    BaiduPCS-Go ls "$dest" 2>/dev/null | grep -q "$(basename "$f")" || { missing=$((missing+1)); echo "cloud 缺失: $(basename "$f")"; }
  done
  [ "$missing" -eq 0 ]
  local ok total
  ok=$(BaiduPCS-Go ls "$dest" 2>/dev/null | grep -c '\.gpg')
  total=$(ls "$BASE_DIR"/cloud/$TODAY/*.gpg 2>/dev/null | wc -l)
  echo "cloud sync: 目标=$dest 本地加密件=$total"
  [ "$total" -gt 0 ]
}
run_step cloud cloud_sync

# 云端暂存目录与网盘侧保留策略：30 天
find "$BASE_DIR/cloud" -name '*.gpg' -mtime +"$CLOUD_KEEP_DAYS" -delete
find "$BASE_DIR/cloud" -mindepth 1 -type d -empty -delete

echo "[$(date '+%F %T')] daily backup: ${STATUS[*]}"
# 主组件任一 FAIL 以非零退出（cloud FAIL 仅记录，不影响退出码）
for s in "${STATUS[@]}"; do [[ "$s" == *:FAIL && "$s" != cloud:* ]] && exit 1; done
exit 0
