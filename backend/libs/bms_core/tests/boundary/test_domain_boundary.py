"""业务域级边界护栏测试（Kiwi 2350）：域布局声明 / 域级基线 / 域维度越界判定 / 运行期守卫。

口径见 07C `03_01` 详细设计：域 ↔ 代码路径映射（`domain_layout.json`）、存量跨域引用基线
（`domain_boundary_baseline.json`，只减不增）、`assess_table(domain=…)` 按归属域判定、
守卫日志与指标随带 `domain` / `owner_domain` 标签（D5）。
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from bms_core.boundary.assess import assess_statement, assess_table
from bms_core.boundary.directory import owned_tables_for_domain, table_domain
from bms_core.boundary.domains import (
    BASELINE_KINDS,
    DEFAULT_BASELINE_RELATIVE,
    DEFAULT_LAYOUT_RELATIVE,
    DOMAIN_STATUSES,
    BaselineEntry,
    DomainEntry,
    DomainLayout,
    dump_baseline,
    load_baseline,
    load_layout,
)
from bms_core.boundary.exceptions import (
    OwnershipException,
    exception_allows,
    load_exceptions,
    validate_exceptions,
)
from bms_core.boundary.table import TableOwnershipGuard
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.exceptions import DataOwnershipError
from bms_core.core.serialization import normalize_collections
from bms_core.services.table_registry import (
    NO_DOMAIN_TABLES,
    OWNER_EVERY_SERVICE,
    Datasource,
    table_ownership_view,
)


def _layout_payload(
    *,
    domains: ConcurrentStableList[ConcurrentStableDict[str, object]] | None = None,
    shared: ConcurrentStableList[str] | None = None,
) -> str:
    """构造域布局 JSON 文本（缺省一域两文件）。

    Returns:
        str: JSON 文本。
    """
    payload = {
        "version": 1,
        "domains": domains
        if domains is not None
        else [
            {
                "domain_key": "user",
                "service_key": "platform",
                "status": "legacy",
                "paths": ["backend/services/platform/src/bms_platform/services/users.py"],
                "public_api": [],
            }
        ],
        "shared_paths": shared if shared is not None else ["backend/services/platform/src/bms_platform/main.py"],
    }
    return json.dumps(normalize_collections(payload), ensure_ascii=False)


def _frozen(*items: str) -> ConcurrentStableFrozenList[str]:
    """构造布局路径字段（不可变插入序集合类）。

    Returns:
        ConcurrentStableFrozenList[str]: 路径列表。
    """
    return ConcurrentStableFrozenList(items)


def _write(path: Path, content: str) -> Path:
    """写文件（自动建父目录）。

    Returns:
        Path: 文件路径。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _exception(**overrides: str) -> OwnershipException:
    """构造测试例外（默认合法，按需覆盖字段）。"""
    values = {
        "service": "report",
        "target_prefix": "sys_role",
        "access": "read",
        "exit": "readonly_projection",
        "consumer": "报表聚合",
        "reason": "测试",
        "alternative": "经角色只读出口",
        "expiry": "测试后移除",
        "registered_at": "2026-10-24",
    }
    values.update(overrides)
    return OwnershipException(**values)


@pytest.mark.kiwi_id(2350)
def test_layout_declaration_constants() -> None:
    """声明契约常量：状态三态 / 基线三类 / 默认路径（与设计 §3.1 / §3.4 一致）。"""
    assert tuple(DOMAIN_STATUSES) == ("placement", "legacy", "planned")
    assert tuple(BASELINE_KINDS) == ("import", "table_ref", "table_declare")
    assert DEFAULT_LAYOUT_RELATIVE == "deploy/boundaries/domain_layout.json"
    assert DEFAULT_BASELINE_RELATIVE == "deploy/boundaries/domain_boundary_baseline.json"


@pytest.mark.kiwi_id(2350)
def test_domain_entry_from_row_and_to_dict() -> None:
    """域布局条目：字段读取 / 状态缺省 / 往返转换。"""
    entry = DomainEntry.from_row(
        {"domain_key": "user", "service_key": "platform", "paths": ["./backend/a.py"], "public_api": ["m.api"]}
    )
    assert entry.status == "legacy"
    assert tuple(entry.paths) == ("backend/a.py",), "路径规范化去 `./`"
    assert tuple(entry.public_api) == ("m.api",)
    assert dict(entry.to_dict())["domain_key"] == "user"


