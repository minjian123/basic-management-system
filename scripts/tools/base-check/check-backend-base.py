#!/usr/bin/env python3
"""后端基座合规对账（bms 权威源侧，CI 与本地运行）。

校验六项（《后端审计规范》B1 / B5 / B6 / B9 的机器化；直继承合法性见 09_01；数据类体系语义见 09_03）：

1. **继承链对账**：《后端基类清单》§10「继承链与代码位置」的 `A → B → …` 链条
   ↔ 代码 `backend/libs/**`、`backend/services/**` 与 `backend/ops/**` 的 `class A(B)` 相邻关系；
2. **清单登记对账**：直接继承 `BaseObject` 的类必须出现在《后端基类清单》文本中；
3. **直继承合法性（09_01，严禁上帝基类）**：除《后端基类清单》§10「体系根清单」登记的**体系根**
   与 `deploy/boundaries/direct_base_object_baseline.json` **基线存量**外，**禁止直接继承 `BaseObject`**
   （体系根必须承载本体系公共语义；存量按盘点报告分批归位并递减基线）；
4. **错误码段位**：`bms_core/core/error_codes.py` 的平台码为 5 位且万位落在平台段（1~9）、
   无产品段（10xxxx 起）混入；
5. **迁移链完整**：`backend/alembic/versions/<链名>/` 按数据源分链——每链恰好一个 head、
   无断链、revision 跨链唯一、链首声明 `branch_labels=("<链名>",)`，且该链在 `alembic.ini`
   登记配置段 `[alembic:<链名>]`（空链允许，脚本不得存放于版本根目录）；
6. **数据类体系语义（09_03）**：**值对象体系**（`BaseValueObject` 及其下各角色链层）的类必须声明
   `@dataclass(frozen=True)`（不可变数据类）；**框架对象体系**（`BaseFrameworkObject` 及其下各层）
   的类**不得**是 dataclass（框架对象为非数据对象）。

用法::

    python3 scripts/tools/base-check/check-backend-base.py [bms 仓库根]
"""

import json
import os
import re
import sys
from collections.abc import Collection, Mapping, Sequence
from datetime import date

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
MANIFEST = os.path.join(ROOT, "bms文档/后端基类清单.md")
SOURCE_DIRS = (
    os.path.join(ROOT, "backend/libs"),
    os.path.join(ROOT, "backend/services"),
    os.path.join(ROOT, "backend/ops"),
)
ERROR_CODES = os.path.join(ROOT, "backend/libs/bms_core/src/bms_core/core/error_codes.py")
VERSIONS_DIR = os.path.join(ROOT, "backend/alembic/versions")
DIRECT_BASELINE = os.path.join(ROOT, "deploy/boundaries/direct_base_object_baseline.json")
"""直继承存量基线快照（09_01；未归位的历史直继承类豁免并递减）。"""
ROOT_BASES_MARKER = "体系根清单"
"""《后端基类清单》§10 内「体系根清单」小节标记（白名单权威来源）。"""
VALUE_OBJECT_ROOT = "BaseValueObject"
"""值对象体系根（其下各类须为不可变数据类：`@dataclass(frozen=True)`）。"""
FRAMEWORK_OBJECT_ROOT = "BaseFrameworkObject"
"""框架对象体系根（其下各类不得为 dataclass：框架对象为非数据对象）。"""

problems: list[str] = []
checked_chains = 0

PAREN_RE = re.compile(r"[（(][^）)]*[）)]")
CLASS_RE = re.compile(r"^class\s+(\w+)(?:\[[^\]]*\])?\s*\(([^)]*)\)", re.M)


