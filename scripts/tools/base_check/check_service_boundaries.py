#!/usr/bin/env python3
"""服务边界机器护栏（bms 权威源侧，CI base-integrity 与本地运行）。

工作区形态（`backend/libs/<共享库>` + `backend/services/<服务>`）下校验十项
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
   **共享模型子包例外（14_01）**：`bms_core/models/<来源服务>/` 下的模型按定义承载跨服务共用的表
   （如 `sys_tenant` / `sys_client`），声明场景**只校验「表已登记」、不判归属越权**；`models/` 根级文件
   与基座其余目录口径不变（仍按 `platform` 判），访问侧判定亦不变；
7. **读侧出口例外白名单核对**：`deploy/boundaries/data_ownership_exceptions.json` 结构 /
   字段 / 归属校验；命中的越界按「已登记例外」放行并计数，**未登记仍失败**；
8. **`ops` 运行镜像声明（14_03）**：`backend/ops/*.py` 须声明机器可读 `RUN_IMAGE`
   （`platform` / `tenant` / `txn` / `ci` / `*`）；**跨包脚本**未声明或声明值非法即失败；
9. **`ops` 导入闭包（14_03）**：脚本声明的运行镜像所含包 ⊇ 其**传递导入闭包**所需服务包
   （传递闭包含 `ops` 内部互导——本次缺陷正是间接链）；`*` 只允许闭包含 `bms_core` + `ops`；
   镜像包集合常量须与 `backend/Dockerfile` 的 COPY 面一致；
10. **运行期代码不得依赖运维通道（14_03）**：`services/*/src` 不得导入 `ops`；非 platform 服务的
    `src` 不得导入 `bms_platform`（硬断言、无例外；`tests/` 不纳入）。

域级断言（07C `03_01`；维度从「服务包」下沉到「业务域」，合并部署下边界不消失）：

D1 **跨域 import 禁止**：域 A 的实现文件 import 域 B 的实现模块即失败（同服务内不同域同样适用）；
D2 **跨域只经公共面**：目标模块为源域的 `public_api` 出口时放行（能力契约 / 事件天然不经文件 import）；
D3 **跨域表引用禁止**：原始 SQL / `ForeignKey` / 表名 token 指向他域归属的表即失败（读侧例外可放行）；
D4 **跨域写禁止**：写操作（insert / update / delete / ddl）指向他域表即失败，**无例外**；
D5 **观测标注**：越界文案带两侧 `domain_key`；运行期守卫日志与指标同带 `domain` / `owner_domain` 标签；
另有：**域布局完整性**（路径重复归属 / 文件缺失 / 未登记的域实现）与**表归属双字段一致**
（`owner` == 域承载服务、基础设施表与不归域表 `domain` 恒空）。

存量跨域引用记入域级基线 `deploy/boundaries/domain_boundary_baseline.json`（**只减不增**：
条目未命中即失败）；`--update-baseline` 人工执行并审阅。

用法::

    python3 scripts/tools/base_check/check_service_boundaries.py [bms 仓库根]
    python3 scripts/tools/base_check/check_service_boundaries.py --self-test
    python3 scripts/tools/base_check/check_service_boundaries.py [bms 仓库根] --json
    python3 scripts/tools/base_check/check_service_boundaries.py [bms 仓库根] --update-baseline
"""

import ast
import contextlib
import hashlib
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
    table_owner,
    table_prefix_of,
)
from bms_core.boundary.directory import (  # noqa: E402
    known_tables as registered_tables,
)
from bms_core.boundary.domains import (  # noqa: E402
    DEFAULT_BASELINE_RELATIVE,
    DEFAULT_LAYOUT_RELATIVE,
    STATUS_PLACEMENT,
    BaselineEntry,
    DomainLayout,
    dump_baseline,
    load_baseline,
    load_layout,
)
from bms_core.boundary.exceptions import (  # noqa: E402
    DEFAULT_EXCEPTIONS_RELATIVE,
    OwnershipException,
    exception_allows,
    load_exceptions,
    validate_exceptions,
)
from bms_core.boundary.sql import analyze, operation_of  # noqa: E402
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet  # noqa: E402
from bms_core.core.serialization import normalize_collections  # noqa: E402
from bms_core.services.table_registry import (  # noqa: E402
    TableOwnershipRegistry,
    table_domain,
    table_ownership_view,
)


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


ROOT = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ".").resolve()

# 分层反向依赖黑名单：源子包 → 禁止依赖的目标子包
_SHARED_LAYER_RULES: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict(
    {
        "core": ConcurrentStableSet({"api", "services"}),
        "repositories": ConcurrentStableSet({"services"}),
    }
)
_SERVICE_LAYER_RULES: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict(
    {
        "services": ConcurrentStableSet({"api"}),
        "repositories": ConcurrentStableSet({"api", "services"}),
        "models": ConcurrentStableSet({"api", "services", "repositories"}),
        "schemas": ConcurrentStableSet({"api", "services", "repositories"}),
    }
)

_SQL_HINTS = ("select", "insert", "update", "delete", "from", "join")
_WRITE_OPERATIONS = frozenset({"write", "ddl"})
"""跨域写判定：SQL 写操作与 DDL（D4 无例外）。"""
_UPDATE_BASELINE = "--update-baseline" in sys.argv
"""是否按当前扫描结果重写域级基线（人工执行并审阅；不做隐式自动更新）。"""
_IDENTIFIER_LIKE = re.compile(r"^[A-Za-z0-9_.]+$")
"""标识符形态字符串（整串即表名 / 点分名；用于表名 token 扫描，避免文档文案误报）。"""

problems: ConcurrentStableList[str] = ConcurrentStableList()
counts: ConcurrentStableDict[str, int] = ConcurrentStableDict(
    {
        "cross_service_dependency": 0,
        "layer_violation": 0,
        "private_reference": 0,
        "table_name_conflict": 0,
        "table_prefix_conflict": 0,
        "table_ownership_violation": 0,
        "cross_service_access_violation": 0,
        "registered_exceptions_total": 0,
        "registered_exceptions_used": 0,
        "ops_run_image_missing": 0,
        "ops_import_closure_violation": 0,
        "ops_image_packages_drift": 0,
        "runtime_ops_dependency": 0,
        "runtime_cross_service_dependency": 0,
        "cross_domain_import": 0,
        "cross_domain_table_reference": 0,
        "cross_domain_write": 0,
        "cross_domain_table_declare": 0,
        "domain_layout_violation": 0,
        "domain_ownership_violation": 0,
        "domain_baseline_total": 0,
        "domain_baseline_used": 0,
        "domain_files_registered": 0,
        "domain_files_unregistered": 0,
    }
)
service_tables: ConcurrentStableDict[str, ConcurrentStableList[str]] = ConcurrentStableDict()
"""各服务声明的表名清单（规则 5 扫描产出；供服务目录（03_01）登记参考）。"""

_DOMAIN_ENABLED = False
"""域级断言开关：域布局声明**未提供或为空**时停用（产品仓 / 临时工程尚无布局，服务维断言照常）。"""

_DOMAIN_BASELINE: ConcurrentStableDict[tuple[str, str, str, str, str], bool] = ConcurrentStableDict()
"""域级基线索引：`(kind, domain, target, file, 指纹)` → 是否命中（未命中即陈旧条目）。"""

_DOMAIN_BASELINE_PENDING: ConcurrentStableList[BaselineEntry] = ConcurrentStableList()
"""`--update-baseline` 时收集的新基线条目。"""


_OWNERSHIP_REGISTRY_RELATIVE = "services/table_registry.py"
"""表归属登记模块（按定义引用全部表名，规则 6② 引用扫描豁免该模块）。"""

_SHARED_MODELS_MARKER = "/libs/bms_core/src/bms_core/models/"
"""共享模型标记（`{仓库根}/backend/libs/bms_core/src/bms_core/models/`；14_01 整包下沉后承载共享表模型）。

按「标记出现在路径中」判定而非固定前缀——自检在临时仓库构造样例时相对路径形态与真实仓库一致。
"""

_FORM_CATALOG_REGISTRY_RELATIVE = "registry/forms.py"
"""`form_key` 构建期清单（按定义登记全部业务实体表名，规则 6② 引用扫描豁免该模块）。"""

