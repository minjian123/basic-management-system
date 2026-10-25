#!/usr/bin/env python3
"""MCP 服务自检：走真实 stdio JSON-RPC 验证工具可发现、可调用、**返回值可正确序列化**。

为什么必须校验返回值结构（实测踩过的坑）：
仅验证「工具存在且可调用」是不够的——曾出现两个只有真调用才暴露的缺陷：
  1) 返回自定义集合类对象，MCP 序列化后变成
     `ConcurrentStableDict([('path', ...)])` 字符串（费 token、模型难解析）；
  2) 某个工具内部 `ConcurrentStableDict` 不支持 item 赋值，一调用就报错。
因此本脚本对**返回文本**做结构断言：必须是合法 JSON，且元素为普通字典，
不得出现集合类的 repr（`ConcurrentStableDict(` / `ConcurrentStableList(` 等）。

用法（需先装依赖，见同目录 requirements.txt）::

    python3 scripts/tools/search/selftest.py

退出码：通过 0，失败 1。可挂 CI 做冒烟检查。
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 集合声明走基座插入序集合类（《后端开发规范》「集合与排序」；
# check_bare_collections.py 强制、scripts/tools 亦在扫描范围内）。
_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))
from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

HERE = Path(__file__).resolve().parent
SERVER = HERE / "search_mcp.py"
ROOT = HERE.parents[3]

# 集合类 repr 的痕迹：出现即说明工具出口没转成内建容器
REPR_MARKERS = (
    "ConcurrentStableDict(",
    "ConcurrentStableList(",
    "ConcurrentStableSet(",
)


def _assert_plain(result, tool: str, failures: ConcurrentStableList[str]) -> ConcurrentStableList:
    """校验一次工具调用结果：文本是合法 JSON、无集合类 repr、元素为普通 dict。"""
    blocks = getattr(result, "content", None) or []
    texts = [getattr(b, "text", "") or "" for b in blocks]
    raw = "\n".join(t for t in texts if t.strip())
    if not raw.strip():
        failures.add(f"{tool}：返回内容为空")
        return ConcurrentStableList()

    # 1) 不得出现集合类 repr（当前返回格式的实际缺陷）
    for marker in REPR_MARKERS:
        if marker in raw:
            failures.add(f"{tool}：返回值含集合类 repr（{marker}），未转内建容器")
            return ConcurrentStableList()

    # 2) 若是逐行 JSON，逐行解析；否则整体解析
    items: ConcurrentStableList = ConcurrentStableList()
    for line in normalized_lines(raw):
        try:
            items.add(json.loads(line))
        except json.JSONDecodeError:
            items = None  # 逐行失败则退回整体解析
            break
    if items is None:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            failures.add(f"{tool}：返回值不是合法 JSON（{exc}）")
            return ConcurrentStableList()
        items = ConcurrentStableList(parsed if isinstance(parsed, list) else [parsed])

    # 3) 元素必须是普通字典（不是集合类实例、不是字符串 repr）
    for item in items:
        if not isinstance(item, dict):
            failures.add(f"{tool}：返回元素不是普通 dict，而是 {type(item).__name__}")
            return ConcurrentStableList()
    return items


def normalized_lines(raw: str) -> ConcurrentStableList[str]:
    """把「多段 JSON 文本」切成可逐行解析的片段。

    MCP 客户端把每个内容块的文本顺序拼接，块之间没有分隔符；
    本服务每块输出一个 JSON 对象，故按 `}\n{` 边界切分。
    """
    cleaned = raw.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        return ConcurrentStableList([cleaned])
    parts = cleaned.split("\n{")
    if len(parts) == 1:
        return ConcurrentStableList([cleaned])
    return [parts[0]] + ["{" + p for p in parts[1:]]


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
                failures.add(f"缺少工具 {need}")

        # 3) search_content：结果非空 + 结构干净
        for q in ("权限计算", "BaseService"):
            res = await session.call_tool("search_content", {"query": q, "limit": 3})
            if res.is_error:
                failures.add(f"search_content「{q}」调用报错")
                continue
            rows = _assert_plain(res, f"search_content「{q}」", failures)
            print(f"[3] search_content「{q}」OK：{len(rows)} 条，结构干净")
            if not rows:
                failures.add(f"search_content「{q}」无结果")
            else:
                for key in ("path", "kind", "title", "score"):
                    if key not in rows[0]:
                        failures.add(f"search_content「{q}」结果缺字段 {key}")

        # 4) search_with_snippet：必须带出 snippet（曾因集合类不支持赋值而报错）
        res = await session.call_tool("search_with_snippet", {"query": "适配器", "limit": 2})
        if res.is_error:
            failures.add("search_with_snippet 调用报错")
        else:
            rows = _assert_plain(res, "search_with_snippet", failures)
            has = [r for r in rows if "snippet" in r]
            print(f"[4] search_with_snippet OK：{len(rows)} 条，{len(has)} 条带片段")
            if rows and not has:
                failures.add("search_with_snippet：返回未包含 snippet 字段")

        # 5) index_update：结构干净且含统计字段
        res = await session.call_tool("index_update", {})
        if res.is_error:
            failures.add("index_update 调用报错")
        else:
            items = _assert_plain(res, "index_update", failures)
            stats = items[0] if items else {}
            print(f"[5] index_update OK：{stats}")
            for key in ("added", "changed", "removed", "total"):
                if key not in stats:
                    failures.add(f"index_update：返回缺字段 {key}")

    if failures:
        print("\n[selftest] 失败：")
        for f in failures:
            print("  - " + f)
        return 1
    print("\n[selftest] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
