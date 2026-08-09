#!/bin/bash
# mjbk Ubuntu 22.04 Server 一键部署脚本
# 用法：sudo bash install-all.sh
# 前置：Ubuntu 安装时勾选 OpenSSH，网络静态 192.168.0.107
set -e
export DEBIAN_FRONTEND=noninteractive
LOG=/root/bms-install.log
exec > >(tee -a $LOG) 2>&1

echo "=== [1/6] apt 清华源 ==="
sed -i 's|http://archive.ubuntu.com|https://mirrors.tuna.tsinghua.edu.cn|g; s|http://security.ubuntu.com|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list
apt-get update -qq

echo "=== [2/6] 基础工具与 Docker ==="
apt-get install -y -qq curl ca-certificates gnupg lsb-release git net-tools jq
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://docker.m.daocloud.io", "https://docker.1ms.run"],
  "storage-driver": "vfs"
}
EOF
systemctl enable docker
systemctl start docker

echo "=== [3/6] 部署目录与 .env ==="
mkdir -p /opt/bms/deploy/compose
cp -r compose/*.yml /opt/bms/deploy/compose/ 2>/dev/null || true
# .env 由管理员手动创建（含密码）

echo "=== [4/6] GitLab CE（清华 deb 直装） ==="
if [ ! -f /root/gitlab-ce.deb ]; then
  curl -sL -o /root/gitlab-ce.deb "https://mirrors.tuna.tsinghua.edu.cn/gitlab-ce/ubuntu/jammy/pool/main/g/gitlab-ce/gitlab-ce_19.2.1-ce.0_amd64.deb"
fi
apt-get install -y -qq postfix openssh-server
dpkg -i /root/gitlab-ce.deb
cat >> /etc/gitlab/gitlab.rb <<'EOF'
external_url 'http://192.168.0.107:8080'
nginx['listen_port'] = 8080
gitlab_rails['gitlab_shell_ssh_port'] = 2222
puma['worker_processes'] = 2
puma['max_threads'] = 4
sidekiq['max_concurrency'] = 5
postgresql['shared_buffers'] = "256MB"
prometheus_monitoring['enable'] = false
grafana['enable'] = false
alertmanager['enable'] = false
node_exporter['enable'] = false
EOF
gitlab-ctl reconfigure

echo "=== [5/6] 时区与主机名 ==="
timedatectl set-timezone Asia/Shanghai
hostnamectl set-hostname mjbk

echo "=== [6/6] 防火墙 ==="
ufw allow OpenSSH
ufw allow 8080/tcp
ufw allow 2222/tcp
ufw allow 3306/tcp
ufw allow 5432/tcp
ufw allow 6379/tcp
ufw allow 9000,9001/tcp
ufw allow 9876,10911,10909/tcp
ufw allow 9200,9300/tcp
ufw allow 5050/tcp
ufw --force enable

echo "=== 完成 ==="
echo "部署日志：$LOG"
echo "下一步：创建 /opt/bms/deploy/.env 后执行 docker compose 启动服务"
