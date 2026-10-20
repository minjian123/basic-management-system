#!/usr/bin/env python3
"""系统字段 `form_key` 校验（02_11 起，02_10 增 `data_source_key` 闭合，CI 与本地运行）。

校验目标：`form_key` 构建期清单（`bms_core/registry/forms.py::FORM_CATALOG`）与数据表文件双向一致，
且 `form_key` 跨表全局唯一；并校验 `form_key → data_source_key` 回填**闭合**
（每个 `FormRecord.data_source_key` 非空且落在 `bms_core/datasource/registry.py::DATA_SOURCE_CATALOG`）。

校验项：
  1. 清单可解析且非空；
  2. `form_key` 格式合法（`^[a-z][a-z0-9_]*$`）且**跨表全局唯一**；`table` 唯一；
  3. 清单每张表：`数据表设计/{表}.md` 存在，且「字段」节含 `form_key` 行与 `parent_id` 行（字典 5 项）；
  4. **反向**：任一表文件含 `form_key` 行者须登记进清单（防「表落了字段却没进清单」）；
  5. **数据源闭合**（02_10）：`FormRecord.data_source_key` 非空且 ∈ `DATA_SOURCE_CATALOG` 的数据源标识集合；
  6. **`kind` 显式声明**（08_01）：`FORM_CATALOG` / `DATA_SOURCE_CATALOG` 逐条**显式写出 `kind`**
     （键存在，不再依赖数据类默认值）且取值 ∈ 对应枚举取值（`FormKind` / `DataSourceKind`）。

自检（反例驱动）：`python3 check-system-fields.py --self-test` 校验纯函数 `diff_form_catalog` /
`diff_data_source_closure` / `diff_explicit_kind`。

任一项不通过则退出码 1。
"""

import ast
import os
import re
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
CATALOG_PY = "backend/libs/bms_core/src/bms_core/registry/forms.py"
DATASOURCE_PY = "backend/libs/bms_core/src/bms_core/datasource/registry.py"
TABLE_DIR = "bms文档/设计/数据库设计/数据表设计"

KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ROW_FORM_KEY_RE = re.compile(r"^\|\s*`form_key`\s*\|", re.MULTILINE)
ROW_PARENT_ID_RE = re.compile(r"^\|\s*`parent_id`\s*\|", re.MULTILINE)

problems = []


def _unwrap_collection(value):
    """拆掉集合类包装，取内层元素序列节点（`ConcurrentStableList((...))` → `(...)`）。

    08_05 起，`FORM_CATALOG` 等构建期清单按《后端开发规范》「集合与排序」落插入序集合类
    （`ConcurrentStableList((FormRecord(...), ...))`），不再是裸 tuple / list 字面量；本助手让护栏
    同时支持两种形态（裸字面量 / 集合类包装），避免护栏因口径整改而误报「清单不可解析」。

    Args:
        value: 常量赋值右侧的 AST 节点。

    Returns:
        ast.Tuple | ast.List | None: 元素序列节点；无法识别时返回 None。
    """
    if isinstance(value, (ast.Tuple, ast.List)):
        return value
    if not isinstance(value, ast.Call):
        return None
    # 集合类构造：首参为元素序列（tuple / list / 生成器不解析）
    for arg in value.args:
        if isinstance(arg, (ast.Tuple, ast.List)):
            return arg
    return None


def parse_records(path, const_name):
    """从模块文件按 AST 解析 `const_name`（tuple / list of 构造调用，或集合类包装）的常量关键字参数。

    Args:
        path: 模块文件路径。
        const_name: 常量名（如 `FORM_CATALOG`）。

    Returns:
        list[dict[str, object]]: 每条记录的常量关键字参数（非字面量参数跳过）；文件 / 目标缺失时为空列表。
    """
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if const_name in targets:
                value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == const_name:
                value = node.value
        sequence = _unwrap_collection(value)
        if sequence is None:
            continue
        records = []
        for item in sequence.elts:
            if not isinstance(item, ast.Call):
                continue
            records.append(
                {kw.arg: kw.value.value for kw in item.keywords if kw.arg and isinstance(kw.value, ast.Constant)}
            )
        return records
    return []


def parse_catalog(path):
    """从 `forms.py` 解析 `FORM_CATALOG` 登记项（AST，零依赖）。

    Args:
        path: `forms.py` 路径。

    Returns:
        list[tuple[str, str]]: （form_key, table）列表；文件 / 目标缺失时为空列表。
    """
    records = []
    for record in parse_records(path, "FORM_CATALOG"):
        key_value = record.get("form_key")
        table_value = record.get("table")
        if isinstance(key_value, str) and isinstance(table_value, str):
            records.append((key_value, table_value))
    return records


