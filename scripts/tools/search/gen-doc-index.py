#!/usr/bin/env python3
"""文档域路由索引进结构生成器（v1）。

扫描工作区各仓库文档根，按「主题域 + 文档类型 + 阶段 + 代码落点」四轴产出
结构骨架（主题归类 / 目录 / 文件数 / 入口文件），语义层（典型问题与首查文件）
由本地 LLM 批量补全后回填，产物为《文档域路由索引》。

设计约束：
- 本脚本只做**导航**，不复制任何口径权威（前后端基类清单、基座文档清单、
  各规范正文）的内容与结论——见 AGENTS.md「代码与文档检索（强制口径）」。
- 生成物随 bms 仓库提交；运行不依赖本地 LLM（缺模型时只产结构骨架）。
- 输出默认落工作区 tmp/（草稿），确认后再人工迁入 bms 文档根。

用法：
    python3 gen-doc-index.py                      # 全量生成结构骨架 + 调用本地模型
    python3 gen-doc-index.py --no-llm             # 仅结构骨架，不调模型
    python3 gen-doc-index.py --out <文件>         # 指定输出路径
    python3 gen-doc-index.py --enrich <骨架.json> # 只对骨架做语义补全（跳过扫描）

依赖：Python 3.11+ 标准库；本地 LLM 走 OpenAI 兼容接口（llama.cpp，127.0.0.1:8080）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path

# bms_core 源码根：集合声明统一落插入序集合类（ConcurrentStable*，见裸集合护栏口径）。
_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableList,
)

# 文档根配置：仓库根（相对工作区）→ 文档根名
DOC_ROOTS: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "bms": "bms文档",
        "mdm": "mdm文档",
        "biz": "biz文档",
        "test": "test文档",
    }
)

# 域归类：目录名前缀 → 主题域标签（用于「主题域」轴）
DOMAIN_OF: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList(
    [
        ("规范", "规范与约束"),
        ("规划", "规划与选型"),
        ("设计/架构设计", "架构设计"),
        ("设计/数据库设计", "数据库设计"),
        ("设计/组件设计", "组件设计"),
        ("设计/布局设计", "布局设计"),
        ("设计/原型设计", "原型设计"),
        ("设计/概要设计", "概要设计"),
        ("设计/基类体系", "基类体系"),
        ("设计", "其他设计"),
        ("项目", "项目进度"),
        ("资料", "资料与知识档案"),
        ("审计", "审计"),
        ("用户文档", "用户文档"),
    ]
)

# 各仓文档域内的「类型」判定（按相对路径第二段或文件名特征）
TYPE_RULES: ConcurrentStableList[tuple[re.Pattern[str], str]] = ConcurrentStableList(
    [
        (re.compile(r"(^|/)规范/"), "规范"),
        (re.compile(r"(^|/)规划/"), "规划"),
        (re.compile(r"(^|/)设计/"), "设计"),
        (re.compile(r"(^|/)项目/"), "项目"),
        (re.compile(r"(^|/)资料/"), "资料"),
        (re.compile(r"(^|/)审计/"), "审计"),
        (re.compile(r"(^|/)需求/"), "需求"),
        (re.compile(r"(^|/)任务/"), "任务"),
        (re.compile(r"(^|/)计划/"), "计划"),
        (re.compile(r"(^|/)实施/"), "实施"),
        (re.compile(r"(^|/)测试/"), "测试"),
        (re.compile(r"(^|/)用户文档/"), "用户文档"),
    ]
)

LLM_URL = os.environ.get("BMS_LLM_URL", "http://127.0.0.1:8080/v1/chat/completions")
LLM_MODEL = os.environ.get("BMS_LLM_MODEL", "qwen")
LLM_TIMEOUT = int(os.environ.get("BMS_LLM_TIMEOUT", "180"))

# 语义提示词：只让模型做导航性归纳，明确禁止它输出口径/结论类内容
PROMPT_TMPL = """你是文档路由索引的助手。下面是项目文档中一个任务域的目录结构与文件名清单。

请只做「导航归纳」，输出 JSON，字段固定：
{{
  "topic": "该域的主题归类（10 字以内中文短语）",
  "questions": ["典型查询问题1", "典型查询问题2", "典型查询问题3"],
  "entry_files": ["首查文件相对路径1", "首查文件相对路径2"]
}}

硬性约束：
- topic / questions 用中文，questions 是「人要查这个域时会怎么问」；
- entry_files 必须是下方清单里真实存在的相对路径，最多 3 个，优先选总览/需求/计划类入口；
- 禁止输出任何规范口径、设计结论、实现细节——你只负责指路；
- 只输出 JSON，不要解释、不要 markdown 代码块。

