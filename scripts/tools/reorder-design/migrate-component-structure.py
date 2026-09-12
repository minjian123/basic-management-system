#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""migrate-component-structure.py - 组件设计按类别归并 + 每类重排编号 + 链接/引用重指

用户确认的改造：
 1. 组件设计下建立 01_字段类/ 02_展示类/ 03_交互类/ 04_基础类/ 四个类别文件夹；
 2. 既有 20 个节点文件夹移入对应类别，并按类内顺序从 01 重排编号；
 3. 节点文件夹/文件保持「{NN}_组件设计_{主题}」命名，编号随类内重排更新；
 4. 全库 md 链接与 html href/src 按新位置重指（源文件与目标文件均可能移动）；
 5. 链接文字去掉旧编号、导航「← NN-主题 / NN-主题 →」改为「← 主题 / 主题 →」、
    「本篇为组件设计体系X类第 NN 篇」更新为新编号。

不在本脚本范围（后续人工/另一脚本处理）：
 - 正文里「NN 节点」旧编号引用的改名（改为「名称 + 链接」）；
 - 《组件设计 · 总览》路线图表格与 mermaid 重写；
 - 文档首页 / 项目规划说明 / 架构等外部编号引用。

用法：
    python3 migrate-component-structure.py --dry-run
    python3 migrate-component-structure.py
