#!/usr/bin/env bash
# 更新 DeepSeek Harness（dsh）源码与 web profile 插件，并确保 dsh web 运行
#
# 用法: dsh-update.sh [--force] [--no-restart]
#   --force       忽略版本检查，强制完整更新（pull + install + build + 插件 up --latest + 重编译）
#   --no-restart  需要更新时只更新不重启（下次手动重启生效）
#
# 幂等逻辑（各部分分别比对版本，一致即跳过更新与编译）：
#   dsh 主体：本地 HEAD 与 origin/master 一致 → 跳过 git pull / pnpm install / pnpm run build；
#   web 插件：已装版本 == npm 最新 → 跳过 up --latest 与重编译；
#             有新版 → up --latest 更新后，rebuild 重跑插件构建脚本（编译/postinstall），
#             并核对更新后版本，未落实则告警；
#   全部无需更新时：web 已在运行 → 提示退出；web 未运行 → 直接启动。
#
# 桌面入口:「更新 dsh与插件」（~/.local/share/applications/更新 dsh与插件.desktop）
# 启动方式: 一律用构建产物 + 纯 node（node apps/cli/lib/bin.js web），不用 pnpm dsh web；
#   tsx 源码模式会同时加载 src 与 lib 两份核心包，dsh-tools 模块级 Symbol 分裂，
#   所有工具调用报 undefined.prepare（2026-09-18 定位，详见部署文档 FAQ）。
# 回滚: web profile 配置/插件树变化由 dsh-undo-savepoint 自动快照，可 undo 回滚（部署文档 8.2 节）。
set -u

REPO=/home/minjian/develop/deepseek-harness
PROFILE="$HOME/.dsh/profiles/web"
WEB_ENTRY="apps/cli/lib/bin.js"
LOG=/home/minjian/.dsh/dsh-update.log
STOP_SH=/home/minjian/.local/bin/dsh-web-stop.sh
PLUGINS="dsh-free-vision dsh-undo-savepoint"
PORT=3080
FORCE=0
RESTART=1
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --no-restart) RESTART=0 ;;
    *) echo "未知参数: $arg（可用 --force / --no-restart）" >&2; exit 2 ;;
  esac
done

# 桌面环境不加载 ~/.bashrc，需手动引入 nvm（Node 24 + pnpm）
export NVM_DIR="$HOME/.nvm"
export NVM_NODEJS_ORG_MIRROR="https://npmmirror.com/mirrors/node"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1

log() { echo "[$(date '+%F %T')] $*"; }

fail() {
  echo
  log "✗ $*"
  echo "已中止。可重跑本脚本；如需回滚，用 dsh-undo-savepoint（undo_list / undo_restore）或 Web UI 快照面板。"
  exit 1
}

ensure_web() { # EXIT 兜底：任何退出路径都保证 dsh web 在跑（--no-restart 除外）
  [ "$RESTART" = 1 ] || return 0
  ss -lptnH 2>/dev/null | grep -q ":$PORT" && return 0
  if [ ! -f "$REPO/$WEB_ENTRY" ]; then
    log "（兜底）缺少构建产物 $WEB_ENTRY，无法启动 dsh web；请重跑本脚本（会执行 pnpm run build）"
    return 0
  fi
  log "（兜底）dsh web 未在运行，后台启动…"
  rm -f "$LOG"
  (cd "$REPO" && setsid nohup node "$WEB_ENTRY" web >>"$LOG" 2>&1 </dev/null &)
  sleep 5
  log "兜底启动已发出，约 20-40 秒后就绪；启动日志: $LOG"
}
trap ensure_web EXIT

log "== dsh 更新检查开始 =="
command -v node >/dev/null 2>&1 || fail "node 不可用（需 nvm 加载 Node 24）"
command -v pnpm >/dev/null 2>&1 || fail "pnpm 不可用"
[ -d "$REPO/.git" ] || fail "dsh 仓库不存在: $REPO"
if [ -n "$(git -C "$REPO" status --porcelain)" ]; then
  fail "dsh 仓库有未提交改动，请先处理再更新：cd $REPO && git status"
