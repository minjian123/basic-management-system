"""远程在开发服务器 mjw 上以 PowerShell 7（pwsh7）执行脚本（Windows/WinRM 通道）。

用法:
    ~/tools/winrm-venv/bin/python pwsh_mjw.py 'Get-Service spooler | Select Status,Name | ConvertTo-Json'
    ~/tools/winrm-venv/bin/python pwsh_mjw.py --file script.ps1
    ~/tools/winrm-venv/bin/python pwsh_mjw.py -c '...' --timeout 300   # 长任务加大超时

背景: mjw 的 Windows PowerShell 5.1 语法/输出受限（2026-09-10 起 mjw 已装 PowerShell 7.6.6）。
本工具把脚本以 UTF-16(BOM) 落盘到 mjw 后调用 pwsh7 -File 执行，返回其 stdout/退出码——
远程执行的语法与能力等价 pwsh7 本机。传输仍为 WinRM（非交互会话，GUI 投递限制不变）。
依赖 pywinrm（开发机 venv：~/tools/winrm-venv）；凭据从 deploy/.env 读取 MJW_*。
"""
import argparse
import base64
import sys
import time
from pathlib import Path

try:
    import winrm
except ImportError:
    print("需要 pywinrm：请用 venv Python 运行（~/tools/winrm-venv/bin/python pwsh_mjw.py），")
    print("或用 pip 安装：pip install pywinrm。")
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / "deploy" / ".env"
PWSH7 = r"C:\Program Files\PowerShell\7\pwsh.exe"


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
    parser = argparse.ArgumentParser(
        description="远程在 mjw 上以 PowerShell 7 执行脚本（WinRM 通道）",
        epilog="示例: %(prog)s 'Get-Service | Where-Object {$_.Status -eq \"Running\"} | Select -First 5 Name'",
    )
    parser.add_argument("script", nargs="?", help="要执行的 pwsh7 脚本内容")
    parser.add_argument("--file", help="从本地 .ps1 文件读取脚本")
    parser.add_argument("--timeout", type=int, default=120, help="等待远程执行完成的超时秒数（默认 120）")
    args = parser.parse_args()

    script = args.script if args.script is not None else None
    if args.file:
        script = Path(args.file).read_text(encoding="utf-8")
    if script is None:
        print("缺少脚本内容：传位置参数或 --file。")
        parser.print_usage()
        return 2

    env = load_env(ENV_FILE)
    ip = env.get("MJW_IP", "")
    user = env.get("MJW_WINRM_USER", "")
    pwd = env.get("MJW_WINRM_PASSWORD", "")
    if not (ip and user and pwd):
        print(f"[失败] {ENV_FILE} 中未配置 MJW_IP / MJW_WINRM_USER / MJW_WINRM_PASSWORD（键位见 .env.example）。")
        return 1

    op_t = min(args.timeout - 5, args.timeout)
    s = winrm.Session(
        ip,
        auth=(user, pwd),
        transport="ntlm",
        operation_timeout_sec=max(10, args.timeout - 5),
        read_timeout_sec=args.timeout + 10,
    )

    # 1) mjw 侧 pwsh7 存在性
    r = s.run_ps(f"[Console]::OutputEncoding=[Text.Encoding]::UTF8; (Test-Path '{PWSH7}')")
    if "True" not in r.std_out.decode("utf-8", "replace"):
        print(f"[失败] mjw 上未找到 pwsh7（{PWSH7}）。请先在 mjw 安装 PowerShell 7（MSI 静默装，见《开发服务器Windows部署使用说明总览》2.1）。")
        return 1

    # 2) 脚本落盘（UTF-16LE 带 BOM，避免 PS 5.1/pwsh 词法错乱）
    name = f"pwsh_mjw_{int(time.time())}.ps1"
    remote = rf"C:\Windows\Temp\{name}"
    payload = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8\n" + script).encode("utf-16-le")
    b64 = base64.b64encode(b"\xff\xfe" + payload).decode()
    write_cmd = (
        f"$b='{b64}'; [IO.File]::WriteAllBytes('{remote}',[Convert]::FromBase64String($b)); "
        f"& '{PWSH7}' -NoProfile -File '{remote}' 2>&1 | Out-String; "
        f"Remove-Item '{remote}' -Force -ErrorAction SilentlyContinue; "
        f"'PWSHEXIT=' + $LASTEXITCODE"
    )
    try:
        r = s.run_ps(write_cmd)
    except Exception as e:  # 超时等：尽力清理远程文件
        try:
            s.run_ps(f"Remove-Item '{remote}' -Force -ErrorAction SilentlyContinue")
        except Exception:
            pass
        print(f"[失败] 远程执行异常: {e}")
        return 1

    out = r.std_out.decode("utf-8", "replace")
    exit_code = 0
    for line in out.splitlines():
        if line.startswith("PWSHEXIT="):
            try:
                exit_code = int(line.split("=", 1)[1])
            except ValueError:
                pass
            out = out.replace(line, "")
            break
    if out.strip():
        print(out.strip())
    if exit_code != 0:
        print(f"[pwsh 退出码 {exit_code}]")
    return exit_code if exit_code else 0


if __name__ == "__main__":
    sys.exit(main())