"""
import argparse
import os
import re
import subprocess
import urllib.parse
from pathlib import Path

BMS = Path(__file__).resolve().parents[3]          # bms/
DOC = BMS / "bms文档"
CD = DOC / "设计" / "组件设计"
REPORT = Path("/tmp/opencode/component-migrate-report.txt")
EXISTING = [
    (2,  "字典字段",         "01_字段类", 1),
    (3,  "日期时间字段",     "01_字段类", 2),
    (4,  "数值与金额字段",   "01_字段类", 3),
    (5,  "树选择字段",       "01_字段类", 4),
    (6,  "组织选择字段",     "01_字段类", 5),
    (7,  "文件上传字段",     "01_字段类", 6),
    (8,  "富文本字段",       "01_字段类", 7),
    (9,  "开关与枚举字段",   "01_字段类", 8),
    (10, "通用表格",         "02_展示类", 1),
    (11, "查询筛选区",       "02_展示类", 2),
    (12, "状态标签与描述列表", "02_展示类", 3),
    (13, "图表卡",           "02_展示类", 4),
    (14, "弹窗抽屉表单",     "03_交互类", 1),
    (15, "导入导出",         "03_交互类", 2),
    (16, "审批流展示",       "03_交互类", 3),
    (17, "图标选择器",       "03_交互类", 4),
    (18, "代码表达式编辑器", "03_交互类", 5),
    (19, "请求封装",         "04_基础类", 1),
    (20, "权限指令",         "04_基础类", 2),
    (21, "格式化工具",       "04_基础类", 3),
]
NEW_NODES = [
    ("异常与空状态",     "02_展示类", 5),
    ("通知与消息",       "02_展示类", 6),
    ("全局搜索",         "02_展示类", 7),
    ("文件预览",         "02_展示类", 8),
    ("审计差异查看",     "02_展示类", 9),
    ("表单设计器",       "03_交互类", 6),
    ("流程建模器",       "03_交互类", 7),
    ("权限配置",         "03_交互类", 8),
    ("报表设计器",       "03_交互类", 9),
    ("大屏设计器与播放", "03_交互类", 10),
    ("AI助手",           "03_交互类", 11),
    ("国际化文案编辑器", "03_交互类", 12),
]
CATS = ["01_字段类", "02_展示类", "03_交互类", "04_基础类"]

OLD2NEW = {o: (t, c, n) for (o, t, c, n) in EXISTING}


def old_abs_dir(o, t):
    return CD / f"{o:02d}_组件设计_{t}"


def new_abs_dir(c, n, t):
    return CD / c / f"{n:02d}_组件设计_{t}"


def rename_nn(name, o, n):
    pref = f"{o:02d}_"
    return f"{n:02d}_" + name[len(pref):] if name.startswith(pref) else name


def build_file_map():
    m = {}
    for (o, t, c, n) in EXISTING:
        old_base = old_abs_dir(o, t)
        new_base = new_abs_dir(c, n, t)
        if not old_base.exists():
            continue
        for p in old_base.rglob("*"):
            if p.is_file():
                rel = p.relative_to(old_base)
                new_rel = Path(*[rename_nn(part, o, n) for part in rel.parts])
                m[p.resolve()] = (new_base / new_rel).resolve()
    return m


FILE_MAP = build_file_map()


def map_abs(old_abs: Path):
    try:
        key = old_abs.resolve()
    except OSError:
        return None
    return FILE_MAP.get(key)


def recompute(src_old_dir: Path, src_new_dir: Path, raw: str):
    if not raw or raw.startswith(("#", "/", "http://", "https://", "mailto:", "data:", "javascript:")):
        return None  # 根相对路径与外部协议一律不动
    parts = re.match(r"^([^?#]*)(.*)$", raw, re.S)
    path, suffix = parts.group(1), parts.group(2)
    if not path:
        return None
    old_abs = (src_old_dir / urllib.parse.unquote(path)).resolve()
    moved_target = map_abs(old_abs)
    src_moved = src_old_dir.resolve() != src_new_dir.resolve()
    if moved_target is None and not src_moved:
        return None  # 与迁移无关的链接一律不动（避免误改冗余相对路径）
    new_abs = moved_target or old_abs
    rel = os.path.relpath(new_abs, src_new_dir.resolve()).replace(os.sep, "/")
    new_link = rel + suffix
    return new_link if new_link != raw else None


MD_LINK = re.compile(r"(\]\()([^)\s]+)(\))")


def rewrite(text, src_old_dir, src_new_dir, changes, html=False):
    pat = re.compile(r'(\b(?:href|src)=")([^"]+)(")') if html else MD_LINK

    def repl(m):
        raw = m.group(2)
        new = recompute(src_old_dir, src_new_dir, raw)
        if new:
            changes.append((raw, new))
            return m.group(1) + new + m.group(3)
        return m.group(0)
    return pat.sub(repl, text)


def fix_link_text(text):
    for o, (t, c, n) in OLD2NEW.items():
        text = text.replace(f"[{o:02d} 节点]", f"[{t}]")
        text = text.replace(f"[{o:02d} {t}]", f"[{t}]")
        text = text.replace(f"[← {o:02d}-{t}]", f"[← {t}]")
        text = text.replace(f"[{o:02d}-{t} →]", f"[{t} →]")
    return text


def fix_edition(text):
    def repl(m):
        o = int(m.group(2))
        if o in OLD2NEW:
            t, c, n = OLD2NEW[o]
            return f"组件设计体系{m.group(1)}第 {n:02d} 篇"
        return m.group(0)
    return re.sub(r"组件设计体系(字段类|展示类|交互类|基础类)第 ([0-9]{2}) 篇", repl, text)


def protect(text, pattern, fn):
    """对不参与改写的片段（代码围栏/行内代码、<script> 块）做占位保护后再处理。"""
    store = []

    def save(m):
        store.append(m.group(0))
        return f"\x00{len(store) - 1}\x00"

    protected = re.sub(pattern, save, text, flags=re.S | re.I)
    protected = fn(protected)
    return re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], protected)


MD_CODE = r"```[\s\S]*?```|`[^`\n]*`"


def protect_html(text, fn):
    """保护 <script> 的“体内”内容，但保留开标签（其 src 属性仍需重指）。"""
    store = []

    def save(m):
        store.append(m.group(2))
        return m.group(1) + f"\x00{len(store) - 1}\x00" + m.group(3)

    t = re.sub(r"(<script\b[^>]*>)([\s\S]*?)(</script>)", save, text, flags=re.I)
    t = fn(t)
    return re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lines, total_links, planned = [], 0, {}
    lines.append("== 目录移动 ==")
    for (o, t, c, n) in EXISTING:
        lines.append(f"  {o:02d}_组件设计_{t}  ->  {c}/{n:02d}_组件设计_{t}")

    all_files = [p for p in DOC.rglob("*") if p.is_file() and p.suffix.lower() in (".md", ".html", ".htm")]
    lines.append("\n== 内容变更 ==")
    for p in all_files:
        under = None
        for (o, t, c, n) in EXISTING:
            try:
                p.relative_to(old_abs_dir(o, t))
                under = (o, t, c, n)
                break
            except ValueError:
                pass
        if under:
            o, t, c, n = under
            src_old_dir, src_new_dir = old_abs_dir(o, t), new_abs_dir(c, n, t)
            new_path = src_new_dir / p.relative_to(src_old_dir).parent / rename_nn(p.name, o, n)
        else:
            src_old_dir = src_new_dir = p.parent
            new_path = p
        changes = []
        raw = p.read_text(encoding="utf-8")
        is_html = p.suffix.lower() in (".html", ".htm")

        def transform(t):
            t = rewrite(t, src_old_dir, src_new_dir, changes, html=is_html)
            return fix_edition(fix_link_text(t))

        text = protect_html(raw, transform) if is_html else protect(raw, MD_CODE, transform)
        if text != raw or new_path != p:
            planned[p] = (new_path, text, changes)
            total_links += len(changes)
            if changes:
                lines.append(f"\n-- {p.relative_to(DOC)}  ({len(changes)} 处)")
                for a, b in changes[:25]:
                    lines.append(f"     {a}  ->  {b}")
                if len(changes) > 25:
                    lines.append(f"     ... 另有 {len(changes)-25} 处")

    lines.append(f"\n合计：{len(planned)} 个文件将移动/改写，{total_links} 处链接重写。")

    if args.dry_run:
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines[:100]))
        print(f"\n[dry-run] 报告写入 {REPORT}（{len(lines)} 行）")
        return

    # 执行：git mv 目录 -> 重命名内部 NN 前缀 -> 写内容
    for (o, t, c, n) in EXISTING:
        (CD / c).mkdir(exist_ok=True)
        old, new = old_abs_dir(o, t), new_abs_dir(c, n, t)
        subprocess.run(["git", "mv", str(old), str(new)], cwd=BMS, check=True)
    for (o, t, c, n) in EXISTING:
        base = new_abs_dir(c, n, t)
        targets = sorted(base.rglob("*"), key=lambda x: len(x.parts), reverse=True)
        for p in targets:
            if p.name.startswith(f"{o:02d}_"):
                subprocess.run(["git", "mv", str(p), str(p.with_name(rename_nn(p.name, o, n)))], cwd=BMS, check=True)
    for old_path, (new_path, text, _) in planned.items():
        target = new_path if new_path.exists() else old_path
        target.write_text(text, encoding="utf-8")
    print(f"迁移完成：移动 {len(EXISTING)} 个节点，改写 {len(planned)} 个文件。")


if __name__ == "__main__":
    main()