def parse_form_data_sources(path):
    """从 `forms.py` 解析 `form_key → data_source_key` 回填对。

    Args:
        path: `forms.py` 路径。

    Returns:
        list[tuple[str, str]]: （form_key, data_source_key）列表（缺 `data_source_key` 记空串）。
    """
    pairs = []
    for record in parse_records(path, "FORM_CATALOG"):
        key_value = record.get("form_key")
        if isinstance(key_value, str):
            source_value = record.get("data_source_key")
            pairs.append((key_value, source_value if isinstance(source_value, str) else ""))
    return pairs


def parse_data_source_keys(path):
    """从 `datasource/registry.py` 解析 `DATA_SOURCE_CATALOG` 的数据源标识集合。

    Args:
        path: `datasource/registry.py` 路径。

    Returns:
        set[str]: 已登记数据源标识集合。
    """
    return {
        record["data_source_key"]
        for record in parse_records(path, "DATA_SOURCE_CATALOG")
        if isinstance(record.get("data_source_key"), str)
    }


def parse_enum_values(path, class_name):
    """从模块 AST 解析 `<class_name>(StrEnum)` 的成员名 → 取值映射。

    Args:
        path: 模块文件路径。
        class_name: 枚举类名（如 `FormKind`）。

    Returns:
        dict[str, str]: 成员名 → 取值；类 / 文件缺失时为空映射。
    """
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8", errors="ignore") as fh:
        tree = ast.parse(fh.read())
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if not (isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant)):
                continue
            if not isinstance(item.value.value, str):
                continue
            for target in item.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = item.value.value
    return values


