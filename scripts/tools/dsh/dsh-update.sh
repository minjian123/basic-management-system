#!/usr/bin/env bash
# 更新 DeepSeek Harness（dsh）源码、web profile 插件与知识图谱工具链，并确保 dsh web 运行
#
# 用法: dsh-update.sh [--force] [--no-restart] [--skip-kg]
#   --force       忽略版本检查，强制完整更新（pull + install + build + 插件 --latest + 图谱全更）
#   --no-restart  需要更新时只更新不重启（下次手动重启生效）
#   --skip-kg     跳过知识图谱检查与更新（dsh-graphify 插件 + graphifyy 运行时）
#
# 幂等逻辑（各部分分别比对版本，一致即跳过更新与编译）：
#   dsh 主体：本地 HEAD 与 origin/master 一致 → 跳过 git pull / pnpm install / pnpm run build；
#   web 插件：已装版本 == npm 最新 → 跳过 up --latest；
#   dsh-graphify（知识图谱插件）：npm 未发布，源码在 ~/develop/dsh-graphify（ghfast 克隆），
#     已装版本 == 远端最新 tag → 跳过；落后时 git pull → pnpm install/build → remove + add file: 重装；
#   graphifyy（知识图谱运行时，uv tool）：已装版本 == PyPI 最新 → 跳过；落后时 uv tool upgrade
#     （清华源），升级后探活 graphify-mcp，extras 缺失则补装 [chinese,openai,mcp]。
#   全部无需更新时：web 已在运行 → 提示退出；web 未运行 → 直接启动。
#
# 桌面入口:「更新 dsh与插件」（~/.local/share/applications/更新 dsh与插件.desktop）
# 回滚: web profile 配置/插件树变化由 dsh-undo-savepoint 自动快照，可 undo 回滚（部署文档 8.2 节）。
set -u

REPO=/home/minjian/develop/deepseek-harness
LOG=/home/minjian/.dsh/dsh-update.log
STOP_SH=/home/minjian/.local/bin/dsh-web-stop.sh
PLUGINS="dsh-free-vision dsh-undo-savepoint"
PORT=3080
FORCE=0
RESTART=1
SKIP_KG=0
# ---------- 知识图谱（graphify）相关 ----------
KG_NPM_PKG=dsh-graphify                      # web profile 内包名（file: 源）
KG_SRC="$HOME/develop/dsh-graphify"          # 插件源码目录（本地构建）
KG_URL="https://ghfast.top/https://github.com/QuantumKuba/dsh-graphify-plugin.git"
PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
GRAPHIFY_BIN="$HOME/.local/bin/graphify"
GRAPHIFY_MCP_BIN="$HOME/.local/bin/graphify-mcp"
UV_BIN="$(command -v uv || echo "$HOME/.local/bin/uv")"
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --no-restart) RESTART=0 ;;
    --skip-kg) SKIP_KG=1 ;;
    *) echo "未知参数: $arg（可用 --force / --no-restart / --skip-kg）" >&2; exit 2 ;;
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
  log "（兜底）dsh web 未在运行，后台启动…"
  rm -f "$LOG"
  (cd "$REPO" && setsid nohup pnpm dsh web >>"$LOG" 2>&1 </dev/null &)
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

installed_version() { # 已装插件版本（profiles/web/node_modules）
  python3 -c "import json;print(json.load(open('$HOME/.dsh/profiles/web/node_modules/$1/package.json'))['version'])" 2>/dev/null
}
latest_version() { # npm 最新版本（pnpm view，走 npmmirror 配置）
  timeout 20 pnpm view "$1" version 2>/dev/null
}