@pytest.mark.kiwi_id(2350)
def test_domain_entry_invalid_rows() -> None:
    """域布局条目非法形态逐项报错（非对象 / 缺字段 / 状态非法 / 数组非法 / 元素非法）。"""
    cases = (
        (["not-a-dict"], "须为对象"),
        ({"service_key": "platform"}, "domain_key"),
        ({"domain_key": "user"}, "service_key"),
        ({"domain_key": "user", "service_key": "platform", "status": "ghost"}, "状态非法"),
        ({"domain_key": "user", "service_key": "platform", "paths": "a.py"}, "须为数组"),
        ({"domain_key": "user", "service_key": "platform", "paths": [1]}, "非空字符串"),
    )
    for row, match in cases:
        with pytest.raises(ValueError, match=match):
            DomainEntry.from_row(row)


@pytest.mark.kiwi_id(2350)
def test_baseline_entry_from_row_and_to_dict() -> None:
    """基线条目：字段读取 / 种类非法 / 非对象 / 往返转换。"""
    entry = BaselineEntry.from_row(
        {"kind": "import", "domain": "user", "target": "role", "file": "backend/a.py", "fingerprint": "abc123"}
    )
    assert dict(entry.to_dict())["kind"] == "import"
    with pytest.raises(ValueError, match="种类非法"):
        BaselineEntry.from_row(
            {"kind": "ghost", "domain": "user", "target": "role", "file": "a.py", "fingerprint": "x"}
        )
    with pytest.raises(ValueError, match="须为对象"):
        BaselineEntry.from_row(("not", "a", "dict"))


@pytest.mark.kiwi_id(2350)
def test_load_layout_valid(tmp_path: Path) -> None:
    """载入合法布局：域清单 / 承载服务映射 / 公共出口 / 路径索引 / 域外路径判定。"""
    _write(tmp_path / "backend/services/platform/src/bms_platform/services/users.py", "")
    _write(tmp_path / "backend/services/platform/src/bms_platform/main.py", "")
    layout = load_layout(_write(tmp_path / DEFAULT_LAYOUT_RELATIVE, _layout_payload()))

    assert tuple(layout.domain_keys()) == ("user",)
    assert layout.service_of("user") == "platform"
    assert layout.service_of("ghost") is None
    assert layout.entry_of("ghost") is None
    assert dict(layout.domain_services()) == {"user": "platform"}
    assert layout.public_api_of("user") == frozenset()
    assert layout.public_api_of("ghost") == frozenset()
    assert layout.domain_of("backend/services/platform/src/bms_platform/services/users.py") == "user"
    assert layout.domain_of("backend/services/platform/src/bms_platform/services/role.py") is None
    assert layout.is_shared("./backend/services/platform/src/bms_platform/main.py")
    assert not layout.is_shared("backend/services/platform/src/bms_platform/services/users.py")
    assert tuple(layout.entries) and tuple(layout.shared_paths) == (
        "backend/services/platform/src/bms_platform/main.py",
    )

    mapping, problems = layout.resolve_files(tmp_path)
    assert dict(mapping) == {"backend/services/platform/src/bms_platform/services/users.py": "user"}
    assert problems == []
    assert layout.validate(tmp_path) == []


@pytest.mark.kiwi_id(2350)
def test_load_layout_missing_and_invalid(tmp_path: Path) -> None:
    """缺文件视为空布局；结构非法抛 `ValueError`（版本 / 根 / 数组 / 条目 / 标识 / 重复）。"""
    empty = load_layout(tmp_path / "none.json")
    assert tuple(empty.domain_keys()) == ()

    cases = (
        ("{not json", "JSON 非法"),
        ("[]", "根须为对象"),
        ('{"version": 2, "domains": []}', "版本非法"),
        ('{"version": 1, "domains": {}}', "domains 须为数组"),
        ('{"version": 1, "domains": [{"service_key": "platform", "paths": []}]}', "第 1 条非法"),
        (
            '{"version": 1, "domains": [{"domain_key": "Bad Key", "service_key": "platform", "paths": []}]}',
            "domain_key 非法",
        ),
        (
            '{"version": 1, "domains": ['
            '{"domain_key": "user", "service_key": "platform", "paths": []},'
            '{"domain_key": "user", "service_key": "platform", "paths": []}]}',
            "domain_key 重复",
        ),
    )
    for content, match in cases:
        with pytest.raises(ValueError, match=match):
            load_layout(_write(tmp_path / "bad.json", content))


