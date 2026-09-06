"""远程关机开发服务器 mjw（S5，Windows/WinRM 通道）。

用法:
    ~/tools/winrm-venv/bin/python shutdown_mjw.py          # 交互确认后关机
    ~/tools/winrm-venv/bin/python shutdown_mjw.py --yes    # 跳过确认直接关机

关机命令：shutdown /s /t 0（优雅关闭，等待应用退出）。关机后再用 wake_mjw.py（WOL）开机。
依赖 pywinrm（开发机 venv：~/tools/winrm-venv）；凭据从 deploy/.env 读取 MJW_*。
"""
import argparse
import sys
from pathlib import Path

try:
    import winrm
except ImportError:
    print("需要 pywinrm：请用 venv Python 运行（~/tools/winrm-venv/bin/python shutdown_mjw.py），")
    print("或用 pip 安装：pip install pywinrm。")
    sys.exit(2)

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
    parser = argparse.ArgumentParser(description="远程关机开发服务器 mjw")
    parser.add_argument("--yes", action="store_true", help="跳过确认直接关机（供脚本化调用，人工操作不建议）")
    args = parser.parse_args()

    env = load_env(ENV_FILE)
    ip = env.get("MJW_IP", "")
    user = env.get("MJW_WINRM_USER", "")
    pwd = env.get("MJW_WINRM_PASSWORD", "")
    if not (ip and user and pwd):
        print(f"[失败] {ENV_FILE} 中未配置 MJW_IP / MJW_WINRM_USER / MJW_WINRM_PASSWORD（键位见 .env.example）。")
        return 1

    if not args.yes:
        answer = input(f"确认远程关机 {ip}（{user}）？(y/N) ").strip().lower()
        if answer not in ("y", "yes"):
            print("已取消。")
            return 0

    print(f"正在远程关机 {ip} ...")
    s = winrm.Session(ip, auth=(user, pwd), transport="ntlm")
    try:
        r = s.run_cmd("shutdown /s /t 0")
        if r.status_code != 0:
            print("[失败] 关机指令返回非 0。")
            return 1
    except Exception as e:
        # 关机瞬间 WinRM 连接被打断属正常，此时视为已下发
        print(f"（连接随关机中断：{type(e).__name__}）")
    print("关机指令已下发。需要开机时用 wake_mjw.py 唤醒。")
    return 0


if __name__ == "__main__":
    sys.exit(main())