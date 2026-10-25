#!/usr/bin/env python3
"""基座完整性校验（bms 权威源侧，CI 与本地运行）。

校验六项：
  1. 基座文件不含跨层相对链接（指向平台专属 `bms文档/规划`、`bms文档/项目`、`bms文档/设计`）；
  2. 基座文件不含项目专属措辞残留（`BMS 项目`、`在 BMS`、`本项目项目`）；
  3. 《基座文档清单》与磁盘一致：清单登记的基座文件均存在，且数量与扫描结果一致；
  4. 跨文档引用不得只写编号：指向另一份文档的引用应写章节名（编号随目标文档重排会静默错指）；
     同文档内引用不受限（同一文件内编号与标题同步修改）；
  5. 数据库设计登记一致：《数据库设计总览》「已设计数据表登记」与 `数据表设计/` 目录双向一致且
     状态与表文件一致；「方言特性登记」与 `方言特性/` 目录双向一致；
  6. **登记面命名形态**：登记型标识一律 snake_case（《命名规范》「大小写风格」节）——只扫**登记面**
     （`scripts/tools/*` 目录与脚本名、`frontend/{packages,modules}/*` 包目录与包名、
     `backend/alembic/versions/*` 清单目录），以及**运行期登记值**（后端 `fieldtype` 的 `widget` 字面量、
     前端 `FIELD_WIDGETS` 控件语义键、业务码 / 动作码 `pattern`、自建图标码 `_ICON_CODE_RE`），
     **不扫**源码文本、注释、前端路由 path、CSS 类、HTML 属性、文档文件名与正文（这些不参与登记与解析，
     受各自生态约定约束）。

自检（反例驱动）：`python3 check_base.py --self-test` 校验第 5、6 项的纯函数（正常 + 反例）。

**链接自洽检查已拆出**：见同目录 `check_links.py`（本地手工跑，不挂 CI）——
链接校验约束太强会逼着文档少写导航链接、损害阅读，故不再作为 CI 强制项。

任一项不通过则退出码 1。工作区模型下基座不再向产品仓库复制/同步，产品侧以符号链接引用基座。
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
MANIFEST = "bms文档/基座文档清单.md"
BASE_DIRS = [
    "bms文档/规范",
    "bms文档/资源",
    "bms文档/资料/AI",
    "bms文档/资料/工具",
    "bms文档/资料/开发服务器",
    "bms文档/资料/开发机",
    "bms文档/资料/知识档案",
    "bms文档/资料/审计",
]
# ② 各仓库自带副本：登记但不参与校验（已 gitignore，工作区中可能不存在）
LOCAL_ONLY = ("bms文档/用户文档/",)
CROSS_LAYER = (
    "bms文档/规划/",
    "bms文档/项目/",
    "bms文档/设计/",
    "bms文档/需求/",
    "bms文档/任务/",
)
BAD_WORDING = ("BMS 项目", "在 BMS", "本项目项目")
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
CODE_RE = re.compile(r"`[^`]*`")

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
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    for i, line in enumerate(fh, 1):
                        for m in LINK_RE.finditer(strip_code(line)):
                            t = m.group(1).strip().lstrip("?")
                            if t.startswith(("http", "mailto")) or not t.split("#")[0].endswith((".md", ".html")):
                                continue
                            ab = os.path.relpath(
                                os.path.normpath(os.path.join(dp, t.split("#")[0])),
                                ROOT,
                            )
                            is_cross = ab.replace(os.sep, "/").startswith(CROSS_LAYER) or (
                                ab.count(os.sep) == 0 and ab.startswith("bms文档/")
                            )
                            if is_cross and (
                                any(ab.replace(os.sep, "/") == b.rstrip("/") for b in CROSS_LAYER)
                                or ab.replace(os.sep, "/").startswith(CROSS_LAYER)
                            ):
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
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    for i, line in enumerate(fh, 1):
                        for w in BAD_WORDING:
                            if w in line:
                                problems.append(f"[措辞残留] {os.path.relpath(p, ROOT)}:{i} 含「{w}」")
                                n += 1
    print(f"2. 项目专属措辞残留：{n} 处（应为 0）")


def manifest_files():
    txt = Path(os.path.join(ROOT, MANIFEST)).read_text(encoding="utf-8")
    m = re.search(r"```text\n(.*?)```", txt, re.S)
    if not m:
        return []
    stack, out = [], []
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        mm = re.match(r"^([│\s]*)(?:├──|└──)\s+(.+?)\s*$", line)
        if not mm:
            continue
        depth = len(mm.group(1)) // 4
        name = mm.group(2).split("#")[0].strip()
        stack = stack[:depth]
        if name.endswith("/"):
            stack.append(name.rstrip("/"))
        else:
            out.append("bms文档/" + "/".join([*stack, name]))
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
        problems.append(
            f"[清单数量不符] 清单登记 {len(entries)} 个，磁盘 {disk} 个（新增/删除基座文件后须同步更新第 2 节清单）"
        )
    print(f"3. 清单一致：登记 {len(entries)} 个，磁盘 {disk} 个，缺失 {len(missing)} 个")


def check_section_refs():
    """跨文档引用若只写编号（第 N 节 / N.M 节 / N 章）即报警。"""
    # 必须有“节/章”字样才判定，避免命中「《X》2026 版」这类非引用文本
    REF_RE = re.compile(r"《(.+?)》[）)，、\s]*(?:第\s*\d+(?:\.\d+)?\s*[章节]|\d+(?:\.\d+)?\s*[章节])")
    n = 0
    for dp, dns, fs in os.walk(os.path.join(ROOT, "bms文档")):
        dns[:] = [d for d in dns if d not in {".git"}]
        for f in fs:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT)
            stem = f[:-3]
            with open(p, encoding="utf-8", errors="ignore") as fh:
                for i, line in enumerate(fh, 1):
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
STATUS_RE = re.compile(r"^\|\s*状态\s*\|\s*([^|]+?)\s*\|")


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
            m = re.search(rf"\({DIALECT_SUBDIR}/([^)]+)\)", cells[1])
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
            out.append(f"[状态不一致] `{name}`：总览登记「{status_head(status)}」/ 表文件「{status_head(actual)}」")
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


# ---- ⑥ 登记面命名形态（01_07 命名收口：登记型标识一律 snake_case） ----

NAMING_TOOL_ROOT = "scripts/tools"
"""工具链根（工具目录名与 `.py` / `.sh` 文件名纳入登记面）。"""

NAMING_PACKAGE_ROOTS = ("frontend/packages", "frontend/modules")
"""前端包根（包目录名与 `package.json` 的 `name` 纳入登记面）。"""

NAMING_VERSIONS_ROOT = "backend/alembic/versions"
"""表结构变更清单根（清单目录名纳入登记面；域标识由迁移注册表校验）。"""

DIR_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""目录 / 业务域标识形态（小写字母开头，仅小写字母、数字与下划线）。"""