_OPS_RELATIVE = "backend/ops"
"""运维脚本目录（规则 8/9 扫描面；`ops` 是运维通道，运行期代码不得依赖）。"""

_DOCKERFILE_RELATIVE = "backend/Dockerfile"
"""服务镜像构建文件（规则 9 用它断言镜像包集合常量与实际 COPY 面一致）。"""

_RUN_IMAGE_VALUES = ("platform", "tenant", "txn", "ci", "*")
"""`RUN_IMAGE` 合法取值（`14_03`；`*` = 任意服务镜像，仅需 `bms_core` + `ops`）。"""

_ALL_SERVICE_PACKAGES = frozenset(
    {
        "bms_platform",
        "bms_identity",
        "bms_tenant",
        "bms_txn",
        "bms_ai",
        "bms_file",
        "bms_notification",
        "bms_report",
        "bms_search",
    }
)
"""平台服务包全集（`ci` 镜像 = 全量工作区，含全部服务包）。"""

_IMAGE_PACKAGES: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict(
    {
        "platform": ConcurrentStableSet({"bms_core", "bms_platform", "ops"}),
        "tenant": ConcurrentStableSet({"bms_core", "bms_tenant", "ops"}),
        "txn": ConcurrentStableSet({"bms_core", "bms_txn", "ops"}),
        "ci": ConcurrentStableSet({"bms_core", "ops"} | set(_ALL_SERVICE_PACKAGES)),
    }
)
"""镜像 → 所含包集合（规则 9 单一来源；`*` 不在此表——它只保证 `bms_core` + `ops`）。"""

_RUNTIME_SERVICE_PACKAGES = frozenset({"bms_core", "ops"})
"""任意服务镜像恒含的包（`*` 声明的可用面；目标服务自身源码亦在镜像内，故 `*` 脚本允许导入本服务包）。"""


# 说明：06_02 分链已把迁移链表集改为由表归属登记派生（`bms_core/db/migration.py` 不再以字面量登记
# 跨归属表名），原「迁移链表集过渡豁免」（`_LEGACY_CHAIN_TABLES_RELATIVE`）已随分链落地移除。


def _record(message: str, counter: str) -> None:
    """记录一条违规并累加分类计数。

    Args:
        message: 违规文案。
        counter: 计数键。
    """
    problems.add(message)
    counts.set(counter, counts.get(counter, 0) + 1)


def _discover_packages() -> ConcurrentStableDict[str, tuple[Path, bool]]:
    """发现工作区包：`{包名: (源码目录, 是否共享库)}`。

    Returns:
        ConcurrentStableDict[str, tuple[Path, bool]]: 包名 → （包根，是否共享库）。
    """
    packages: ConcurrentStableDict[str, tuple[Path, bool]] = ConcurrentStableDict()
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
                    packages.set(pkg.name, (pkg, shared))
    return packages