@pytest.mark.kiwi_id(2350)
def test_layout_validate_detects_problems(tmp_path: Path) -> None:
    """布局语义校验：域重复归属 / 与域外路径冲突 / 文件不存在 / planned 无路径 / glob 未命中。"""
    shared_file = _write(tmp_path / "backend/shared.py", "")
    layout = DomainLayout(
        ConcurrentStableList(
            [
                DomainEntry(domain_key="user", service_key="platform"),
                DomainEntry(domain_key="role", service_key="platform", paths=_frozen("backend/missing.py")),
                DomainEntry(domain_key="tenant", service_key="tenant", status="planned"),
                DomainEntry(domain_key="task", service_key="platform", paths=_frozen("backend/shared.py")),
                DomainEntry(domain_key="ai", service_key="ai", paths=_frozen("backend/*.nomatch")),
                DomainEntry(domain_key="txn", service_key="txn", paths=_frozen("backend/shared.py")),
            ]
        ),
        ConcurrentStableList([shared_file.relative_to(tmp_path).as_posix(), "backend/missing_shared.py"]),
    )

    joined = "；".join(layout.validate(tmp_path))

    assert "user 状态 legacy 但未声明代码路径" in joined
    assert "task 的路径同时登记为域外路径：backend/shared.py" in joined
    assert "backend/shared.py 同时归属 task 与 txn" in joined
    assert "路径未命中文件：backend/missing.py" in joined
    assert "路径未命中文件：backend/*.nomatch" in joined
    assert "域外路径未命中文件：backend/missing_shared.py" in joined
    assert "tenant 状态 planned" not in joined, "planned 域允许无路径"


@pytest.mark.kiwi_id(2350)
def test_resolve_files_reports_glob_miss_and_duplicate(tmp_path: Path) -> None:
    """路径展开：glob 命中 / 未命中报问题；同一文件归属两域报重复。"""
    _write(tmp_path / "backend/a/user.py", "")
    layout = DomainLayout(
        ConcurrentStableList(
            [
                DomainEntry(domain_key="user", service_key="platform", paths=_frozen("backend/a/*.py")),
                DomainEntry(domain_key="role", service_key="platform", paths=_frozen("backend/a/user.py")),
                DomainEntry(domain_key="ai", service_key="ai", paths=_frozen("backend/none/*.py")),
            ]
        ),
        ConcurrentStableList([]),
    )

    mapping, problems = layout.resolve_files(tmp_path)

    assert dict(mapping) == {"backend/a/user.py": "user"}
    assert any("同时归属 user 与 role" in problem for problem in problems)
    assert any("路径未命中文件：backend/none/*.py" in problem for problem in problems)


@pytest.mark.kiwi_id(2350)
def test_baseline_roundtrip_and_invalid(tmp_path: Path) -> None:
    """域级基线：缺失返回空 / 写出按稳定序 / 往返一致 / 结构非法报错。"""
    path = tmp_path / "baseline.json"
    assert tuple(load_baseline(path)) == ()

    entries = ConcurrentStableList(
        [
            BaselineEntry(kind="table_ref", domain="user", target="role", file="b.py", fingerprint="f2"),
            BaselineEntry(kind="import", domain="user", target="role", file="b.py", fingerprint="f1"),
        ]
    )
    assert dump_baseline(path, entries) == 2
    loaded = load_baseline(path)
    assert [entry.kind for entry in loaded] == ["import", "table_ref"], "按 kind / file / domain / target 稳定排序"
    assert load_baseline(path) == loaded

    cases = (
        ("{not json", "JSON 非法"),
        ("[]", "根须为对象"),
        ('{"version": 9, "entries": []}', "版本非法"),
        ('{"version": 1, "entries": {}}', "entries 须为数组"),
        ('{"version": 1, "entries": [{"kind": "ghost"}]}', "第 1 条非法"),
    )
    for content, match in cases:
        with pytest.raises(ValueError, match=match):
            load_baseline(_write(tmp_path / "bad.json", content))


@pytest.mark.kiwi_id(2350)
def test_exception_domain_field_and_matching() -> None:
    """例外登记域维度：可选字段解析 / 非字符串报错 / 按域命中 / 域未登记报错。"""
    entries = ConcurrentStableList([_exception(service="identity", domain="user")])
    assert exception_allows(entries, service="platform", table="sys_role", operation="read", domain="user"), "域命中"
    assert not exception_allows(entries, service="platform", table="sys_role", operation="read", domain="role")
    assert exception_allows(entries, service="identity", table="sys_role", operation="read"), "服务维仍可命中"

    problems = validate_exceptions(
        (_exception(domain="ghost"),),
        known_tables=ConcurrentStableSet({"sys_role"}),
        known_prefixes=ConcurrentStableSet({"sys_"}),
        known_services=ConcurrentStableSet({"report"}),
        known_domains=ConcurrentStableSet({"user"}),
    )
    assert any("domain 未在业务域清单：ghost" in item for item in problems)
    assert (
        validate_exceptions(
            (_exception(domain="ghost"),),
            known_tables=ConcurrentStableSet({"sys_role"}),
            known_prefixes=ConcurrentStableSet({"sys_"}),
            known_services=ConcurrentStableSet({"report"}),
        )
        == []
    ), "未提供域清单时跳过域校验"


