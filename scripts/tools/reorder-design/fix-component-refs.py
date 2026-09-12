#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix-component-refs.py - 组件设计节点内「旧编号」正文引用改为「名称 + 链接」

在 migrate-component-structure.py 完成目录归并与链接重指之后运行：
 1. 链接文字剥编号：[19 请求封装与错误处理](u) -> [请求封装与错误处理](u)；[19 节点](u) -> [请求封装](u)
 2. 正文「NN 节点」->「[主题](相对链接)」
 3. 正文「NN 主题名」->「[主题名](相对链接)」（排除数量词如「30 字典字段」）
 4. 区间/并列引用专门替换（02-09 节点、02/09 节点、07 与 15 节点、12/21 节点）
 5. 去掉已建节点上残留的「（规划中…）」标注（仅限协作列表中的节点标注）

用法：python3 fix-component-refs.py --dry-run / python3 fix-component-refs.py
"""
import argparse
import os
import re
from pathlib import Path

BMS = Path(__file__).resolve().parents[3]
DOC = BMS / "bms文档"
CD = DOC / "设计" / "组件设计"
REPORT = Path("/tmp/opencode/component-refs-report.txt")

EXISTING = [
    (2, "字典字段", "01_字段类", 1), (3, "日期时间字段", "01_字段类", 2),
    (4, "数值与金额字段", "01_字段类", 3), (5, "树选择字段", "01_字段类", 4),
    (6, "组织选择字段", "01_字段类", 5), (7, "文件上传字段", "01_字段类", 6),
    (8, "富文本字段", "01_字段类", 7), (9, "开关与枚举字段", "01_字段类", 8),
    (10, "通用表格", "02_展示类", 1), (11, "查询筛选区", "02_展示类", 2),
    (12, "状态标签与描述列表", "02_展示类", 3), (13, "图表卡", "02_展示类", 4),
    (14, "弹窗抽屉表单", "03_交互类", 1), (15, "导入导出", "03_交互类", 2),
    (16, "审批流展示", "03_交互类", 3), (17, "图标选择器", "03_交互类", 4),
    (18, "代码表达式编辑器", "03_交互类", 5), (19, "请求封装", "04_基础类", 1),
    (20, "权限指令", "04_基础类", 2), (21, "格式化工具", "04_基础类", 3),
]
OLD2NEW = {o: (t, c, n) for (o, t, c, n) in EXISTING}
TOPICS = [t for (_, t, _, _) in EXISTING]
TOPIC_RE = "|".join(sorted(TOPICS, key=len, reverse=True))
MD_CODE = r"```[\s\S]*?```|`[^`\n]*`"


def target_rel(o, src_dir):
    t, c, n = OLD2NEW[o]
    target = CD / c / f"{n:02d}_组件设计_{t}" / f"{n:02d}_组件设计_{t}.md"
    return os.path.relpath(target, src_dir).replace(os.sep, "/")


def protect(text, pattern, fn):
    store = []

    def save(m):
        store.append(m.group(0))
        return f"\x00{len(store)-1}\x00"
    p = re.sub(pattern, save, text, flags=re.S)
    p = fn(p)
    return re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], p)


def fix_text(text, src_dir, changes, cur_topic=None):
    def rep(pattern, repl):
        nonlocal text
        text = re.sub(pattern, repl, text)

    # 0) 协作列表里已建节点的「（规划中…）」标注去掉
    for o, (t, c, n) in OLD2NEW.items():
        text = text.replace(f"{o:02d} {t}（规划中）", f"{t}")
        text = text.replace(f"{o:02d} {t}（规划中，", f"{t}（")

    # 1) 链接文字剥编号：[NN xxx](u)
    def strip_link_text(m):
        o = int(m.group(1))
        label = m.group(2)
        if o in OLD2NEW:
            return f"[{OLD2NEW[o][0] if label == '节点' else label}]"
        return m.group(0)
    text = re.sub(r"\[(\d{2}) ([^\]]+)\]", strip_link_text, text)

    # 2) 区间/并列
    text = text.replace("02-09 节点", "字段类各节点")
    text = re.sub(r"07 与 15 节点",
                  f"[文件上传字段]({target_rel(7, src_dir)}) 与 [导入导出]({target_rel(15, src_dir)})", text)
    text = re.sub(r"02/09 节点",
                  f"[字典字段]({target_rel(2, src_dir)})/[开关与枚举字段]({target_rel(9, src_dir)})", text)
    text = re.sub(r"12/21 节点",
                  f"[状态标签与描述列表]({target_rel(12, src_dir)})/[格式化工具]({target_rel(21, src_dir)})", text)

    # 3) 「NN 节点」
    def node_repl(m):
        o = int(m.group(1))
        if o not in OLD2NEW:
            return m.group(0)
        t = OLD2NEW[o][0]
        changes.append((f"{o:02d} 节点", f"[{t}]"))
        if t == cur_topic:
            return t
        return f"[{t}]({target_rel(o, src_dir)})"
    text = re.sub(r"(?<![\d\[])(\d{2}) 节点", node_repl, text)

    # 4) 「NN 主题名」
    def topic_repl(m):
        o = int(m.group(1))
        topic = m.group(2)
        if o not in OLD2NEW or OLD2NEW[o][0] != topic:
            return m.group(0)
        changes.append((f"{o:02d} {topic}", f"[{topic}]"))
        if topic == cur_topic:
            return topic
        return f"[{topic}]({target_rel(o, src_dir)})"
    text = re.sub(r"(?<![\d\[])(\d{2}) (" + TOPIC_RE + r")", topic_repl, text)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    lines, planned = [], {}
    for p in CD.rglob("*"):
        if not p.is_file() or p.suffix.lower() != ".md":
            continue
        raw = p.read_text(encoding="utf-8")
        changes = []
        mm = re.match(r"\d{2}_组件设计_(.+)\.md$", p.name)
        cur_topic = mm.group(1) if mm else None
        text = protect(raw, MD_CODE, lambda t: fix_text(t, p.parent, changes, cur_topic))
        if text != raw:
            planned[p] = text
            lines.append(f"-- {p.relative_to(CD)}  ({len(changes)} 处编号引用)")
            for a, b in changes[:20]:
                lines.append(f"     {a}  ->  {b}")
    lines.append(f"合计：{len(planned)} 个文件。")
    if args.dry_run:
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines[:200]))
        print(f"[dry-run] 报告写入 {REPORT}")
        return
    for p, text in planned.items():
        p.write_text(text, encoding="utf-8")
    print(f"完成：改写 {len(planned)} 个文件。")


if __name__ == "__main__":
    main()
