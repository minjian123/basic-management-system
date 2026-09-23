#!/usr/bin/env python3
"""服务边界机器护栏（bms 权威源侧，CI base-integrity 与本地运行）。

工作区形态（`backend/libs/<共享库>` + `backend/services/<服务>`）下校验七项
（《后端开发规范》§3.1「依赖方向」、§3.2「模块边界与数据所有权」；《微服务演进规划》S1 / S2）：

1. **共享库不得依赖服务**：`libs/*` 包不得 import 任一 `services/*` 包；
2. **服务不得互相依赖**：任一服务包不得 import 另一服务包；
3. **分层依赖单向**：共享库 `core → {api, services}`、`repositories → services` 禁止；
   服务内 `api → services → repositories → models/schemas` 单向，`models/schemas` 不得反向；
4. **跨包不得引用私有实现**：跨包 import 目标模块含下划线前缀（模块内部实现）即失败；
5. **表名 / 表前缀跨服务唯一 + 表归属已登记**：各服务 `models` 声明的表名不得跨服务重复；表前缀不得被
   两个服务声明（`sys_` 为平台共享前缀，按表级归属判定、不判前缀冲突）；**声明的表名须在表归属登记中，
   未登记即失败**（06_03）；
6. **跨服务库访问**：按**表级归属**（表归属登记 `TABLE_OWNERSHIP`）判定——① 声明越权（服务声明他服务
   归属的表）；② 引用越界（原始 SQL / `ForeignKey` 目标 / 字符串表名 token 指向他服务归属的表）；
   基础设施表（发件箱三表）每服务自有、放行；引用中的未登记表名无归属可判、放行（声明场景已拦）；
7. **读侧出口例外白名单核对**：`deploy/boundaries/data_ownership_exceptions.json` 结构 /
   字段 / 归属校验；命中的越界按「已登记例外」放行并计数，**未登记仍失败**。

用法::

    python3 scripts/tools/base-check/check-service-boundaries.py [bms 仓库根]
    python3 scripts/tools/base-check/check-service-boundaries.py --self-test
    python3 scripts/tools/base-check/check-service-boundaries.py [bms 仓库根] --json
"""

import ast
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_REPO = Path(__file__).resolve().parents[3]
"""本脚本所在 bms 仓库根（按脚本位置定位，自检的临时仓库不影响 bms_core 导入）。"""

_SRC_ROOT = SCRIPT_REPO / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.boundary.assess import OwnershipViolation, assess_table  # noqa: E402
from bms_core.boundary.directory import (  # noqa: E402
    known_prefixes,
    known_services,
    known_tables as registered_tables,
    table_owner,
    table_prefix_of,
)
from bms_core.boundary.exceptions import (  # noqa: E402
    DEFAULT_EXCEPTIONS_RELATIVE,
    OwnershipException,
    load_exceptions,
    validate_exceptions,
)
from bms_core.boundary.sql import analyze, operation_of  # noqa: E402

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ".").resolve()

# 分层反向依赖黑名单：源子包 → 禁止依赖的目标子包
_SHARED_LAYER_RULES: dict[str, frozenset[str]] = {
    "core": frozenset({"api", "services"}),
    "repositories": frozenset({"services"}),
}
_SERVICE_LAYER_RULES: dict[str, frozenset[str]] = {
    "services": frozenset({"api"}),
    "repositories": frozenset({"api", "services"}),
    "models": frozenset({"api", "services", "repositories"}),
    "schemas": frozenset({"api", "services", "repositories"}),
}

_SQL_HINTS = ("select", "insert", "update", "delete", "from", "join")
_IDENTIFIER_LIKE = re.compile(r"^[A-Za-z0-9_.]+$")
"""标识符形态字符串（整串即表名 / 点分名；用于表名 token 扫描，避免文档文案误报）。"""

problems: list[str] = []
counts: dict[str, int] = {
    "cross_service_dependency": 0,
    "layer_violation": 0,
    "private_reference": 0,
    "table_name_conflict": 0,
    "table_prefix_conflict": 0,
    "table_ownership_violation": 0,
    "cross_service_access_violation": 0,
    "registered_exceptions_total": 0,
    "registered_exceptions_used": 0,
}
service_tables: dict[str, list[str]] = {}
"""各服务声明的表名清单（规则 5 扫描产出；供服务目录（03_01）登记参考）。"""


