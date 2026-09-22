#!/usr/bin/env python3
"""基座完整性校验（bms 权威源侧，CI 与本地运行）。

校验五项：
  1. 基座文件不含跨层相对链接（指向平台专属 `bms文档/规划`、`bms文档/项目`、`bms文档/设计`）；
  2. 基座文件不含项目专属措辞残留（`BMS 项目`、`在 BMS`、`本项目项目`）；
  3. 《基座文档清单》与磁盘一致：清单登记的基座文件均存在，且数量与扫描结果一致；
  4. 跨文档引用不得只写编号：指向另一份文档的引用应写章节名（编号随目标文档重排会静默错指）；
     同文档内引用不受限（同一文件内编号与标题同步修改）；
  5. 数据库设计登记一致：《数据库设计总览》「已设计数据表登记」与 `数据表设计/` 目录双向一致且
     状态与表文件一致；「方言特性登记」与 `方言特性/` 目录双向一致。

自检（反例驱动）：`python3 check-base.py --self-test` 校验第 5 项的纯函数（正常 + 3 个反例）。

**链接自洽检查已拆出**：见同目录 `check-links.py`（本地手工跑，不挂 CI）——
链接校验约束太强会逼着文档少写导航链接、损害阅读，故不再作为 CI 强制项。

任一项不通过则退出码 1。工作区模型下基座不再向产品仓库复制/同步，产品侧以符号链接引用基座。
"""
import os
import re
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
MANIFEST = "bms文档/基座文档清单.md"
BASE_DIRS = [
    "bms文档/规范", "bms文档/资源", "bms文档/资料/AI", "bms文档/资料/工具",
    "bms文档/资料/开发服务器", "bms文档/资料/开发机", "bms文档/资料/知识档案",
    "bms文档/资料/审计",
]
# ② 各仓库自带副本：登记但不参与校验（已 gitignore，工作区中可能不存在）
LOCAL_ONLY = ("bms文档/用户文档/",)
CROSS_LAYER = ("bms文档/规划/", "bms文档/项目/", "bms文档/设计/", "bms文档/需求/", "bms文档/任务/")
BAD_WORDING = ("BMS 项目", "在 BMS", "本项目项目")
LINK_RE = re.compile(r'\]\(([^)\s]+)\)')
CODE_RE = re.compile(r'`[^`]*`')

problems = []


def strip_code(line):
    return CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def check_cross_layer():
    n = 0
    for d in BASE_DIRS:
        for dp, _, fs in os.walk(os.path.join(ROOT, d)):
            for f in fs:
                if not f.endswith(".md"):
                    continue
                p = os.path.join(dp, f)
                for i, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
                    for m in LINK_RE.finditer(strip_code(line)):
                        t = m.group(1).strip().lstrip("?")
                        if t.startswith(("http", "mailto")) or not t.split("#")[0].endswith((".md", ".html")):
                            continue
                        ab = os.path.relpath(os.path.normpath(os.path.join(dp, t.split("#")[0])), ROOT)
                        if ab.replace(os.sep, "/").startswith(CROSS_LAYER) or ab.count(os.sep) == 0 and ab.startswith("bms文档/"):
                            if any(ab.replace(os.sep, "/") == b.rstrip("/") for b in CROSS_LAYER) or \
                               ab.replace(os.sep, "/").startswith(CROSS_LAYER):
                                problems.append(f"[跨层引用] {os.path.relpath(p, ROOT)}:{i} -> {t}")
                                n += 1
    print(f"1. 基座跨层引用：{n} 处（应为 0，跨层一律写「平台《文档名》」）")


def check_wording():
    n = 0
    for d in BASE_DIRS:
        for dp, _, fs in os.walk(os.path.join(ROOT, d)):
            for f in fs:
                if not f.endswith(".md"):
                    continue
                p = os.path.join(dp, f)
                for i, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
                    for w in BAD_WORDING:
                        if w in line:
                            problems.append(f"[措辞残留] {os.path.relpath(p, ROOT)}:{i} 含「{w}」")
                            n += 1
    print(f"2. 项目专属措辞残留：{n} 处（应为 0）")


def manifest_files():
    txt = open(os.path.join(ROOT, MANIFEST), encoding="utf-8").read()
    m = re.search(r'```text\n(.*?)```', txt, re.S)
    if not m:
        return []
    stack, out = [], []
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        mm = re.match(r'^([│\s]*)(?:├──|└──)\s+(.+?)\s*$', line)
        if not mm:
            continue
        depth = len(mm.group(1)) // 4
        name = mm.group(2).split("#")[0].strip()
        stack = stack[:depth]
        if name.endswith("/"):
            stack.append(name.rstrip("/"))
        else:
            out.append("bms文档/" + "/".join(stack + [name]))
    return out


