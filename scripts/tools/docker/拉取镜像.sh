#!/usr/bin/env bash
# BMS 批量镜像拉取（断点续传 + 失败自动重试直到完成）
#
# 背景（2026-09-23 实测补记，详见《DockerEngine 部署使用说明》2.6 节）：
# 本机 Docker 用 containerd 镜像存储，blob 层按 HTTP Range 断点续传、已完成层落缓存；
# 大镜像（几百 MB）在加速器限速下常中途断开，**重复 docker pull 即可续传累积**，不会重下已完成层。
# 本脚本把「逐个拉 + 中断重试 + 已就位跳过」固化为一条命令，避免手工反复试源。
#
# 用法：
#   scripts/tools/docker/拉取镜像.sh [选项] [镜像...]
#   scripts/tools/docker/拉取镜像.sh                       # 读脚本同目录 镜像清单.txt
#   scripts/tools/docker/拉取镜像.sh --host user@ip        # 在远程 Docker 主机执行（默认读 MJBK_SSH_USER@MJBK_IP）
#   scripts/tools/docker/拉取镜像.sh nginx:1.27 redis:8    # 直接给镜像
#   scripts/tools/docker/拉取镜像.sh --file 我的清单.txt
#
# 选项：
#   --host <user@ip>   远程 Docker 主机（缺省：MJBK_SSH_USER@MJBK_IP，再缺省本机）
#   --file <路径>      镜像清单文件（每行一个；# 注释、空行忽略）
#   --retries <N>      单个镜像最大重试次数（0 = 不限，默认 0，直到成功）
#   --interval <秒>    失败重试间隔（默认 5）
#   --attempt-timeout <秒>  单次 docker pull 超时（默认 300；0 = 不限）——防“卡住不退出”导致重试不触发
#   --reset            先删除目标镜像再拉（默认跳过已就位镜像）
#   -h, --help         帮助
#
# 注意：
#   - 不要并发跑多个本脚本拉同一镜像（内容锁争用会假死）；脚本内部已按序逐个拉。
#   - 不要用 `docker system prune -a`，会清掉续传缓存。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

HOST=""
FILE=""
RETRIES=0
INTERVAL=5
ATTEMPT_TIMEOUT=300
RESET=0
IMAGES=()

usage() {
    # 打印文件头部的注释块（第 2 行起，遇到首个非注释行停止）
    awk 'NR > 1 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print } else { exit } }' "$0"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST="${2:?--host 需要值}"; shift 2 ;;
        --file) FILE="${2:?--file 需要值}"; shift 2 ;;
        --retries) RETRIES="${2:?--retries 需要值}"; shift 2 ;;
        --interval) INTERVAL="${2:?--interval 需要值}"; shift 2 ;;
        --attempt-timeout) ATTEMPT_TIMEOUT="${2:?--attempt-timeout 需要值}"; shift 2 ;;
        --reset) RESET=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; IMAGES+=("$@"); break ;;
        -*) echo "未知选项：$1" >&2; usage; exit 2 ;;
        *) IMAGES+=("$1"); shift ;;
    esac
done

# 缺省清单文件
if [[ -z "$FILE" && ${#IMAGES[@]} -eq 0 ]]; then
    FILE="$SCRIPT_DIR/镜像清单.txt"
fi
if [[ -n "$FILE" ]]; then
    [[ -f "$FILE" ]] || { echo "清单文件不存在：$FILE" >&2; exit 2; }
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"
        line="$(printf '%s' "$line" | tr -d '[:space:]')"
        [[ -n "$line" ]] && IMAGES+=("$line")
    done < "$FILE"
fi

if [[ ${#IMAGES[@]} -eq 0 ]]; then
    echo "未提供镜像，且清单为空。用 --file 或直接给镜像名。" >&2
    exit 2
fi

# 缺省主机：环境变量 MJBK_SSH_USER / MJBK_IP
if [[ -z "$HOST" && -n "${MJBK_IP:-}" && -n "${MJBK_SSH_USER:-}" ]]; then
    HOST="${MJBK_SSH_USER}@${MJBK_IP}"
fi

echo "目标主机：${HOST:-本机}；镜像数：${#IMAGES[@]}；重试上限：${RETRIES:-0}（0=不限）；间隔：${INTERVAL}s；单次超时：${ATTEMPT_TIMEOUT}s"

# 目标主机上运行的执行体（stdin 传入）：$1=重试上限 $2=间隔 $3=单次超时 $4=reset $5...=镜像
read -r -d '' BODY <<'EOS' || true
set -u
retries="$1"; interval="$2"; attempt_timeout="$3"; reset="$4"; shift 4
images=("$@")
fail=0
for img in "${images[@]}"; do
    if [[ "$reset" != "1" ]] && docker image inspect "$img" >/dev/null 2>&1; then
        echo "[跳过] $img（已就位）"
        continue
    fi
    attempt=0
    while :; do
        attempt=$((attempt + 1))
        echo "[拉取] $img（第 ${attempt} 次）"
        if [[ "$attempt_timeout" -gt 0 ]]; then
            # 单次超时：卡住不退出也会被中断，从而触发续传重试
            timeout "$attempt_timeout" docker pull "$img"
            rc=$?
        else
            docker pull "$img"
            rc=$?
        fi
        if [[ $rc -eq 0 ]]; then
            echo "[完成] $img"
            break
        fi
        if [[ $rc -eq 124 ]]; then
            echo "[超时] $img 单次超过 ${attempt_timeout}s，将续传重试（已完成层复用）"
        fi
        if [[ "$retries" -gt 0 && "$attempt" -ge "$retries" ]]; then
            echo "[失败] $img（已达最大重试 ${retries} 次）"
            fail=1
            break
        fi
        echo "[续传] $img 中断，${interval}s 后重试（已完成层会复用）..."
        sleep "$interval"
    done
done
exit "$fail"
EOS

# 组装目标端参数（镜像名经 %q 转义）
REMOTE_ARGS="'$RETRIES' '$INTERVAL' '$ATTEMPT_TIMEOUT' '$RESET'"
for img in "${IMAGES[@]}"; do
    REMOTE_ARGS+=" $(printf '%q' "$img")"
done

if [[ -n "$HOST" ]]; then
    ssh -o ConnectTimeout=8 "$HOST" "bash -s -- $REMOTE_ARGS" <<<"$BODY"
else
    bash -s -- "$RETRIES" "$INTERVAL" "$ATTEMPT_TIMEOUT" "$RESET" "${IMAGES[@]}" <<<"$BODY"
fi