_OWNERSHIP_REGISTRY_RELATIVE = "services/table_registry.py"
"""表归属登记模块（按定义引用全部表名，规则 6② 引用扫描豁免该模块）。"""

# 说明：06_02 分链已把迁移链表集改为由表归属登记派生（`bms_core/db/migration.py` 不再以字面量登记
# 跨归属表名），原「迁移链表集过渡豁免」（`_LEGACY_CHAIN_TABLES_RELATIVE`）已随分链落地移除。


def _record(message: str, counter: str) -> None:
    """记录一条违规并累加分类计数。

    Args:
        message: 违规文案。
        counter: 计数键。
    """
    problems.append(message)
    counts[counter] += 1


def _discover_packages() -> dict[str, tuple[Path, bool]]:
    """发现工作区包：`{包名: (源码目录, 是否共享库)}`。

    Returns:
        dict[str, tuple[Path, bool]]: 包名 → （包根，是否共享库）。
    """
    packages: dict[str, tuple[Path, bool]] = {}
    for kind, shared in (("libs", True), ("services", False)):
        base = ROOT / "backend" / kind
        if not base.is_dir():
            continue
        for project in sorted(base.iterdir()):
            src = project / "src"
            if not src.is_dir():
                continue
            for pkg in sorted(src.iterdir()):
                if pkg.is_dir() and (pkg / "__init__.py").is_file():
                    packages[pkg.name] = (pkg, shared)
    return packages


def _iter_imports(path: Path) -> list[tuple[int, str]]:
    """解析文件并产出受管包导入（任意工作区包名开头）。

    Args:
        path: Python 源文件路径。

    Returns:
        list[tuple[int, str]]: 行号与导入模块名。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module] if node.module else []
        else:
            continue
        found.extend((node.lineno, module) for module in modules)
    return found


def _iter_tablenames(root: Path) -> list[str]:
    """解析包内源文件，产出全部 `__tablename__ = "..."` 表名。

    Args:
        root: 包根目录。

    Returns:
        list[str]: 表名列表（按文件与行号顺序）。
    """
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.append(value.value)
    return found


def _subpackage(package: str, root: Path, path: Path) -> str:
    """取源文件子包名（包根下文件返回包名）。

    Args:
        package: 包名。
        root: 包根目录。
        path: 源文件路径。

    Returns:
        str: 子包名。
    """
    rel = path.relative_to(root).as_posix()
    parts = rel.split("/")
    return parts[0] if len(parts) > 1 else package


def _service_of_package(package: str) -> str:
    """包名 → 归属服务标识（共享库 `bms_core` 归 `platform`）。

    Args:
        package: 包名。

    Returns:
        str: 服务标识。
    """
    if package == "bms_core":
        return "platform"
    return package[4:] if package.startswith("bms_") else package


def _is_test_path(path: Path, root: Path) -> bool:
    """源文件是否位于测试目录（跨服务库访问引用扫描跳过测试）。

    Args:
        path: 源文件路径。
        root: 包根目录。

    Returns:
        bool: 测试目录下返回 True。
    """
    rel = path.relative_to(root).as_posix()
    return "tests" in rel.split("/")


def _iter_cross_reference_tables(root: Path, known_tables: frozenset[str]) -> list[tuple[str, int, str, str]]:
    """扫描包内源码的跨服务表引用（原始 SQL / ForeignKey / 已知表名字符串 token）。

    仅扫描非测试源码；跳过 docstring / 裸字符串表达式。表名 token 只匹配**已声明的表名**
    （避免列名 / 插件键 / 业务码等误报），原始 SQL 经 `sql.analyze` 提取。

    Args:
        root: 包根目录。
        known_tables: 全仓已声明表名集合。

    Returns:
        list[tuple[str, int, str, str]]: （相对路径, 行号, 表名, 操作）。
    """
    found: list[tuple[str, int, str, str]] = []
    if known_tables:
        token_re: re.Pattern[str] | None = re.compile(
            r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(table) for table in sorted(known_tables)) + r")(?![A-Za-z0-9_])"
        )
    else:
        token_re = None
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or _is_test_path(path, root):
            continue
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bare_strings = _bare_string_nodes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = _foreign_key_target(node)
                if target is not None:
                    found.append((rel, node.lineno, target, "schema"))
                continue
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in bare_strings:
                continue
            value = node.value
            if operation_of(value) != "unknown" and any(hint in value.lower() for hint in _SQL_HINTS):
                for ref in analyze(value):
                    found.append((rel, node.lineno, ref.table, ref.operation))
                continue
            if token_re is not None and _IDENTIFIER_LIKE.fullmatch(value.strip()):
                for match in token_re.findall(value):
                    found.append((rel, node.lineno, match, "unknown"))
    return found


def _bare_string_nodes(tree: ast.AST) -> set[int]:
    """收集裸字符串表达式常量节点 id（docstring / 属性文档等，扫描时排除）。

    Args:
        tree: 语法树。

    Returns:
        set[int]: 裸字符串常量节点 id 集合。
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            ids.add(id(node.value))
    return ids


