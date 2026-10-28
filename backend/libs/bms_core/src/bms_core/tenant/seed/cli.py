"""种子统一编排 CLI（07B `02_03`）：触发内部端点并渲染逐项报告。

**职责边界**：本 CLI 是**薄客户端**——不装载种子、不做编排，只把参数转成一次 HTTP 调用，
再把服务返回的 JSON 报告渲染成人类可读表格。执行全在 platform 服务进程内完成
（XA 分支需要引擎注册表 + 分支处理器 + 事务参与方，这些由应用装配提供）。

用法：

```bash
cd backend
uv run python -m ops.seed_platform --dry-run              # 只预检，不开事务
uv run python -m ops.seed_platform --tenant demo          # 执行全部种子
uv run python -m ops.seed_platform --only seed-menu     # 只跑指定种子
```

退出码：0 成功 / 1 数据冲突 / 2 执行失败（已整体回滚）/ 3 前置错误 / 64 参数错误。
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, NoReturn, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.tenant.seed.orchestrator import EXIT_USAGE

__all__ = ["build_parser", "main", "render_report"]

RUN_IMAGE = "platform"
"""本脚本只依赖 `bms_core` 与 `ops`，并需访问 platform 服务；部署态在 platform 容器内运行。"""

ORCHESTRATE_PATH = "/api/v1/platform/internal/seeds/orchestrate"
"""编排内部端点路径。"""

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
"""缺省服务基址（容器内自身回环）。"""


class _UsageParser(argparse.ArgumentParser):
    """参数解析器：参数错误退 **64**（`EX_USAGE`），不沿用 argparse 缺省的 2。

    **为什么**：退出码 2 已表示「执行失败（已整体回滚）」，若参数错误也退 2，调用方无法区分
    「我传错了」与「跑失败了」（详设 §3.11）。
    """

    def error(self, message: str) -> NoReturn:
        """参数非法即退 64。

        Args:
            message: argparse 的错误说明。

        Raises:
            SystemExit: 恒定抛出（退出码 64）。
        """
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: 参数错误：{message}\n")
        raise SystemExit(EXIT_USAGE)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = _UsageParser(description="种子统一编排（平台 + 产品同构声明，一个 XA 全局事务内串行执行）")
    parser.add_argument("--tenant", default="", help="目标租户（缺省取 [platform_tenant].code）")
    parser.add_argument("--only", action="append", default=[], help="只执行指定种子（可多次）")
    parser.add_argument("--skip", action="append", default=[], help="跳过指定种子（可多次）")
    parser.add_argument("--require", action="append", default=[], help="人工强制前置（可多次）")
    parser.add_argument("--dry-run", action="store_true", help="只做装载 + 排序 + 冲突预检")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--timeout", type=float, default=300.0, help="全局事务超时（秒）")
    parser.add_argument("--base-url", default="", help="platform 服务基址（缺省取环境变量或回环）")
    return parser


def _base_url(raw: str) -> str:
    """解析服务基址（参数 > 环境变量 > 回环）。

    Args:
        raw: 命令行传入的基址。

    Returns:
        str: 服务基址（无尾斜杠）。
    """
    if raw:
        return raw.rstrip("/")
    env = os.environ.get("BMS_SEED_ORCHESTRATE_URL", "")
    if env:
        return env.rstrip("/")
    return DEFAULT_BASE_URL


def render_report(payload: object) -> str:
    """把编排结果渲染成人类可读表格。

    Args:
        payload: 服务返回的 `data` 对象。

    Returns:
        str: 渲染后的文本。
    """
    data: Any = cast("Any", payload) if isinstance(payload, dict) else {}
    reports: Any = data.get("reports") or []
    errors: Any = data.get("errors") or []
    conflicts: Any = data.get("conflicts") or []
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    if reports:
        lines.add(f"{'种子':<24}{'来源':<10}{'状态':<14}说明")
        lines.add("-" * 78)
        for item in reports:
            note = str(item.get("note") or "")
            lines.add(f"{item.get('name', '')!s:<24}{item.get('source', '')!s:<10}{item.get('status', '')!s:<14}{note}")
    for label, group in (("前置错误", errors), ("数据冲突", conflicts)):
        if not group:
            continue
        lines.add("")
        lines.add(f"[{label}]")
        for item in group:
            lines.add(f"  - {item}")
    exit_code = int(data.get("exitCode", 0) or 0)
    lines.add("")
    if exit_code == 0:
        lines.add("→ 全部成功（幂等；重复执行结果为 0 新增）")
    elif exit_code == 1:
        lines.add("→ 存在数据冲突：未进入事务，按上方明细人工处置（不自动覆盖）")
    elif exit_code == 2:
        lines.add("→ 执行失败：全局事务已回滚，无脏数据")
    else:
        lines.add("→ 编排前置错误：未进入事务")
    return "\n".join(lines)


def _call(base_url: str, body: ConcurrentStableDict[str, Any]) -> ConcurrentStableDict[str, Any]:
    """调用编排端点并返回 `data`。

    Args:
        base_url: 服务基址。
        body: 请求体。

    Returns:
        ConcurrentStableDict[str, Any]: 响应 `data`。

    Raises:
        RuntimeError: 网络失败或响应非法。
    """
    request = urllib.request.Request(
        f"{base_url}{ORCHESTRATE_PATH}",
        data=json.dumps(dict(body)).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=body.get("timeout_seconds", 300) + 30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"编排端点返回 HTTP {exc.code}：{exc.read().decode('utf-8', 'ignore')[:400]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接编排端点（{base_url}）：{exc.reason}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"编排端点响应非法（非 JSON）：{raw[:200]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("编排端点响应非法（非 JSON 对象）")
    payload = cast("Mapping[str, Any]", parsed)
    data: Any = payload.get("data")
    return ConcurrentStableDict(cast("dict[str, Any]", data)) if isinstance(data, dict) else ConcurrentStableDict()


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口：解析参数 → 调端点 → 渲染报告 → 返回退出码。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（0 / 1 / 2 / 3 / 64）。
    """
    args = build_parser().parse_args(argv)
    body: ConcurrentStableDict[str, Any] = ConcurrentStableDict()
    body.set("tenant", args.tenant)
    body.set("only", list(args.only))
    body.set("skip", list(args.skip))
    body.set("require", list(args.require))
    body.set("dry_run", bool(args.dry_run))
    body.set("timeout_seconds", float(args.timeout))
    try:
        data = _call(_base_url(args.base_url), body)
    except RuntimeError as exc:
        print(f"[seed_platform] {exc}")
        # HTTP 400 = 编排端点拒绝参数（`--only` / `--skip` / `--require` 引用不存在的种子），
        # 属参数错误而非执行失败：映射为 64（详设 §3.11），与「执行失败退 2」区分。
        return EXIT_USAGE if "HTTP 400" in str(exc) else 2
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_report(data))
    return int(data.get("exitCode", 0))