def check_manifest():
    entries = [e for e in manifest_files() if not e.startswith(LOCAL_ONLY)]
    missing = [e for e in entries if not os.path.exists(os.path.join(ROOT, e))]
    disk = 0
    for d in BASE_DIRS:
        for _, _, fs in os.walk(os.path.join(ROOT, d)):
            disk += len(fs)
    for e in missing:
        problems.append(f"[清单缺文件] {MANIFEST} 登记但磁盘不存在：{e}")
    if disk != len(entries):
        problems.append(f"[清单数量不符] 清单登记 {len(entries)} 个，磁盘 {disk} 个（新增/删除基座文件后须同步更新第 2 节清单）")
    print(f"3. 清单一致：登记 {len(entries)} 个，磁盘 {disk} 个，缺失 {len(missing)} 个")


def check_section_refs():
    """跨文档引用若只写编号（第 N 节 / N.M 节 / N 章）即报警。"""
    # 必须有“节/章”字样才判定，避免命中「《X》2026 版」这类非引用文本
    REF_RE = re.compile(r'《(.+?)》[）)，、\s]*(?:第\s*\d+(?:\.\d+)?\s*[章节]|\d+(?:\.\d+)?\s*[章节])')
    n = 0
    for dp, dns, fs in os.walk(os.path.join(ROOT, "bms文档")):
        dns[:] = [d for d in dns if d not in {".git"}]
        for f in fs:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT)
            stem = f[:-3]
            for i, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
                for m in REF_RE.finditer(strip_code(line)):
                    raw = m.group(1)
                    name = raw.split("]")[0].lstrip("[") if "]" in raw else raw
                    name = name.strip()
                    # 同文档内自引不受限（编号与标题在同一文件内同步修改）
                    if name == stem or name.replace(" ", "") == stem or stem in name or name in stem:
                        continue
                    problems.append(f"[编号引用] {rel}:{i} -> {m.group(0)[:60]}（跨文档引用请写章节名）")
                    n += 1
    print(f"4. 跨文档编号引用：{n} 处（应为 0，跨文档引用优先写章节名）")


DESIGN_DIR = "bms文档/设计/数据库设计"
OVERVIEW = DESIGN_DIR + "/01_数据库设计_总览.md"
TABLE_SUBDIR = "数据表设计"
DIALECT_SUBDIR = "方言特性"
STATUS_VALUES = ("已设计", "待落库", "已落库", "已废弃")
STATUS_RE = re.compile(r'^\|\s*状态\s*\|\s*([^|]+?)\s*\|')