def parse_chains(raw_line: str) -> list[tuple[str, ...]]:
    """解析清单链条目：支持 `` `A` / `B` → `C` / `D` `` 组配对与 `+` 多父类说明。

    - 去括号注释与反引号；按 `→` 切段、按 `/` 切组；
    - 组内非法标识符（中文占位 / `Sorted*` 等）过滤后：各组等长（或长度为 1 的广播）→
      逐项配对成链；否则跳过。
    """
    line = PAREN_RE.sub("", raw_line).replace("`", "")
    if "→" not in line:
        return []
    # 链间分隔（顿号 / 全角逗号 / 分号）：逐条独立解析（避免跨链错配）
    if any(sep in line for sep in ("、", "，", "；")):
        chains: list[tuple[str, ...]] = []
        for part in re.split(r"[、，；]", line):
            chains.extend(parse_chains(part))
        return chains
    segments = [seg for seg in line.split("→")]
    groups: list[list[str]] = []
    for seg in segments:
        # 段内可能混中文说明（如「链路 `NullX`」）：先删 `Xxx*` 占位，再提取标识符；
        # 仅保留含小写字母者（类名惯例 PascalCase），滤掉中文描述中的全大写缩写（LLM / SSO）
        cleaned = re.sub(r"[A-Za-z_][A-Za-z0-9_]*\*", "", seg)
        words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", cleaned)
        groups.append([word for word in words if re.search(r"[a-z]", word)])
    groups = [group for group in groups if group]
    if not groups:
        return []
    length = max(len(group) for group in groups)
    if not all(len(group) in (1, length) for group in groups):
        return []
    return [
        tuple(group[0] if len(group) == 1 else group[index] for group in groups)
        for index in range(length)
    ]


def split_bases(raw: str) -> Sequence[str]:
    """按**顶层**逗号切分类声明的父类列表（尊重 `[` `]` 嵌套）。

    朴素 `str.split(",")` 会把泛型参数内的逗号一并切开（如
    `BaseConcurrentSorted[ItemT, SortedList[ItemT]]` → `BaseConcurrentSorted[ItemT`），
    导致该类在「继承链对账」中被静默跳过——故按括号深度切分。

    Args:
        raw: `class X(...)` 括号内的原始文本。

    Returns:
        Sequence[str]: 父类表达式（含泛型参数，未归一化）。
    """
    parts: list[str] = []
    depth = 0
    current = ""
    for char in raw:
        if char in "[(":
            depth += 1
        elif char in "])":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += char
    parts.append(current)
    return [part for part in (item.strip() for item in parts) if part]


def normalize_parent(raw: str) -> str:
    """归一化父类名：先去泛型参数，再取模块前缀后的末段（`bc.X[Y, Z]` → `X`）。

    Args:
        raw: 父类表达式。

    Returns:
        str: 归一化类名。
    """
    return re.sub(r"\[.*\]", "", raw, flags=re.S).strip().split(".")[-1].strip()


def index_classes() -> dict[str, list[list[str]]]:
    """类名 → 父类名列表（重复定义保留全部；覆盖工作区共享库与服务全部源码）。"""
    index: dict[str, list[list[str]]] = {}
    for source_dir in SOURCE_DIRS:
        for dp, _, files in os.walk(source_dir):
            if "__pycache__" in dp or "tests" in dp.split(os.sep):
                continue
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dp, name)
                text = open(path, encoding="utf-8", errors="ignore").read()
                for cls, bases in CLASS_RE.findall(text):
                    parents = [normalize_parent(base) for base in split_bases(bases)]
                    index.setdefault(cls, []).append(parents)
    return index


def check_inheritance(index: dict[str, list[list[str]]]) -> int:
    global checked_chains
    text = open(MANIFEST, encoding="utf-8").read()
    section = text[text.index("## 10. 继承链与代码位置") : text.index("## 11.")]
    for raw_line in section.splitlines():
        for chain in parse_chains(raw_line):
            for parent, child in zip(chain, chain[1:]):
                checked_chains += 1
                definitions = index.get(parent)
                if not definitions:
                    problems.append(f"[继承链] 清单登记 `{parent}` 起始链，但代码未找到该类（链：{' → '.join(chain)}）")
                    continue
                if not any(child in parents for parents in definitions):
                    found = " | ".join(",".join(p) or "object" for p in definitions)
                    problems.append(
                        f"[继承链] `{parent}` 应为 `{child}` 子类，实际父类：{found}（链：{' → '.join(chain)}）"
                    )
    return checked_chains