# ---------- 知识图谱辅助函数 ----------
kg_latest_tag() { # dsh-graphify 远端最新 tag（去 v 前缀），失败返回空
  timeout 30 git ls-remote --tags "$KG_URL" 2>/dev/null \
    | awk -F/ '{print $NF}' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1 | sed 's/^v//'
}
runtime_installed() { # 已装 graphifyy 版本（~/.local/bin/graphify --version）
  "$GRAPHIFY_BIN" --version 2>/dev/null | awk '{print $NF}'
}
runtime_latest() { # PyPI 最新 graphifyy 版本（清华 simple 索引，重试 2 次），失败返回空
  local v=""
  for _ in 1 2; do
    v=$(timeout 30 curl -fsSL "$PYPI_MIRROR/graphifyy/" 2>/dev/null \
      | grep -oE 'graphifyy-[0-9]+(\.[0-9]+)+' | sed 's/graphifyy-//' | sort -V | tail -1)
    [ -n "$v" ] && break
    sleep 1
  done
  printf '%s' "$v"
}
upgrade_runtime() { # uv tool 升级 graphifyy（清华源），随后探活 mcp extras
  local before after
  before=$(runtime_installed)
  log "更新 graphifyy（uv tool，清华源，最长 2 分钟）…"
  if ! UV_DEFAULT_INDEX="$PYPI_MIRROR" timeout 120 "$UV_BIN" tool upgrade graphifyy >/dev/null 2>&1; then
    log "⚠ uv tool upgrade 失败（网络？），尝试 --force 直装最新…"
  fi
  after=$(runtime_installed)
  if [ -n "$after" ] && [ "$before" != "$after" ]; then
    log "graphifyy 已更新: $before → $after"
  else
    # 原安装可能带版本 pin（如 @0.9.51），upgrade 不会越过 pin → 去 pin 直装最新（extras 带全）
    log "upgrade 未改变版本（可能受原固定版本约束），改为 --force 直装最新…"
    if UV_DEFAULT_INDEX="$PYPI_MIRROR" timeout 180 "$UV_BIN" tool install 'graphifyy[chinese,openai,mcp]' --force >/dev/null 2>&1; then
      after=$(runtime_installed)
      if [ -n "$after" ] && [ "$before" != "$after" ]; then
        log "graphifyy 已更新: $before → $after"
      else
        log "graphifyy 仍为 ${after:-未知}（请手动检查: $UV_BIN tool list）"
      fi
    else
      log "⚠ uv tool install --force 失败（网络？），保留 ${before:-未知}"
    fi
  fi
  # extras 探活：graphify-mcp 能打印 usage 说明 mcp 依赖在位；否则补装
  if ! timeout 5 "$GRAPHIFY_MCP_BIN" --help 2>&1 | grep -q "usage"; then
    log "graphify-mcp 探活失败（mcp extras 缺失？），补装 [chinese,openai,mcp] …"
    UV_DEFAULT_INDEX="$PYPI_MIRROR" timeout 180 "$UV_BIN" tool install 'graphifyy[chinese,openai,mcp]' --force >/dev/null 2>&1 \
      && log "graphifyy extras 补装完成" \
      || log "⚠ extras 补装失败，请手动执行: uv tool install 'graphifyy[chinese,openai,mcp]' --force"
  else
    log "graphify-mcp 探活正常"
  fi
}
build_kg() { # 拉取 dsh-graphify 源码并重装进 web profile；失败仅告警不中止
  if [ ! -d "$KG_SRC/.git" ]; then
    log "⚠ dsh-graphify 源码目录不存在（$KG_SRC），跳过其更新；首次部署："
    log "  ghfast clone $KG_URL → $KG_SRC → cd $KG_SRC && pnpm install && pnpm run build"
    return 1
  fi
  log "拉取 dsh-graphify 源码（$KG_SRC）…"
  timeout 120 git -C "$KG_SRC" pull --ff-only 2>/dev/null || { log "⚠ git pull 失败（网络？），跳过其更新"; return 1; }
  log "pnpm install / build（$KG_SRC）…"
  (cd "$KG_SRC" && timeout 300 pnpm install) >/dev/null 2>&1 || { log "⚠ pnpm install 失败，跳过其更新"; return 1; }
  (cd "$KG_SRC" && timeout 300 pnpm run build) >/dev/null 2>&1 || { log "⚠ pnpm run build 失败，跳过其更新"; return 1; }
  log "重装进 web profile（remove → add file:$KG_SRC）…"
  (cd "$REPO" && timeout 120 pnpm dsh plugin --profile web remove "$KG_NPM_PKG") >/dev/null 2>&1 \
    || { log "⚠ 插件 remove 失败，跳过其更新"; return 1; }
  (cd "$REPO" && timeout 120 pnpm dsh plugin --profile web add "file:$KG_SRC") >/dev/null 2>&1 \
    || { log "⚠ 插件 add file: 失败（源码 lib/ 未构建？），跳过其更新"; return 1; }
  log "dsh-graphify 已重装（新版本插件将在重启后的会话生效）"
}

# ---------- 版本比对 ----------
NEED_SRC=0
NEED_PLUGINS=""
NEED_KG=0
NEED_RUNTIME=0
if [ "$FORCE" = 1 ]; then
  log "── --force：跳过版本检查，强制完整更新 ──"
  NEED_SRC=1
  NEED_PLUGINS="$PLUGINS"
  if [ "$SKIP_KG" = 1 ]; then
    log "（--skip-kg：不强制知识图谱更新）"
  else
    NEED_KG=1
    NEED_RUNTIME=1
  fi