@pytest.mark.kiwi_id(2350)
def test_exception_load_with_domain_field(tmp_path: Path) -> None:
    """白名单载入：`domain` 可选字段读取；类型非法即报错。"""
    valid = _write(
        tmp_path / "valid.json",
        json.dumps({"version": 1, "exceptions": [dict(_exception(domain="user").__dict__)]}, ensure_ascii=False),
    )
    loaded = load_exceptions(valid)
    assert loaded[0].domain == "user"

    invalid = _write(
        tmp_path / "invalid.json",
        json.dumps({"version": 1, "exceptions": [{**dict(_exception().__dict__), "domain": 1}]}, ensure_ascii=False),
    )
    with pytest.raises(ValueError, match="domain"):
        load_exceptions(invalid)


@pytest.mark.kiwi_id(2350)
def test_assess_table_by_domain() -> None:
    """域维度越界判定：同域放行 / 跨域越界（带两侧域）/ 不归域与未登记表放行 / 域例外放行。"""
    assert assess_table("sys_role", service="platform", operation="write", domain="role") is None
    assert assess_table("sys_outbox", service="platform", operation="write", domain="role") is None
    assert assess_table("zzz_unknown", service="platform", operation="read", domain="role") is None

    violation = assess_table("sys_role", service="platform", operation="write", domain="user")
    assert violation is not None
    assert (violation.domain, violation.owner_domain, violation.owner) == ("user", "role", "platform")
    assert violation.service == "platform"

    exceptions = (_exception(domain="user"),)
    assert assess_table("sys_role", service="platform", operation="read", domain="user", exceptions=exceptions) is None
    assert (
        assess_table("sys_role", service="platform", operation="write", domain="user", exceptions=exceptions)
        is not None
    ), "写侧硬禁无例外"


@pytest.mark.kiwi_id(2350)
def test_assess_statement_by_domain() -> None:
    """语句级域维度判定：跨域引用逐表产出（含域标识）。"""
    violations = assess_statement("select * from sys_role", service="platform", domain="user")
    assert [violation.table for violation in violations] == ["sys_role"]
    assert violations[0].owner_domain == "role"
    assert assess_statement("select * from sys_role", service="platform", domain="role") == ()


@pytest.mark.kiwi_id(2350)
def test_service_level_violation_carries_owner_domain() -> None:
    """服务维判定保持原语义，并随带表归属域（便于观测归因）。"""
    violation = assess_table("sys_role", service="report", operation="read")
    assert violation is not None and violation.owner == "platform"
    assert (violation.domain, violation.owner_domain) == ("", "role")


@pytest.mark.kiwi_id(2350)
def test_guard_domain_mode_blocks_cross_domain() -> None:
    """运行期守卫域维度：同域放行、跨域 `enforce` 阻断且文案带两侧域。"""
    guard = TableOwnershipGuard("platform", mode="enforce", domain="user")
    engine = create_engine("sqlite://")
    guard.install()
    try:
        with engine.connect() as conn, pytest.raises(DataOwnershipError, match="跨域库访问被拒：域 user 访问 sys_role"):
            conn.execute(text("update sys_role set code = 'x'"))
    finally:
        guard.uninstall()
        engine.dispose()
    assert guard.snapshot().blocked == 1


@pytest.mark.kiwi_id(2350)
def test_guard_service_mode_message_unchanged() -> None:
    """服务维守卫文案不变（未传 domain 时按服务报）。"""
    guard = TableOwnershipGuard("report", mode="enforce")
    engine = create_engine("sqlite://")
    guard.install()
    try:
        with engine.connect() as conn:
            assert guard.assess("select * from sys_role", service="report") != ()
            with pytest.raises(DataOwnershipError, match="跨服务库访问被拒"):
                conn.execute(text("select * from sys_role"))
    finally:
        guard.uninstall()
        engine.dispose()


@pytest.mark.kiwi_id(2350)
def test_directory_domain_queries() -> None:
    """边界模块的域查询出口：表 → 域、域 → 表集（与登记同源）。"""
    assert table_domain("sys_user") == "user"
    assert table_domain("zzz_unknown") is None
    assert "sys_user" in owned_tables_for_domain("user")
    assert owned_tables_for_domain("user", datasource=Datasource.TENANT, include_planned=False) == frozenset(
        {"sys_user", "sys_account_lock", "sys_user_extension"}
    )


@pytest.mark.kiwi_id(2350)
def test_table_records_declare_domains() -> None:
    """登记清单双字段齐备：除基础设施表与不归域表外，每条记录都带已登记业务域。"""
    for record in table_ownership_view():
        if record.owner == OWNER_EVERY_SERVICE or record.table_name in NO_DOMAIN_TABLES:
            assert record.domain == ""
            continue
        assert record.domain, f"{record.table_name} 未登记归属业务域"
