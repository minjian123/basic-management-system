"""远程让开发服务器 mjbk 进入系统睡眠（S3 suspend）。

用法:
    python sleep_mjbk.py          # 交互确认后远程睡眠
    python sleep_mjbk.py --yes    # 跳过确认直接睡眠

与 wake_mjbk.py 配套：本脚本把 mjbk 睡下，之后可用 wake_mjbk.py（WOL）唤醒。
注意：睡眠期间 mjbk 上的服务（GitLab / MySQL / 数据库等）会暂停，恢复后自动继续。

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
    parser = argparse.ArgumentParser(description="远程让开发服务器 mjbk 进入系统睡眠（S3）")
    parser.add_argument("--yes", action="store_true", help="跳过确认直接睡眠")
    args = parser.parse_args()

    env = load_env(ENV_FILE)
    ip = env.get("MJBK_IP", "")
    user = env.get("MJBK_SSH_USER", "")
    pwd = env.get("MJBK_SUDO_PASSWORD", "")
    if not (ip and user):
        print(f"[失败] {ENV_FILE} 中未配置 MJBK_IP / MJBK_SSH_USER（键位见 .env.example）。")
        return 1
    if not pwd:
        print(f"[失败] {ENV_FILE} 中未配置 MJBK_SUDO_PASSWORD。")
        return 1

    if not args.yes:
        answer = input(f"确认让 {ip}（{user}）进入系统睡眠？(y/N) ").strip().lower()
        if answer not in ("y", "yes"):
            print("已取消。")
            return 0

    print(f"正在让 {ip} 进入系统睡眠 ...")
    escaped = pwd.replace("'", "'\\''")
    cmd = ["ssh", "-o", "ConnectTimeout=5", f"{user}@{ip}",
           f"echo '{escaped}' | sudo -S systemctl suspend"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("睡眠指令已下发，机器即将休眠（可随后用 wake_mjbk.py 唤醒）。")
        return 0
    if result.stderr.strip():
        print(result.stderr.strip())
    print("[失败] 远程睡眠指令执行失败。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