def check_manifest_coverage(index: dict[str, list[list[str]]]) -> int:
    """双向对账（B5 补充）：直接继承 `BaseObject` 的基座类必须出现在《后端基类清单》文本中。"""
    manifest_text = open(MANIFEST, encoding="utf-8").read()
    classes = [
        name
        for name, definitions in index.items()
        if not name.startswith("_") and any("BaseObject" in parents for parents in definitions)
    ]
    for name in sorted(classes):
        if not re.search(rf"\b{name}\b", manifest_text):
            problems.append(f"[清单对账] 直接继承 BaseObject 的 `{name}` 未在《后端基类清单》登记")
    return len(classes)


def parse_root_bases() -> Sequence[str]:
    """解析《后端基类清单》§10「体系根清单」小节的体系根类名（白名单）。

    Returns:
        Sequence[str]: 允许直接继承 `BaseObject` 的体系根类名（稳定序；小节缺失时为空）。
    """
    text = open(MANIFEST, encoding="utf-8").read()
    if "## 10." in text and "## 11." in text:
        section = text[text.index("## 10.") : text.index("## 11.")]
    else:
        section = text
    marker_index = section.find(ROOT_BASES_MARKER)
    if marker_index < 0:
        return set()
    roots: set[str] = set()
    for raw_line in section[marker_index:].splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith("- "):
            break
        match = re.match(r"-\s*`([A-Za-z_][A-Za-z0-9_]*)`", line)
        if match:
            roots.add(match.group(1))
    return tuple(sorted(roots))


def load_direct_baseline() -> Sequence[tuple[str, str]]:
    """读取直继承存量基线快照（`(相对文件, 类名)` 条目；缺文件视为空基线）。

    Returns:
        Sequence[tuple[str, str]]: 基线条目（稳定序）。
    """
    if not os.path.isfile(DIRECT_BASELINE):
        return ()
    try:
        payload = json.loads(open(DIRECT_BASELINE, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"[直继承] 基线快照不可解析：{DIRECT_BASELINE}（{exc}）")
        return ()
    if not isinstance(payload, dict) or payload.get("version") != 1:
        problems.append(f"[直继承] 基线快照版本非法（须为 1）：{DIRECT_BASELINE}")
        return ()
    entries = payload.get("entries")
    if not isinstance(entries, list):
        problems.append(f"[直继承] 基线快照 entries 非法（须为数组）：{DIRECT_BASELINE}")
        return ()
    baseline: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict) or "file" not in entry or "class" not in entry:
            problems.append(f"[直继承] 基线快照条目非法（须含 file / class）：{DIRECT_BASELINE}")
            continue
        baseline.add((str(entry["file"]), str(entry["class"])))
    return tuple(sorted(baseline))


def scan_direct_base_object() -> Sequence[tuple[str, str]]:
    """扫描直接继承 `BaseObject` 的类（返回 `(相对文件, 类名)`，排除测试目录）。"""
    found: list[tuple[str, str]] = []
    for source_dir in SOURCE_DIRS:
        for dp, _, files in os.walk(source_dir):
            if "__pycache__" in dp or "tests" in dp.split(os.sep):
                continue
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dp, name)
                text = open(path, encoding="utf-8", errors="ignore").read()
                for cls, bases in CLASS_RE.findall(text):
                    parents = [normalize_parent(base) for base in split_bases(bases)]
                    if "BaseObject" in parents:
                        found.append((os.path.relpath(path, ROOT), cls))
    return found


def check_direct_inheritance() -> int:
    """直继承合法性（09_01）：除体系根（清单白名单）与基线存量外，禁止直接继承 `BaseObject`。"""
    roots = parse_root_bases()
    if not roots:
        problems.append(
            f"[直继承] 《后端基类清单》§10 未登记「{ROOT_BASES_MARKER}」小节（白名单缺失，按拒绝处理）"
        )
        return 0
    baseline = load_direct_baseline()
    found = scan_direct_base_object()
    for rel, cls in found:
        if cls in roots or (rel, cls) in baseline:
            continue
        problems.append(
            f"[直继承] `{cls}` 直接继承 BaseObject（{rel}）：仅体系根可直继承，请归位到所属体系基类"
        )
    return len(found)


