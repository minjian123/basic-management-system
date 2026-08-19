"""远程唤醒开发服务器 mjbk（Wake-on-LAN）。

用法:
    python wake_mjbk.py                 # 默认参数唤醒并等待 SSH 就绪（IP 从 deploy/.env 的 MJBK_IP 读取）
    python wake_mjbk.py --timeout 60    # 自定义等待超时
    python wake_mjbk.py --host <mjbk-IP> --mac B0-25-AA-27-0C-32

服务器端已配置 /etc/systemd/system/wol.service 固化网卡 WOL 设置。
"""
import argparse
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / "deploy" / ".env"

DEFAULT_MAC = "B0-25-AA-27-0C-32"
DEFAULT_TIMEOUT = 120


def load_env(path: Path) -> dict:
    env = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return env
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def build_magic_packet(mac: str) -> bytes:
    mac_bytes = bytes(int(x, 16) for x in mac.replace("-", ":").split(":"))
    return b"\xff" * 6 + mac_bytes * 16


def send_wol(mac: str, host: str) -> None:
    packet = build_magic_packet(mac)
    for target in ("255.255.255.255", host):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(packet, (target, 9))


def wait_ssh_ready(host: str, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, 22), timeout=2):
                return True
        except OSError:
            time.sleep(1)
    return False


def main() -> int:
    env = load_env(ENV_FILE)
    default_host = env.get("MJBK_IP", "")
    default_mac = env.get("MJBK_WOL_MAC", DEFAULT_MAC)
    parser = argparse.ArgumentParser(description="远程唤醒开发服务器 mjbk（Wake-on-LAN）")
    parser.add_argument("--host", default=default_host, help="服务器 IP（默认取 deploy/.env 的 MJBK_IP）")
    parser.add_argument("--mac", default=default_mac, help=f"服务器网卡 MAC（默认 {default_mac}）")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"等待就绪超时秒数（默认 {DEFAULT_TIMEOUT}）")
    args = parser.parse_args()
    if not args.host:
        parser.error("未指定服务器 IP：请在 deploy/.env 中设置 MJBK_IP（见 .env.example）或使用 --host 参数")

    print(f"[1/2] 发送魔术包唤醒 {args.host}（{args.mac}）...")
    send_wol(args.mac, args.host)
    print(f"魔术包已发送，等待服务器启动（最多 {args.timeout} 秒）...")
    if wait_ssh_ready(args.host, args.timeout):
        print(f"[完成] 开发服务器已就绪，可以 SSH 连接 {args.host}。")
        return 0
    print("[失败] 等待超时，服务器未就绪。请检查：")
    print("    1. 服务器电源线与网线已连接、交换机端口正常")
    print("    2. 服务器 BIOS 中已开启 Wake-on-LAN（笔记本机型找 Power/LAN 相关选项）")
    return 1


if __name__ == "__main__":
    sys.exit(main())