#!/usr/bin/env bash
# 本机裸跑「全套」后端：SQLite 本地库 + 内存缓存（无需 Docker / 无需 mjbk），供**本机开发与真机回归**。
#
# 为什么这样起（口径）：
# - 开发态配置（`backend/config.dev.toml`）本就是 SQLite + 内存缓存 + 字典/参数走 SQL，**不依赖容器**；
# - 服务间调用基址模板是 `http://{service}:8000`（`[service_client].options.base_url_template`），
#   故本机给每个服务一个 loopback 别名（`127.0.0.2 tenant` …）+ **统一 8000 端口**，与容器形态同形；
# - `require_auth` 支持「本地 Bearer 用户令牌」路径、`[edge].require_gateway_identity = false`
#   ⇒ 不经网关直连服务可行；前端由 `VITE_LOCAL_API`（见 `env` 子命令）按服务就近代理。
#
# 用法: 本地全套.sh <up|down|stop|status|seed|env|logs> [选项]
#   up                起服务（幂等；已在跑则跳过）+ 自愈 hosts 别名 / 开发密钥，并等待健康
#   down              停本脚本起的服务（仅按 pid 文件；`--force` 才连带清理 IDE 起的同名进程）
#   stop <服务名...>  只停指定服务（其余保持纳管）——供「用 debugpy 调试某服务」时腾出该服务
#   status            进程与 /healthz、/readyz 一览
#   seed              幂等种子：租户注册库 + 菜单元数据 + 建号（缺省账号 admin；口令随机生成并打印一次）
#   env               确保 `frontend/apps/desktop/.env.local` 含 `VITE_LOCAL_API` 本地服务映射
#   logs [服务名]     打印日志尾部（缺省全部服务；追看用 tail -f）
#
# 选项:
#   --services "a b c"   要起的服务（缺省 tenant org platform identity）
#   --redis URL          Redis 连接串（缺省远端开发机 DB5：redis://192.168.0.107:6379/5）
#   --reset-db           起服务前把 `backend/bms_*.db` 备份移走（库结构/表归属变更后必须，否则 catalog 校验失败）
#   --username NAME      建号账号（缺省 admin）
#   --password PASS      建号口令（缺省**随机生成并仅打印一次**）
#   --reset-password     建号时重置既有账号口令
#   --force              down 时连带清理本机全部 `python -m bms_*` 进程
#
# 账号: `seed` 缺省建 `admin`，口令缺省随机生成并**仅打印一次**——**凭据只登记在
#       《bms文档/用户文档/本地资源.md》「BMS 应用账号」节（凭据不入库、不写入其他文档，见《AI开发规范》）**；
#       起栈后若登录 401，先看是否漏跑 seed。
#
# 状态目录: ${BMS_LOCAL_STATE_DIR:-/tmp/bms-local-stack}（pid 与日志）
# 退出码: 0 = 成功；1 = 失败（含健康等待超时）；2 = 参数错误
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND_ENV="$ROOT/frontend/apps/desktop/.env.local"
STATE_DIR="${BMS_LOCAL_STATE_DIR:-/tmp/bms-local-stack}"
KEYS_FILE="$BACKEND/.dev-keys.local"
PY="$BACKEND/.venv/bin/python"
PORT="${BMS_LOCAL_PORT:-8000}"
SERVICES_DEFAULT="tenant org platform identity"
SERVICES="$SERVICES_DEFAULT"
REDIS_URL="${BMS_LOCAL_REDIS:-redis://192.168.0.107:6379/5}"
RESET_DB=0
USERNAME="admin"
PASSWORD=""
RESET_PASSWORD=0
FORCE=0
HEALTH_TIMEOUT="${BMS_LOCAL_HEALTH_TIMEOUT:-45}"

log() { echo "[本地全套] $*"; }
err() { echo "[本地全套] $*" >&2; }