def _foreign_key_target(node: ast.Call) -> str | None:
    """识别 `ForeignKey("tbl.col")` 目标表名。

    Args:
        node: 调用节点。

    Returns:
        str | None: 目标表名；非 ForeignKey 调用返回 None。
    """
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name != "ForeignKey" or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value.split(".")[0].lower()
    return None


def _assess(service: str, table: str, operation: str, exceptions: tuple[OwnershipException, ...]) -> OwnershipViolation | None:
    """越界判定（含只读例外放行）。

    Args:
        service: 归属服务标识。
        table: 表名。
        operation: 操作归类。
        exceptions: 例外登记条目。

    Returns:
        OwnershipViolation | None: 越界返回违规项；放行返回 None。
    """
    return assess_table(table, service=service, operation=operation, exceptions=exceptions)


def _load_exceptions() -> tuple[tuple[OwnershipException, ...], list[str]]:
    """载入并校验例外白名单。

    Returns:
        tuple[tuple[OwnershipException, ...], list[str]]: （例外条目, 校验问题）。
    """
    path = ROOT / DEFAULT_EXCEPTIONS_RELATIVE
    try:
        entries = load_exceptions(path)
    except ValueError as exc:
        return (), [f"[例外登记] {exc}"]
    problems_ = validate_exceptions(
        entries,
        known_tables=registered_tables(),
        known_prefixes=known_prefixes(),
        known_services=known_services(),
    )
    return entries, problems_


