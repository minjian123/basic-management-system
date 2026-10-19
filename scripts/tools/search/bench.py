#!/usr/bin/env python3
"""检索效果评测：本方案 vs ripgrep（标准 IR 指标）。

**为什么用 MRR / Recall@K**：扫描速度不是瓶颈（rg 全库仅 60~70ms），
真正的成本是"打开候选并判断是否相关"。因此指标应衡量**排序质量**，
而非速度。人工标注每个查询的"相关文档集"（本仓权威文档），再算：

- Recall@10：前 10 条里覆盖了多少相关文档
- MRR@10：第一个相关文档名次的倒数（1.0 = 首条即相关）
- 候选量：需人工判断的条数
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import search_mcp as S

RG = Path(
    r"C:\Users\minjian\AppData\Local\Programs\DeepSeek Harness\resources\app.asar.unpacked"
    r"\dsh\node_modules\@vscode\ripgrep-win32-x64\bin\rg.exe"
)

# (查询, 人工标注的相关文档前缀集) —— 按本仓领域知识指定权威落点
CASES: list[tuple[str, list[str]]] = [
    (
        "权限计算",
        [
            "bms/bms文档/项目/07_RBAC基础模块/任务/02_用户与角色/02_用户与角色_04_主体链权限计算引擎",
            "bms/bms文档/项目/07_RBAC基础模块/需求/",
        ],
    ),
    (
        "基类继承链",
        [
            "bms/bms文档/设计/基类体系/",
            "bms/bms文档/设计/架构设计/04_架构设计_后端基础类体系.md",
        ],
    ),
    (
        "认证刷新令牌",
        [
            "bms/bms文档/项目/06_认证与安全/任务/01_认证与会话/01_认证与会话_03_本地登录刷新登出链路",
            "bms/bms文档/项目/06_认证与安全/任务/05_登录前端/05_登录前端_02_token与401静默刷新接线",
        ],
    ),
    (
        "resolve_plugin",
        [
            "bms/backend/libs/bms_core/src/bms_core/",
            "bms/backend/services/platform/tests/contracts/",
        ],
    ),
    (
        "租户隔离",
        [
            "bms/bms文档/设计/",
            "bms/backend/libs/bms_core/src/",
        ],
    ),
]
K = 10


def relevant(path: str, prefixes: list[str]) -> bool:
    return any(path.startswith(p) for p in prefixes)


def rg_ranked(query: str, k: int = K) -> tuple[list[str], float]:
    t0 = time.perf_counter()
    out = subprocess.run(
        [str(RG), "-l", "--no-heading", query],
        cwd=str(S.ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    dt = (time.perf_counter() - t0) * 1000
    return [l.strip() for l in out.stdout.splitlines() if l.strip()][:k], dt


def rr(paths: list[str], prefixes: list[str]) -> tuple[float, int]:
    """返回 (MRR, 命中相关文档数)。"""
    for i, p in enumerate(paths, 1):
        if relevant(p, prefixes):
            return 1.0 / i, sum(1 for x in paths if relevant(x, prefixes))
    return 0.0, sum(1 for x in paths if relevant(x, prefixes))


def main() -> int:
    S.search("预热")
    print(f"工作区根：{S.ROOT}　K={K}\n")
    hdr = (
        f"{'查询':<16}{'rg候选':>7}{'本方案':>7}"
        f"{'rg MRR':>9}{'本MRR':>8}{'rg召回':>8}{'本召回':>8}{'rg耗时':>8}{'本耗时':>8}"
    )
    print(hdr)
    print("-" * len(hdr))
    acc = {
        "rg_mrr": 0.0,
        "our_mrr": 0.0,
        "rg_rec": 0,
        "our_rec": 0,
        "rg_ms": 0.0,
        "our_ms": 0.0,
        "n": 0,
    }
    for q, prefixes in CASES:
        rg_paths, rg_ms = rg_ranked(q)
        t0 = time.perf_counter()
        rows = S.search(q, limit=K)
        our_ms = (time.perf_counter() - t0) * 1000
        our_paths = [r["path"] for r in rows]
        rg_mrr, rg_rec = rr(rg_paths, prefixes)
        our_mrr, our_rec = rr(our_paths, prefixes)
        acc["rg_mrr"] += rg_mrr
        acc["our_mrr"] += our_mrr
        acc["rg_rec"] += rg_rec
        acc["our_rec"] += our_rec
        acc["rg_ms"] += rg_ms
        acc["our_ms"] += our_ms
        acc["n"] += 1
        print(
            f"{q:<16}{len(rg_paths):>7}{len(rows):>7}"
            f"{rg_mrr:>9.2f}{our_mrr:>8.2f}{rg_rec:>8}{our_rec:>8}"
            f"{rg_ms:>7.0f}ms{our_ms:>7.1f}ms"
        )
    n = acc["n"]
    print("-" * len(hdr))
    print(
        f"{'平均':<16}{'':>7}{'':>7}"
        f"{acc['rg_mrr'] / n:>9.2f}{acc['our_mrr'] / n:>8.2f}"
        f"{acc['rg_rec'] / n:>8.1f}{acc['our_rec'] / n:>8.1f}"
        f"{acc['rg_ms'] / n:>7.0f}ms{acc['our_ms'] / n:>7.1f}ms"
    )
    print("\n指标：")
    print("  MRR     = 首个相关文档名次的倒数，1.00 表示第一条就命中（越高越好）")
    print("  召回    = 前 10 条中相关文档条数")
    print("  候选    = 返回条数（rg 为全量命中，本方案封顶 10）")
    print("\n注：rg 的候选顺序为文件系统遍历序，未经相关性排序——这正是它")
    print("    在大仓上「命中几百个文件、逐个打开判断」的根因。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
