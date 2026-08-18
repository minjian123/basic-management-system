"""远程关机开发服务器 mjbk。

用法:
    python shutdown_mjbk.py          # 交互确认后远程关机
    python shutdown_mjbk.py --yes    # 跳过确认直接关机

凭据从 deploy/.env 读取（MJBK_IP / MJBK_SSH_USER / MJBK_SUDO_PASSWORD），
SSH 连接走公钥免密，仅 sudo 密码来自 .env。
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / "deploy" / ".env"


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


def main() -> int:
    parser = argparse.ArgumentParser(description="远程关机开发服务器 mjbk")
    parser.add_argument("--yes", action="store_true", help="跳过确认直接关机")
    args = parser.parse_args()

    env = load_env(ENV_FILE)
    ip = env.get("MJBK_IP", "192.168.0.107")
    user = env.get("MJBK_SSH_USER", "minjian")
    pwd = env.get("MJBK_SUDO_PASSWORD", "")
    if not pwd:
        print(f"[失败] {ENV_FILE} 中未配置 MJBK_SUDO_PASSWORD。")
        return 1

    if not args.yes:
        answer = input(f"确认远程关机 {ip}（{user}）？(y/N) ").strip().lower()
        if answer not in ("y", "yes"):
            print("已取消。")
            return 0

    print(f"正在远程关机 {ip} ...")
    escaped = pwd.replace("'", "'\\''")
    cmd = ["ssh", "-o", "ConnectTimeout=5", f"{user}@{ip}",
           f"echo '{escaped}' | sudo -S shutdown -h now"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("关机指令已下发。")
        return 0
    if result.stderr.strip():
        print(result.stderr.strip())
    print("[失败] 关机指令执行失败。")
    return 1


if __name__ == "__main__":
    sys.exit(main())