def _iter_class_defs(path: str) -> Sequence[object]:
    """解析文件并返回全部类定义节点（语法 / 读取异常时返回空）。

    Args:
        path: Python 源文件路径。

    Returns:
        Sequence[object]: `ast.ClassDef` 节点序列。
    """
    import ast

    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="ignore").read())
    except (OSError, SyntaxError):
        return []
    return [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def _dataclass_shape(node: object) -> tuple[bool, bool]:
    """判定类节点的 dataclass 形态。

    Args:
        node: `ast.ClassDef` 节点。

    Returns:
        tuple[bool, bool]: （是否 dataclass，是否 `frozen=True`）。
    """
    import ast

    decorators = getattr(node, "decorator_list", [])
    for decorator in decorators:
        call = decorator if isinstance(decorator, ast.Call) else None
        target = call.func if call is not None else decorator
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name != "dataclass":
            continue
        frozen = False
        if call is not None:
            frozen = any(
                keyword.arg == "frozen" and getattr(keyword.value, "value", False) is True for keyword in call.keywords
            )
        return True, frozen
    return False, False


def scan_class_shapes() -> Mapping[str, Sequence[tuple[bool, bool]]]:
    """扫描源目录，返回 类名 → [（是否 dataclass, 是否 frozen）]（同名类保留全部定义）。

    Returns:
        Mapping[str, Sequence[tuple[bool, bool]]]: 类形态索引。
    """
    shapes: dict[str, list[tuple[bool, bool]]] = {}
    for source_dir in SOURCE_DIRS:
        for dp, _, files in os.walk(source_dir):
            if "__pycache__" in dp or "tests" in dp.split(os.sep):
                continue
            for name in files:
                if not name.endswith(".py"):
                    continue
                for node in _iter_class_defs(os.path.join(dp, name)):
                    shapes.setdefault(node.name, []).append(_dataclass_shape(node))
    return shapes


def _descendants(index: Mapping[str, Sequence[Sequence[str]]], root: str) -> Collection[str]:
    """按类名计算 `root` 的传递子类集合（不含 `root` 自身）。

    Args:
        index: 类名 → 父类名列表。
        root: 起始类名。

    Returns:
        Collection[str]: 传递子类类名集合。
    """
    children: dict[str, set[str]] = {}
    for child, definitions in index.items():
        for parents in definitions:
            for parent in parents:
                children.setdefault(parent, set()).add(child)
    found: set[str] = set()
    pending = list(children.get(root, ()))
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(children.get(current, ()))
    return found


def check_data_class_semantics() -> int:
    """数据类体系语义（09_03）：值对象体系须为 `@dataclass(frozen=True)`；框架对象体系不得为 dataclass。

    Returns:
        int: 受检查的类形态条目数。
    """
    index = index_classes()
    shapes = scan_class_shapes()
    value_tree = _descendants(index, VALUE_OBJECT_ROOT)
    framework_tree = _descendants(index, FRAMEWORK_OBJECT_ROOT)
    checked = 0
    for name in sorted(shapes):
        if name not in value_tree and name not in framework_tree:
            continue
        for is_dataclass, frozen in shapes[name]:
            checked += 1
            if name in value_tree and not (is_dataclass and frozen):
                problems.append(
                    f"[数据类语义] `{name}` 属值对象体系（{VALUE_OBJECT_ROOT}），须声明 @dataclass(frozen=True)"
                    f"（实际 dataclass={is_dataclass} / frozen={frozen}）"
                )
            elif name in framework_tree and is_dataclass:
                problems.append(
                    f"[数据类语义] `{name}` 属框架对象体系（{FRAMEWORK_OBJECT_ROOT}），不得为 dataclass"
                    "（框架对象为非数据对象，不参与值语义与序列化输出）"
                )
    return checked


def check_error_segments() -> int:
    text = open(ERROR_CODES, encoding="utf-8").read()
    body = text[text.index("class ErrorCode") :]
    count = 0
    for name, raw in re.findall(r"^\s{4}([A-Z][A-Z0-9_]*)\s*=\s*(\d+)", body, re.M):
        value = int(raw)
        count += 1
        if not (10000 <= value <= 99999):
            problems.append(f"[错误码] {name} = {value} 不是 5 位平台码（产品段 10xxxx 起不得混入）")
            continue
        if str(value)[0] not in "123456789":
            problems.append(f"[错误码] {name} = {value} 万位段超出平台段（1~9）")
    return count


def _revision_fields(text: str) -> tuple[str | None, str | None, tuple[str, ...]]:
    """解析迁移脚本的 revision / down_revision / branch_labels。

    Args:
        text: 脚本内容。

    Returns:
        tuple: （revision, down_revision, branch_labels 元组）。
    """
    rev = re.search(r"^revision(?::\s*str)?\s*=\s*[\"']([^\"']+)", text, re.M)
    down = re.search(r"^down_revision[^=]*=\s*(None|[\"']([^\"']+)[\"'])", text, re.M)
    branch_line = re.search(r"^branch_labels[^=]*=\s*(None|\([^)]*\))", text, re.M)
    labels: tuple[str, ...] = ()
    if branch_line and branch_line.group(1) != "None":
        labels = tuple(re.findall(r"[\"']([^\"']+)[\"']", branch_line.group(1)))
    parent = None if (not down or down.group(1) == "None") else down.group(2)
    return (rev.group(1) if rev else None), parent, labels


DATASOURCES = ("platform", "tenant", "archive")
"""合法数据源段（链名 `{service}:{datasource}` 的第二段）。"""

DEFAULT_CHAIN_NAME = "platform:tenant"
"""缺省链（配置段 `[alembic]` 指向它）。"""


def _iter_chain_dirs() -> list[tuple[str, str, str]]:
    """遍历版本目录 `versions/{service}/{datasource}/`（两级），返回（服务, 数据源, 目录）。

    Returns:
        list[tuple[str, str, str]]: 链目录清单（保序）。
    """
    found: list[tuple[str, str, str]] = []
    for service in sorted(os.listdir(VERSIONS_DIR)):
        if service.startswith(".") or service == "__pycache__":
            continue
        service_path = os.path.join(VERSIONS_DIR, service)
        if os.path.isfile(service_path):
            if service.endswith(".py"):
                problems.append(
                    f"[迁移链] {service} 位于版本根目录（迁移脚本须按 versions/<服务>/<数据源>/ 两级存放）"
                )
            continue
        if not os.path.isdir(service_path):
            continue
        if service not in _known_services():
            problems.append(f"[迁移链] 服务目录 {service} 不在服务目录登记内（服务标识须已登记）")
        for datasource in sorted(os.listdir(service_path)):
            if datasource.startswith(".") or datasource == "__pycache__":
                continue
            ds_path = os.path.join(service_path, datasource)
            if os.path.isfile(ds_path):
                if datasource.endswith(".py"):
                    problems.append(f"[迁移链] {service}/{datasource} 位于服务目录（版本目录须为 {service}/<数据源>/）")
                continue
            if not os.path.isdir(ds_path):
                continue
            if datasource not in DATASOURCES:
                problems.append(f"[迁移链] {service}/{datasource} 数据源段非法（允许 {' / '.join(DATASOURCES)}）")
            found.append((service, datasource, ds_path))
    return found


def _known_services() -> set[str]:
    """从服务目录常量静态提取已登记服务标识（不导入服务包）。

    Returns:
        set[str]: 服务标识集合（`service_key` ∪ 模块标识）。
    """
    path = os.path.join(ROOT, "backend/libs/bms_core/src/bms_core/services/module_registry.py")
    if not os.path.isfile(path):
        return set()
    text = open(path, encoding="utf-8", errors="ignore").read()
    keys = set(re.findall(r'service_key="([a-z0-9_-]+)"', text))
    keys |= set(re.findall(r'module_key="([a-z0-9_-]+)"', text))
    keys.add("permission")  # 预留服务标识（表归属登记）
    return keys


def check_alembic_chain() -> int:
    """校验按「服务 × 数据源」分链的迁移脚本（每链单 head / 无断链 / 分支标签与配置段一致）。"""
    if not os.path.isdir(VERSIONS_DIR):
        problems.append("[迁移链] 未找到 backend/alembic/versions/")
        return 0
    ini_path = os.path.join(ROOT, "backend/alembic.ini")
    ini_text = open(ini_path, encoding="utf-8", errors="ignore").read() if os.path.isfile(ini_path) else ""
    total = 0
    for service, datasource, path in _iter_chain_dirs():
        chain = f"{service}:{datasource}"
        revisions: dict[str, str | None] = {}
        labels: dict[str, tuple[str, ...]] = {}
        for name in sorted(os.listdir(path)):
            if not name.endswith(".py"):
                continue
            text = open(os.path.join(path, name), encoding="utf-8", errors="ignore").read()
            rev, parent, branch_labels = _revision_fields(text)
            if not rev:
                problems.append(f"[迁移链] {chain}/{name} 缺少 revision 定义")
                continue
            if rev in revisions:
                problems.append(f"[迁移链] 链 {chain} 内 revision「{rev}」重复")
            revisions[rev] = parent
            labels[rev] = branch_labels
        if not revisions:
            continue
        heads = [rev for rev in revisions if rev not in {p for p in revisions.values() if p}]
        if len(heads) != 1:
            problems.append(f"[迁移链] 链 {chain} 的 head 应为 1 个，实际 {len(heads)} 个：{', '.join(sorted(heads))}")
        for rev, parent in revisions.items():
            if parent and parent not in revisions:
                problems.append(f"[迁移链] {chain}/{rev} 的 down_revision「{parent}」不在本链（断链）")
            if parent is None and chain not in labels[rev]:
                problems.append(f"[迁移链] 链 {chain} 的链首 {rev} 须声明 branch_labels=(\"{chain}\",)")
            if parent is not None and labels[rev]:
                problems.append(f"[迁移链] {chain}/{rev} 非链首不应声明 branch_labels")
        section = "[alembic]" if chain == DEFAULT_CHAIN_NAME else f"[alembic:{chain}]"
        if ini_text and section not in ini_text:
            problems.append(f"[迁移链] 链 {chain} 未在 alembic.ini 登记配置段 {section}")
        total += len(revisions)
    if total == 0:
        print("  （迁移版本目录为空——迁移随后续阶段建立，跳过链检查）")
    return total


def self_test() -> int:
    """fixture 拦截自检（《后端审计规范》§8：护栏须可验证拦截）。

    在临时目录构造「清单 vs 代码」违规样例，断言脚本报错。
    """
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "bms文档"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "backend/libs/bms_core/src/bms_core/core"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "backend/libs/bms_core/src/bms_core/services"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "backend/alembic/versions/tenant/tenant"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "deploy/boundaries"), exist_ok=True)
        open(
            os.path.join(tmp, "backend/libs/bms_core/src/bms_core/services/module_registry.py"),
            "w",
            encoding="utf-8",
        ).write('SERVICE_CATALOG = (\n    dict(module_key="tenant", service_key="tenant"),\n)\n')
        open(os.path.join(tmp, "backend/libs/bms_core/src/bms_core/core/probe.py"), "w", encoding="utf-8").write(
            "class BaseObject:\n    pass\n\n\nclass BaseValueObject(BaseObject):\n    pass\n\n\n"
            "class StrayChild(BaseObject):  # 非体系根直继承样例（应拦截或按基线豁免）\n    pass\n\n\n"
            "class Orphan:\n    pass\n"
        )
        open(os.path.join(tmp, "backend/libs/bms_core/src/bms_core/core/error_codes.py"), "w", encoding="utf-8").write(
            'class ErrorCode:\n    OK = 10001\n'
        )
        open(os.path.join(tmp, "backend/alembic.ini"), "w", encoding="utf-8").write(
            "[alembic]\nscript_location = x\n\n[alembic:tenant:tenant]\nversion_locations = y\n"
        )
        open(
            os.path.join(tmp, "backend/alembic/versions/tenant/tenant/0001_demo.py"), "w", encoding="utf-8"
        ).write(
            'revision: str = "0001_demo"\ndown_revision: str | None = None\n'
            'branch_labels: tuple[str, ...] | None = ("tenant:tenant",)\n'
        )

        def write_manifest(*, chains: str = "", roots: tuple[str, ...] = ("BaseValueObject",)) -> None:
            root_lines = "\n".join(f"- `{name}`：测试体系" for name in roots)
            open(os.path.join(tmp, "bms文档/后端基类清单.md"), "w", encoding="utf-8").write(
                "# 清单\n\n## 10. 继承链与代码位置\n\n"
                f"**{ROOT_BASES_MARKER}（允许直接继承 `BaseObject`）**：\n\n{root_lines}\n\n{chains}\n\n## 11. 扩展\n"
            )

        def write_baseline(entries: Sequence[tuple[str, str]]) -> None:
            payload = {
                "version": 1,
                "generated_at": "2026-10-08",
                "entries": [
                    {"file": rel, "class": cls, "target_system": "value_object", "count": 1} for rel, cls in entries
                ],
            }
            open(
                os.path.join(tmp, "deploy/boundaries/direct_base_object_baseline.json"), "w", encoding="utf-8"
            ).write(json.dumps(payload, ensure_ascii=False))

        def run_case(name: str, expect_fail: bool) -> None:
            nonlocal ok
            import subprocess

            result = subprocess.run(
                [sys.executable, os.path.abspath(__file__), tmp],
                capture_output=True,
                text=True,
            )
            failed = result.returncode != 0
            passed = failed == expect_fail
            ok = ok and passed
            print(f"  [self-test] {name}：{'通过' if passed else '不通过'}（期望{'拦截' if expect_fail else '放行'}，实际{'拦截' if failed else '放行'}）")

        probe = "backend/libs/bms_core/src/bms_core/core/probe.py"
        # 1) 正向：清单链一致 + 体系根放行 + 非体系根直继承入基线 → 放行
        write_manifest(chains="- `StrayChild → BaseObject`。")
        write_baseline([(probe, "StrayChild")])
        run_case("清单一致 / 体系根放行 / 基线豁免", expect_fail=False)
        # 2) 非体系根直继承且未入基线 → 拦截
        write_baseline([])
        run_case("非体系根直继承未入基线", expect_fail=True)
        # 3) 体系根清单小节缺失（白名单为空）→ 拦截
        open(os.path.join(tmp, "bms文档/后端基类清单.md"), "w", encoding="utf-8").write(
            "# 清单\n\n## 10. 继承链与代码位置\n\n## 11. 扩展\n"
        )
        run_case("体系根清单缺失", expect_fail=True)
        # 4) 清单登记未存在的类 → 拦截（继承链缺类）
        write_manifest(chains="- `GhostClass → BaseObject`。")
        write_baseline([(probe, "StrayChild")])
        run_case("清单登记未存在的类", expect_fail=True)
        # 5) 错误码越段（100001 / 万位 0）→ 拦截
        write_manifest()
        open(os.path.join(tmp, "backend/libs/bms_core/src/bms_core/core/error_codes.py"), "w", encoding="utf-8").write(
            'class ErrorCode:\n    OK = 10001\n    BAD = 100001\n'
        )
        run_case("错误码越段", expect_fail=True)
        # 6) 迁移链分链合规（单 head + 链首分支标签 + 配置段）→ 放行
        write_manifest(chains="- `StrayChild → BaseObject`。")
        open(os.path.join(tmp, "backend/libs/bms_core/src/bms_core/core/error_codes.py"), "w", encoding="utf-8").write(
            'class ErrorCode:\n    OK = 10001\n'
        )
        run_case("迁移链分链合规", expect_fail=False)
        # 5) 同链双 head → 拦截
        open(
            os.path.join(tmp, "backend/alembic/versions/tenant/tenant/0002_demo.py"), "w", encoding="utf-8"
        ).write(
            'revision: str = "0002_demo"\ndown_revision: str | None = None\n'
            'branch_labels: tuple[str, ...] | None = ("tenant:tenant",)\n'
        )
        run_case("同链双 head", expect_fail=True)
        # 7) 数据类体系语义：值对象体系子类未声明 frozen dataclass → 拦截
        os.remove(os.path.join(tmp, "backend/alembic/versions/tenant/tenant/0002_demo.py"))
        write_manifest(chains="- `StrayChild → BaseObject`。")
        write_baseline([(probe, "StrayChild")])
        data_probe = os.path.join(tmp, "backend/libs/bms_core/src/bms_core/core/probe_data.py")
        with open(data_probe, "w", encoding="utf-8") as handle:
            handle.write("class LooseValue(BaseValueObject):\n    pass\n")
        run_case("值对象体系子类未声明 frozen dataclass", expect_fail=True)
        # 8) 数据类体系语义：框架对象体系子类为 dataclass → 拦截
        with open(data_probe, "w", encoding="utf-8") as handle:
            handle.write(
                "import dataclasses\n\n\n@dataclasses.dataclass\nclass DataFramework(BaseFrameworkObject):\n    x: int = 0\n"
            )
        run_case("框架对象体系子类为 dataclass", expect_fail=True)
        # 9) 数据类体系语义：值对象 frozen dataclass + 框架对象普通类 → 放行
        with open(data_probe, "w", encoding="utf-8") as handle:
            handle.write(
                "import dataclasses\n\n\n@dataclasses.dataclass(frozen=True)\nclass GoodValue(BaseValueObject):\n"
                "    x: int = 0\n\n\nclass GoodFramework(BaseFrameworkObject):\n    pass\n"
            )
        run_case("数据类体系语义合规", expect_fail=False)
    return 0 if ok else 1


