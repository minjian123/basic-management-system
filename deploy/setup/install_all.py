#!/usr/bin/env python3
"""mjbk Ubuntu 22.04 Server 一键部署（Python 单一实现）。

用法（在服务器上以 root 执行；同名 `install-all.sh` 为转调本文件的 bash 瘦包装）：
    sudo bash install-all.sh
    sudo python3 deploy/setup/install_all.py
前置：Ubuntu 安装时勾选 OpenSSH，网络静态 IP（IP 与账号见《本地资源》）；执行前 export MJBK_IP=服务器IP
      —— 未设置 MJBK_IP 即报错退出 1（原 `: "${MJBK_IP:?未设置 MJBK_IP：...}"` 语义）。
日志：终端与 /root/bms-install.log 同时得到全部输出（原 `exec > >(tee -a $LOG) 2>&1` 的 tee -a 语义；
      本文件以管道 + 系统 tee 进程实现，故子进程（apt/dpkg/gitlab-ctl 等）输出同样入日志）。

分步流程（[N/7] 步骤名与原 shell 实现逐字一致；失败即停，退出码同失败命令）：
    [1/7] apt 清华源（archive/security → mirrors.tuna.tsinghua.edu.cn）→ apt-get update
    [2/7] 基础工具与 Docker（清华 docker-ce 源；daemon.json 用 daocloud / 1ms 镜像加速 + vfs 存储驱动）
    [3/7] RocketMQ 数据目录（bind mount，属主 3000:3000）
    [4/7] 部署目录 /opt/bms/deploy/compose 与 compose *.yml 拷贝（.env 由管理员手动创建）
    [5/7] GitLab CE（清华 deb 直装；追加 /etc/gitlab/gitlab.rb 后 gitlab-ctl reconfigure）
    [6/7] 时区 Asia/Shanghai 与主机名 mjbk
    [7/7] ufw 放行（OpenSSH / GitLab / 三库 / 中间件端口）并 --force enable
"""

import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

PREFIX = "[install-all]"
LOG_PATH = Path("/root/bms-install.log")
# 本文件位于 <仓库根>/deploy/setup/ 下（compose 源目录按此解析，不依赖调用者 cwd）
DEPLOY_DIR = Path(__file__).resolve().parent.parent

DOCKER_GPG_URL = "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu/gpg"
DOCKER_LIST_LINE = (
    "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] "
    "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu {codename} stable\n"
)
GITLAB_DEB_URL = (
    "https://mirrors.tuna.tsinghua.edu.cn/gitlab-ce/ubuntu/jammy/pool/main/g/gitlab-ce/gitlab-ce_19.2.1-ce.0_amd64.deb"
)
DOCKER_DAEMON_JSON = """{
  "registry-mirrors": ["https://docker.m.daocloud.io", "https://docker.1ms.run"],
  "storage-driver": "vfs"
}
"""
# 原实现为**带引号的 heredoc**（`cat >> /etc/gitlab/gitlab.rb <<'EOF'`），`${MJBK_IP}` 按字面写入
# 不做展开——为保持行为等价，本次照字面保留（GitLab 实际部署走 deploy/compose/gitlab.yml，其
# `${MJBK_IP:?}` 由 compose 注入）；如需在 gitlab.rb 落实际 IP，属行为变更，另行拍板。
GITLAB_RB_BLOCK = """external_url "http://${MJBK_IP}:8080"
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
"""
UFW_ALLOW = (
    "OpenSSH",
    "8080/tcp",
    "2222/tcp",
    "3306/tcp",
    "5432/tcp",
    "6379/tcp",
    "9000,9001/tcp",
    "9876,10911,10909/tcp",
    "9200,9300/tcp",
    "5050/tcp",
    "8090/tcp",
)


class StepFailed(Exception):
    """单步失败：对齐 shell `set -e`（退出码取失败命令的退出码）。"""

    def __init__(self, message, exit_code=1):
        super().__init__(message)
        self.exit_code = exit_code


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def say(message):
    """一步一行的进度输出（即时 flush，与子进程输出保持先后次序）。"""
    print(message, flush=True)