def parse_design_overview(text):
    """解析总览登记表：返回（表登记 {表名: 状态}, 方言登记 {文件名: 状态}）。"""
    tables, dialects = {}, {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if f"{TABLE_SUBDIR}/" in cells[1]:
            tables[cells[0].strip("`")] = cells[-1]
        elif f"{DIALECT_SUBDIR}/" in cells[1]:
            m = re.search(rf'\({DIALECT_SUBDIR}/([^)]+)\)', cells[1])
            if m:
                dialects[m.group(1)] = cells[-1]
    return tables, dialects


def status_head(value):
    """取状态首值（四值枚举；括号补充不计）。"""
    return re.split(r"[（(]", value.strip())[0].strip()


def diff_design_registry(overview_text, table_files, dialect_files, table_status):
    """纯函数：比对总览登记与目录 / 表文件状态，返回问题清单。

    Args:
        overview_text: 总览文档全文。
        table_files: `数据表设计/` 下的文件名集合（含 `.md`）。
        dialect_files: `方言特性/` 下的文件名集合（含 `.md`）。
        table_status: `{表名: 状态值}`（取自各表文件「归属与依据」表）。
    """
    tables, dialects = parse_design_overview(overview_text)
    out = []
    for name, status in sorted(tables.items()):
        fname = f"{name}.md"
        if fname not in table_files:
            out.append(f"[表文件缺失] 总览登记 `{name}` 但 `{TABLE_SUBDIR}/{fname}` 不存在")
            continue
        actual = table_status.get(name)
        if actual is None:
            out.append(f"[表文件缺状态] `{TABLE_SUBDIR}/{fname}` 无「状态」行")
            continue
        if status_head(actual) != status_head(status):
            out.append(
                f"[状态不一致] `{name}`：总览登记「{status_head(status)}」/ 表文件「{status_head(actual)}」"
            )
        if status_head(status) not in STATUS_VALUES:
            out.append(f"[状态取值非法] `{name}`：{status_head(status)}（须为 {' / '.join(STATUS_VALUES)}）")
    for fname in sorted(table_files):
        name = fname[:-3]
        if name not in tables:
            out.append(f"[未登记表文件] `{TABLE_SUBDIR}/{fname}` 未在总览「已设计数据表登记」登记")
    for fname in sorted(dialects):
        if fname not in dialect_files:
            out.append(f"[方言文件缺失] 总览登记 `{fname}` 但 `{DIALECT_SUBDIR}/{fname}` 不存在")
    for fname in sorted(dialect_files):
        if fname not in dialects:
            out.append(f"[未登记方言文件] `{DIALECT_SUBDIR}/{fname}` 未在总览「方言特性登记」登记")
    return out


def read_table_status(path):
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            m = STATUS_RE.match(strip_code(line.strip()))
            if m:
                return m.group(1).strip()
    return None


def list_md(path):
    if not os.path.isdir(path):
        return set()
    return {f for f in os.listdir(path) if f.endswith(".md")}


def check_design_registry():
    overview_path = os.path.join(ROOT, OVERVIEW)
    if not os.path.exists(overview_path):
        print(f"5. 数据库设计登记一致：跳过（{OVERVIEW} 不存在）")
        return
    with open(overview_path, encoding="utf-8", errors="ignore") as fh:
        text = fh.read()
    table_dir = os.path.join(ROOT, DESIGN_DIR, TABLE_SUBDIR)
    dialect_dir = os.path.join(ROOT, DESIGN_DIR, DIALECT_SUBDIR)
    files, dialect_files = list_md(table_dir), list_md(dialect_dir)
    status = {f[:-3]: read_table_status(os.path.join(table_dir, f)) or "" for f in files}
    found = diff_design_registry(text, files, dialect_files, status)
    problems.extend(f"[设计登记] {x}" for x in found)
    print(f"5. 数据库设计登记一致：{len(found)} 处问题（表文件 {len(files)} 个 / 方言特性 {len(dialect_files)} 个）")


def self_test():
    """第 5 项纯函数自检：1 正常 + 3 反例。"""
    ok_overview = """
| 表 | 数据表文件 | 所属库 | 模块 | 状态 |
| --- | --- | --- | --- | --- |
| sys_tenant | [sys_tenant.md](数据表设计/sys_tenant.md) | 平台库 | 26-租户管理 | 已落库 |

| 库 | 方言特性文件 | 适用版本 | 应用侧驱动 | 状态 |
| --- | --- | --- | --- | --- |
| MySQL | [01_MySQL.md](方言特性/01_MySQL.md) | 8.x | `aiomysql` | 已实测 |
"""
    cases = [
        ("正常：登记与目录 / 状态一致", ok_overview,
         {"sys_tenant.md"}, {"01_MySQL.md"}, {"sys_tenant": "已落库（平台链迁移，2026-09-22）"}, 0),
        ("反例 A：目录多出未登记表文件", ok_overview,
         {"sys_tenant.md", "sys_module.md"}, {"01_MySQL.md"}, {"sys_tenant": "已落库"}, 1),
        ("反例 B：总览状态与表文件状态不一致", ok_overview,
         {"sys_tenant.md"}, {"01_MySQL.md"}, {"sys_tenant": "待落库"}, 1),
        ("反例 C：方言特性目录多出未登记文件", ok_overview,
         {"sys_tenant.md"}, {"01_MySQL.md", "02_PostgreSQL.md"}, {"sys_tenant": "已落库"}, 1),
    ]
    bad = 0
    for title, overview, tables, dialects, status, expect in cases:
        got = diff_design_registry(overview, tables, dialects, status)
        flag = "OK" if len(got) == expect else "FAIL"
        bad += flag == "FAIL"
        print(f"  [{flag}] {title}：期望 {expect} 项，实得 {len(got)} 项")
        for g in got:
            print(f"        {g}")
    print(f"\n[base-integrity self-test] {'通过' if not bad else '不通过'}：第 5 项断言用例 {len(cases)} 个")
    return 1 if bad else 0


def main():
    check_cross_layer()
    check_wording()
    check_manifest()
    check_section_refs()
    check_design_registry()
    if problems:
        print(f"\n[base-integrity] 不通过：{len(problems)} 项")
        for p in problems[:50]:
            print("  " + p)
        if len(problems) > 50:
            print(f"  ... 其余 {len(problems) - 50} 项")
        sys.exit(1)
    print("\n[base-integrity] 通过：无跨层引用、无措辞残留、清单与磁盘一致、跨文档引用均写章节名、数据库设计登记一致。"
          "\n（链接自洽不在本脚本：需要时手工跑 scripts/tools/base-check/check-links.py）")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    main()
