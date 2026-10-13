#!/usr/bin/env bash
# 在 mjpc 上以 root 执行一次（sudo bash install-systemd.sh）：
#   1) 安装并启用 openssh-server（供 mjbk 远程启停模型 / 关机）
#   2) ufw 放行 mjbk 的 22 / 8080 / 8082
#   3) 把 qwen-serve.sh 同步到 llama.cpp 源码目录，并安装系统级 llamacpp-qwen / llamacpp-bge 服务
#      （默认不自启，由 MIRIX 模型代理按需 start）
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MJBK="${MJBK_IP:-192.168.0.107}"
LLAMA_DIR="${LLAMA_DIR:-/home/minjian/develop/llama.cpp}"

if [ "$(id -u)" -ne 0 ]; then
  echo "请以 root 运行：sudo bash $0" >&2
  exit 1
fi

echo "[1/5] 安装 openssh-server ..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -q openssh-server

echo "[2/5] 启用 ssh ..."
systemctl enable --now ssh

echo "[3/5] ufw 放行 mjbk（${MJBK}）的 22 / 8080 / 8082 ..."
for p in 22 8080 8082; do
  ufw allow from "$MJBK" to any port "$p" proto tcp
done
ufw reload 2>/dev/null || true

echo "[4/5] 同步包装脚本与模型档位配置到 ${LLAMA_DIR} ..."
mkdir -p "$LLAMA_DIR"
install -m 755 "$HERE/qwen-serve.sh" "$LLAMA_DIR/qwen-serve.sh"
if [ ! -f "$LLAMA_DIR/llamacpp-qwen.env" ]; then
  install -m 644 "$HERE/llamacpp-qwen.env.example" "$LLAMA_DIR/llamacpp-qwen.env"
fi

echo "[5/5] 安装系统级服务单元 ..."
install -m 644 "$HERE/llamacpp-qwen.service" /etc/systemd/system/llamacpp-qwen.service
install -m 644 "$HERE/llamacpp-bge.service" /etc/systemd/system/llamacpp-bge.service
systemctl daemon-reload

echo
echo "完成。服务默认不随开机自启，由 MIRIX 代理按需启动："
echo "  sudo systemctl start llamacpp-qwen llamacpp-bge"
echo "  sudo systemctl status llamacpp-qwen llamacpp-bge"