def _class_kind(path: str, class_name: str) -> str:
    """判定直继承类的拟归位体系（基线登记用）：frozen dataclass / dataclass / 普通类。"""
    import ast

    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="ignore").read())
    except (OSError, SyntaxError):
        return "unknown"
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "dataclass":
                return "data_contract"
            if isinstance(decorator, ast.Call) and getattr(decorator.func, "id", "") == "dataclass":
                frozen = any(k.arg == "frozen" and getattr(k.value, "value", False) for k in decorator.keywords)
                return "value_object" if frozen else "data_contract"
        return "framework_object"
    return "unknown"


def update_direct_baseline() -> int:
    """按当前扫描结果重写直继承存量基线快照（体系根不入基线；已完成归位者自然递减）。"""
    roots = parse_root_bases()
    entries: list[dict[str, object]] = []
    for rel, cls in sorted(set(scan_direct_base_object())):
        if cls in roots:
            continue
        entries.append(
            {
                "file": rel,
                "class": cls,
                "target_system": _class_kind(os.path.join(ROOT, rel), cls),
                "count": 1,
            }
        )
    payload = {"version": 1, "generated_at": date.today().isoformat(), "entries": entries}
    os.makedirs(os.path.dirname(DIRECT_BASELINE), exist_ok=True)
    open(DIRECT_BASELINE, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"[check-backend-base] 直继承基线已更新：{len(entries)} 条 → {os.path.relpath(DIRECT_BASELINE, ROOT)}")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if "--update-baseline" in sys.argv:
        return update_direct_baseline()
    index = index_classes()
    chains = check_inheritance(index)
    covered = check_manifest_coverage(index)
    direct = check_direct_inheritance()
    shapes = check_data_class_semantics()
    codes = check_error_segments()
    revs = check_alembic_chain()
    print(f"1. 继承链对账：检查 {chains} 条相邻关系（清单 §10 ↔ 代码）")
    print(f"2. 清单对账（补充）：直接继承 BaseObject 的 {covered} 个基座类均已登记")
    print(f"3. 直继承合法性：检查 {direct} 个直接继承 BaseObject 的类（体系根 / 基线放行）")
    print(f"4. 数据类体系语义：检查 {shapes} 个类形态（值对象须 frozen dataclass / 框架对象不得 dataclass）")
    print(f"5. 错误码段位：检查 {codes} 个平台码")
    print(f"6. 迁移链：检查 {revs} 个 revision")
    if problems:
        print(f"\n[check-backend-base] 不通过：{len(problems)} 项")
        for problem in problems:
            print("  " + problem)
        return 1
    print(
        "\n[check-backend-base] 通过：继承链 / 清单登记 / 直继承合法性 / 数据类体系语义 / 错误码段位 / 迁移链全部对齐。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