fi

installed_version() { # 已装插件版本（profile 的 node_modules）
  python3 -c "import json;print(json.load(open('$PROFILE/node_modules/$1/package.json'))['version'])" 2>/dev/null
}
latest_version() { # npm 最新版本（在 profile 目录内查询，与安装同源同注册表）
  (cd "$PROFILE" 2>/dev/null && timeout 20 pnpm view "$1" version 2>/dev/null)
}

# ---------- 版本比对 ----------
NEED_SRC=0
NEED_PLUGINS=""
declare -A PLUGIN_FROM=() PLUGIN_TO=()
if [ "$FORCE" = 1 ]; then
  log "── --force：跳过版本检查，强制完整更新 ──"
  NEED_SRC=1
  NEED_PLUGINS="$PLUGINS"
else
  # 1) dsh 主体：fetch 远端后比较 HEAD
  if timeout 60 git -C "$REPO" fetch origin master --quiet 2>/dev/null; then
    LOCAL=$(git -C "$REPO" rev-parse HEAD)
    REMOTE=$(git -C "$REPO" rev-parse origin/master)
    if [ "$LOCAL" != "$REMOTE" ]; then
      log "dsh 有新版本: 本地 ${LOCAL:0:8} → 远端 ${REMOTE:0:8}，需更新"
      NEED_SRC=1
    else
      log "dsh 主体已是最新（${LOCAL:0:8}），跳过源码拉取/依赖安装/构建"
    fi
  else
    log "⚠ 无法连接远端（离线或网络慢），按现有版本处理，不更新主体"
  fi

  # 2) web 插件：已装版本与 npm 最新比对；查询失败视为"无法检查"，跳过该插件（不误停 web）
  for p in $PLUGINS; do
    have=$(installed_version "$p")
    latest=$(latest_version "$p")
    if [ -z "$have" ]; then
      log "⚠ 读不到插件 $p 的已装版本（node_modules 缺失？），跳过该插件"
    elif [ -z "$latest" ]; then
      log "⚠ 无法查询插件 $p 最新版本（离线或网络慢），跳过该插件，不更新"
    elif [ "$have" = "$latest" ]; then
      log "插件 $p 已是最新（$have），跳过更新"
    else
      log "插件 $p 可更新: 已装 $have → 最新 $latest"
      NEED_PLUGINS="$NEED_PLUGINS $p"
      PLUGIN_FROM[$p]="$have"
      PLUGIN_TO[$p]="$latest"
    fi
  done
fi

# ---------- 无需更新：直接启动 / 维持运行 ----------
if [ "$NEED_SRC" = 0 ] && [ -z "$NEED_PLUGINS" ]; then
  if ss -lptnH 2>/dev/null | grep -q ":$PORT"; then
    PID=$(ss -lptnH 2>/dev/null | grep ":$PORT" | grep -oP 'pid=\K[0-9]+' | head -1)
    log "全部已是最新，dsh web 正在运行（:$PORT，pid $PID），无需动作。"
    notify-send "dsh 更新检查" "全部已是最新，dsh web 运行中（pid $PID）" 2>/dev/null || true
    echo
    log "完成。"
    exit 0
  fi
  log "全部已是最新，dsh web 未运行，直接启动…"
  # 落入下方启动段（不执行任何更新）