usage() {
  # 打印文件头注释块（锚定到 `set -uo pipefail` 前，避免头部增删行后范围漫进代码）
  sed -n '2,/^set -uo pipefail/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

# 服务 → loopback 别名（与服务基址模板 http://{service}:8000 同形）
ip_of() {
  case "$1" in
    tenant) echo "127.0.0.2" ;;
    org) echo "127.0.0.3" ;;
    platform) echo "127.0.0.4" ;;
    identity) echo "127.0.0.5" ;;
    *) echo "" ;;
  esac
}

# 解析 `[server]` 端口环境变量名：`BMS_SERVER__PORT`（不是 BMS_APP__PORT）
start_one() {
  local svc="$1" ip="$2"
  if [ -f "$STATE_DIR/$svc.pid" ] && kill -0 "$(cat "$STATE_DIR/$svc.pid")" 2>/dev/null; then
    log "$svc 已在跑（pid $(cat "$STATE_DIR/$svc.pid")），跳过"
    return 0
  fi
  # 已在监听（例如 IDE 调试起的）→ 接管跳过，避免二次绑定端口失败
  if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://$ip:$PORT/healthz" 2>/dev/null)" = "200" ]; then
    log "$svc 已在监听 $ip:$PORT（非本脚本启动；未纳管 pid），跳过"
    return 0
  fi
  # 直接后台起 python（**不套子 shell 包装**）——否则 `$!` 记到的是 bash 包装进程而非服务本体，
  # 停服务会打空、留下孤儿进程。cwd 与密钥由 cmd_up 在主进程内设定，子进程自然继承。
  BMS_SERVER__HOST="$ip" BMS_SERVER__PORT="$PORT" BMS_REDIS__URL="$REDIS_URL" PYTHONUNBUFFERED=1 \
    nohup "$PY" -m "bms_$svc" > "$STATE_DIR/$svc.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$STATE_DIR/$svc.pid"
  log "$svc 启动中：$ip:$PORT（pid $pid，日志 $STATE_DIR/$svc.log）"
}

# 停一个进程：TERM → 等 5s → KILL → 再等 2s；仍活则**报错交人工**（绝不无限等）
stop_pid() {
  local svc="$1" pid="$2" i k kids alive=0
  kids="$(pgrep -P "$pid" 2>/dev/null | tr '\n' ' ')"
  [ -n "$kids" ] && log "$svc：连带子进程 $kids"
  # shellcheck disable=SC2086
  kill -TERM $pid $kids 2>/dev/null || true
  for i in 1 2 3 4 5; do
    alive=0
    kill -0 "$pid" 2>/dev/null && alive=1
    for k in $kids; do kill -0 "$k" 2>/dev/null && alive=1; done
    [ "$alive" -eq 0 ] && { log "已停 $svc（pid $pid${kids:+ + 子进程}）"; return 0; }
    sleep 1
  done
  err "$svc（pid $pid）TERM 后 5s 仍未退出 → 强制 KILL"
  # shellcheck disable=SC2086
  kill -KILL $pid $kids 2>/dev/null || true
  sleep 2
  alive=0
  kill -0 "$pid" 2>/dev/null && alive=1
  for k in $kids; do kill -0 "$k" 2>/dev/null && alive=1; done
  if [ "$alive" -eq 1 ]; then
    err "$svc（pid $pid）**无法终止**（僵尸 / 权限不足 / 内核 IO 阻塞）——请人工处理：kill -9 $pid"
    return 1
  fi
  log "已强制停 $svc（pid $pid${kids:+ + 子进程}）"
  return 0
}