def _iter_imports(path: Path) -> ConcurrentStableList[tuple[int, str]]:
    """解析文件并产出受管包导入（任意工作区包名开头）。

    Args:
        path: Python 源文件路径。

    Returns:
        ConcurrentStableList[tuple[int, str]]: 行号与导入模块名。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: ConcurrentStableList[tuple[int, str]] = ConcurrentStableList()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module] if node.module else []
        else:
            continue
        found.update((node.lineno, module) for module in modules)
    return found


def _iter_tablenames(root: Path) -> ConcurrentStableList[str]:
    """解析包内源文件，产出全部 `__tablename__ = "..."` 表名。

    Args:
        root: 包根目录。

    Returns:
        ConcurrentStableList[str]: 表名列表（按文件与行号顺序）。
    """
    found: ConcurrentStableList[str] = ConcurrentStableList()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.add(value.value)
    return found


def _subpackage(package: str, root: Path, path: Path) -> str:
    """取源文件子包名（包根下文件返回包名；域子包取「域内层名」）。

    域子包形态 `domains/<domain_key>/<层>/…`：分层规则按**跳过域目录后的层名**判定，
    否则同一域内的 `api → services → repositories` 方向会因第一段都是 `domains` 而失效。

    Args:
        package: 包名。
        root: 包根目录。
        path: 源文件路径。

    Returns:
        str: 子包名（域内层名；域根文件返回 `domains`）。
    """
    rel = path.relative_to(root).as_posix()
    parts = rel.split("/")
    if parts[0] == "domains" and len(parts) > 2:
        return parts[2]
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


def _iter_cross_reference_tables(
    root: Path, known_tables: ConcurrentStableSet[str]
) -> ConcurrentStableList[tuple[str, int, str, str]]:
    """扫描包内源码的跨服务表引用（原始 SQL / ForeignKey / 已知表名字符串 token）。

    仅扫描非测试源码；跳过 docstring / 裸字符串表达式。表名 token 只匹配**已声明的表名**
    （避免列名 / 插件键 / 业务码等误报），原始 SQL 经 `sql.analyze` 提取。

    Args:
        root: 包根目录。
        known_tables: 全仓已声明表名集合。

    Returns:
        ConcurrentStableList[tuple[str, int, str, str]]: （相对路径, 行号, 表名, 操作）。
    """
    found: ConcurrentStableList[tuple[str, int, str, str]] = ConcurrentStableList()
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
                    found.add((rel, node.lineno, target, "schema"))
                continue
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in bare_strings:
                continue
            value = node.value
            if operation_of(value) != "unknown" and any(hint in value.lower() for hint in _SQL_HINTS):
                for ref in analyze(value):
                    found.add((rel, node.lineno, ref.table, ref.operation))
                continue
            if token_re is not None and _IDENTIFIER_LIKE.fullmatch(value.strip()):
                for match in token_re.findall(value):
                    found.add((rel, node.lineno, match, "unknown"))
    return found


def _bare_string_nodes(tree: ast.AST) -> ConcurrentStableSet[int]:
    """收集裸字符串表达式常量节点 id（docstring / 属性文档等，扫描时排除）。

    Args:
        tree: 语法树。

    Returns:
        ConcurrentStableSet[int]: 裸字符串常量节点 id 集合。
    """
    ids: ConcurrentStableSet[int] = ConcurrentStableSet()
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


def _assess(
    service: str, table: str, operation: str, exceptions: ConcurrentStableList[OwnershipException]
) -> OwnershipViolation | None:
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


def _load_exceptions(
    known_domains: ConcurrentStableSet[str] | None = None,
) -> tuple[ConcurrentStableList[OwnershipException], ConcurrentStableList[str]]:
    """载入并校验例外白名单。

    Args:
        known_domains: 业务域清单（域布局声明的域标识）；None 时跳过域校验。

    Returns:
        tuple[tuple[OwnershipException, ...], ConcurrentStableList[str]]: （例外条目, 校验问题）。
    """
    path = ROOT / DEFAULT_EXCEPTIONS_RELATIVE
    try:
        entries = load_exceptions(path)
    except ValueError as exc:
        return (), ConcurrentStableList([f"[例外登记] {exc}"])
    problems_ = validate_exceptions(
        entries,
        known_tables=registered_tables(),
        known_prefixes=known_prefixes(),
        known_services=known_services(),
        known_domains=known_domains,
    )
    return entries, problems_


def _fingerprint(line: str) -> str:
    """行指纹：规范化（去首尾空白、压缩空白）后的 SHA-1 前 12 位。

    用指纹而非行号——基线不因上下插行而失效，但跨域那一行的内容变了就要重新审阅。

    Args:
        line: 源文件行文本。

    Returns:
        str: 指纹（稳定 12 位十六进制）。
    """
    return hashlib.sha1(" ".join(line.split()).encode("utf-8")).hexdigest()[:12]


def _load_domain_layout() -> DomainLayout:
    """载入域布局声明（结构非法记违规并返回空布局）。

    Returns:
        DomainLayout: 域布局（缺文件 / 非法时为空布局）。
    """
    path = ROOT / DEFAULT_LAYOUT_RELATIVE
    try:
        return load_layout(path)
    except ValueError as exc:
        _record(f"[域布局] {exc}", "domain_layout_violation")
        return load_layout(ROOT / "deploy/boundaries/__missing__.json")


def _load_domain_baseline() -> ConcurrentStableDict[tuple[str, str, str, str, str], bool]:
    """载入域级基线为「键 → 是否命中」表（只减不增：未命中的键即陈旧条目）。

    Returns:
        ConcurrentStableDict[tuple, bool]: 基线索引。
    """
    path = ROOT / DEFAULT_BASELINE_RELATIVE
    try:
        entries = load_baseline(path)
    except ValueError as exc:
        _record(f"[域级基线] {exc}", "domain_layout_violation")
        return ConcurrentStableDict()
    counts.set("domain_baseline_total", len(entries))
    index: ConcurrentStableDict[tuple[str, str, str, str, str], bool] = ConcurrentStableDict()
    for entry in entries:
        index.set((entry.kind, entry.domain, entry.target, entry.file, entry.fingerprint), False)
    return index


def _domain_issue(
    message: str,
    *,
    kind: str,
    domain: str,
    target: str,
    rel: str,
    line: str,
    counter: str,
) -> None:
    """处置一条域级越界：基线条目命中即放行计数；`--update-baseline` 收集；否则记违规。

    Args:
        message: 违规文案（含两侧域标识）。
        kind: 基线条目种类（`import` / `table_ref` / `table_declare`）。
        domain: 源业务域。
        target: 目标业务域。
        rel: 源文件相对路径。
        line: 触发越界的源行文本（指纹用）。
        counter: 计数键。
    """
    key = (kind, domain, target, rel, _fingerprint(line))
    if key in _DOMAIN_BASELINE:
        if not _DOMAIN_BASELINE[key]:
            _DOMAIN_BASELINE.set(key, True)
            counts.set("domain_baseline_used", counts.get("domain_baseline_used", 0) + 1)
        return
    if _UPDATE_BASELINE:
        _DOMAIN_BASELINE_PENDING.add(
            BaselineEntry(kind=kind, domain=domain, target=target, file=rel, fingerprint=key[4])
        )
        return
    _record(message, counter)


def _iter_import_candidates(path: Path) -> ConcurrentStableList[tuple[int, str]]:
    """产出文件内全部可解析导入目标候选（含 `from pkg import sub` 的 `pkg.sub` 形态）。

    Args:
        path: Python 源文件路径。

    Returns:
        ConcurrentStableList[tuple[int, str]]: 行号与候选模块名（同一行可多条）。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: ConcurrentStableList[tuple[int, str]] = ConcurrentStableList()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update((node.lineno, alias.name) for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        found.add((node.lineno, node.module))
        found.update((node.lineno, f"{node.module}.{alias.name}") for alias in node.names)
    return found


def _module_file_of(module: str, packages: ConcurrentStableDict[str, tuple[Path, bool]]) -> str | None:
    """模块名 → 相对仓库根的源文件路径（模块 / 包不存在返回 None）。

    Args:
        module: 模块名（如 `bms_platform.services.users`）。
        packages: 工作区包表（包名 → （包根, 是否共享库））。

    Returns:
        str | None: 源文件相对路径（模块或包的 `__init__.py`）。
    """
    top = module.split(".")[0]
    package = packages.get(top)
    if package is None:
        return None
    base = package[0]
    parts = module.split(".")[1:]
    for candidate in (
        base.joinpath(*parts).with_suffix(".py") if parts else None,
        base.joinpath(*parts, "__init__.py"),
    ):
        if candidate is not None and candidate.is_file():
            return candidate.relative_to(ROOT).as_posix()
    return None


def _check_domain_imports(
    packages: ConcurrentStableDict[str, tuple[Path, bool]],
    file_domain: ConcurrentStableDict[str, str],
    layout: DomainLayout,
) -> None:
    """D1 / D2：跨域 import 断言（同服务内 + 共享库模型；跨服务 import 已由规则 1 / 2 拦截）。

    判定范围（07C `03_03`）：
    - **同服务包内**跨域 import；
    - **共享库模型**（`bms_core.models.*`）跨域 import——模型按域登记后，模型 import 即跨域数据面引用；
    - 其余 `bms_core` 模块（core / db / boundary / …）不归域，天然放行。

    Args:
        packages: 工作区包表。
        file_domain: 文件 → 域映射。
        layout: 域布局（取域内公共出口）。
    """
    if not _DOMAIN_ENABLED:
        return
    for package, (root, _shared) in packages.items():
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or _is_test_path(path, root):
                continue
            rel = path.relative_to(ROOT).as_posix()
            source_domain = file_domain.get(rel)
            if source_domain is None:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for lineno, module in _iter_import_candidates(path):
                top = module.split(".")[0]
                if top != package and not module.startswith("bms_core.models"):
                    continue
                target_rel = _module_file_of(module, packages)
                if target_rel is None:
                    continue
                target_domain = file_domain.get(target_rel)
                if target_domain is None or target_domain == source_domain:
                    continue
                if module in layout.public_api_of(target_domain):
                    continue  # D2：目标是该域的公共 API 出口，允许跨域引用
                line = lines[lineno - 1] if 0 < lineno <= len(lines) else module
                _domain_issue(
                    f"[跨域 import] {rel}:{lineno} {source_domain} → {target_domain}（{module}）",
                    kind="import",
                    domain=source_domain,
                    target=target_domain,
                    rel=rel,
                    line=line,
                    counter="cross_domain_import",
                )


def _check_domain_tables(
    packages: ConcurrentStableDict[str, tuple[Path, bool]],
    file_domain: ConcurrentStableDict[str, str],
    exceptions: ConcurrentStableList[OwnershipException],
    known_table_set: ConcurrentStableSet[str],
) -> None:
    """D3 / D4 / 域实现登记：跨域表声明与跨域表引用（写操作归 D4、读侧例外可放行）。

    Args:
        packages: 工作区包表。
        file_domain: 文件 → 域映射。
        exceptions: 只读例外条目。
        known_table_set: 已声明表名集合（引用扫描用）。
    """
    if not _DOMAIN_ENABLED:
        return
    declared_by_file: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
    for _package, (root, _shared) in packages.items():
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or _is_test_path(path, root):
                continue
            rel = path.relative_to(ROOT).as_posix()
            lines = path.read_text(encoding="utf-8").splitlines()
            declared = _check_table_declarations(rel, lines, file_domain)
            if declared:
                declared_by_file.set(rel, declared)
    for package, (root, _shared) in packages.items():
        service = _service_of_package(package)
        seen: ConcurrentStableSet[tuple[str, int, str]] = ConcurrentStableSet()
        for rel, lineno, table, operation in _iter_cross_reference_tables(root, known_table_set):
            if rel.endswith(_OWNERSHIP_REGISTRY_RELATIVE) or rel.endswith(_FORM_CATALOG_REGISTRY_RELATIVE):
                continue
            source_domain = file_domain.get(rel)
            target_domain = table_domain(table)
            if source_domain is None or not target_domain or target_domain == source_domain:
                continue
            if table in declared_by_file.get(rel, ConcurrentStableSet()):
                continue  # 本文件的 `__tablename__` 声明（已由声明侧判定，不重复计引用）
            if _assess(service, table, operation, exceptions) is not None:
                continue  # 跨服务越界已由规则 6 拦截，此处不重复计
            key = (rel, lineno, table)
            if key in seen:
                continue
            seen.add(key)
            line = _line_of(rel, lineno, table)
            if operation in _WRITE_OPERATIONS:
                _domain_issue(
                    f"[跨域写] {rel}:{lineno} {source_domain} 写 {table}（归属域 {target_domain}，"
                    f"操作 {operation}；跨域写须走能力契约或事件）",
                    kind="table_ref",
                    domain=source_domain,
                    target=target_domain,
                    rel=rel,
                    line=line,
                    counter="cross_domain_write",
                )
                continue
            if exception_allows(exceptions, service=service, table=table, operation=operation, domain=source_domain):
                counts.set("registered_exceptions_used", counts.get("registered_exceptions_used", 0) + 1)
                continue
            _domain_issue(
                f"[跨域表引用] {rel}:{lineno} {source_domain} 引用 {table}（归属域 {target_domain}，操作 {operation}）",
                kind="table_ref",
                domain=source_domain,
                target=target_domain,
                rel=rel,
                line=line,
                counter="cross_domain_table_reference",
            )


def _check_table_declarations(
    rel: str, lines: ConcurrentStableList[str], file_domain: ConcurrentStableDict[str, str]
) -> ConcurrentStableSet[str]:
    """表声明侧：声明他域表（D3 债务）与「声明了已登记表却未归域」的域实现。

    Args:
        rel: 源文件相对路径。
        lines: 源文件行（指纹用）。
        file_domain: 文件 → 域映射。

    Returns:
        ConcurrentStableSet[str]: 本文件声明的表名集合（引用扫描去重用）。
    """
    declared: ConcurrentStableSet[str] = ConcurrentStableSet()
    if not any("__tablename__" in line for line in lines):
        return declared
    for lineno, table in _declared_tables(rel):
        declared.add(table)
        target_domain = table_domain(table)
        if not target_domain:
            continue
        source_domain = file_domain.get(rel)
        if source_domain is None:
            _record(
                f"[域实现未登记] {rel}:{lineno} 声明 {table}（归属域 {target_domain}；须在域布局登记该文件）",
                "domain_layout_violation",
            )
            continue
        if target_domain == source_domain:
            continue
        _domain_issue(
            f"[跨域表声明] {rel}:{lineno} {source_domain} 声明 {table}（归属域 {target_domain}）",
            kind="table_declare",
            domain=source_domain,
            target=target_domain,
            rel=rel,
            line=lines[lineno - 1] if 0 < lineno <= len(lines) else table,
            counter="cross_domain_table_declare",
        )
    return declared


def _declared_tables(rel: str) -> ConcurrentStableList[tuple[int, str]]:
    """取文件内 `__tablename__` 表声明（表名小写）。

    Args:
        rel: 源文件相对路径。

    Returns:
        ConcurrentStableList[tuple[int, str]]: 行号与表名。
    """
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    found: ConcurrentStableList[tuple[int, str]] = ConcurrentStableList()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            found.add((node.lineno, value.value.lower()))
    return found


def _line_of(rel: str, lineno: int, fallback: str) -> str:
    """取源文件指定行文本（越界时用表名兜底）。

    Args:
        rel: 源文件相对路径。
        lineno: 行号（1 起）。
        fallback: 兜底文本。

    Returns:
        str: 行文本。
    """
    lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
    return lines[lineno - 1] if 0 < lineno <= len(lines) else fallback


def _check_domain_files(
    packages: ConcurrentStableDict[str, tuple[Path, bool]],
    file_domain: ConcurrentStableDict[str, str],
    layout: DomainLayout,
) -> None:
    """域实现覆盖：登记文件数 / 未归属域的实现文件数（**硬门禁**：分包后未归属即失败）。

    Args:
        packages: 工作区包表。
        file_domain: 文件 → 域映射。
        layout: 域布局（域外路径判定）。
    """
    registered = 0
    unregistered: ConcurrentStableList[str] = ConcurrentStableList()
    if not _DOMAIN_ENABLED:
        counts.set("domain_files_registered", 0)
        counts.set("domain_files_unregistered", 0)
        return
    for _package, (root, shared) in packages.items():
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or _is_test_path(path, root):
                continue
            rel = path.relative_to(ROOT).as_posix()
            if shared and "/models/" not in f"/{rel}":
                continue  # 基座横切面（core / db / boundary / …）不是业务域实现，不计入覆盖度
            if rel in file_domain:
                registered += 1
            elif not layout.is_shared(rel):
                unregistered.add(rel)
    counts.set("domain_files_registered", registered)
    counts.set("domain_files_unregistered", len(unregistered))
    for rel in unregistered:
        _record(
            f"[域实现未登记] {rel}（既不在任何域 paths，也不在 shared_paths；分包后不允许未归属）",
            "domain_layout_violation",
        )


def _is_model_module(rel: str) -> bool:
    """文件是否声明 ORM 表（`__tablename__` 常量赋值即视为模型模块）。

    Args:
        rel: 相对仓库根 posix 路径。

    Returns:
        bool: 声明表返回 True。
    """
    try:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    except OSError, SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__tablename__" for target in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return True
    return False


def _check_domain_layout_shape(layout: DomainLayout, packages: ConcurrentStableDict[str, tuple[Path, bool]]) -> None:
    """`placement` 形态校验（L1 ~ L3）：域子包目录 / 唯一公共出口 / 模型单文件例外。

    - L1：每条路径要么是 `<包根>/domains/<domain_key>/**` 目录 glob，要么是声明表的单文件（模型）；
    - L2：路径中的域目录段必须等于 `domain_key`（由 L1 的前缀判定同时覆盖）；
    - L3：`placement` 域必须声明恰好 1 个 `public_api`，且模块文件位于该域目录内、可导入。

    Args:
        layout: 域布局。
        packages: 工作区包表（公共出口模块解析用）。
    """
    if not _DOMAIN_ENABLED:
        return
    for entry in layout.entries:
        if entry.status != STATUS_PLACEMENT:
            continue
        expected = f"/domains/{entry.domain_key}/"
        for declared in entry.paths:
            if expected in f"/{declared}":
                continue
            if declared.endswith(".py") and _is_model_module(declared):
                continue
            _record(
                f"[域布局形态] {entry.domain_key} 的路径既不是域子包目录（{expected}）也不是模型单文件：{declared}",
                "domain_layout_violation",
            )
        if len(entry.public_api) != 1:
            _record(
                f"[域布局形态] {entry.domain_key} 的 public_api 须恰好 1 个（现 {len(entry.public_api)} 个）",
                "domain_layout_violation",
            )
            continue
        module = entry.public_api[0]
        target = _module_file_of(module, packages)
        if target is None:
            _record(
                f"[域布局形态] {entry.domain_key} 的公共出口模块不存在：{module}",
                "domain_layout_violation",
            )
            continue
        if expected not in f"/{target}":
            _record(
                f"[域布局形态] {entry.domain_key} 的公共出口不在该域目录内：{module} → {target}",
                "domain_layout_violation",
            )


def _finish_domain_baseline() -> None:
    """基线与双字段收尾：陈旧基线条目即失败；`--update-baseline` 时重写基线。"""
    if not _DOMAIN_ENABLED:
        return
    stale = [key for key, used in _DOMAIN_BASELINE.items() if not used]
    if _UPDATE_BASELINE:
        merged: ConcurrentStableList[BaselineEntry] = ConcurrentStableList(
            BaselineEntry(kind=key[0], domain=key[1], target=key[2], file=key[3], fingerprint=key[4])
            for key, used in _DOMAIN_BASELINE.items()
            if used
        )
        merged.update(_DOMAIN_BASELINE_PENDING)
        written = dump_baseline(ROOT / DEFAULT_BASELINE_RELATIVE, merged)
        counts.set("domain_baseline_total", written)
        return
    for key in stale:
        _record(
            f"[域级基线陈旧] {key[0]} {key[1]} → {key[2]}（{key[3]}，指纹 {key[4]}）已不再命中，"
            "基线只减不增，请从基线删除该条",
            "domain_layout_violation",
        )


def _check_domain_ownership(layout: DomainLayout) -> None:
    """表归属双字段一致性（`owner` == 域承载服务；基础设施表与不归域表 `domain` 恒空）。

    Args:
        layout: 域布局（域 → 承载服务映射）。
    """
    domain_services = layout.domain_services()
    for message in TableOwnershipRegistry(table_ownership_view()).validate(
        domain_services=domain_services if domain_services else None
    ):
        _record(f"[表归属域] {message}", "domain_ownership_violation")


def check() -> int:
    """执行七项护栏检查 + 域级断言 D1 ~ D5。

    Returns:
        int: 违规项数。
    """
    global _DOMAIN_ENABLED
    packages = _discover_packages()
    names = set(packages)
    layout = _load_domain_layout()
    _DOMAIN_ENABLED = bool(layout.domain_keys())
    _DOMAIN_BASELINE.update(_load_domain_baseline())
    file_domain, layout_problems = layout.resolve_files(ROOT)
    for message in layout_problems:
        _record(message, "domain_layout_violation")
    for message in layout.validate(ROOT):
        _record(message, "domain_layout_violation")
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
                if top == package and target in layer_rules.get(source, ConcurrentStableSet()):
                    _record(f"[分层反向依赖] {detail}", "layer_violation")
                if top != package and any(part.startswith("_") for part in parts[1:]):
                    _record(f"[跨包私有引用] {detail}", "private_reference")

    # 规则 5：表名跨服务唯一 + 表名前缀跨服务唯一（`sys_` 为平台共享前缀，按表级归属判定、不判前缀冲突）
    tables: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    prefixes: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
    known_tables: ConcurrentStableSet[str] = ConcurrentStableSet()
    ownership = registered_tables()
    for package, (root, shared) in packages.items():
        declared = _iter_tablenames(root)
        known_tables.update(declared)
        if shared:
            continue
        service_tables.set(package, declared)
        for table in declared:
            owner = tables.get(table)
            if owner is not None and owner != package:
                _record(f"[表名跨服务重复] {table}：{owner} / {package}", "table_name_conflict")
            else:
                tables.set(table, package)
            prefix_key = table_prefix_of(table)
            prefix_owners = prefixes.get(prefix_key)
            if prefix_owners is None:
                prefix_owners = ConcurrentStableSet()
                prefixes.set(prefix_key, prefix_owners)
            prefix_owners.add(package)
    for prefix, owners in sorted(prefixes.items()):
        if prefix != "sys_" and len(owners) > 1:
            _record(f"[表前缀跨服务重复] {prefix}：{'、'.join(sorted(owners))}", "table_prefix_conflict")

    # 规则 5（表级归属，06_03 新增）：声明的表名须在归属登记中；未登记即失败
    for package, declared in service_tables.items():
        for table in declared:
            if table not in ownership:
                _record(f"[表归属未登记] {package} 声明 {table}（表归属登记无此表）", "table_ownership_violation")

    # 规则 7：例外白名单核对（先校验，命中放行由规则 6 / D3 使用）
    exceptions, exception_problems = _load_exceptions(layout.domain_keys())
    for message in exception_problems:
        _record(message, "table_ownership_violation")
    counts.set("registered_exceptions_total", len(exceptions))

    # 规则 6①：声明越权（`__tablename__` 归属他服务；未登记表名同拦）
    shared_declarations: ConcurrentStableSet[tuple[str, str]] = ConcurrentStableSet()
    """共享模型子包内的声明点（`(文件, 表名)`）——规则 6② 引用扫描对同一处不再重复计违规。"""
    for package, (root, _shared) in packages.items():
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
                if _is_shared_model_subpackage(rel):
                    # 共享模型子包：跨服务共用表模型的正常形态（只校验已登记，不判归属越权；14_01）
                    shared_declarations.add((rel, value.value))
                    continue
                if _assess(service, value.value, "declare", exceptions) is not None:
                    _record(
                        f"[跨服务表归属] {rel}:{node.lineno} 声明 {value.value}（归属 {_owner_of(value.value)}）",
                        "table_ownership_violation",
                    )

    # 规则 6②：引用越界（原始 SQL / ForeignKey / 已知表名字符串 token；未登记表名无归属可判、放行）
    # 例外：表归属登记模块本身按定义要引用全部表名（`TABLE_OWNERSHIP` 常量），不参与引用越界扫描
    known_table_set = ConcurrentStableSet(known_tables)
    for package, (root, _shared) in packages.items():
        service = _service_of_package(package)
        seen: ConcurrentStableSet[tuple[str, int, str]] = ConcurrentStableSet()
        for rel, lineno, table, operation in _iter_cross_reference_tables(root, known_table_set):
            if rel.endswith(_OWNERSHIP_REGISTRY_RELATIVE) or rel.endswith(_FORM_CATALOG_REGISTRY_RELATIVE):
                continue
            if _is_shared_model_subpackage(rel) and (rel, table) in shared_declarations:
                # 共享模型子包的 `__tablename__` 是声明而非引用（14_01）；声明侧由规则 6① 判定
                continue
            key = (rel, lineno, table)
            if key in seen:
                continue
            seen.add(key)
            violation = _assess(service, table, operation, exceptions)
            if violation is None:
                if _assess(service, table, operation, ()) is not None:
                    counts.set("registered_exceptions_used", counts.get("registered_exceptions_used", 0) + 1)
                continue
            _record(
                f"[跨服务库访问] {rel}:{lineno} {table}（归属 {violation.owner}，操作 {operation}）",
                "cross_service_access_violation",
            )

    # 规则 8 / 9：`ops` 运行镜像声明与导入闭包（14_03）
    ops_imports, run_images = _scan_ops()
    _check_ops_run_images(run_images, ops_imports)
    _check_ops_import_closure(run_images, ops_imports)

    # 规则 10：运行期代码不得依赖运维通道 / 跨服务源码（14_03）
    _check_runtime_dependencies()

    # 域级断言（07C 03_01）：D1 / D2 跨域 import、D3 / D4 跨域表、域实现覆盖、双字段一致
    _check_domain_imports(packages, file_domain, layout)
    _check_domain_tables(packages, file_domain, exceptions, known_table_set)
    _check_domain_files(packages, file_domain, layout)
    _check_domain_layout_shape(layout, packages)
    _check_domain_ownership(layout)
    _finish_domain_baseline()

    return len(problems)


def _owner_of(table: str) -> str:
    """表名归属标签（未登记返回「未登记」）。

    Args:
        table: 表名。

    Returns:
        str: 归属标签。
    """
    return table_owner(table) or "未登记"


def _is_shared_model_subpackage(rel: str) -> bool:
    """判定文件是否位于共享模型子包（`bms_core/models/<来源服务>/`，14_01）。

    子包语义为「跨服务共用的表模型」，其 `__tablename__` 归属必然散布在多个服务，故声明场景只校验
    「表已登记」；`models/` 根级文件（`ownership.py` / `outbox.py` / `base.py`）不属本例外，仍按
    `platform` 判归属。

    Args:
        rel: 相对仓库根的源文件路径（posix 形态）。

    Returns:
        bool: 位于共享模型子包内 True。
    """
    marker = _SHARED_MODELS_MARKER
    if marker not in f"/{rel}":
        return False
    return "/" in rel.split(marker, 1)[1]


def _module_name_of(path: Path) -> str:
    """源文件 → 模块名（`backend/ops/seed_user.py` → `ops.seed_user`）。

    Args:
        path: 源文件路径。

    Returns:
        str: 模块名（`__init__.py` 取包名）。
    """
    rel = path.relative_to(ROOT).as_posix()
    parts = rel[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    # 去掉仓库内的目录前缀（`backend`），只保留可导入的包路径
    if parts and parts[0] == "backend":
        parts = parts[1:]
    return ".".join(parts)


def _run_image_of(tree: ast.Module) -> str | None:
    """取模块级 `RUN_IMAGE` 声明值（14_03）。

    Args:
        tree: 语法树。

    Returns:
        str | None: 声明值；未声明或非字符串常量返回 None。
    """
    for node in tree.body:
        targets: ConcurrentStableList[ast.expr] = ConcurrentStableList()
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = ConcurrentStableList(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = ConcurrentStableList([node.target])
            value = node.value
        if not targets or value is None:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "RUN_IMAGE" for t in targets):
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        return None
    return None


def _ops_closure(
    script: str, ops_imports: ConcurrentStableDict[str, ConcurrentStableSet[str]]
) -> ConcurrentStableSet[str]:
    """计算 `ops` 脚本的**传递导入闭包**（含 `ops` 内部互导）。

    Args:
        script: 脚本模块名（`ops.seed_user`）。
        ops_imports: `ops` 模块 → 其导入的模块名集合。

    Returns:
        ConcurrentStableSet[str]: 闭包内全部被导入模块名（不含脚本自身）。
    """
    seen: ConcurrentStableSet[str] = ConcurrentStableSet()
    pending = list(ops_imports.get(script, ConcurrentStableSet()))
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        pending.extend(ops_imports.get(module, ConcurrentStableSet()))
    return seen


def _needed_service_packages(closure: ConcurrentStableSet[str]) -> ConcurrentStableSet[str]:
    """从闭包取「所需服务包」（`bms_core` 与 `ops` 之外的工作区包）。

    Args:
        closure: 导入闭包。

    Returns:
        ConcurrentStableSet[str]: 所需服务包名集合。
    """
    needed: ConcurrentStableSet[str] = ConcurrentStableSet()
    for module in closure:
        top = module.split(".")[0]
        if top in _ALL_SERVICE_PACKAGES:
            needed.add(top)
    return needed


def _scan_ops() -> tuple[ConcurrentStableDict[str, ConcurrentStableSet[str]], ConcurrentStableDict[str, str | None]]:
    """扫描 `backend/ops`：各模块导入面与 `RUN_IMAGE` 声明。

    Returns:
        tuple[dict, dict]: （模块 → 导入模块集合，模块 → RUN_IMAGE 值）。
    """
    imports: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
    run_images: ConcurrentStableDict[str, str | None] = ConcurrentStableDict()
    ops_dir = ROOT / _OPS_RELATIVE
    if not ops_dir.is_dir():
        return imports, run_images
    for path in sorted(ops_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = _module_name_of(path)
        imports.set(module, ConcurrentStableSet(m for _lineno, m in _iter_imports(path)))
        run_images.set(module, _run_image_of(ast.parse(path.read_text(encoding="utf-8"))))
    return imports, run_images


def _dockerfile_image_packages() -> tuple[ConcurrentStableSet[str], ConcurrentStableList[str]]:
    """解析 `backend/Dockerfile` 的源码 COPY 面，推导镜像所含工作区包。

    口径：镜像 = `bms_core`（`COPY libs/bms_core/src`）+ 目标服务（`COPY services/${SERVICE}/src`）
    + `ops`（`COPY ops`）。参数化服务目录无法静态展开为具体包名，故返回「固定包集合」与「是否参数化服务」标记。

    Returns:
        tuple[set, list]: （固定包集合，问题列表）。
    """
    packages: ConcurrentStableSet[str] = ConcurrentStableSet()
    issues: ConcurrentStableList[str] = ConcurrentStableList()
    path = ROOT / _DOCKERFILE_RELATIVE
    if not path.is_file():
        issues.add(f"[镜像包集合] 缺 {_DOCKERFILE_RELATIVE}（无法断言镜像 COPY 面）")
        return packages, issues
    text = path.read_text(encoding="utf-8")
    if "COPY libs/bms_core/src" not in text:
        issues.add("[镜像包集合] Dockerfile 未 COPY `libs/bms_core/src`（镜像不含基座）")
    else:
        packages.add("bms_core")
    if "COPY ops" not in text:
        issues.add("[镜像包集合] Dockerfile 未 COPY `ops`（运维脚本不在镜像内）")
    else:
        packages.add("ops")
    if "COPY services/${SERVICE}/src" not in text:
        issues.add("[镜像包集合] Dockerfile 未按 `${SERVICE}` 参数化 COPY 目标服务源码")
    return packages, issues


def _check_ops_run_images(
    run_images: ConcurrentStableDict[str, str | None],
    imports: ConcurrentStableDict[str, ConcurrentStableSet[str]],
) -> None:
    """规则 8：`ops` 脚本运行镜像声明（14_03）。

    跨包脚本（闭包含服务包）未声明或声明值非法即失败；非跨包脚本声明可选（声明则须合法）。

    Args:
        run_images: 模块 → RUN_IMAGE 值。
        imports: 模块 → 导入模块集合。
    """
    for module in sorted(run_images):
        declared = run_images[module]
        closure = _ops_closure(module, imports)
        needed = _needed_service_packages(closure)
        if declared is None:
            if needed:
                _record(
                    f"[运行镜像未声明] {module} 跨包导入 {sorted(needed)} 但未声明 RUN_IMAGE"
                    f"（合法取值：{' / '.join(_RUN_IMAGE_VALUES)}）",
                    "ops_run_image_missing",
                )
            continue
        if declared not in _RUN_IMAGE_VALUES:
            _record(
                f"[运行镜像非法] {module} 声明 RUN_IMAGE = {declared!r}（合法取值：{' / '.join(_RUN_IMAGE_VALUES)}）",
                "ops_run_image_missing",
            )


def _check_ops_import_closure(
    run_images: ConcurrentStableDict[str, str | None],
    imports: ConcurrentStableDict[str, ConcurrentStableSet[str]],
) -> None:
    """规则 9：`ops` 导入闭包 ⊇ 声明镜像所含包（14_03）。

    传递闭包（含 `ops` 内部互导）所需服务包必须被声明镜像覆盖；`*` 只覆盖 `bms_core` + `ops`；
    镜像包集合常量须与 Dockerfile COPY 面一致。

    Args:
        run_images: 模块 → RUN_IMAGE 值。
        imports: 模块 → 导入模块集合。
    """
    docker_packages, docker_issues = _dockerfile_image_packages()
    for message in docker_issues:
        _record(message, "ops_image_packages_drift")
    for image, packages in _IMAGE_PACKAGES.items():
        missing_in_image = ConcurrentStableSet(docker_packages - packages)
        if missing_in_image:
            _record(
                f"[镜像包集合漂移] 声明 {image} 含 {sorted(packages)}，但 Dockerfile 实际含 {sorted(docker_packages)}",
                "ops_image_packages_drift",
            )
            break
    for module in sorted(run_images):
        declared = run_images[module]
        if declared is None or declared not in _RUN_IMAGE_VALUES:
            continue
        needed = _needed_service_packages(_ops_closure(module, imports))
        if not needed:
            continue
        if declared == "*":
            _record(
                f"[导入闭包越界] {module} 声明 RUN_IMAGE = '*'（仅含 bms_core + ops），"
                f"但闭包需要服务包 {sorted(needed)}",
                "ops_import_closure_violation",
            )
            continue
        allowed = _IMAGE_PACKAGES.get(declared, ConcurrentStableSet())
        missing = ConcurrentStableSet(needed - allowed)
        if missing:
            _record(
                f"[导入闭包越界] {module} 声明 RUN_IMAGE = {declared!r}（含 {sorted(allowed)}），"
                f"但闭包需要 {sorted(missing)}",
                "ops_import_closure_violation",
            )


def _check_runtime_dependencies() -> None:
    """规则 10：运行期代码不得依赖运维通道 / 跨服务源码（14_03）。

    `services/*/src` 不得导入 `ops`；非 platform 服务的 `src` 不得导入 `bms_platform`（硬断言、无例外）。
    """
    services_dir = ROOT / "backend" / "services"
    if not services_dir.is_dir():
        return
    for project in sorted(services_dir.iterdir()):
        src = project / "src"
        if not src.is_dir():
            continue
        is_platform = project.name == "platform"
        for path in sorted(src.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            for lineno, module in _iter_imports(path):
                top = module.split(".")[0]
                if top == "ops":
                    _record(
                        f"[运行期依赖运维通道] {rel}:{lineno} import {module}"
                        "（服务运行期代码不得导入 ops；开通种子 / 编排归基座 bms_core）",
                        "runtime_ops_dependency",
                    )
                elif top == "bms_platform" and not is_platform:
                    _record(
                        f"[运行期跨服务依赖] {rel}:{lineno} import {module}"
                        f"（服务 {project.name} 不得导入 bms_platform）",
                        "runtime_cross_service_dependency",
                    )


def _self_test() -> int:
    """护栏拦截自检：在临时仓库构造违规样例，断言脚本报错。"""
    import subprocess
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        core = tmp_path / "backend/libs/bms_core/src/bms_core"
        svc = tmp_path / "backend/services/platform/src/bms_platform"
        report = tmp_path / "backend/services/report/src/bms_report"
        ai = tmp_path / "backend/services/ai/src/bms_ai"
        (core / "core").mkdir(parents=True)
        (core / "__init__.py").write_text("", encoding="utf-8")
        (core / "core/__init__.py").write_text("", encoding="utf-8")
        (svc / "api").mkdir(parents=True)
        (svc / "__init__.py").write_text("", encoding="utf-8")
        (svc / "api/__init__.py").write_text("", encoding="utf-8")
        (report / "models").mkdir(parents=True)
        (report / "__init__.py").write_text("", encoding="utf-8")
        (report / "models/__init__.py").write_text("", encoding="utf-8")
        (ai / "models").mkdir(parents=True)
        (ai / "__init__.py").write_text("", encoding="utf-8")
        (ai / "models/__init__.py").write_text("", encoding="utf-8")
        # 规则 8 / 9 前置：Dockerfile（镜像 COPY 面）与 ops 目录（样例随用随建 / 随清）
        (tmp_path / "backend/Dockerfile").write_text(
            "COPY libs/bms_core/src libs/bms_core/src\n"
            "COPY services/${SERVICE}/src services/${SERVICE}/src\n"
            "COPY ops ./ops\n",
            encoding="utf-8",
        )
        ops_dir = tmp_path / "backend/ops"
        ops_dir.mkdir(parents=True)
        (ops_dir / "__init__.py").write_text("", encoding="utf-8")

        def run(expect_fail: bool, label: str) -> None:
            nonlocal ok
            result = subprocess.run(
                [sys.executable, os.path.abspath(__file__), str(tmp_path)], capture_output=True, text=True
            )
            failed = result.returncode != 0
            passed = failed == expect_fail
            ok = ok and passed
            print(f"  [self-test] {label}：{'通过' if passed else '不通过'}（期望{'拦截' if expect_fail else '放行'}）")
            if not passed:
                detail = (result.stdout or result.stderr or "").strip()
                for line in detail.splitlines()[:6]:
                    print(f"      {line}")

        def declare(target: Path, table: str) -> None:
            (target / "m.py").write_text(f'__tablename__ = "{table}"\n', encoding="utf-8")

        # 规则 8 / 9 / 10（14_03）：运行镜像声明、导入闭包、运行期反向依赖
        def write_ops(name: str, body: str) -> None:
            (ops_dir / f"{name}.py").write_text(body, encoding="utf-8")

        write_ops("clean", 'RUN_IMAGE = "*"\nimport bms_core\n')
        run(False, "ops 声明 * 且闭包只含基座放行")

        write_ops("needs_platform", 'RUN_IMAGE = "*"\nfrom bms_platform import models\n')
        run(True, "ops 声明 * 但闭包含服务包拦截（本次缺陷形态）")

        write_ops("needs_platform", 'RUN_IMAGE = "ci"\nfrom bms_platform import models\n')
        run(False, "ops 声明 ci 覆盖全部包放行")

        write_ops("needs_platform", 'RUN_IMAGE = "tenant"\nfrom bms_platform import models\n')
        run(True, "ops 声明 tenant 但需要 platform 拦截")

        write_ops("needs_platform", "from bms_platform import models\n")
        run(True, "ops 跨包但未声明运行镜像拦截")

        write_ops("needs_platform", 'RUN_IMAGE = "ghost"\nfrom bms_platform import models\n')
        run(True, "ops 运行镜像取值非法拦截")

        # 间接链：脚本本身不跨包，但经 ops 内部互导跨包（本次缺陷的传递形态）
        write_ops("needs_platform", 'RUN_IMAGE = "ci"\nfrom bms_platform import models\n')
        write_ops("relay", 'RUN_IMAGE = "*"\nfrom ops.needs_platform import models\n')
        run(True, "ops 间接跨包（传递闭包）拦截")

        (ops_dir / "needs_platform.py").unlink()
        (ops_dir / "relay.py").unlink()
        run(False, "ops 清理后放行")

        # 运行期反向依赖：服务 src 导入 ops / 非 platform 服务导入 bms_platform
        tenant_main = tmp_path / "backend/services/tenant/src/bms_tenant/main.py"
        tenant_main.parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "backend/services/tenant/src/bms_tenant/__init__.py").write_text("", encoding="utf-8")
        tenant_main.write_text("import bms_core\n", encoding="utf-8")
        run(False, "服务运行期只依赖基座放行")

        tenant_main.write_text("from ops.tenant_provisioning import provision_infrastructure\n", encoding="utf-8")
        run(True, "服务运行期导入 ops 拦截")

        tenant_main.write_text("from bms_platform.models import menu\n", encoding="utf-8")
        run(True, "非 platform 服务导入 bms_platform 拦截")

        tenant_main.write_text("import bms_core\n", encoding="utf-8")
        (svc / "main.py").write_text("import bms_platform\n", encoding="utf-8")
        run(False, "platform 服务导入 bms_platform 放行")

        # 镜像包集合与 Dockerfile 漂移（放最后：会改坏 Dockerfile，影响后续样例）
        (tmp_path / "backend/Dockerfile").write_text(
            "COPY services/${SERVICE}/src services/${SERVICE}/src\n", encoding="utf-8"
        )
        run(True, "Dockerfile 缺 COPY 基座 / ops 时镜像包集合漂移拦截")
        (tmp_path / "backend/Dockerfile").write_text(
            "COPY libs/bms_core/src libs/bms_core/src\n"
            "COPY services/${SERVICE}/src services/${SERVICE}/src\n"
            "COPY ops ./ops\n",
            encoding="utf-8",
        )

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

        # 共享模型子包（14_01）：`bms_core/models/<来源服务>/` 内声明他归属表是正常形态
        declare(ai / "models", "ai_chat_log")
        (core / "models/tenant").mkdir(parents=True)
        (core / "models/__init__.py").write_text("", encoding="utf-8")
        (core / "models/tenant/__init__.py").write_text("", encoding="utf-8")
        declare(core / "models/tenant", "sys_tenant")
        run(False, "共享模型子包声明他归属表放行")

        (core / "models/tenant/m.py").unlink()
        declare(core / "models", "sys_tenant")
        run(True, "models 根级声明他归属表拦截")
        (core / "models/m.py").unlink()

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

        # 复位例外白名单（上一样例留下非法条目，会污染后续样例）
        (boundaries / "data_ownership_exceptions.json").write_text(
            json.dumps({"version": 1, "exceptions": []}, ensure_ascii=False), encoding="utf-8"
        )

    ok = _self_test_domains() and ok
    return 0 if ok else 1


def _self_test_domains() -> bool:
    """域级断言自检（07C `03_01` 设计 §5 用例 1~14 的脚本侧反例）。

    Returns:
        bool: 全部样例符合预期返回 True。
    """
    import hashlib
    import subprocess
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = root / "backend/services/platform/src/bms_platform"
        services = svc / "services"
        services.mkdir(parents=True)
        (svc / "__init__.py").write_text("", encoding="utf-8")
        (services / "__init__.py").write_text("", encoding="utf-8")
        (root / "backend/Dockerfile").write_text(
            "COPY libs/bms_core/src libs/bms_core/src\n"
            "COPY services/${SERVICE}/src services/${SERVICE}/src\n"
            "COPY ops ./ops\n",
            encoding="utf-8",
        )
        ops_dir = root / "backend/ops"
        ops_dir.mkdir(parents=True)
        (ops_dir / "__init__.py").write_text("", encoding="utf-8")
        boundaries = root / "deploy/boundaries"
        boundaries.mkdir(parents=True)
        layout_path = boundaries / "domain_layout.json"
        baseline_path = boundaries / "domain_boundary_baseline.json"

        a_user = services / "a_user.py"
        b_role = services / "b_role.py"
        c_orphan = services / "c_orphan.py"
        b_role.write_text("VALUE = 1\n", encoding="utf-8")
        a_user.write_text("import bms_platform.services.b_role\n", encoding="utf-8")

        def rel(path: Path) -> str:
            return path.relative_to(root).as_posix()

        def fingerprint(text: str) -> str:
            return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]

        def carrier_map() -> ConcurrentStableDict[str, str]:
            """按真实表归属登记推出「域 → 承载服务」（自检样例须与登记一致，才不误报双字段不一致）。"""
            mapping: ConcurrentStableDict[str, str] = ConcurrentStableDict()
            for record in table_ownership_view():
                if record.domain and record.domain not in mapping:
                    mapping.set(record.domain, record.owner)
            return mapping

        def write_layout(*, role_service: str = "", public_api: bool = False, duplicate: bool = False) -> None:
            entries: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
            carriers = carrier_map()
            sample = {"user": a_user, "role": b_role}
            for domain, carrier in carriers.items():
                path = sample.get(domain)
                if path is None:
                    path = services / f"d_{domain.replace('-', '_')}.py"
                    path.write_text("VALUE = 0\n", encoding="utf-8")
                paths: ConcurrentStableList[str] = ConcurrentStableList([rel(path)])
                if duplicate and domain == "user":
                    paths.add(rel(b_role))
                entries.add(
                    ConcurrentStableDict(
                        {
                            "domain_key": domain,
                            "service_key": role_service if domain == "role" and role_service else carrier,
                            "status": "legacy",
                            "paths": paths,
                            "public_api": ["bms_platform.services.b_role"] if public_api and domain == "role" else [],
                        }
                    )
                )
            shared_paths = ConcurrentStableList([rel(svc / "__init__.py"), rel(services / "__init__.py")])
            payload = {"version": 1, "domains": entries, "shared_paths": shared_paths}
            layout_path.write_text(json.dumps(normalize_collections(payload), ensure_ascii=False), encoding="utf-8")

        def write_baseline(entries: ConcurrentStableList[ConcurrentStableDict[str, str]]) -> None:
            baseline_path.write_text(
                json.dumps(normalize_collections({"version": 1, "entries": entries}), ensure_ascii=False),
                encoding="utf-8",
            )

        def run(expect_fail: bool, label: str) -> None:
            nonlocal ok
            result = subprocess.run(
                [sys.executable, os.path.abspath(__file__), str(root)], capture_output=True, text=True
            )
            failed = result.returncode != 0
            passed = failed == expect_fail
            ok = ok and passed
            print(f"  [self-test] {label}：{'通过' if passed else '不通过'}（期望{'拦截' if expect_fail else '放行'}）")
            if not passed:
                detail = (result.stdout or result.stderr or "").strip()
                for line in detail.splitlines()[:6]:
                    print(f"      {line}")

        write_baseline(ConcurrentStableList())
        write_layout()
        run(True, "同服务内跨域 import 拦截")

        import_line = "import bms_platform.services.b_role"

        def import_entry() -> ConcurrentStableList[ConcurrentStableDict[str, str]]:
            """构造一条 import 基线（源域 user → 目标域 role，指纹取当前导入行）。

            Returns:
                ConcurrentStableList[ConcurrentStableDict[str, str]]: 基线条目。
            """
            return ConcurrentStableList(
                [
                    ConcurrentStableDict(
                        {
                            "kind": "import",
                            "domain": "user",
                            "target": "role",
                            "file": rel(a_user),
                            "fingerprint": fingerprint(import_line),
                        }
                    )
                ]
            )

        write_baseline(import_entry())
        run(False, "跨域 import 命中基线放行")

        a_user.write_text(f"{import_line}\nfrom bms_platform.services.b_role import VALUE\n", encoding="utf-8")
        run(True, "基线外新增跨域 import 拦截")

        write_baseline(ConcurrentStableList())
        a_user.write_text(import_line + "\n", encoding="utf-8")
        write_layout(public_api=True)
        run(False, "域内公共 API 出口放行（D2）")

        write_layout()
        a_user.write_text('SQL = "select * from sys_role"\n', encoding="utf-8")
        run(True, "跨域表引用拦截（D3）")

        a_user.write_text('SQL = "update sys_role set value = 2"\n', encoding="utf-8")
        run(True, "跨域写拦截（D4，无例外）")

        a_user.write_text("VALUE = 1\n", encoding="utf-8")
        write_layout(role_service="report")
        run(True, "表归属域与承载服务不一致拦截")

        write_layout(duplicate=True)
        run(True, "同一路径归属两个域拦截")

        write_layout()
        c_orphan.write_text('__tablename__ = "sys_role"\n', encoding="utf-8")
        run(True, "域实现未登记拦截（声明已登记表但文件未在布局）")

        c_orphan.unlink()
        a_user.write_text("VALUE = 2\n", encoding="utf-8")
        write_baseline(import_entry())
        run(True, "陈旧基线条目拦截（只减不增）")

        write_baseline(ConcurrentStableList())
        layout_path.unlink()
        a_user.write_text(import_line + "\n", encoding="utf-8")
        run(False, "未提供域布局时域级断言停用")

        # ---- placement 形态校验（L1 / L3） ----
        domain_dir = svc / "domains" / "user" / "api"
        domain_dir.mkdir(parents=True)
        (svc / "domains" / "__init__.py").write_text("", encoding="utf-8")
        (svc / "domains" / "user" / "__init__.py").write_text("", encoding="utf-8")
        (domain_dir / "__init__.py").write_text("", encoding="utf-8")
        domain_file = domain_dir / "users.py"
        domain_file.write_text("VALUE = 1\n", encoding="utf-8")
        a_user.unlink()

        def write_placement(*, public_api: ConcurrentStableList[str], extra_path: str = "") -> None:
            """写「user 为 placement、其余域 legacy」的样例布局。

            Args:
                public_api: user 域的公共出口模块名清单。
                extra_path: 追加到 user 域 paths 的额外路径（相对仓库根）。
            """
            entries: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
            for domain, carrier in carrier_map().items():
                path = {
                    "user": domain_file,
                    "role": b_role,
                }.get(domain) or services / f"d_{domain.replace('-', '_')}.py"
                if domain not in {"user", "role"}:
                    path.write_text("VALUE = 0\n", encoding="utf-8")
                declared = (
                    "backend/services/platform/src/bms_platform/domains/user/**/*.py" if domain == "user" else rel(path)
                )
                paths: ConcurrentStableList[str] = ConcurrentStableList([declared])
                if domain == "user" and extra_path:
                    paths.add(extra_path)
                entries.add(
                    ConcurrentStableDict(
                        {
                            "domain_key": domain,
                            "service_key": carrier,
                            "status": "placement" if domain == "user" else "legacy",
                            "paths": paths,
                            "public_api": public_api if domain == "user" else [],
                        }
                    )
                )
            shared_paths = ConcurrentStableList(
                [rel(svc / "__init__.py"), rel(services / "__init__.py"), rel(svc / "domains" / "__init__.py")]
            )
            payload = {"version": 1, "domains": entries, "shared_paths": shared_paths}
            layout_path.write_text(json.dumps(normalize_collections(payload), ensure_ascii=False), encoding="utf-8")

        write_placement(public_api=[])
        run(True, "placement 域缺公共出口拦截（L3）")

        write_placement(public_api=["bms_platform.domains.user.public"])
        run(True, "placement 域公共出口模块缺失拦截（L3）")

        (svc / "domains" / "user" / "public.py").write_text("", encoding="utf-8")
        write_placement(public_api=["bms_platform.domains.user.public"])
        run(False, "placement 域子包 + 公共出口放行")

        write_placement(public_api=["bms_platform.domains.user.public"], extra_path=rel(b_role))
        run(True, "placement 域路径越出域子包拦截（L1）")

    return ok


def _emit(as_json: bool) -> None:
    """输出检查结果（文本或 JSON）。

    Args:
        as_json: 是否输出 JSON（供度量脚本解析）。
    """
    if as_json:
        payload = {"passed": not problems, "counts": dict(counts), "problems": list(problems)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if problems:
        print(f"\n[check_service_boundaries] 不通过：{len(problems)} 项")
        for problem in problems:
            print("  " + problem)
        return
    print(
        "[check_service_boundaries] 通过：共享库 / 服务边界、分层依赖单向、表 / 表前缀跨服务唯一、跨服务库访问硬校验。"
    )
    for package, tables in sorted(service_tables.items()):
        listing = "、".join(f"{table}（{table_prefix_of(table)}）" for table in tables) or "无表声明"
        print(f"  - {package}：{listing}")
    print(
        f"  例外白名单：登记 {counts['registered_exceptions_total']} 条、"
        f"命中 {counts['registered_exceptions_used']} 条。"
    )
    registered_files = counts.get("domain_files_registered", 0)
    unregistered_files = counts.get("domain_files_unregistered", 0)
    domain_scope = (
        f"域布局登记文件 {registered_files} / 未归属域 {unregistered_files}"
        if registered_files or unregistered_files
        else "域布局未提供（域级断言停用）"
    )
    print(
        f"  域级断言：{domain_scope}；跨域 import {counts.get('cross_domain_import', 0)}、"
        f"表引用 {counts.get('cross_domain_table_reference', 0)}、写 {counts.get('cross_domain_write', 0)}、"
        f"表声明 {counts.get('cross_domain_table_declare', 0)}；"
        f"域级基线 {counts.get('domain_baseline_total', 0)} 条（命中 {counts.get('domain_baseline_used', 0)} 条）。"
    )
    if _UPDATE_BASELINE:
        print("  （--update-baseline：已按当前扫描结果重写域级基线，请人工审阅 diff 后再提交）")


def main() -> int:
    """入口：执行护栏或自检。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    configure_stdio()
    if "--self-test" in sys.argv:
        return _self_test()
    as_json = "--json" in sys.argv
    check()
    _emit(as_json)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