def check() -> int:
    """执行七项护栏检查。

    Returns:
        int: 违规项数。
    """
    packages = _discover_packages()
    names = set(packages)
    for package, (root, shared) in packages.items():
        layer_rules = _SHARED_LAYER_RULES if shared else _SERVICE_LAYER_RULES
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            source = _subpackage(package, root, path)
            for lineno, module in _iter_imports(path):
                top = module.split(".")[0]
                if top not in names:
                    continue
                detail = f"{rel}:{lineno} import {module}"
                target_shared = packages[top][1]
                if shared and not target_shared:
                    _record(f"[共享库依赖服务] {detail}", "cross_service_dependency")
                if not shared and top != package and not target_shared:
                    _record(f"[服务互相依赖] {detail}", "cross_service_dependency")
                parts = module.split(".")
                target = parts[1] if len(parts) > 1 else top
                if top == package and target in layer_rules.get(source, frozenset()):
                    _record(f"[分层反向依赖] {detail}", "layer_violation")
                if top != package and any(part.startswith("_") for part in parts[1:]):
                    _record(f"[跨包私有引用] {detail}", "private_reference")

    # 规则 5：表名跨服务唯一 + 表名前缀跨服务唯一（`sys_` 为平台共享前缀，按表级归属判定、不判前缀冲突）
    tables: dict[str, str] = {}
    prefixes: dict[str, set[str]] = {}
    known_tables: set[str] = set()
    ownership = registered_tables()
    for package, (root, shared) in packages.items():
        declared = _iter_tablenames(root)
        known_tables.update(declared)
        if shared:
            continue
        service_tables[package] = declared
        for table in declared:
            owner = tables.get(table)
            if owner is not None and owner != package:
                _record(f"[表名跨服务重复] {table}：{owner} / {package}", "table_name_conflict")
            else:
                tables[table] = package
            prefixes.setdefault(table_prefix_of(table), set()).add(package)
    for prefix, owners in sorted(prefixes.items()):
        if prefix != "sys_" and len(owners) > 1:
            _record(f"[表前缀跨服务重复] {prefix}：{'、'.join(sorted(owners))}", "table_prefix_conflict")

    # 规则 5（表级归属，06_03 新增）：声明的表名须在归属登记中；未登记即失败
    for package, declared in service_tables.items():
        for table in declared:
            if table not in ownership:
                _record(f"[表归属未登记] {package} 声明 {table}（表归属登记无此表）", "table_ownership_violation")

    # 规则 7：例外白名单核对（先校验，命中放行由规则 6 使用）
    exceptions, exception_problems = _load_exceptions()
    for message in exception_problems:
        _record(message, "table_ownership_violation")
    counts["registered_exceptions_total"] = len(exceptions)

    # 规则 6①：声明越权（`__tablename__` 归属他服务；未登记表名同拦）
    for package, (root, shared) in packages.items():
        service = _service_of_package(package)
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or _is_test_path(path, root):
                continue
            rel = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                if not any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets):
                    continue
                value = node.value
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    continue
                if value.value not in ownership:
                    _record(
                        f"[表归属未登记] {rel}:{node.lineno} 声明 {value.value}（表归属登记无此表）",
                        "table_ownership_violation",
                    )
                    continue
                if _assess(service, value.value, "declare", exceptions) is not None:
                    _record(
                        f"[跨服务表归属] {rel}:{node.lineno} 声明 {value.value}"
                        f"（归属 {_owner_of(value.value)}）",
                        "table_ownership_violation",
                    )

    # 规则 6②：引用越界（原始 SQL / ForeignKey / 已知表名字符串 token；未登记表名无归属可判、放行）
    # 例外：表归属登记模块本身按定义要引用全部表名（`TABLE_OWNERSHIP` 常量），不参与引用越界扫描
    known_table_set = frozenset(known_tables)
    for package, (root, _shared) in packages.items():
        service = _service_of_package(package)
        seen: set[tuple[str, int, str]] = set()
        for rel, lineno, table, operation in _iter_cross_reference_tables(root, known_table_set):
            if rel.endswith(_OWNERSHIP_REGISTRY_RELATIVE):
                continue
            key = (rel, lineno, table)
            if key in seen:
                continue
            seen.add(key)
            violation = _assess(service, table, operation, exceptions)
            if violation is None:
                if _assess(service, table, operation, ()) is not None:
                    counts["registered_exceptions_used"] += 1
                continue
            _record(
                f"[跨服务库访问] {rel}:{lineno} {table}（归属 {violation.owner}，操作 {operation}）",
                "cross_service_access_violation",
            )

    return len(problems)


def _owner_of(table: str) -> str:
    """表名归属标签（未登记返回「未登记」）。

    Args:
        table: 表名。

    Returns:
        str: 归属标签。
    """
    return table_owner(table) or "未登记"