def resolve_kind_node(node, enum_name, enum_values):
    """解析 `kind` 取值节点：字符串字面量直取；`<Enum>.<MEMBER>.value` 经枚举映射解析。

    Args:
        node: 关键字的取值 AST 节点。
        enum_name: 枚举类名（如 `FormKind`）。
        enum_values: 枚举成员名 → 取值映射。

    Returns:
        str | None: 解析出的取值；无法解析返回 None。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "value"
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == enum_name
    ):
        return enum_values.get(node.value.attr)
    return None


def parse_kind_declarations(path, const_name, enum_name, enum_values):
    """解析清单每条记录的 `kind` 显式声明（键存在性 + 取值）。

    Args:
        path: 模块文件路径。
        const_name: 常量名（如 `FORM_CATALOG`）。
        enum_name: 枚举类名（如 `FormKind`）。
        enum_values: 枚举成员名 → 取值映射。

    Returns:
        list[tuple[str, bool, str | None]]: （定位键, 是否出现 `kind` 关键字, 解析出的取值）。
    """
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if const_name in targets:
                value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == const_name:
                value = node.value
        sequence = _unwrap_collection(value)
        if sequence is None:
            continue
        declarations = []
        for item in sequence.elts:
            if not isinstance(item, ast.Call):
                continue
            locator = ""
            declared = False
            kind_value = None
            for kw in item.keywords:
                if kw.arg in ("form_key", "data_source_key") and isinstance(kw.value, ast.Constant):
                    if isinstance(kw.value.value, str):
                        locator = kw.value.value
                elif kw.arg == "kind":
                    declared = True
                    kind_value = resolve_kind_node(kw.value, enum_name, enum_values)
            declarations.append((locator or "?", declared, kind_value))
        return declarations
    return []


def diff_explicit_kind(declarations, valid_kinds):
    """纯函数：断言清单逐条**显式声明** `kind` 且取值合法。

    Args:
        declarations: （定位键, 是否出现 `kind` 关键字, 解析出的取值）列表。
        valid_kinds: 合法取值集合。

    Returns:
        list[str]: 问题描述列表（空 = 通过）。
    """
    issues = []
    for locator, declared, kind_value in declarations:
        if not declared:
            issues.append(f"未显式声明 kind（现依赖数据类默认值）：{locator!r}")
        elif kind_value is None or kind_value not in valid_kinds:
            allowed = " / ".join(sorted(valid_kinds))
            issues.append(f"kind 取值非法或无法解析：{locator!r} → {kind_value!r}（须 {allowed}）")
    return issues


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


def diff_data_source_closure(pairs, known_keys):
    """纯函数：`form_key → data_source_key` 回填闭合（非空且已登记）。

    Args:
        pairs: （form_key, data_source_key）列表。
        known_keys: 已登记数据源标识集合。

    Returns:
        list[str]: 问题描述列表（空 = 通过）。
    """
    issues = []
    for form_key, data_source_key in pairs:
        if not data_source_key:
            issues.append(f"form_key 未回填 data_source_key：{form_key!r}")
        elif not KEY_RE.match(data_source_key):
            issues.append(f"data_source_key 格式非法：{form_key!r} → {data_source_key!r}")
        elif data_source_key not in known_keys:
            issues.append(f"data_source_key 未登记：{form_key!r} → {data_source_key!r}")
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
    """清单 ↔ 表文件一致性 + 全局唯一 + `data_source_key` 闭合（累加进 `problems`）。"""
    catalog = parse_catalog(os.path.join(ROOT, CATALOG_PY))
    if not catalog:
        problems.append(f"[form_key] 清单不可解析或为空：{CATALOG_PY}")
        return
    for issue in diff_form_catalog(catalog, load_table_texts()):
        problems.append(f"[form_key] {issue}")
    known_keys = parse_data_source_keys(os.path.join(ROOT, DATASOURCE_PY))
    if not known_keys:
        problems.append(f"[data_source_key] 数据源清单不可解析或为空：{DATASOURCE_PY}")
        return
    for issue in diff_data_source_closure(parse_form_data_sources(os.path.join(ROOT, CATALOG_PY)), known_keys):
        problems.append(f"[data_source_key] {issue}")
    check_explicit_kind()


def check_explicit_kind():
    """两份清单逐条显式声明 `kind` 且取值合法（累加进 `problems`）。"""
    catalog_path = os.path.join(ROOT, CATALOG_PY)
    datasource_path = os.path.join(ROOT, DATASOURCE_PY)
    targets = (
        ("[form_key]", catalog_path, "FORM_CATALOG", "FormKind"),
        ("[data_source_key]", datasource_path, "DATA_SOURCE_CATALOG", "DataSourceKind"),
    )
    for label, path, const_name, enum_name in targets:
        enum_values = parse_enum_values(path, enum_name)
        if not enum_values:
            problems.append(f"{label} 枚举不可解析：{const_name} → {enum_name}")
            continue
        declarations = parse_kind_declarations(path, const_name, enum_name, enum_values)
        if not declarations:
            problems.append(f"{label} 清单不可解析或为空：{const_name}")
            continue
        for issue in diff_explicit_kind(declarations, set(enum_values.values())):
            problems.append(f"{label} {issue}")


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
    closure_cases = [
        ("正常：回填值均已登记", [("role", "role"), ("tenant", "tenant")], {"role", "tenant"}, 0),
        ("反例 A：未回填", [("role", "")], {"role"}, 1),
        ("反例 B：回填值未登记", [("role", "ghost")], {"role"}, 1),
        ("反例 C：回填值格式非法", [("role", "Bad-Key")], {"role"}, 1),
    ]
    kind_cases = [
        ("正常：逐条显式声明且取值合法", [("role", True, "dict"), ("order", True, "form")], {"dict", "form"}, 0),
        ("反例 A：未显式声明 kind", [("role", False, None)], {"dict", "form"}, 1),
        ("反例 B：取值非法", [("role", True, "ghost")], {"dict", "form"}, 1),
        ("反例 C：取值无法解析", [("role", True, None)], {"dict", "form"}, 1),
    ]
    bad = 0
    for title, catalog, tables, expect in cases:
        got = diff_form_catalog(catalog, tables)
        flag = "OK" if len(got) == expect else "FAIL"
        bad += flag == "FAIL"
        print(f"  [{flag}] {title}：期望 {expect} 项，实得 {len(got)} 项")
        for g in got:
            print(f"        {g}")
    for title, pairs, known, expect in closure_cases:
        got = diff_data_source_closure(pairs, known)
        flag = "OK" if len(got) == expect else "FAIL"
        bad += flag == "FAIL"
        print(f"  [{flag}] {title}：期望 {expect} 项，实得 {len(got)} 项")
        for g in got:
            print(f"        {g}")
    for title, declarations, valid_kinds, expect in kind_cases:
        got = diff_explicit_kind(declarations, valid_kinds)
        flag = "OK" if len(got) == expect else "FAIL"
        bad += flag == "FAIL"
        print(f"  [{flag}] {title}：期望 {expect} 项，实得 {len(got)} 项")
        for g in got:
            print(f"        {g}")
    total = len(cases) + len(closure_cases) + len(kind_cases)
    print(f"\n[system-fields self-test] {'通过' if not bad else '不通过'}：断言用例 {total} 个")
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
    print(
        "[system-fields] 通过：form_key 清单与表文件双向一致、跨表全局唯一，data_source_key 回填闭合，"
        "两份清单 kind 均显式声明且取值合法。"
    )


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    main()