# 等待全部健康：单一总超时（不逐服务串行耗满），且**进程已退出即立刻报错 + 打印日志尾部**
wait_all_health() {
  local deadline pending svc ip pid rc=0
  deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  while :; do
    pending=""
    for svc in $SERVICES; do
      ip="$(ip_of "$svc")"
      if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://$ip:$PORT/healthz" 2>/dev/null)" = "200" ]; then
        continue
      fi
      pid=""
      [ -f "$STATE_DIR/$svc.pid" ] && pid="$(cat "$STATE_DIR/$svc.pid")"
      if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
        err "$svc 进程已退出（pid $pid）——日志尾部："
        tail -n 20 "$STATE_DIR/$svc.log" >&2 2>/dev/null || true
        return 1
      fi
      pending="$pending $svc"
    done
    [ -z "$pending" ] && { log "全部健康（healthz 200）：$SERVICES"; return 0; }
    if [ "$(date +%s)" -ge "$deadline" ]; then
      err "健康等待超时（${HEALTH_TIMEOUT}s），未就绪：$pending —— 看 $STATE_DIR/<服务>.log"
      return 1
    fi
    sleep 1
  done
  return "$rc"
}

ensure_dirs() { mkdir -p "$STATE_DIR"; }

ensure_hosts() {
  local missing=0 svc ip
  for svc in $SERVICES; do
    ip="$(ip_of "$svc")"
    if [ -z "$ip" ]; then
      err "未知服务：$svc（可选 tenant / org / platform / identity）"
      return 2
    fi
    getent hosts "$svc" >/dev/null 2>&1 || missing=1
  done
  [ "$missing" -eq 0 ] && return 0
  log "补 /etc/hosts 别名（服务间基址模板 http://{service}:8000 需要）"
  local block="# BMS 本地多服务寻址（本地全套.sh；与服务基址模板 http://{service}:8000 同形）"
  local line
  for svc in $SERVICES; do
    ip="$(ip_of "$svc")"
    getent hosts "$svc" >/dev/null 2>&1 || block="$block
$ip $svc"
  done
  if printf '%s\n' "$block" | sudo -n tee -a /etc/hosts >/dev/null 2>&1; then
    log "已写入 /etc/hosts"
  else
    err "写入 /etc/hosts 失败（需 sudo）——请手工追加："
    printf '%s\n' "$block" >&2
    return 1
  fi
}

ensure_keys() {
  [ -f "$KEYS_FILE" ] && return 0
  if [ ! -x "$PY" ]; then
    err "缺后端虚拟环境：$PY（先跑 uv sync）"
    return 1
  fi
  log "生成开发密钥 → $KEYS_FILE（用户令牌 usr- 前缀 + 服务令牌 svc- 前缀；本机专用、不入库）"
  "$PY" - <<PY
import json
from pathlib import Path
from joserfc.jwk import RSAKey


def pair():
    key = RSAKey.generate_key(2048, private=True)
    return key.as_pem(private=False).decode(), key.as_pem(private=True).decode()


user_pub, user_priv = pair()
svc_pub, svc_priv = pair()
Path("$KEYS_FILE").write_text("\n".join([
    "export BMS_SECURITY__KEYS='" + json.dumps({"usr-k1": {"algorithm": "RS256", "public_key": user_pub, "private_key": user_priv}}) + "'",
    "export BMS_SECURITY__ACTIVE_KID='usr-k1'",
    "export BMS_SERVICE_TOKEN__KEYS='" + json.dumps({"svc-k1": {"algorithm": "RS256", "public_key": svc_pub, "private_key": svc_priv}}) + "'",
    "export BMS_SERVICE_TOKEN__ACTIVE_KID='svc-k1'",
]) + "\n", encoding="utf-8")
print("已生成")
PY
}

reset_db() {
  local stamp backup
  stamp="$(date +%Y%m%d-%H%M%S)"
  backup="$BACKEND/.db-backup-$stamp"
  mkdir -p "$backup"
  local moved=0
  for f in "$BACKEND"/bms_*.db; do
    [ -e "$f" ] || continue
    mv "$f" "$backup/" && moved=$((moved + 1))
  done
  log "--reset-db：移走 $moved 个本地库文件 → $backup（服务启动会按当前表结构重建）"
}

