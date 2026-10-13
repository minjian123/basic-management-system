#!/usr/bin/env bash
# 前台常驻版 llama-server 包装（供 systemd --user 使用；不做 stop-others / nohup）
# 用法: qwen-serve.sh [ud|std|unc]     默认 std
# 环境变量: HOST(默认 0.0.0.0) PORT(默认 8080) MODEL_KEY(默认 std)
# 与人工脚本 qwen-start.sh 的区别：前台运行、不杀其它进程、默认监听 0.0.0.0。
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
MODELS_DIR=/home/minjian/ai/models
MMPROJ="$MODELS_DIR/mmproj-Qwen3.8-27B-f16.gguf"
CHAT_TPL="$DIR/templates/chat_template_qwen38_v22.4.jinja"

declare -A MODEL
MODEL[ud]="$MODELS_DIR/Qwen3.8-27B-UD-Q4_K_M.gguf"
MODEL[std]="$MODELS_DIR/Qwen3.8-27B-Q4_K_M.gguf"
MODEL[unc]="$MODELS_DIR/Qwen3.8-27B-Uncensored-Q4_K_M.gguf"

KEY="${1:-${MODEL_KEY:-std}}"
GGUF="${MODEL[$KEY]:-}"
if [ -z "$GGUF" ]; then
  echo "未知模型: $KEY（可选: ud / std / unc）" >&2
  exit 1
fi
if [ ! -f "$GGUF" ]; then
  echo "模型文件不存在: $GGUF" >&2
  exit 1
fi

echo "启动 llama-server: model=$KEY host=$HOST port=$PORT file=$GGUF"
exec "$DIR/build/bin/llama-server" \
  -m "$GGUF" \
  -mm "$MMPROJ" \
  -ngl 999 -c 153600 -ctk q4_0 -ctv q4_0 \
  --flash-attn on --host "$HOST" --port "$PORT" \
  --jinja \
  --chat-template-file "$CHAT_TPL" \
  --reasoning-format deepseek \
  --reasoning-effort max \
  --reasoning-preserve \
  --spec-type ngram-mod --spec-ngram-mod-n-match 16 --spec-ngram-mod-n-min 32 --spec-ngram-mod-n-max 64