else
  # ---------- 需要更新 ----------
  # 仅当涉及插件树变更（主体 / npm 插件）才停 web。
  STOP_NEEDED=0
  [ "$NEED_SRC" = 1 ] && STOP_NEEDED=1
  [ -n "$NEED_PLUGINS" ] && STOP_NEEDED=1
  if [ "$STOP_NEEDED" = 1 ] && ss -lptnH 2>/dev/null | grep -q ":$PORT"; then
    log "停止 dsh web（:$PORT）…"
    bash "$STOP_SH" || fail "停止 dsh web 失败（$STOP_SH）"
    sleep 1
  fi

  if [ "$NEED_SRC" = 1 ]; then
    log "── 拉取源码（git pull origin master，外部输出为英文）──"
    timeout 300 git -C "$REPO" pull --ff-only origin master || fail "拉取源码失败（网络或冲突，见上）"
    log "✓ 源码已更新（HEAD $(git -C "$REPO" rev-parse --short HEAD)）"
    log "── 安装依赖（pnpm install，最长 10 分钟，外部输出为英文）──"
    (cd "$REPO" && timeout 600 pnpm install) || fail "依赖安装失败（见上）"
    log "✓ 依赖安装完成"
    log "── 构建（pnpm run build，最长 15 分钟，外部输出为英文）──"
    (cd "$REPO" && timeout 900 pnpm run build) || fail "构建失败（见上）"
    log "✓ 构建完成"
  fi

  if [ -n "$NEED_PLUGINS" ]; then
    log "── 更新插件（up --latest，外部输出为英文）: $NEED_PLUGINS ──"
    (cd "$REPO" && timeout 300 pnpm dsh plugin --profile web up --latest $NEED_PLUGINS) || fail "插件更新失败（见上）"
    log "✓ 插件更新完成"
    log "── 重跑插件构建脚本（rebuild 即编译，外部输出为英文）: $NEED_PLUGINS ──"
    (cd "$REPO" && timeout 300 pnpm dsh plugin --profile web rebuild $NEED_PLUGINS) || fail "插件重编译失败（构建脚本，见上）"
    log "✓ 插件重编译完成"
    for p in $NEED_PLUGINS; do
      now=$(installed_version "$p")
      if [ -n "${PLUGIN_FROM[$p]:-}" ] && [ "$now" = "${PLUGIN_FROM[$p]}" ]; then
        log "⚠ 插件 $p 更新后版本仍为 $now（期望 ${PLUGIN_TO[$p]:-未知}），请检查上面的 pnpm 输出"
      else
        log "插件 $p 已装版本 ${now:-未知}，更新与重编译均已完成"
      fi
    done
  fi

  [ "$RESTART" = 0 ] && { log "更新完成（--no-restart），请手动重启 dsh web 生效。"; exit 0; }
fi

# ---------- 启动 dsh web（幂等：未监听才启动） ----------
if ss -lptnH 2>/dev/null | grep -q ":$PORT"; then
  log "dsh web 已在运行（:$PORT），跳过启动"
else
  log "后台启动 dsh web（构建产物方式）…"
  [ -f "$REPO/$WEB_ENTRY" ] || fail "缺少构建产物 $WEB_ENTRY；请重跑本脚本（会执行 pnpm run build）或手动: cd $REPO && pnpm run build"
  rm -f "$LOG"
  (cd "$REPO" && setsid nohup node "$WEB_ENTRY" web >>"$LOG" 2>&1 </dev/null &) || fail "dsh web 启动失败"
  ok=""
  for _ in $(seq 1 60); do
    if ss -lptnH 2>/dev/null | grep -q ":$PORT"; then ok=1; break; fi
    sleep 1
  done
  [ -n "$ok" ] || fail "dsh web 未能在 60 秒内监听 :$PORT，查看日志: $LOG"
fi

URL=$(grep -aoE "http://127\.0\.0\.1:$PORT/\?token=[A-Za-z0-9_-]+" "$LOG" 2>/dev/null | tail -1)
notify-send "dsh 更新完成" "dsh 检查/更新结束，web 已就绪${URL:+，$URL}" 2>/dev/null || true
log "dsh web 已就绪"
echo
log "完成。访问: ${URL:-http://127.0.0.1:$PORT （token 见 $LOG 或浏览器已自动打开）}"
