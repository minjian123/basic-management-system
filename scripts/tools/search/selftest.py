#!/usr/bin/env python3
"""MCP 服务自检：走真实 stdio JSON-RPC 验证工具可发现、可调用。

用法（需先装依赖，见同目录 requirements.txt）::

    python3 scripts/tools/search/selftest.py

退出码：通过 0，失败 1。可挂 CI 做「服务能起来、工具能调」的冒烟检查。
"""

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 集合声明走基座插入序集合类（《后端开发规范》「集合与排序」；
# check-bare-collections.py 强制、scripts/tools 亦在扫描范围内）。
_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))
from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402  须先注入 sys.path

HERE = Path(__file__).resolve().parent
SERVER = HERE / "search_mcp.py"
ROOT = HERE.parents[3]


async def run() -> int:
    env = dict(os.environ)
    env["SEARCH_ROOT"] = str(ROOT)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
        env=env,
    )
    failures: ConcurrentStableList[str] = ConcurrentStableList()
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        init = await session.initialize()
        si = init.server_info
        print(f"[1] initialize OK：{si.name}")

        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        print(f"[2] tools OK：{sorted(names)}")
        for need in ("search_content", "index_update", "search_with_snippet"):
            if need not in names:
                failures.append(f"缺少工具 {need}")

        for q in ("权限计算", "BaseService"):
            res = await session.call_tool("search_content", {"query": q, "limit": 3})
            if res.is_error:
                failures.append(f"{q} 调用报错")
                continue
            payload = res.structured_content
            if isinstance(payload, dict):
                payload = payload.get("result", [payload])
            print(f"[3] search_content「{q}」OK：{len(payload)} 条")
            if not payload:
                failures.append(f"{q} 无结果")

        res = await session.call_tool("index_update", {})
        if res.is_error:
            failures.append("index_update 报错")
        else:
            print(f"[4] index_update OK：{res.structured_content}")

    if failures:
        print("\n[selftest] 失败：")
        for f in failures:
            print("  - " + f)
        return 1
    print("\n[selftest] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