目录：{root}
文件清单（相对路径）：
{files}
"""


def log(msg: str) -> None:
    print(msg, flush=True)


def first_heading(path: Path) -> str:
    """取文档首个一级标题作为标题（无则用文件名去扩展名）。"""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
                if line and not line.startswith("<!--"):
                    break
    except OSError:
        pass
    return path.stem


def classify(rel_posix: str) -> str:
    for pattern, label in TYPE_RULES:
        if pattern.search(rel_posix):
            return label
    return "其他"


def domain_of(rel_posix: str) -> str:
    for prefix, label in DOMAIN_OF:
        if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
            return label
    return "其他"


def scan(root: Path) -> ConcurrentStableList[ConcurrentStableDict]:
    """扫描一个文档根，产出扁平文件记录。"""
    records: ConcurrentStableList[ConcurrentStableDict] = ConcurrentStableList()
    if not root.is_dir():
        return records
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        records.add(
            {
                "rel": rel,
                "title": first_heading(path),
                "domain": domain_of(rel),
                "type": classify(rel),
                "depth": rel.count("/"),
            }
        )
    return records


def unit_key(rec: ConcurrentStableDict) -> str:
    """语义单元键：项目域按「阶段」聚合（一个大阶段一次模型调用），其余域按一级子目录聚合。

    项目域单个任务的「设计 / 实施 / 测试」三件套各自只有 1~3 份，逐任务问模型纯属浪费；
    阶段才是人工「这个阶段在干什么、从哪查起」的自然粒度。规范 / 设计 / 资料等域体量小，
    按一级子目录（如 设计/架构设计）聚合即可。
    """
    rel = rec["rel"]
    parts = rel.split("/")
    if parts[0] == "项目" and len(parts) >= 2:
        return "/".join(parts[:2])  # 项目/<NN_阶段名>
    # 第二段是文件（.md）说明这是「域根下的散文件」——按整域聚成一个单元，
    # 否则 22 份规范会被拆成 22 个「1 份」单元，失去路由意义。
    if len(parts) >= 2 and not parts[1].endswith(".md"):
        return parts[0] + "/" + parts[1]
    return parts[0] or "."


def group_units(
    records: ConcurrentStableList[ConcurrentStableDict],
) -> ConcurrentStableList[ConcurrentStableDict]:
    """把文件记录聚合为「语义单元」：项目域按阶段，其余域按一级子目录。"""
    units: ConcurrentStableDict[str, ConcurrentStableList[ConcurrentStableDict]] = (
        ConcurrentStableDict()
    )
    for rec in records:
        key = unit_key(rec)
        if key not in units:
            units.set(key, ConcurrentStableList())
        units.get(key).add(rec)
    out = ConcurrentStableList()
    for key, recs in sorted(units.items()):
        out.add(
            {
                "dir": key,
                "files": recs,
                "domain": recs[0]["domain"],
                "types": sorted({r["type"] for r in recs}),
            }
        )
    return out


def _plain(obj):
    """把集合类对象递归还原为普通 list / dict（json 无法序列化集合类）。"""
    if isinstance(obj, Mapping):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)) or (
        hasattr(obj, "__iter__") and not isinstance(obj, str)
    ):
        return [_plain(x) for x in obj]
    return obj


def dump(skeleton: ConcurrentStableList[ConcurrentStableDict], path: str) -> None:
    Path(path).write_text(
        json.dumps(_plain(skeleton), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"[输出] {path}")


def representative_files(
    unit: ConcurrentStableDict, cap: int = 200
) -> ConcurrentStableList[ConcurrentStableDict]:
    """挑出给模型看的代表文件，避免大阶段被「任务叶子文件」淹没。

    优先保留：路径浅的（总览 / 需求 / 计划）、以及类型上更像入口的
    （需求、规划、计划、任务总览），剩余的按路径序补足到 cap。
    本地模型上下文 150K，单次给几百个路径（每行约 80 字符）远未触顶，
    因此 cap 取 200；超出部分以「其余 N 份」提示模型。
    """
    priority = {"需求": 0, "规划": 1, "计划": 2, "任务": 3, "审计": 4}
    files = sorted(
        unit["files"],
        key=lambda r: (
            priority.get(r["type"], 9),
            r["rel"].count("/"),
            r["rel"],
        ),
    )
    head = files[:cap]
    if len(files) > cap:
        # 保留一个「其余 N 份」的提示，让模型知道还有同族文件
        head = head + [
            {
                "rel": f"……（其余 {len(files) - cap} 份同族文档略）",
                "title": "",
                "type": "",
                "domain": "",
                "depth": 0,
            }
        ]
    return head


def call_llm(root: Path, unit: ConcurrentStableDict) -> ConcurrentStableDict | None:
    files_txt = "\n".join(f"  {r['rel']}" for r in representative_files(unit))
    prompt = PROMPT_TMPL.format(root=root, files=files_txt)
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 1024,
        # 本地服务按 deepseek 推理格式启动；此类抽取任务不需要思考，
        # 关闭 thinking 可省下大量 token（否则推理内容会挤占输出上限）。
        "chat_template_kwargs": {"enable_thinking": False},
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        LLM_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"].get("content", "")
        return extract_json(content)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        log(f"    [!] LLM 调用失败：{exc}")
        return None


def extract_json(text: str) -> ConcurrentStableDict | None:
    """从模型输出中提取 JSON 对象（容忍 ```json 包裹与首尾杂文本）。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    # 字段校验：缺字段或类型不对即视为无效
    if not isinstance(obj.get("topic"), str) or not isinstance(
        obj.get("questions"), list
    ):
        return None
    if not isinstance(obj.get("entry_files"), list):
        return None
    return obj


def enrich(
    skeleton: ConcurrentStableList[ConcurrentStableDict], limit: int | None
) -> None:
    """按任务域批量调本地 LLM 补语义。"""
    targets = [u for u in skeleton if u.get("needs_llm") and not u.get("semantic")]
    if limit:
        targets = targets[:limit]
    log(f"[LLM] 待补全 {len(targets)} 个任务域")
    for idx, unit in enumerate(targets, 1):
        root = Path(unit["repo_root"])
        log(f"  [{idx}/{len(targets)}] {root} / {unit['dir']}")
        result = call_llm(root, unit)
        if result:
            valid = [f for f in result["entry_files"] if (root / f).is_file()]
            unit["semantic"] = {
                "topic": result["topic"],
                "questions": result["questions"][:3],
                "entry_files": valid or [r["rel"] for r in unit["files"][:1]],
            }
            log(f"      ✓ {result['topic']}")
        else:
            unit["semantic"] = {
                "topic": "",
                "questions": [],
                "entry_files": [r["rel"] for r in unit["files"][:1]],
            }
            log("      ✗ 失败，回退为文件名兜底")


def main() -> int:
    parser = argparse.ArgumentParser(description="文档域路由索引进结构生成器")
    parser.add_argument("--workspace", default=".", help="工作区根（默认当前目录）")
    parser.add_argument("--out", help="输出骨架 JSON 路径（默认打印摘要）")
    parser.add_argument(
        "--no-llm", action="store_true", help="只产结构骨架，不调本地模型"
    )
    parser.add_argument("--enrich", help="读取既有骨架 JSON 后只做语义补全")
    parser.add_argument("--limit", type=int, help="限制 LLM 调用数量（调试用）")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()

    if args.enrich:
        skeleton = json.loads(Path(args.enrich).read_text(encoding="utf-8"))
        log(f"[读取] 已有骨架 {len(skeleton)} 个单元")
        needs = sum(1 for u in skeleton if u.get("needs_llm") and not u.get("semantic"))
        log(f"[待补全] {needs} 个单元（已有语义的自动跳过）")
        if not args.no_llm:
            enrich(skeleton, args.limit)
        if args.out:
            dump(skeleton, args.out)
        return 0
    else:
        skeleton = ConcurrentStableList()
        for repo, docname in DOC_ROOTS.items():
            root = workspace / repo / docname
            if not root.is_dir():
                log(f"[跳过] {root} 不存在")
                continue
            records = scan(root)
            units = group_units(records)
            for unit in units:
                unit["repo"] = repo
                unit["repo_root"] = str(root)
                # 单文件单元（如某份规范）不需要问模型——它自己就是入口
                unit["needs_llm"] = len(unit["files"]) >= 2
                unit["file_count"] = len(unit["files"])
            for _u in units:
                skeleton.add(_u)
            log(
                f"[扫描] {repo}/{docname}：{len(records)} 份文档 → {len(units)} 个任务域"
            )
        log(
            f"[合计] {len(skeleton)} 个任务域，其中需补语义 "
            f"{sum(1 for u in skeleton if u.get('needs_llm'))} 个"
        )

    if not args.no_llm and not args.enrich:
        enrich(skeleton, args.limit)

    if args.out:
        dump(skeleton, args.out)
    else:
        for unit in skeleton:
            sem = unit.get("semantic") or {}
            topic = sem.get("topic") or "-"
            log(
                f"  {unit['repo']:>4} | {unit['domain']:<8} | {unit['dir']:<50} | "
                f"{unit['file_count']:>3} 份 | {topic}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
