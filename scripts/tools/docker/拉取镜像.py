#!/usr/bin/env python3
"""BMS 批量镜像拉取（断点续传 + 失败自动重试直到完成）—— Python 单一实现（Linux / Windows 通用）

背景（2026-09-23 实测补记，详见《DockerEngine 部署使用说明》2.6 节）：
本机 Docker 用 containerd 镜像存储，blob 层按 HTTP Range 断点续传、已完成层落缓存；
大镜像（几百 MB）在加速器限速下常中途断开，**重复 docker pull 即可续传累积**，不会重下已完成层。
本脚本把「逐个拉 + 中断重试 + 已就位跳过」固化为一条命令，避免手工反复试源。

用法：
  scripts/tools/docker/拉取镜像.sh [选项] [镜像...]      # Linux 入口（转调本文件）
  scripts/tools/docker/拉取镜像.bat [选项] [镜像...]     # Windows 入口（转调本文件）
  python3 scripts/tools/docker/拉取镜像.py [选项] [镜像...]
  scripts/tools/docker/拉取镜像.sh                       # 读脚本同目录 镜像清单.txt
  scripts/tools/docker/拉取镜像.sh --host user@ip        # 在远程 Docker 主机执行（默认读 MJBK_SSH_USER@MJBK_IP）
  scripts/tools/docker/拉取镜像.sh nginx:1.27 redis:8    # 直接给镜像
  scripts/tools/docker/拉取镜像.sh --file 我的清单.txt

选项：
  --host <user@ip>   远程 Docker 主机（缺省：环境变量 MJBK_SSH_USER / MJBK_IP，其次 deploy/.env 同名键，再缺省本机）
  --file <路径>      镜像清单文件（每行一个；# 注释、空行忽略）
  --retries <N>      单个镜像最大重试次数（0 = 不限，默认 0，直到成功）
  --interval <秒>    失败重试间隔（默认 5）
  --attempt-timeout <秒>  单次 docker pull 超时（默认 300；0 = 不限）——防“卡住不退出”导致重试不触发
  --reset            先删除目标镜像再拉（默认跳过已就位镜像）
  -h, --help         帮助

注意：
  - 不要并发跑多个本脚本拉同一镜像（内容锁争用会假死）；脚本内部已按序逐个拉。
  - 不要用 `docker system prune -a`，会清掉续传缓存。

实现口径（2026-10-16 起 Python 单一实现，同级 .sh / .bat 均为转调本文件的薄包装）：
  - 远端模式对目标主机逐条执行 `ssh <host> docker pull …` / `ssh <host> docker image inspect …`
    （原实现为一条 ssh 流式执行 shell 脚本，语义不变，仅多几次连接开销）。
  - 单次超时：远端仍用远端 `timeout` 命令（由目标机中断本次 pull），本机模式用 Python 侧超时实现
    （Windows 无 coreutils timeout）；两条路径的超时统一按退出码 124 口径处理，触发续传重试。
  - `--reset`：先 `docker rmi` 尽力删除本地同名镜像（删除失败如在用则不中断），随后照常拉取，打印一行 [重置]。
  - 选项数值按非负整数校验；用法错误（缺参 / 未知选项 / 清单缺失 / 无镜像）退出码 2（原 shell 版缺参经 ${2:?} 为 1）。
"""

import contextlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LIST_FILE = SCRIPT_DIR / "镜像清单.txt"
ENV_FILE = SCRIPT_DIR.parents[2] / "deploy" / ".env"  # 仓库根 deploy/.env：缺省远程主机键位

TIMEOUT_RC = 124  # 与原脚本 `timeout` 命令一致的超时退出码
WHITESPACE = re.compile(r"\s+")


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def usage():
    """打印本文件头部注释（等价原脚本 usage：输出文件头的注释块）。"""
    text = (__doc__ or "").strip()
    if text:
        print(text)


class UsageError(Exception):
    """用法错误（缺参 / 取值非法）——调用方按退出码 2 处理。"""


def parse_positive_int(name, text):
    """非负整数取值（原 shell 版对非法数值行为未定义，此处显式报用法错误）。"""
    try:
        value = int(text)
    except ValueError:
        value = -1
    if value < 0:
        raise UsageError(f"{name} 需要非负整数：{text}")
    return value


def parse_args(argv):
    """解析命令行（与原脚本 case 分支等价：`--` 之后一律按镜像名、未知选项报用法错误）。"""
    opts = {"host": "", "file": "", "retries": 0, "interval": 5, "attempt_timeout": 300, "reset": False}
    images = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("--host", "--file", "--retries", "--interval", "--attempt-timeout"):
            # 等价原脚本 ${2:?...}：后无参数或取值为空串均视为缺参
            if index + 1 >= len(argv) or argv[index + 1] == "":
                raise UsageError(f"{arg} 需要值")
            value = argv[index + 1]
            if arg == "--host":
                opts["host"] = value
            elif arg == "--file":
                opts["file"] = value
            elif arg == "--retries":
                opts["retries"] = parse_positive_int(arg, value)
            elif arg == "--interval":
                opts["interval"] = parse_positive_int(arg, value)
            else:
                opts["attempt_timeout"] = parse_positive_int(arg, value)
            index += 2
        elif arg == "--reset":
            opts["reset"] = True
            index += 1
        elif arg in ("-h", "--help"):
            usage()
            raise SystemExit(0)
        elif arg == "--":
            images.extend(argv[index + 1 :])
            break
        elif arg.startswith("-"):
            sys.stderr.write(f"未知选项：{arg}\n")
            usage()
            raise SystemExit(2)
        else:
            images.append(arg)
            index += 1
    return opts, images