SCRIPT_STEM_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
"""工具脚本文件名主体形态（不含扩展名）。"""


def _sub_dirs(path):
    """目录下的一级子目录名（不存在返回空列表）。

    Args:
        path: 目录路径。

    Returns:
        list[str]: 子目录名（字典序）。
    """
    if not os.path.isdir(path):
        return []
    return sorted(name for name in os.listdir(path) if os.path.isdir(os.path.join(path, name)))


def _is_ascii(text):
    """是否全 ASCII（中文名脚本按既有约定豁免改名）。

    Args:
        text: 待判定文本。

    Returns:
        bool: 全 ASCII 为 True。
    """
    return all(ord(char) < 128 for char in text)


def _package_name(manifest):
    """读 `package.json` 的 `name` 字段（缺失 / 非法返回空串）。

    Args:
        manifest: `package.json` 路径。

    Returns:
        str: 包名；读不到返回空串。
    """
    try:
        with open(manifest, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError, ValueError:
        return ""
    name = data.get("name") if isinstance(data, dict) else ""
    return name.strip() if isinstance(name, str) else ""


def naming_problems(root):
    """登记面命名形态问题清单（只扫登记面，不扫源码 / 文档 / 前端路由与样式）。

    Args:
        root: 仓库根。

    Returns:
        list[str]: 问题明细（空列表表示通过）。
    """
    found = []
    for name in _sub_dirs(os.path.join(root, NAMING_TOOL_ROOT)):
        if not DIR_IDENT_RE.match(name):
            found.append(f"[命名] 工具目录名须为 snake_case：{NAMING_TOOL_ROOT}/{name}")
    for dirpath, _dirnames, filenames in os.walk(os.path.join(root, NAMING_TOOL_ROOT)):
        for filename in sorted(filenames):
            stem, dot, ext = filename.rpartition(".")
            if ext not in ("py", "sh") or not dot or not _is_ascii(stem):
                continue
            if not SCRIPT_STEM_RE.match(stem):
                relative = os.path.relpath(os.path.join(dirpath, filename), root).replace(os.sep, "/")
                found.append(f"[命名] 工具脚本名须为 snake_case：{relative}")
    for package_root in NAMING_PACKAGE_ROOTS:
        base = os.path.join(root, package_root)
        for name in _sub_dirs(base):
            if not DIR_IDENT_RE.match(name):
                found.append(f"[命名] 前端包目录名须为 snake_case：{package_root}/{name}")
            package_name = _package_name(os.path.join(base, name, "package.json"))
            if package_name and "-" in package_name:
                found.append(f"[命名] 包名须为 snake_case（不含连字符）：{package_name}（{package_root}/{name}）")
    for name in _sub_dirs(os.path.join(root, NAMING_VERSIONS_ROOT)):
        if not DIR_IDENT_RE.match(name):
            found.append(f"[命名] 清单目录名须为 snake_case：{NAMING_VERSIONS_ROOT}/{name}")
    return found


# ---- ⑥-2 运行期登记值形态（01_08：控件语义键 / 业务动作码 / 自建图标码） ----

RUNTIME_FIELD_WIDGETS_PY = "backend/libs/bms_core/src/bms_core/fieldtype/local.py"
"""后端字段类型注册表（`widget=` 字面量纳入登记面）。"""

RUNTIME_FIELD_WIDGETS_TS = "frontend/packages/core/src/domain/form-render.ts"
"""前端控件语义键全量清单（`FIELD_WIDGETS` 纳入登记面）。"""

RUNTIME_CODE_SCHEMA_PY = "backend/services/platform/src/bms_platform/domains/permission_meta/schemas/permission_meta.py"
"""业务码 / 动作码契约（`code` 字段 `pattern` 纳入登记面）。"""

RUNTIME_ICON_BASE_PY = "backend/libs/bms_core/src/bms_core/icon/base.py"
"""自建图标码校验基座（`_ICON_CODE_RE` 纳入登记面）。"""

SNAKE_PATTERN = r"^[a-z][a-z0-9_]*$"
"""登记值形态（小写字母开头，仅小写字母、数字与下划线）。"""

WIDGET_LITERAL_RE = re.compile(r'widget="([^"]+)"')
"""后端 `widget="…"` 字面量。"""

FIELD_WIDGETS_BLOCK_RE = re.compile(r"export const FIELD_WIDGETS[^=]*=\s*\[(.*?)\]", re.DOTALL)
"""前端 `FIELD_WIDGETS` 数组块。"""

TS_WIDGET_RE = re.compile(r"'([^']+)'")
"""前端块内单引号字符串。"""

CODE_FIELD_PATTERN_RE = re.compile(r'code: str = Field\(\s*min_length=1,\s*max_length=64,\s*pattern=r"([^"]+)"')
"""业务码 / 动作码 `code` 字段的 `pattern`。"""

ICON_CODE_PATTERN_RE = re.compile(r'_ICON_CODE_RE = re\.compile\(r"([^"]+)"\)')
"""自建图标码正则。"""


def _read_text(path):
    """读文本文件（不存在返回 `None`）。

    Args:
        path: 文件路径。

    Returns:
        str | None: 文本；不存在或不可读返回 `None`。
    """
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def runtime_identifier_problems(root):
    """运行期登记值形态问题清单（控件语义键 / 业务动作码 / 自建图标码）。

    只扫三处登记面（后端字段类型注册表、前端 `FIELD_WIDGETS`、权限元数据契约与图标基座），
    不扫业务源码字符串、CSS 类、路由 path 与 `data-*` 属性值。

    Args:
        root: 仓库根。

    Returns:
        list[str]: 问题明细（空列表表示通过）。
    """
    found = []
    widgets_py = _read_text(os.path.join(root, RUNTIME_FIELD_WIDGETS_PY))
    if widgets_py is not None:
        literals = WIDGET_LITERAL_RE.findall(widgets_py)
        if not literals:
            found.append(f"[命名] 未找到后端控件语义键字面量：{RUNTIME_FIELD_WIDGETS_PY}")
        for literal in literals:
            if not DIR_IDENT_RE.match(literal):
                found.append(f'[命名] 控件语义键须为 snake_case：{RUNTIME_FIELD_WIDGETS_PY} widget="{literal}"')
    widgets_ts = _read_text(os.path.join(root, RUNTIME_FIELD_WIDGETS_TS))
    if widgets_ts is not None:
        block = FIELD_WIDGETS_BLOCK_RE.search(widgets_ts)
        if block is None:
            found.append(f"[命名] 未找到前端控件语义键清单 FIELD_WIDGETS：{RUNTIME_FIELD_WIDGETS_TS}")
        else:
            for literal in TS_WIDGET_RE.findall(block.group(1)):
                if not DIR_IDENT_RE.match(literal):
                    found.append(f"[命名] 控件语义键须为 snake_case：{RUNTIME_FIELD_WIDGETS_TS} '{literal}'")
    code_schema = _read_text(os.path.join(root, RUNTIME_CODE_SCHEMA_PY))
    if code_schema is not None:
        patterns = CODE_FIELD_PATTERN_RE.findall(code_schema)
        if len(patterns) < 2:
            found.append(f"[命名] 未找到业务码 / 动作码两处 code pattern：{RUNTIME_CODE_SCHEMA_PY}")
        for pattern in patterns:
            if pattern != SNAKE_PATTERN:
                found.append(
                    f"[命名] 业务码 / 动作码 pattern 须为 {SNAKE_PATTERN}：{RUNTIME_CODE_SCHEMA_PY} "
                    f'pattern=r"{pattern}"'
                )
    icon_base = _read_text(os.path.join(root, RUNTIME_ICON_BASE_PY))
    if icon_base is not None:
        icon_pattern = ICON_CODE_PATTERN_RE.search(icon_base)
        if icon_pattern is None:
            found.append(f"[命名] 未找到自建图标码正则 _ICON_CODE_RE：{RUNTIME_ICON_BASE_PY}")
        elif icon_pattern.group(1) != SNAKE_PATTERN:
            found.append(
                f'[命名] 自建图标码正则须为 {SNAKE_PATTERN}：{RUNTIME_ICON_BASE_PY} r"{icon_pattern.group(1)}"'
            )
    return found


def check_naming():
    """第 6 项：登记面命名形态（登记目录 / 包名 / 工具脚本名 + 运行期登记值）。"""
    found = naming_problems(ROOT) + runtime_identifier_problems(ROOT)
    problems.extend(found)
    print(
        f"6. 登记面命名形态：{len(found)} 处（应为 0，登记目录 / 包名 / 脚本名与控件键 / 业务动作码 / "
        "自建图标码一律 snake_case）"
    )


def self_test():
    """第 5、6 项纯函数自检：正常 + 反例。"""
    ok_overview = """
| 表 | 数据表文件 | 所属库 | 模块 | 状态 |
| --- | --- | --- | --- | --- |
| sys_tenant | [sys_tenant.md](数据表设计/sys_tenant.md) | 平台库 | 26-租户管理 | 已落库 |

| 库 | 方言特性文件 | 适用版本 | 应用侧驱动 | 状态 |
| --- | --- | --- | --- | --- |
| MySQL | [01_MySQL.md](方言特性/01_MySQL.md) | 8.x | `aiomysql` | 已实测 |
"""
    cases = [
        (
            "正常：登记与目录 / 状态一致",
            ok_overview,
            {"sys_tenant.md"},
            {"01_MySQL.md"},
            {"sys_tenant": "已落库（平台链迁移，2026-09-22）"},
            0,
        ),
        (
            "反例 A：目录多出未登记表文件",
            ok_overview,
            {"sys_tenant.md", "sys_module.md"},
            {"01_MySQL.md"},
            {"sys_tenant": "已落库"},
            1,
        ),
        (
            "反例 B：总览状态与表文件状态不一致",
            ok_overview,
            {"sys_tenant.md"},
            {"01_MySQL.md"},
            {"sys_tenant": "待落库"},
            1,
        ),
        (
            "反例 C：方言特性目录多出未登记文件",
            ok_overview,
            {"sys_tenant.md"},
            {"01_MySQL.md", "02_PostgreSQL.md"},
            {"sys_tenant": "已落库"},
            1,
        ),
    ]
    bad = 0
    for title, overview, tables, dialects, status, expect in cases:
        got = diff_design_registry(overview, tables, dialects, status)
        flag = "OK" if len(got) == expect else "FAIL"
        bad += flag == "FAIL"
        print(f"  [{flag}] {title}：期望 {expect} 项，实得 {len(got)} 项")
        for g in got:
            print(f"        {g}")
    naming_cases = naming_self_test()
    bad += naming_cases
    total = len(cases) + NAMING_CASES
    print(
        f"\n[base-integrity self-test] {'通过' if not bad else '不通过'}：第 5、6 项断言用例共 {total} 个"
        f"（第 6 项 {NAMING_CASES} 个）"
    )
    return 1 if bad else 0


NAMING_CASES = 11
"""第 6 项自检用例数（登记面 6 个 + 运行期登记值 5 个）。"""


def _build_naming_tree(root, *, tool_dir, script, package_dir, package_name, version_dir):
    """按给定名称搭一棵最小仓库树（自检夹具）。

    Args:
        root: 临时仓库根。
        tool_dir: `scripts/tools/` 下的目录名。
        script: 该目录下的脚本文件名。
        package_dir: `frontend/packages/` 下的目录名。
        package_name: 包名（写 `package.json`）。
        version_dir: `backend/alembic/versions/` 下的清单目录名。
    """
    os.makedirs(os.path.join(root, NAMING_TOOL_ROOT, tool_dir), exist_ok=True)
    with open(os.path.join(root, NAMING_TOOL_ROOT, tool_dir, script), "w", encoding="utf-8") as handle:
        handle.write("")
    package_path = os.path.join(root, NAMING_PACKAGE_ROOTS[0], package_dir)
    os.makedirs(package_path, exist_ok=True)
    with open(os.path.join(package_path, "package.json"), "w", encoding="utf-8") as handle:
        json.dump({"name": package_name}, handle)
    os.makedirs(os.path.join(root, NAMING_VERSIONS_ROOT, version_dir), exist_ok=True)


def _build_runtime_tree(root, *, widgets, ts_widgets, code_patterns, icon_pattern):
    """搭运行期登记值自检夹具（字段类型注册表 / 前端清单 / 权限契约 / 图标基座）。

    Args:
        root: 临时仓库根。
        widgets: 后端 `widget=` 字面量清单。
        ts_widgets: 前端 `FIELD_WIDGETS` 取值清单。
        code_patterns: 业务码 / 动作码 `pattern` 清单。
        icon_pattern: 自建图标码正则文本。
    """
    fieldtype = os.path.join(root, RUNTIME_FIELD_WIDGETS_PY)
    os.makedirs(os.path.dirname(fieldtype), exist_ok=True)
    with open(fieldtype, "w", encoding="utf-8") as handle:
        for widget in widgets:
            handle.write(f'SimpleFieldType(key="x", widget="{widget}")\n')
    render_ts = os.path.join(root, RUNTIME_FIELD_WIDGETS_TS)
    os.makedirs(os.path.dirname(render_ts), exist_ok=True)
    with open(render_ts, "w", encoding="utf-8") as handle:
        handle.write("export const FIELD_WIDGETS: readonly FormWidget[] = [\n")
        for widget in ts_widgets:
            handle.write(f"  '{widget}',\n")
        handle.write("]\n")
    code_schema = os.path.join(root, RUNTIME_CODE_SCHEMA_PY)
    os.makedirs(os.path.dirname(code_schema), exist_ok=True)
    with open(code_schema, "w", encoding="utf-8") as handle:
        for pattern in code_patterns:
            handle.write(
                "    code: str = Field(\n"
                "        min_length=1,\n"
                "        max_length=64,\n"
                f'        pattern=r"{pattern}",\n'
                '        description="码值",\n'
                "    )\n"
            )
    icon_base = os.path.join(root, RUNTIME_ICON_BASE_PY)
    os.makedirs(os.path.dirname(icon_base), exist_ok=True)
    with open(icon_base, "w", encoding="utf-8") as handle:
        handle.write(f'_ICON_CODE_RE = re.compile(r"{icon_pattern}")\n')


def naming_self_test():
    """第 6 项自检：登记面 6 例 + 运行期登记值 5 例。

    Returns:
        int: 失败用例数。
    """
    ok = {
        "tool_dir": "base_check",
        "script": "check_base.py",
        "package_dir": "ui_ep",
        "package_name": "@bms/ui_ep",
        "version_dir": "user",
    }
    cases = [
        ("正例：全 snake_case 通过", ok, 0),
        ("反例 A：工具目录连字符", {**ok, "tool_dir": "bad-name"}, 1),
        ("反例 B：工具脚本连字符", {**ok, "script": "check-bad.py"}, 1),
        (
            "反例 C：前端包目录与包名连字符",
            {**ok, "package_dir": "bad-name", "package_name": "@bms/bad-name"},
            2,
        ),
        ("反例 D：清单目录连字符", {**ok, "version_dir": "Bad-Name"}, 1),
        ("正例：中文名脚本豁免", {**ok, "script": "安装-重启.py"}, 0),
    ]
    bad = 0
    for title, spec, expect in cases:
        with tempfile.TemporaryDirectory() as root:
            _build_naming_tree(root, **spec)
            got = naming_problems(root)
        flag = "OK" if len(got) == expect else "FAIL"
        bad += flag == "FAIL"
        print(f"  [{flag}] {title}：期望 {expect} 项，实得 {len(got)} 项")
        for g in got:
            print(f"        {g}")
    runtime_ok = {
        "widgets": ["dict_select", "dict_multi"],
        "ts_widgets": ["dict_select", "dict_multi", "i18n_name"],
        "code_patterns": [SNAKE_PATTERN, SNAKE_PATTERN],
        "icon_pattern": SNAKE_PATTERN,
    }
    runtime_cases = [
        ("正例：控件键 / 码值 / 图标码全 snake_case", runtime_ok, 0),
        ("反例 E：后端控件键连字符", {**runtime_ok, "widgets": ["dict-select"]}, 1),
        (
            "反例 F：前端控件键连字符",
            {**runtime_ok, "ts_widgets": ["dict-select", "i18n-name"]},
            2,
        ),
        (
            "反例 G：业务动作码 pattern 允许连字符",
            {
                **runtime_ok,
                "code_patterns": [r"^[a-z][a-z0-9-]*$", r"^[a-z][a-z0-9-]*$"],
            },
            2,
        ),
        (
            "反例 H：自建图标码正则 kebab",
            {**runtime_ok, "icon_pattern": r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"},
            1,
        ),
    ]
    for title, spec, expect in runtime_cases:
        with tempfile.TemporaryDirectory() as root:
            _build_runtime_tree(root, **spec)
            got = runtime_identifier_problems(root)
        flag = "OK" if len(got) == expect else "FAIL"
        bad += flag == "FAIL"
        print(f"  [{flag}] {title}：期望 {expect} 项，实得 {len(got)} 项")
        for g in got:
            print(f"        {g}")
    return bad


def main():
    check_cross_layer()
    check_wording()
    check_manifest()
    check_section_refs()
    check_design_registry()
    check_naming()
    if problems:
        print(f"\n[base-integrity] 不通过：{len(problems)} 项")
        for p in problems[:50]:
            print("  " + p)
        if len(problems) > 50:
            print(f"  ... 其余 {len(problems) - 50} 项")
        sys.exit(1)
    print(
        "\n[base-integrity] 通过：无跨层引用、无措辞残留、清单与磁盘一致、跨文档引用均写章节名、"
        "数据库设计登记一致、登记面命名均为 snake_case。"
        "\n（链接自洽不在本脚本：需要时手工跑 scripts/tools/base_check/check_links.py）"
    )


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    main()
