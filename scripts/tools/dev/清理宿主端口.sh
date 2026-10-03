#!/usr/bin/env bash
# 清理占用指定端口的**本项目**旧 dev server（仅限进程 cwd == 给定目录者；非本项目占用则中止，不误杀）。
#
# 背景：宿主 vite 配置为 `strictPort: true`（端口被占即启动失败、不会自动换端口），而 IDE 启动项
# （「全套」等）重复启动时经常撞上上一次残留的 dev server，故启动前先自愈。
#
# 用法: 清理宿主端口.sh <端口> <本项目宿主目录绝对路径>
# 退出码: 0 = 端口已空闲（原本空闲，或已清理本项目旧进程）；1 = 被非本项目进程占用（未清理）；
#         2 = 参数错误
#
# **不要**把它挂成 VS Code 任务的 dependsOn —— 实测「带 dependsOn 的 background 任务」会让
# preLaunchTask 一直等不到就绪信号（弹出「正在等待 preLaunchTask」），故一律内联在 dev 任务的
# command 开头调用（见 .vscode/tasks.json）。
set -uo pipefail

PORT="${1:-}"
DIR="${2:-}"
if [ -z "$PORT" ] || [ -z "$DIR" ]; then
  echo "用法: $0 <端口> <本项目宿主目录绝对路径>" >&2
  exit 2
fi
DIR=$(readlink -f "$DIR" 2>/dev/null || echo "$DIR")

# 监听该端口的进程 PID 列表
port_pids() {
  ss -ltnp 2>/dev/null | awk -v p=":${PORT}\$" '$4 ~ p {print}' \
    | grep -oP 'pid=\K[0-9]+' | sort -u
}

rc=0
pids=$(port_pids)
for pid in $pids; do
  cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || echo "")
  if [ "$cwd" = "$DIR" ]; then
    echo "[dev-port] 清理本项目旧 dev server：pid=$pid port=$PORT cwd=$cwd"
    kill -TERM "$pid" 2>/dev/null || true
  else
    echo "[dev-port] 端口 $PORT 被非本项目进程占用：pid=$pid cwd=${cwd:-未知}，中止启动（不误杀）" >&2
    rc=1
  fi
done

# 等端口释放（最多 10s），仅在本轮确有清理动作时等待
if [ "$rc" -eq 0 ] && [ -n "$pids" ]; then
  for _ in $(seq 1 20); do
    [ -z "$(port_pids)" ] && break
    sleep 0.5
  done
  [ -z "$(port_pids)" ] && echo "[dev-port] 端口 $PORT 已释放"
fi

exit "$rc"