def read_image_list(path):
    """读镜像清单：每行 `#` 起为注释、行内空白全去除、空行忽略（与原脚本口径一致）。"""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    images = []
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        line = WHITESPACE.sub("", line)
        if line:
            images.append(line)
    return images


def read_env_file(path):
    """解析 .env 风格键值对（# 注释、空行忽略；值去两侧引号；读不到返回空表）。"""
    values = {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_host():
    """缺省远程主机：环境变量 MJBK_SSH_USER / MJBK_IP 优先，其次 deploy/.env 同名键（缺任一 → 本机）。"""
    env_values = read_env_file(ENV_FILE)
    user = os.environ.get("MJBK_SSH_USER", "").strip() or env_values.get("MJBK_SSH_USER", "")
    ip = os.environ.get("MJBK_IP", "").strip() or env_values.get("MJBK_IP", "")
    return f"{user}@{ip}" if user and ip else ""


def docker_cmd(host, args):
    """组装 docker 命令：远端经 ssh 逐条执行（与原脚本同一 ConnectTimeout 口径），本机直连。"""
    if host:
        return ["ssh", "-o", "ConnectTimeout=8", host, *args]
    return list(args)


def run_command(cmd, quiet=False, timeout=None):
    """执行外部命令，返回退出码（stdin 置空，避免 ssh / docker 抢占脚本输入）。"""
    kwargs = {"stdin": subprocess.DEVNULL, "timeout": timeout}
    if quiet:
        # 等价原脚本 `>/dev/null 2>&1`
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    try:
        return subprocess.run(cmd, **kwargs).returncode
    except subprocess.TimeoutExpired:
        return TIMEOUT_RC
    except FileNotFoundError as exc:
        # Windows 下 subprocess 抛出的 FileNotFoundError 不带 filename，此处补齐命令名供上层报错
        raise FileNotFoundError(exc.errno, exc.strerror, cmd[0]) from None


def image_present(host, image):
    """已就位判定（原脚本 `docker image inspect … >/dev/null 2>&1` 判退出码口径）。"""
    return run_command(docker_cmd(host, ["docker", "image", "inspect", image]), quiet=True) == 0


def remove_image(host, image):
    """--reset 第一步：尽力删除本地同名镜像（失败如在用则不中断，随后照常拉取覆盖）。"""
    run_command(docker_cmd(host, ["docker", "rmi", image]), quiet=True)


def docker_pull(host, image, attempt_timeout):
    """执行一次 docker pull，返回退出码（进度直通控制台）；超时按 124 口径返回。"""
    if host:
        # 远端保持远端 `timeout` 命令：由目标机中断本次 pull，退出码 124 原样回传
        args = ["docker", "pull", image]
        if attempt_timeout > 0:
            args = ["timeout", str(attempt_timeout), *args]
        return run_command(docker_cmd(host, args))
    if attempt_timeout > 0:
        # 本机模式：Python 侧超时（Windows 无 coreutils timeout），超时杀掉 docker 客户端即中断本次拉取
        return run_command(["docker", "pull", image], timeout=attempt_timeout)
    return run_command(["docker", "pull", image])


def pull_image(image, host, opts):
    """拉取单个镜像（已就位跳过 / 中断重试）；返回 True=成功，False=达上限仍失败。"""
    if not opts["reset"] and image_present(host, image):
        print(f"[跳过] {image}（已就位）")
        return True
    if opts["reset"]:
        print(f"[重置] {image}（先删除本地同名镜像，再重新拉取）")
        remove_image(host, image)

    attempt = 0
    while True:
        attempt += 1
        print(f"[拉取] {image}（第 {attempt} 次）")
        rc = docker_pull(host, image, opts["attempt_timeout"])
        if rc == 0:
            print(f"[完成] {image}")
            return True
        if rc == TIMEOUT_RC:
            print(f"[超时] {image} 单次超过 {opts['attempt_timeout']}s，将续传重试（已完成层复用）")
        if opts["retries"] > 0 and attempt >= opts["retries"]:
            print(f"[失败] {image}（已达最大重试 {opts['retries']} 次）")
            return False
        print(f"[续传] {image} 中断，{opts['interval']}s 后重试（已完成层会复用）...")
        time.sleep(opts["interval"])


def main(argv):
    try:
        opts, images = parse_args(argv)
    except UsageError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    # 缺省清单文件：无 --file 且未直接给镜像时，读脚本同目录 镜像清单.txt
    list_file = opts["file"]
    if not list_file and not images:
        list_file = str(DEFAULT_LIST_FILE)
    if list_file:
        if not os.path.isfile(list_file):
            sys.stderr.write(f"清单文件不存在：{list_file}\n")
            return 2
        images.extend(read_image_list(list_file))

    if not images:
        sys.stderr.write("未提供镜像，且清单为空。用 --file 或直接给镜像名。\n")
        return 2

    host = opts["host"] or resolve_host()
    print(
        f"目标主机：{host or '本机'}；镜像数：{len(images)}；"
        f"重试上限：{opts['retries']}（0=不限）；间隔：{opts['interval']}s；单次超时：{opts['attempt_timeout']}s"
    )

    failed = False
    try:
        for image in images:
            if not pull_image(image, host, opts):
                failed = True
    except FileNotFoundError as exc:
        sys.stderr.write(f"未找到命令：{exc.filename}（远程模式需 ssh 客户端，本机模式需 docker CLI）\n")
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    configure_stdio()
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