cmd_up() {
  ensure_dirs || return 1
  [ -x "$PY" ] || { err "缺后端虚拟环境：$PY（先跑 uv sync）"; return 1; }
  ensure_keys || return 1
  ensure_hosts || return $?
  [ "$RESET_DB" -eq 1 ] && reset_db
  # 切到 backend 并加载开发密钥（服务子进程继承 cwd 与已导出的环境变量；脚本其余路径全用绝对路径）
  cd "$BACKEND" || return 1
  set -a
  # shellcheck disable=SC1090
  . "$KEYS_FILE"
  set +a
  local svc ip
  for svc in $SERVICES; do
    ip="$(ip_of "$svc")"
    start_one "$svc" "$ip"
  done
  wait_all_health || return 1
  log "全套已就绪；前端请在 IDE 跑「前端：宿主 dev」（.env.local 的 VITE_LOCAL_API 见 env 子命令）"
  return 0
}

cmd_down() {
  ensure_dirs
  local svc pid rc=0 seen=""
  for svc in $SERVICES_DEFAULT $SERVICES; do
    case " $seen " in *" $svc "*) continue ;; esac
    seen="$seen $svc"
    [ -f "$STATE_DIR/$svc.pid" ] || continue
    pid="$(cat "$STATE_DIR/$svc.pid")"
    if kill -0 "$pid" 2>/dev/null; then
      stop_pid "$svc" "$pid" || rc=1
    else
      log "$svc 已不在跑（残留 pid 文件，清理）"
    fi
    rm -f "$STATE_DIR/$svc.pid"
  done
  local rest
  rest="$(pgrep -f '\.venv/bin/python -m bms_' | tr '\n' ' ')"
  if [ -n "$rest" ]; then
    if [ "$FORCE" -eq 1 ]; then
      log "--force：逐个停剩余进程：$rest"
      for pid in $rest; do
        stop_pid "未纳管进程" "$pid" || rc=1
      done
    else
      err "另有未跟踪的后端进程：$rest（可能是 IDE 调试起的；如需一并停用 --force）"
    fi
  elif [ "$rc" -eq 0 ]; then
    log "本地后端已无残留进程"
  fi
  return "$rc"
}

cmd_stop() {
  ensure_dirs
  if [ "$#" -eq 0 ]; then
    err "用法：本地全套.sh stop <服务名...>（如 stop identity）"
    return 2
  fi
  local svc pid rc=0 stopped=0
  for svc in "$@"; do
    svc="${svc#bms_}"
    if [ -z "$(ip_of "$svc")" ]; then
      err "未知服务：$svc（可选 tenant / org / platform / identity）"
      rc=2
      continue
    fi
    if [ ! -f "$STATE_DIR/$svc.pid" ]; then
      err "$svc 未被本脚本纳管（无 pid 文件）——若它由 IDE 调试启动，请在 IDE 里停止"
      rc=1
      continue
    fi
    pid="$(cat "$STATE_DIR/$svc.pid")"
    if kill -0 "$pid" 2>/dev/null; then
      stop_pid "$svc" "$pid" || rc=1
    else
      log "$svc 已不在跑（清理残留 pid 文件）"
    fi
    rm -f "$STATE_DIR/$svc.pid"
    stopped=$((stopped + 1))
  done
  [ "$stopped" -gt 0 ] && log "已停 $stopped 个服务（其余仍纳管）；调试完用 up 一键补回"
  return "$rc"
}

cmd_status() {
  ensure_dirs
  local svc ip pid health ready
  printf '%-10s %-12s %-8s %-9s %s\n' 服务 地址 PID healthz readyz
  for svc in $SERVICES; do
    ip="$(ip_of "$svc")"
    pid="-"
    [ -f "$STATE_DIR/$svc.pid" ] && pid="$(cat "$STATE_DIR/$svc.pid")"
    health="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://$ip:$PORT/healthz" 2>/dev/null)"
    ready="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://$ip:$PORT/readyz" 2>/dev/null)"
    printf '%-10s %-12s %-8s %-9s %s\n' "$svc" "$ip:$PORT" "$pid" "${health:-000}" "${ready:-000}"
  done
}