def _self_test() -> int:
    """护栏拦截自检：在临时仓库构造违规样例，断言脚本报错。"""
    import subprocess
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        core = tmp_path / "backend/libs/bms_core/src/bms_core"
        svc = tmp_path / "backend/services/platform/src/bms_platform"
        org = tmp_path / "backend/services/org/src/bms_org"
        ai = tmp_path / "backend/services/ai/src/bms_ai"
        (core / "core").mkdir(parents=True)
        (core / "__init__.py").write_text("", encoding="utf-8")
        (core / "core/__init__.py").write_text("", encoding="utf-8")
        (svc / "api").mkdir(parents=True)
        (svc / "__init__.py").write_text("", encoding="utf-8")
        (svc / "api/__init__.py").write_text("", encoding="utf-8")
        (org / "models").mkdir(parents=True)
        (org / "__init__.py").write_text("", encoding="utf-8")
        (org / "models/__init__.py").write_text("", encoding="utf-8")
        (ai / "models").mkdir(parents=True)
        (ai / "__init__.py").write_text("", encoding="utf-8")
        (ai / "models/__init__.py").write_text("", encoding="utf-8")

        def run(expect_fail: bool, label: str) -> None:
            nonlocal ok
            result = subprocess.run([sys.executable, os.path.abspath(__file__), str(tmp_path)], capture_output=True, text=True)
            failed = result.returncode != 0
            passed = failed == expect_fail
            ok = ok and passed
            print(f"  [self-test] {label}：{'通过' if passed else '不通过'}（期望{'拦截' if expect_fail else '放行'}）")

        def declare(target: Path, table: str) -> None:
            (target / "m.py").write_text(f'__tablename__ = "{table}"\n', encoding="utf-8")

        (svc / "api/router.py").write_text("import bms_core\n", encoding="utf-8")
        run(False, "服务依赖共享库放行")

        (core / "core/probe.py").write_text("import bms_platform\n", encoding="utf-8")
        run(True, "共享库依赖服务拦截")

        (core / "core/probe.py").write_text("import bms_core\n", encoding="utf-8")
        (svc / "api/router.py").write_text("from bms_core.repositories import base_repository\n", encoding="utf-8")
        run(False, "合规导入放行")

        # 表归属登记（06_03）：样例使用真实登记表——sys_icon/ai_chat_log 各归其主、sys_tenant 归 tenant、
        # sys_module 归 platform、发件箱三表每服务自有
        declare(svc / "api", "sys_icon")
        declare(ai / "models", "ai_chat_log")
        run(False, "已登记表各归其主放行")

        declare(svc / "api", "sys_icon")
        declare(ai / "models", "sys_outbox")
        run(False, "基础设施表（每服务自有）放行")

        declare(ai / "models", "zzz_unknown")
        run(True, "未登记表名拦截")

        declare(svc / "api", "sys_icon")
        declare(ai / "models", "sys_icon")
        run(True, "表名跨服务重复拦截")

        declare(ai / "models", "sys_tenant")
        run(True, "跨服务声明越权拦截")

        declare(ai / "models", "ai_chat_log")
        (ai / "repository.py").write_text('SQL = "select * from sys_module"\n', encoding="utf-8")
        run(True, "跨服务库访问（原始 SQL）拦截")

        (ai / "repository.py").write_text("import bms_core\n", encoding="utf-8")
        run(False, "引用清理后放行")

        boundaries = tmp_path / "deploy/boundaries"
        boundaries.mkdir(parents=True)
        (boundaries / "data_ownership_exceptions.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "exceptions": [
                        {
                            "service": "ai",
                            "target_prefix": "sys_module",
                            "access": "read",
                            "exit": "readonly_projection",
                            "consumer": "ai 报表投影",
                            "reason": "自检样例",
                            "alternative": "自检替代方案",
                            "expiry": "自检后移除",
                            "registered_at": "2026-09-23",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (ai / "models/m.py").write_text('__tablename__ = "ai_chat_log"\n', encoding="utf-8")
        (ai / "repository.py").write_text('SQL = "select * from sys_module"\n', encoding="utf-8")
        run(False, "命中例外白名单（表名）放行")

        (boundaries / "data_ownership_exceptions.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "exceptions": [
                        {
                            "service": "ai",
                            "target_prefix": "sys_module",
                            "access": "write",
                            "exit": "readonly_projection",
                            "consumer": "ai",
                            "reason": "非法样例",
                            "alternative": "无",
                            "expiry": "无",
                            "registered_at": "2026-09-23",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        run(True, "例外白名单 access=write 拦截")
    return 0 if ok else 1


def _emit(as_json: bool) -> None:
    """输出检查结果（文本或 JSON）。

    Args:
        as_json: 是否输出 JSON（供度量脚本解析）。
    """
    if as_json:
        print(json.dumps({"passed": not problems, "counts": counts, "problems": problems}, ensure_ascii=False, indent=2))
        return
    if problems:
        print(f"\n[check-service-boundaries] 不通过：{len(problems)} 项")
        for problem in problems:
            print("  " + problem)
        return
    print("[check-service-boundaries] 通过：共享库 / 服务边界、分层依赖单向、表 / 表前缀跨服务唯一、跨服务库访问硬校验。")
    for package, tables in sorted(service_tables.items()):
        listing = "、".join(f"{table}（{table_prefix_of(table)}）" for table in tables) or "无表声明"
        print(f"  - {package}：{listing}")
    print(
        f"  例外白名单：登记 {counts['registered_exceptions_total']} 条、命中 {counts['registered_exceptions_used']} 条。"
    )


def main() -> int:
    """入口：执行护栏或自检。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    if "--self-test" in sys.argv:
        return _self_test()
    as_json = "--json" in sys.argv
    check()
    _emit(as_json)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
