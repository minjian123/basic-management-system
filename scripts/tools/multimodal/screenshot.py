"""screenshot.py - Edge/Chrome 无头模式将 HTML 或 URL 渲染为 PNG（Windows）。

用法:
    python screenshot.py --url "file:///D:/Develop/bms/文档/设计/原型设计/02_通用骨架/03_主框架.html" --out out.png [--width 1440] [--height 900] [--budget 3000]

参数:
    --url     必填，file:// 本地路径或 http(s) URL
    --out     必填，PNG 输出路径
    --width   窗口宽度，默认 1440
    --height  窗口高度，默认 900
    --budget  渲染等待毫秒数（动画/角标模拟），默认 3000
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Edge/Chrome 无头截图")
    parser.add_argument("--url", required=True, help="file:// 本地路径或 http(s) URL")
    parser.add_argument("--out", required=True, help="PNG 输出路径")
    parser.add_argument("--width", type=int, default=1440, help="窗口宽度（默认 1440）")
    parser.add_argument("--height", type=int, default=900, help="窗口高度（默认 900）")
    parser.add_argument("--budget", type=int, default=3000, help="渲染等待毫秒数（默认 3000）")
    args = parser.parse_args()

    exe = next((p for p in CANDIDATES if Path(p).exists()), None)
    if not exe:
        print("错误: 未找到 Edge/Chrome", file=sys.stderr)
        return 1

    out_dir = Path(args.out).parent
    if out_dir and not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [exe, "--headless", "--disable-gpu", f"--screenshot={args.out}",
         f"--window-size={args.width},{args.height}", f"--virtual-time-budget={args.budget}", args.url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)

    if Path(args.out).exists():
        print(f"OK: {args.out}")
        return 0
    print(f"错误: 截图失败 {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())