cmd_seed() {
  [ -x "$PY" ] || { err "缺后端虚拟环境：$PY"; return 1; }
  local rc=0
  log "种子：租户注册库（bms_tenant.db）"
  ( cd "$BACKEND" && "$PY" -m ops.seed_tenant --url "sqlite+aiosqlite:///./bms_tenant.db" ) || rc=1
  log "种子：菜单元数据（bms_platform.db）"
  ( cd "$BACKEND" && "$PY" -m ops.seed_menu --url "sqlite+aiosqlite:///./bms_platform.db" ) || rc=1
  log "建号：$USERNAME（demo 租户 org 库；口令只打印这一次——请登记到《本地资源》「BMS 应用账号」节）"
  local extra=()
  [ "$RESET_PASSWORD" -eq 1 ] && extra+=(--reset-password)
  # 口令不入库：未显式给 `--password` 时由建号脚本随机生成并打印一次（凭据只落《本地资源》）。
  [ -n "$PASSWORD" ] && extra+=(--password "$PASSWORD")
  ( cd "$BACKEND" && "$PY" -m ops.seed_user --url "sqlite+aiosqlite:///./bms_org_demo.db" \
      --username "$USERNAME" "${extra[@]}" ) || rc=1
  [ "$rc" -eq 0 ] && log "种子完成（幂等：重复执行新增为 0）"
  return "$rc"
}

cmd_env() {
  local mapping="" svc
  for svc in tenant org platform identity; do
    mapping="$mapping${mapping:+,}$svc=$(ip_of "$svc")"
  done
  if [ -f "$FRONTEND_ENV" ] && grep -q '^VITE_LOCAL_API=' "$FRONTEND_ENV"; then
    log "已存在 VITE_LOCAL_API：$(grep '^VITE_LOCAL_API=' "$FRONTEND_ENV")"
    return 0
  fi
  mkdir -p "$(dirname "$FRONTEND_ENV")"
  {
    echo ""
    echo "# 本机裸跑后端时的服务直连映射（由 scripts/tools/dev/本地全套.sh env 维护；未列出的服务走 VITE_API_PROXY）"
    echo "VITE_LOCAL_API=$mapping"
  } >> "$FRONTEND_ENV"
  log "已写入 $FRONTEND_ENV：VITE_LOCAL_API=$mapping"
}

cmd_logs() {
  ensure_dirs
  local targets
  if [ "$#" -gt 0 ] && [ -n "$1" ]; then
    targets="$1"
  else
    targets="$SERVICES"
  fi
  local svc
  for svc in $targets; do
    echo "===== $svc ====="
    [ -f "$STATE_DIR/$svc.log" ] && tail -n 40 "$STATE_DIR/$svc.log" || echo "（无日志 $STATE_DIR/$svc.log）"
  done
}

CMD="${1:-}"
[ -n "$CMD" ] && shift
POSITIONAL=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --services) SERVICES="${2:-}"; shift 2 ;;
    --redis) REDIS_URL="${2:-}"; shift 2 ;;
    --reset-db) RESET_DB=1; shift ;;
    --username) USERNAME="${2:-}"; shift 2 ;;
    --password) PASSWORD="${2:-}"; shift 2 ;;
    --reset-password) RESET_PASSWORD=1; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) err "未知参数：$1"; usage >&2; exit 2 ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done

case "$CMD" in
  up) cmd_up ;;
  down) cmd_down ;;
  stop) cmd_stop "${POSITIONAL[@]}" ;;
  status) cmd_status ;;
  seed) cmd_seed ;;
  env) cmd_env ;;
  logs) cmd_logs "${POSITIONAL[@]}" ;;
  ""|-h|--help|help) usage ;;
  *) err "未知子命令：$CMD"; usage >&2; exit 2 ;;
esac