def run(*cmd, capture=False):
    """执行外部命令；失败即抛 StepFailed（`set -e` 语义，退出码透传）。

    capture=True 时取 stdout 并去掉尾部换行（等价 shell 的 `$(...)`），否则输出直通终端。
    """
    kwargs = {"check": True}
    if capture:
        kwargs.update(stdout=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        result = subprocess.run(list(cmd), **kwargs)
    except FileNotFoundError:
        raise StepFailed(f"命令不存在：{cmd[0]}", 127) from None
    except subprocess.CalledProcessError as exc:
        failed = " ".join(str(x) for x in exc.cmd)
        raise StepFailed(f"命令失败（退出码 {exc.returncode}）：{failed}", exc.returncode) from None
    return result.stdout.strip() if capture else None


def start_tee(log_path):
    """接管 stdout/stderr：等价原 `exec > >(tee -a $LOG) 2>&1`。

    tee 的 stdout 接当前终端（须在 dup2 之前启动）；父进程 fd 1/2 改接管道，此后本进程与
    其子进程的输出全部经 tee 双写到终端与日志文件。tee 随本进程退出（管道 EOF）自然收敛。
    """
    tee = shutil.which("tee")
    if not tee:
        raise StepFailed("未找到 tee 命令（应由 coreutils 自带），无法同时写日志与终端", 127)
    read_fd, write_fd = os.pipe()
    try:
        subprocess.Popen([tee, "-a", str(log_path)], stdin=read_fd)
    finally:
        os.close(read_fd)
    os.dup2(write_fd, 1)
    os.dup2(write_fd, 2)
    os.close(write_fd)


def replace_apt_sources():
    """apt 换清华源（archive/security 两处，全量替换；文件不存在即失败退出，同原 sed -i）。

    surrogateescape 口径 = 原 sed 的逐字节替换：非 UTF-8 字节原样保留，不会被解码失败卡住。
    """
    sources = Path("/etc/apt/sources.list")
    text = sources.read_text(encoding="utf-8", errors="surrogateescape")
    text = text.replace("http://archive.ubuntu.com", "https://mirrors.tuna.tsinghua.edu.cn")
    text = text.replace("http://security.ubuntu.com", "https://mirrors.tuna.tsinghua.edu.cn")
    sources.write_text(text, encoding="utf-8", errors="surrogateescape")


def install_docker():
    """基础工具 + Docker Engine（清华 docker-ce 源），并写 daemon.json 后启动。"""
    run("apt-get", "install", "-y", "-qq", "curl", "ca-certificates", "gnupg", "lsb-release", "git", "net-tools", "jq")

    keyrings = Path("/etc/apt/keyrings")
    if not keyrings.is_dir():  # 原 `install -m 0755 -d`：新建目录 0755，不受 umask 影响
        keyrings.mkdir(parents=True, mode=0o755)
        os.chmod(keyrings, 0o755)
    gpg_asc = keyrings / "docker.asc"
    run("curl", "-fsSL", DOCKER_GPG_URL, "-o", str(gpg_asc))
    os.chmod(gpg_asc, os.stat(gpg_asc).st_mode | 0o444)  # 原 `chmod a+r`

    codename = run("lsb_release", "-cs", capture=True)  # 原 `$(lsb_release -cs)`
    Path("/etc/apt/sources.list.d/docker.list").write_text(DOCKER_LIST_LINE.format(codename=codename), encoding="utf-8")
    run("apt-get", "update", "-qq")
    run(
        "apt-get",
        "install",
        "-y",
        "-qq",
        "docker-ce",
        "docker-ce-cli",
        "containerd.io",
        "docker-buildx-plugin",
        "docker-compose-plugin",
    )

    Path("/etc/docker").mkdir(parents=True, exist_ok=True)
    Path("/etc/docker/daemon.json").write_text(DOCKER_DAEMON_JSON, encoding="utf-8")
    run("systemctl", "enable", "docker")
    run("systemctl", "start", "docker")


def prepare_rocketmq_dirs():
    """RocketMQ 数据目录（bind mount，属主 3000:3000）。

    apache/rocketmq 镜像以 uid 3000(rocketmq) 运行且不含 /home/rocketmq/{logs,store}；
    若用命名卷会被 Docker 建成 root:root，broker 写不了日志会启动即退出并无限重启，
    故预建宿主机目录并授权给 3000（与 deploy/compose/base.yml 的 bind mount 对应）。
    """
    for path in (
        "/mnt/ssd2t/rocketmq/broker/store",
        "/mnt/ssd2t/rocketmq/broker/logs",
        "/mnt/ssd2t/rocketmq/nameserver/logs",
    ):
        Path(path).mkdir(parents=True, exist_ok=True)
    run("chown", "-R", "3000:3000", "/mnt/ssd2t/rocketmq")


def copy_compose_files():
    """部署目录与 compose 文件（原 `cp -r compose/*.yml <目标>/ 2>/dev/null || true`：best-effort、静默失败）。

    源目录以本文件位置解析为 `<仓库根>/deploy/compose`（原实现相对调用者 cwd 的 `compose/`）。
    """
    target = Path("/opt/bms/deploy/compose")
    target.mkdir(parents=True, exist_ok=True)
    for yml in sorted((DEPLOY_DIR / "compose").glob("*.yml")):
        # 与 `2>/dev/null || true` 一致：拷贝失败静默忽略，不中断部署
        with contextlib.suppress(OSError):
            shutil.copy2(yml, target / yml.name)
    # .env 由管理员手动创建（含密码）


def install_gitlab():
    """GitLab CE（清华 deb 直装 + gitlab.rb 追加 + reconfigure）。"""
    deb = Path("/root/gitlab-ce.deb")
    if not deb.is_file():
        run("curl", "-sL", "-o", str(deb), GITLAB_DEB_URL)
    run("apt-get", "install", "-y", "-qq", "postfix", "openssh-server")
    run("dpkg", "-i", str(deb))
    with open("/etc/gitlab/gitlab.rb", "a", encoding="utf-8") as config:
        config.write(GITLAB_RB_BLOCK)  # 追加（原 `cat >>`，同名键后写者生效）
    run("gitlab-ctl", "reconfigure")


def configure_time_and_hostname():
    """时区与主机名（部署口径：Asia/Shanghai + mjbk）。"""
    run("timedatectl", "set-timezone", "Asia/Shanghai")
    run("hostnamectl", "set-hostname", "mjbk")


def configure_firewall():
    """ufw 放行 gitlab / 三库 / 中间件端口并启用。"""
    for rule in UFW_ALLOW:
        run("ufw", "allow", rule)
    run("ufw", "--force", "enable")


def deploy():
    """分步流程主体（与原 shell 的 [N/7] 顺序、措辞一致）。"""
    say("=== [1/7] apt 清华源 ===")
    replace_apt_sources()
    run("apt-get", "update", "-qq")

    say("=== [2/7] 基础工具与 Docker ===")
    install_docker()

    say("=== [3/7] RocketMQ 数据目录（bind mount，属主 3000:3000）===")
    prepare_rocketmq_dirs()

    say("=== [4/7] 部署目录与 .env ===")
    copy_compose_files()

    say("=== [5/7] GitLab CE（清华 deb 直装） ===")
    install_gitlab()

    say("=== [6/7] 时区与主机名 ===")
    configure_time_and_hostname()

    say("=== [7/7] 防火墙 ===")
    configure_firewall()

    say("=== 完成 ===")
    say(f"部署日志：{LOG_PATH}")
    say("下一步：创建 /opt/bms/deploy/.env 后执行 docker compose 启动服务")


def main(argv=None):
    configure_stdio()
    if not os.environ.get("MJBK_IP", ""):
        # 原 `: "${MJBK_IP:?未设置 MJBK_IP：...}"`：报错退出 1；此时尚未接管输出，故只进终端、不入日志
        sys.stderr.write("未设置 MJBK_IP：请先 export MJBK_IP=服务器IP（取值见《本地资源》）\n")
        return 1

    os.environ["DEBIAN_FRONTEND"] = "noninteractive"  # 原 export，供 apt / dpkg 子进程继承
    try:
        start_tee(LOG_PATH)
        deploy()
    except StepFailed as exc:
        sys.stderr.write(f"{PREFIX} 失败：{exc}\n")
        return exc.exit_code
    except OSError as exc:
        sys.stderr.write(f"{PREFIX} 失败：{exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
