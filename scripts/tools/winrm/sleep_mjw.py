"""远程让开发服务器 mjw 进入系统睡眠（S3，Windows/WinRM 通道）。

用法:
    ~/tools/winrm-venv/bin/python sleep_mjw.py          # 交互确认后睡眠
    ~/tools/winrm-venv/bin/python sleep_mjw.py --yes    # 跳过确认直接睡眠

与 wake_mjw.py 配套：本脚本把 mjw 睡下，之后可用 wake_mjw.py（WOL）唤醒。
睡眠命令：rundll32.exe powrprof.dll,SetSuspendState 0,0,0（S3 待机）。
依赖 pywinrm（开发机 venv：~/tools/winrm-venv）；凭据从 deploy/.env 读取 MJW_*。
"""
import argparse
import sys
from pathlib import Path

try:
    import winrm
except ImportError:
    print("需要 pywinrm：请用 venv Python 运行（~/tools/winrm-venv/bin/python sleep_mjw.py），")
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
    parser = argparse.ArgumentParser(description="远程让开发服务器 mjw 进入系统睡眠（S3）")
    parser.add_argument("--yes", action="store_true", help="跳过确认直接睡眠")
    args = parser.parse_args()

    env = load_env(ENV_FILE)
    ip = env.get("MJW_IP", "")
    user = env.get("MJW_WINRM_USER", "")
    pwd = env.get("MJW_WINRM_PASSWORD", "")
    if not (ip and user and pwd):
        print(f"[失败] {ENV_FILE} 中未配置 MJW_IP / MJW_WINRM_USER / MJW_WINRM_PASSWORD（键位见 .env.example）。")
        return 1

    if not args.yes:
        answer = input(f"确认让 {ip}（{user}）进入系统睡眠？(y/N) ").strip().lower()
        if answer not in ("y", "yes"):
            print("已取消。")
            return 0

    print(f"正在让 {ip} 进入系统睡眠 ...")
    s = winrm.Session(ip, auth=(user, pwd), transport="ntlm")
    try:
        r = s.run_cmd("rundll32.exe powrprof.dll,SetSuspendState 0,0,0")
        if r.status_code != 0:
            print("[失败] 远程睡眠指令返回非 0。")
            return 1
    except Exception as e:
        # 睡眠触发瞬间 WinRM 连接被打断属正常，此时视为已下发
        print(f"（连接随睡眠中断：{type(e).__name__}）")
    print("睡眠指令已下发，机器即将休眠（可随后用 wake_mjw.py 唤醒）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())