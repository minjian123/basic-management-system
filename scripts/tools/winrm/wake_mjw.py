"""远程唤醒开发服务器 mjw（Wake-on-LAN，Windows/WinRM 通道）。

用法:
    python wake_mjw.py                 # 默认参数唤醒并等待 WinRM 就绪（IP/MAC 从 deploy/.env 读取）
    python wake_mjw.py --timeout 180   # 自定义等待超时

与 mjbk（SSH 22 端口）不同，mjw 走 WinRM，就绪判据为 5985 端口可连。
已实测（2026-09-06）：mjw 从 S3 睡眠与 S5 关机状态均可被魔术包唤醒。
依赖：仅 Python 标准库（UDP 发魔术包 + 轮询端口）。
"""
import argparse
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / "deploy" / ".env"

DEFAULT_MAC = "B0-25-AA-40-57-CC"
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


def wait_winrm_ready(host: str, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, 5985), timeout=2):
                return True
        except OSError:
            time.sleep(1)
    return False


def main() -> int:
    env = load_env(ENV_FILE)
    parser = argparse.ArgumentParser(description="远程唤醒开发服务器 mjw（Wake-on-LAN）")
    parser.add_argument("--host", default=env.get("MJW_IP", ""), help="服务器 IP（默认取 deploy/.env 的 MJW_IP）")
    parser.add_argument("--mac", default=env.get("MJW_WOL_MAC", DEFAULT_MAC), help="网卡 MAC（默认取 MJW_WOL_MAC）")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"等待 WinRM 就绪超时秒数（默认 {DEFAULT_TIMEOUT}）")
    args = parser.parse_args()
    if not args.host:
        parser.error("未指定服务器 IP：请在 deploy/.env 中设置 MJW_IP（见 .env.example）或使用 --host 参数")

    print(f"[1/2] 发送魔术包唤醒 {args.host}（{args.mac}）...")
    send_wol(args.mac, args.host)
    print(f"魔术包已发送，等待 WinRM 就绪（最多 {args.timeout} 秒）...")
    if wait_winrm_ready(args.host, args.timeout):
        print(f"[完成] 开发服务器已就绪，WinRM 端口 5985 可连。")
        return 0
    print("[失败] 等待超时，服务器未就绪。请检查：")
    print("    1. 服务器电源线、网线已连接，交换机端口正常")
    print("    2. mjw 是否处于睡眠/关机状态、BIOS 中 WOL 是否开启")
    return 1


if __name__ == "__main__":
    sys.exit(main())