else
  # 1) dsh 主体：fetch 远端后比较 HEAD
  if timeout 60 git -C "$REPO" fetch origin master --quiet 2>/dev/null; then
    LOCAL=$(git -C "$REPO" rev-parse HEAD)
    REMOTE=$(git -C "$REPO" rev-parse origin/master)
    if [ "$LOCAL" != "$REMOTE" ]; then
      log "dsh 有新版本: 本地 ${LOCAL:0:8} → 远端 ${REMOTE:0:8}，需更新"
      NEED_SRC=1
    else
      log "dsh 主体已是最新（${LOCAL:0:8}），跳过 pull/install/build"
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
      log "插件 $p 已是最新（$have），跳过 up"
    else
      log "插件 $p 可更新: 已装 $have → 最新 $latest"
      NEED_PLUGINS="$NEED_PLUGINS $p"
    fi
  done

  # 3) 知识图谱（默认包含；--skip-kg 关闭）
  if [ "$SKIP_KG" = 1 ]; then
    log "── --skip-kg：跳过知识图谱（dsh-graphify / graphifyy）检查 ──"
  else
    have_kg=$(installed_version "$KG_NPM_PKG")
    latest_kg=$(kg_latest_tag)
    if [ -z "$have_kg" ]; then
      log "⚠ 读不到插件 $KG_NPM_PKG 的已装版本（node_modules 缺失？），跳过其检查"
    elif [ -z "$latest_kg" ]; then
      log "⚠ 无法查询 $KG_NPM_PKG 最新 tag（ghfast 离线或慢），跳过其检查，不更新"
    elif [ "$have_kg" = "$latest_kg" ]; then
      log "插件 $KG_NPM_PKG 已是最新（$have_kg），跳过重建"
    else
      log "插件 $KG_NPM_PKG 可更新: 已装 $have_kg → 远端 tag $latest_kg"
      NEED_KG=1
    fi

    have_rt=$(runtime_installed)
    latest_rt=$(runtime_latest)
    if [ -z "$have_rt" ]; then
      log "⚠ 读不到 graphifyy 已装版本（$GRAPHIFY_BIN 缺失？），跳过其检查"
    elif [ -z "$latest_rt" ]; then
      log "⚠ 无法查询 graphifyy 最新版（PyPI 镜像不可达？），跳过其检查，不更新"
    elif [ "$have_rt" = "$latest_rt" ]; then
      log "graphifyy 已是最新（$have_rt），跳过 upgrade"
    else
      log "graphifyy 可更新: 已装 $have_rt → 最新 $latest_rt"
      NEED_RUNTIME=1
    fi
  fi
fi

# ---------- 无需更新：直接启动 / 维持运行 ----------
if [ "$NEED_SRC" = 0 ] && [ -z "$NEED_PLUGINS" ] && [ "$NEED_KG" = 0 ] && [ "$NEED_RUNTIME" = 0 ]; then
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
  # 仅当涉及插件树变更（主体 / npm 插件 / dsh-graphify 重装）才停 web；
  # 仅 graphifyy 运行时更新时无需停 web（MCP 子进程按需启动，新版本即时生效）。
  STOP_NEEDED=0
  [ "$NEED_SRC" = 1 ] && STOP_NEEDED=1
  [ -n "$NEED_PLUGINS" ] && STOP_NEEDED=1
  [ "$NEED_KG" = 1 ] && STOP_NEEDED=1
  if [ "$STOP_NEEDED" = 1 ] && ss -lptnH 2>/dev/null | grep -q ":$PORT"; then
    log "停止 dsh web（:$PORT）…"
    bash "$STOP_SH" || fail "停止 dsh web 失败（$STOP_SH）"
    sleep 1
  fi

  if [ "$NEED_SRC" = 1 ]; then
    log "git pull origin master …"
    timeout 300 git -C "$REPO" pull --ff-only origin master || fail "git pull 失败（网络或冲突，见上）"
    log "pnpm install（npmmirror 源，最长 10 分钟）…"
    (cd "$REPO" && timeout 600 pnpm install) || fail "pnpm install 失败"
    log "pnpm run build（最长 15 分钟）…"
    (cd "$REPO" && timeout 900 pnpm run build) || fail "pnpm run build 失败"
  fi

  if [ -n "$NEED_PLUGINS" ]; then
    log "更新插件:$NEED_PLUGINS"
    (cd "$REPO" && timeout 300 pnpm dsh plugin --profile web up --latest $NEED_PLUGINS) || fail "插件更新失败"
  fi

  if [ "$NEED_KG" = 1 ]; then
    log "── 更新知识图谱插件 $KG_NPM_PKG ──"
    build_kg
  fi

  if [ "$NEED_RUNTIME" = 1 ]; then
    log "── 更新知识图谱运行时 graphifyy ──"
    upgrade_runtime
  fi

  [ "$RESTART" = 0 ] && { log "更新完成（--no-restart），请手动重启 dsh web 生效。"; exit 0; }
fi

# ---------- 启动 dsh web（幂等：未监听才启动） ----------
if ss -lptnH 2>/dev/null | grep -q ":$PORT"; then
  log "dsh web 已在运行（:$PORT），跳过启动"
else
  log "后台启动 dsh web …"
  rm -f "$LOG"
  (cd "$REPO" && setsid nohup pnpm dsh web >>"$LOG" 2>&1 </dev/null &) || fail "dsh web 启动失败"
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
