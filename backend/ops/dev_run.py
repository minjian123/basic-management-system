"""本机四服务形态下**带调试器**启动单个服务（开发联调；配合 `scripts/tools/dev/本地全套.sh`）。

用法：

```bash
cd backend
uv run python -m ops.dev_run --service identity                 # 起 identity（绑 127.0.0.5:8000 + 载开发密钥）
uv run python -m ops.dev_run --service bms_identity --dry-run    # 只看解析结果（不启动）
```

- **为何需要**：本机多服务要求每个服务绑各自 loopback 别名（`127.0.0.2 tenant` /
  `.4 platform` / `.5 identity`）且**同一 8000 端口**（服务间基址模板 `http://{service}:8000`），
  并加载 `backend/.dev-keys.local` 的开发密钥；IDE 的 `后端：单服务（debugpy）` 只设
  `PYTHONUNBUFFERED` ⇒ 起来的是 `127.0.0.1:8000` 且**无密钥**，登录链路必断。
  本脚本在**导入服务前**把 host / 端口 / Redis / 密钥按本机全套口径注入 `os.environ`，
  再 `runpy.run_module` 进服务入口 ⇒ 断点、变量、调用栈、日志与 `python -m bms_<服务>` 完全一致
  （IDE 侧把本模块作为 `module` 启动即可打断点，见 `.vscode/launch.json` 的
  「后端：单服务（debugpy · 本机四服务）」）。
- **冲突**：目标地址已被占用（通常是脚本起的同名服务）时**直接报错**并提示
  `bash scripts/tools/dev/本地全套.sh stop <服务>`——本脚本不做任何清理动作。
- **边界**：只注入环境变量并进服务入口，不改配置、不写库、不动脚本纳管的其它服务；
  停止即随前台进程结束（Ctrl+C / IDE 停止调试）。
"""

import argparse
import os
import runpy
import socket
import sys
from pathlib import Path

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList

HOST_BY_SERVICE: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "tenant": "127.0.0.2",
        "platform": "127.0.0.4",
        "identity": "127.0.0.5",
    }
)
"""服务 → loopback 别名（与 `scripts/tools/dev/本地全套.sh`、服务基址模板 `http://{service}:8000` 同形）。

`org` 已随组织主数据归 mdm 产品服务（2026-10-07）退出平台服务清单，本机全套不再纳管。
"""

KNOWN_SERVICES = "tenant / platform / identity"
"""本机全套包含的服务（其余服务需显式 `--host`）。"""

DEFAULT_PORT = "8000"
"""缺省端口（四服务同一端口，靠别名区分）。"""

DEFAULT_REDIS = "redis://192.168.0.107:6379/5"
"""缺省 Redis（本机无 Redis，指向开发机 DB5 隔离；经 `BMS_REDIS__URL` / `--redis` 覆盖）。"""

KEYS_FILE = Path(__file__).resolve().parents[1] / ".dev-keys.local"
"""开发密钥文件（由 `本地全套.sh up` 生成；`export K='V'` 形态）。"""


def load_keys(path: Path) -> int:
    """读开发密钥文件并把键值注入 `os.environ`（已存在的键不覆盖）。

    Args:
        path: 密钥文件路径。

    Returns:
        注入的密钥项数（文件不存在时为 0）。
    """
    if not path.is_file():
        return 0
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
        count += 1
    return count


def in_use(host: str, port: int) -> bool:
    """目标地址是否已在监听（能连上即视为占用）。

    Args:
        host: 绑定地址。
        port: 绑定端口。

    Returns:
        已占用返回 True。
    """
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def service_of(name: str) -> str:
    """归一服务名（接受 `identity` 或 `bms_identity`）。

    Args:
        name: 传入的服务名。

    Returns:
        归一后的服务名（不含 `bms_` 前缀）。
    """
    return name[4:] if name.startswith("bms_") else name


def main(argv: ConcurrentStableList[str]) -> int:
    """注入本机全套口径环境变量并进入服务入口。

    Args:
        argv: 命令行参数（不含程序名）。

    Returns:
        进程退出码；正常启动时不会返回（服务前台常驻）。
    """
    parser = argparse.ArgumentParser(description="本机四服务形态下起单个服务（可断点调试）")
    parser.add_argument("--service", required=True, help=f"服务名（{KNOWN_SERVICES}；可带 bms_ 前缀）")
    parser.add_argument("--host", default="", help="覆盖绑定地址（缺省按服务别名）")
    parser.add_argument("--port", default=DEFAULT_PORT, help=f"绑定端口（缺省 {DEFAULT_PORT}）")
    parser.add_argument("--redis", default="", help=f"Redis 连接串（缺省 {DEFAULT_REDIS}）")
    parser.add_argument("--dry-run", action="store_true", help="只打印解析结果，不启动")
    args = parser.parse_args(argv)

    service = service_of(args.service)
    host = args.host or HOST_BY_SERVICE.get(service, "")
    if not host:
        print(
            f"[dev_run] 未知服务：{args.service}（本机全套仅含 {KNOWN_SERVICES}；其他服务请显式给 --host）",
            file=sys.stderr,
        )
        return 2

    os.environ.setdefault("BMS_SERVER__HOST", host)
    os.environ.setdefault("BMS_SERVER__PORT", args.port)
    os.environ.setdefault("BMS_REDIS__URL", args.redis or DEFAULT_REDIS)
    keys = load_keys(KEYS_FILE)

    if keys == 0:
        print(
            f"[dev_run] 提示：未找到开发密钥 {KEYS_FILE}（本地登录 / 东西向调用会失败）——"
            f"先跑 `bash scripts/tools/dev/本地全套.sh up` 生成",
            file=sys.stderr,
        )
    if args.dry_run:
        print(
            f"[dev_run] 目标 bms_{service}｜BMS_SERVER__HOST={os.environ['BMS_SERVER__HOST']} "
            f"BMS_SERVER__PORT={os.environ['BMS_SERVER__PORT']} BMS_REDIS__URL={os.environ['BMS_REDIS__URL']} "
            f"｜注入密钥 {keys} 项（值不外显）"
        )
        return 0

    if in_use(host, int(args.port)):
        print(
            f"[dev_run] {host}:{args.port} 已被占用——先停脚本纳管的同名服务："
            f"`bash scripts/tools/dev/本地全套.sh stop {service}`",
            file=sys.stderr,
        )
        return 1

    print(f"[dev_run] 启动 bms_{service}：{host}:{args.port}（断点就绪；Ctrl+C 停止）", flush=True)
    sys.argv = [f"bms_{service}"]
    runpy.run_module(f"bms_{service}", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(ConcurrentStableList(sys.argv[1:])))
