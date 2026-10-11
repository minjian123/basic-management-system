#!/usr/bin/env python3
"""系统字段 `form_key` 校验（02_11，CI 与本地运行）。

校验目标：`form_key` 构建期清单（`bms_core/registry/forms.py::FORM_CATALOG`）与数据表文件双向一致，
且 `form_key` 跨表全局唯一。

校验项：
  1. 清单可解析且非空；
  2. `form_key` 格式合法（`^[a-z][a-z0-9_]*$`）且**跨表全局唯一**；`table` 唯一；
  3. 清单每张表：`数据表设计/{表}.md` 存在，且「字段」节含 `form_key` 行与 `parent_id` 行（字典 5 项）；
  4. **反向**：任一表文件含 `form_key` 行者须登记进清单（防「表落了字段却没进清单」）。

自检（反例驱动）：`python3 check-system-fields.py --self-test` 校验纯函数 `diff_form_catalog`。

任一项不通过则退出码 1。
"""

import ast
import os
import re
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
CATALOG_PY = "backend/libs/bms_core/src/bms_core/registry/forms.py"
TABLE_DIR = "bms文档/设计/数据库设计/数据表设计"

KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ROW_FORM_KEY_RE = re.compile(r"^\|\s*`form_key`\s*\|", re.MULTILINE)
ROW_PARENT_ID_RE = re.compile(r"^\|\s*`parent_id`\s*\|", re.MULTILINE)

problems = []


def parse_catalog(path):
    """从 `forms.py` 解析 `FORM_CATALOG` 登记项（AST，零依赖）。

    Args:
        path: `forms.py` 路径。

    Returns:
        list[tuple[str, str]]: （form_key, table）列表；文件 / 目标缺失时为空列表。
    """
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "FORM_CATALOG" in targets:
                value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "FORM_CATALOG":
                value = node.value
        if not isinstance(value, (ast.Tuple, ast.List)):
            continue
        records = []
        for item in value.elts:
            if not isinstance(item, ast.Call):
                continue
            kwargs = {kw.arg: kw.value for kw in item.keywords if kw.arg}
            key_node = kwargs.get("form_key")
            table_node = kwargs.get("table")
            if isinstance(key_node, ast.Constant) and isinstance(table_node, ast.Constant):
                records.append((str(key_node.value), str(table_node.value)))
        return records
    return []


def diff_form_catalog(catalog, table_texts):
    """纯函数：比对清单与表文件文本。

    Args:
        catalog: （form_key, table）列表。
        table_texts: {表名: 表文件文本}。

    Returns:
        list[str]: 问题描述列表（空 = 通过）。
    """
    issues = []
    seen_keys = set()
    seen_tables = set()
    for form_key, table in catalog:
        if not KEY_RE.match(form_key):
            issues.append(f"form_key 格式非法：{form_key!r}（须 ^[a-z][a-z0-9_]*$）")
        if form_key in seen_keys:
            issues.append(f"form_key 跨表重复：{form_key!r}（须全局唯一）")
        seen_keys.add(form_key)
        if table in seen_tables:
            issues.append(f"表名重复登记：{table!r}")
        seen_tables.add(table)
        text = table_texts.get(table)
        if text is None:
            issues.append(f"清单表缺表文件：{table}.md（未在 数据表设计/ 找到）")
            continue
        if not ROW_FORM_KEY_RE.search(text):
            issues.append(f"表文件缺 form_key 行：{table}.md")
        if not ROW_PARENT_ID_RE.search(text):
            issues.append(f"字典表文件缺 parent_id 行：{table}.md")
    for table, text in sorted(table_texts.items()):
        if ROW_FORM_KEY_RE.search(text) and table not in seen_tables:
            issues.append(f"表文件有 form_key 行但未登记清单：{table}.md")
    return issues


def load_table_texts():
    """读取 `数据表设计/` 全部表文件文本。

    Returns:
        dict[str, str]: {表名: 文本}。
    """
    directory = os.path.join(ROOT, TABLE_DIR)
    texts = {}
    if not os.path.isdir(directory):
        return texts
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(directory, name), encoding="utf-8", errors="ignore") as fh:
            texts[name[: -len(".md")]] = fh.read()
    return texts


def check_form_catalog():
    """清单 ↔ 表文件一致性 + 全局唯一（累加进 `problems`）。"""
    catalog = parse_catalog(os.path.join(ROOT, CATALOG_PY))
    if not catalog:
        problems.append(f"[form_key] 清单不可解析或为空：{CATALOG_PY}")
        return
    for issue in diff_form_catalog(catalog, load_table_texts()):
        problems.append(f"[form_key] {issue}")


def self_test():
    """纯函数反例自检。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    ok_catalog = [("role", "sys_role"), ("tenant", "sys_tenant")]
    ok_tables = {
        "sys_role": "| `form_key` | VARCHAR(64) |\n| `parent_id` | BIGINT |\n",
        "sys_tenant": "| `form_key` | VARCHAR(64) |\n| `parent_id` | BIGINT |\n",
    }
    cases = [
        ("正常：清单与表文件一致", ok_catalog, ok_tables, 0),
        (
            "反例 A：form_key 跨表重复",
            [("role", "sys_role"), ("role", "sys_tenant")],
            ok_tables,
            1,
        ),
        (
            "反例 B：表文件缺 parent_id 行",
            ok_catalog,
            {"sys_role": "| `form_key` | VARCHAR(64) |\n", "sys_tenant": "| `form_key` |\n| `parent_id` |\n"},
            1,
        ),
        (
            "反例 C：表文件有 form_key 行但未登记清单",
            ok_catalog,
            dict(ok_tables, sys_extra="| `form_key` | VARCHAR(64) |\n| `parent_id` | BIGINT |\n"),
            1,
        ),
    ]
    bad = 0
    for title, catalog, tables, expect in cases:
        got = diff_form_catalog(catalog, tables)
        flag = "OK" if len(got) == expect else "FAIL"
        bad += flag == "FAIL"
        print(f"  [{flag}] {title}：期望 {expect} 项，实得 {len(got)} 项")
        for g in got:
            print(f"        {g}")
    print(f"\n[system-fields self-test] {'通过' if not bad else '不通过'}：断言用例 {len(cases)} 个")
    return 1 if bad else 0


def main():
    """入口。"""
    check_form_catalog()
    if problems:
        print(f"[system-fields] 不通过：{len(problems)} 项")
        for p in problems[:50]:
            print("  " + p)
        if len(problems) > 50:
            print(f"  ... 其余 {len(problems) - 50} 项")
        sys.exit(1)
    print("[system-fields] 通过：form_key 清单与表文件双向一致、跨表全局唯一。")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    main()
