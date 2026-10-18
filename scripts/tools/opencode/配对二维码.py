"""生成 opencode Web 配对链接与二维码（手机扫码直连浏览器打开 Web UI）。

用法:
    python 配对二维码.py                             # 自动探测局域网 IP 与服务端口，出 PNG 二维码
    python 配对二维码.py --host 192.168.0.124 --port 45278
    python 配对二维码.py --out D:/tmp/qr.png --open   # 指定输出路径并立即用系统图片查看器打开
    python 配对二维码.py --ascii                     # 同时在终端打印字符二维码（不依赖看图）
    python 配对二维码.py --print-only                # 只打印配对链接，不出图

口径:
    - 链接由 `opencode pair --url <局域网地址>` 生成，**一次性、5 分钟内有效**，用一次即失效，过期重跑本脚本；
    - 手机与电脑须在同一局域网，且共享后台服务已监听 `0.0.0.0`
      （`opencode service set hostname 0.0.0.0`，重启桌面端生效；Windows 侧还须放行防火墙端口）；
    - 手机侧**无需安装 OpenCode App**：用系统相机 / 浏览器扫码即可打开 Web UI 登录
      （会话 30 天）；登录后把 `http://<host>:<port>` 存为书签，之后无需再扫码。
    详见《opencode部署使用说明》「Web 与手机访问」节。

依赖:
    segno（纯 Python 二维码库，无编译依赖，见同目录 requirements.txt）:
        pip install segno -i https://pypi.tuna.tsinghua.edu.cn/simple
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

# bms_core 源码根：脚本在仓库内运行，集合声明统一落插入序集合类（ConcurrentStable*）。
_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
LINK_RE = re.compile(r"https?://\S+/auth/connect/\S+")
STATUS_RE = re.compile(r"https?://([^:/\s]+):(\d+)")

# 共享后台服务默认端口：Windows 侧 45278（低于系统保留段 49152+），其余平台 49374
DEFAULT_PORT_WINDOWS = 45278
DEFAULT_PORT_OTHER = 49374
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def log(message: str) -> None:
    print(f"[配对二维码] {message}")


def opencode_exe() -> str:
    """定位 opencode CLI：PATH 优先，其次官方 curl 安装落点。"""
    found = shutil.which("opencode")
    if found:
        return found
    name = "opencode.exe" if os.name == "nt" else "opencode"
    candidate = Path.home() / ".opencode" / "bin" / name
    if candidate.exists():
        return str(candidate)
    log("未找到 opencode 命令：请确认已安装并登记 PATH（新开终端后再试）。")
    sys.exit(2)


def run(cmd: ConcurrentStableList[str]) -> str:
    """执行命令并返回去掉 ANSI 色码的标准输出。"""
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        log(f"命令失败（退出码 {proc.returncode}）：{' '.join(cmd)}")
        if (proc.stderr or "").strip():
            log(proc.stderr.strip())
        sys.exit(3)
    return ANSI_RE.sub("", proc.stdout or "")


def service_status() -> tuple[str, int] | None:
    """读 `opencode service status`（形如 `http://0.0.0.0:45278`）→ (监听地址, 端口)。"""
    proc = subprocess.run(
        [opencode_exe(), "service", "status"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    match = STATUS_RE.search(ANSI_RE.sub("", proc.stdout or ""))
    if not match:
        return None
    return match.group(1), int(match.group(2))


def lan_ip() -> str:
    """探测本机默认路由出口 IP（只建 socket 不实际发包）；失败退回主机名解析。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def default_port() -> int:
    return DEFAULT_PORT_WINDOWS if os.name == "nt" else DEFAULT_PORT_OTHER


def segno_module():
    """加载 segno；缺失时给出安装命令并退出。"""
    try:
        import segno
    except ImportError:
        log("缺少依赖 segno（纯 Python 二维码库）：")
        log("  pip install segno -i https://pypi.tuna.tsinghua.edu.cn/simple")
        log("（只想拿链接：加 --print-only；只想看终端字符码：装好后再加 --ascii）")
        sys.exit(4)
    return segno


def pair_link(base_url: str) -> str:
    """调用 `opencode pair --url` 取一次性配对链接。"""
    text = run(ConcurrentStableList([opencode_exe(), "pair", "--url", base_url]))
    match = LINK_RE.search(text)
    if not match:
        log("未从 `opencode pair` 输出中解析到配对链接，原文如下：")
        print(text.strip())
        sys.exit(3)
    return match.group(0)


def open_file(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 opencode Web 配对链接与二维码（手机扫码直连浏览器，无需装 App）")
    parser.add_argument("--host", help="局域网地址主机（默认自动探测本机局域网 IP）")
    parser.add_argument(
        "--port",
        type=int,
        help=f"服务端口（默认取服务状态，取不到时用平台默认 {DEFAULT_PORT_WINDOWS} / {DEFAULT_PORT_OTHER}）",
    )
    parser.add_argument("--out", help="二维码 PNG 输出路径（默认 <临时目录>/opencode/pair-qr.png）")
    parser.add_argument("--scale", type=int, default=8, help="每个二维码模块的像素数（默认 8）")
    parser.add_argument("--border", type=int, default=4, help="静默区模块数（默认 4，建议不小于 4）")
    parser.add_argument("--ascii", action="store_true", help="同时在终端打印字符二维码")
    parser.add_argument("--print-only", action="store_true", help="只打印配对链接，不生成图片")
    parser.add_argument("--open", action="store_true", help="生成后用系统图片查看器打开")
    parser.add_argument("--force", action="store_true", help="服务只监听回环时也强行出码（手机大概率连不上）")
    args = parser.parse_args()

    status = service_status()
    if status is None:
        log("读不到共享服务状态（`opencode service status` 无输出）——桌面端是否在运行？服务随桌面端启停。")
        if not args.force:
            return 2
        bind_host, detected_port = None, None
    else:
        bind_host, detected_port = status

    host = args.host or lan_ip()
    port = args.port or detected_port or default_port()

    if bind_host in LOOPBACK_HOSTS and args.host is None and not args.force:
        log(f"共享服务当前只监听 {bind_host}:{port}（仅本机可达），手机连不上。")
        log("先改监听并重启桌面端：opencode service set hostname 0.0.0.0")
        log(
            "Windows 侧还须放行防火墙端口（见《opencode部署使用说明》「Web 与手机访问」节）；确认要强行出码加 --force。"
        )
        return 2

    base_url = f"http://{host}:{port}"
    link = pair_link(base_url)

    log(f"局域网地址：{base_url}（登录后可存书签，会话 30 天）")
    log("配对链接（一次性、5 分钟内有效）：")
    print(f"  {link}")
    log("手机无需装 App：用系统相机 / 浏览器扫码，或把上面的链接粘进浏览器即可登录 Web UI。")

    if args.print_only:
        return 0

    segno = segno_module()
    qr = segno.make(link, error="m", boost_error=True)
    if args.ascii:
        print(qr.terminal(compact=True), flush=True)

    out = Path(args.out).expanduser() if args.out else Path(tempfile.gettempdir()) / "opencode" / "pair-qr.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    qr.save(str(out), scale=args.scale, border=args.border)
    log(f"二维码图片：{out}")

    if args.open:
        open_file(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
