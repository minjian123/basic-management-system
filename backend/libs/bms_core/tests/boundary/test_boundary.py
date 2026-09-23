"""数据所有权能力域测试（Kiwi 2170 / 2171）：归属 / SQL 提取 / 越界判定 / 例外 / 守卫三模式。"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from bms_core.boundary.assess import assess_statement, assess_table
from bms_core.boundary.base import get_data_ownership_guard
from bms_core.boundary.directory import (
    known_prefixes,
    known_services,
    table_owner,
    table_prefix_of,
)
from bms_core.boundary.exceptions import (
    OwnershipException,
    exception_allows,
    load_exceptions,
    validate_exceptions,
)
from bms_core.boundary.null import NullDataOwnershipGuard
from bms_core.boundary.sql import analyze, extract_tables, operation_of
from bms_core.boundary.table import TableOwnershipGuard
from bms_core.core.exceptions import ConfigError, DataOwnershipError
from bms_core.metrics.null import NullMetrics


def _exception(**overrides: str) -> OwnershipException:
    """构造测试例外（默认合法，按需覆盖字段）。"""
    values = {
        "service": "report",
        "target_prefix": "org_",
        "access": "read",
        "exit": "readonly_projection",
        "consumer": "报表聚合",
        "reason": "测试",
        "alternative": "经组织主数据基座",
        "expiry": "测试后移除",
        "registered_at": "2026-09-23",
    }
    values.update(overrides)
    return OwnershipException(**values)


def _write_exceptions(path: Path, entries: list[dict[str, str]]) -> None:
    """写例外白名单文件（version=1）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "exceptions": entries}, ensure_ascii=False), encoding="utf-8")


@pytest.mark.kiwi_id(2170)
def test_directory_ownership() -> None:
    """表级归属查询口径（06_03：不再有共享前缀，`sys_` 表按表级归属判定）。"""
    assert table_prefix_of("org_item") == "org_"
    assert table_prefix_of("demo") == "demo"
    assert table_owner("sys_tenant") == "tenant"
    assert table_owner("sys_module") == "platform"
    assert table_owner("sys_outbox") == "*"
    assert table_owner("zzz_unknown") is None
    assert "sys_" in known_prefixes()
    assert "report" in known_services()


@pytest.mark.kiwi_id(2170)
def test_sql_operation_and_tables() -> None:
    """SQL 操作归类与表名提取（去引号 / schema 末段 / 注释）。"""
    assert operation_of("SELECT 1") == "read"
    assert operation_of("update org_item set x=1") == "write"
    assert operation_of("create table x (id int)") == "ddl"
    assert operation_of("pragma x") == "unknown"
    assert extract_tables('SELECT * FROM "sys_tenant"') == ("sys_tenant",)
    tables = extract_tables("select a from public.org_item join pur_order on 1 -- note\n where 1")
    assert tables == ("org_item", "pur_order")
    assert [ref.table for ref in analyze("delete from org_item")] == ["org_item"]


@pytest.mark.kiwi_id(2170)
def test_assess_table_ownership() -> None:
    """越界判定：基础设施表 / 自身归属 / 未登记表名放行，他服务归属越界。"""
    assert assess_table("sys_outbox", service="org", operation="read") is None
    assert assess_table("demo", service="platform", operation="read") is None
    assert assess_table("zzz_unknown", service="org", operation="read") is None
    violation = assess_table("sys_tenant", service="org", operation="read")
    assert violation is not None
    assert violation.owner == "tenant" and violation.prefix == "sys_"


@pytest.mark.kiwi_id(2170)
def test_assess_statement_and_exception() -> None:
    """SQL 越界判定 + 只读例外只放行 read 操作。"""
    exceptions = (_exception(target_prefix="sys_dict_type"),)
    assert assess_statement("select * from sys_dict_type", service="report", exceptions=exceptions) == ()
    assert assess_statement("select * from sys_dict_type", service="report") != ()
    assert assess_statement("update sys_dict_type set x=1", service="report", exceptions=exceptions) != ()


@pytest.mark.kiwi_id(2170)
def test_exceptions_load_and_validate(tmp_path: Path) -> None:
    """例外白名单加载 / 结构校验 / 命中判定。"""
    assert load_exceptions(tmp_path / "none.json") == ()
    valid = tmp_path / "valid.json"
    _write_exceptions(valid, [_exception().__dict__])
    entries = load_exceptions(valid)
    assert len(entries) == 1
    assert exception_allows(entries, service="report", table="org_item", operation="read")
    assert not exception_allows(entries, service="report", table="org_item", operation="write")

    invalid = tmp_path / "invalid.json"
    _write_exceptions(invalid, [_exception(access="write").__dict__])
    with pytest.raises(ValueError, match="access"):
        load_exceptions(invalid)

    problems = validate_exceptions(
        (_exception(service="unknown_svc"), _exception(target_prefix="zzz_"), _exception(exit="bad")),
        known_tables=frozenset({"org_item"}),
        known_prefixes=frozenset({"org_"}),
        known_services=frozenset({"report"}),
    )
    assert any("service" in item for item in problems)
    assert any("目标" in item for item in problems)
    assert any("exit" in item for item in problems)


@pytest.mark.kiwi_id(2171)
def test_null_guard() -> None:
    """缺省守卫恒定无越界、不安装监听。"""
    guard = NullDataOwnershipGuard()
    assert guard.assess("select * from sys_tenant", service="report") == ()
    assert guard.snapshot().violations == 0


@pytest.mark.kiwi_id(2171)
def test_guard_modes_and_counters() -> None:
    """守卫三模式：off 不检测 / warn 计数不抛 / enforce 阻断。"""
    off = TableOwnershipGuard("report", mode="off")
    assert off.assess("select * from sys_tenant", service="report") != ()

    warn = TableOwnershipGuard("report", mode="warn")
    enforce = TableOwnershipGuard("report", mode="enforce")

    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite://")
        warn.install()
        enforce.install()
        try:
            async with engine.connect() as conn:
                with pytest.raises(DataOwnershipError):
                    await conn.execute(text("select * from sys_tenant"))
                await conn.execute(text("select 1"))
        finally:
            warn.uninstall()
            enforce.uninstall()
            await engine.dispose()

    asyncio.run(_run())
    assert warn.snapshot().violations == 1
    assert enforce.snapshot().violations == 1 and enforce.snapshot().blocked == 1
    assert DataOwnershipError().code == 10008


@pytest.mark.kiwi_id(2170)
def test_sql_duplicate_and_ignored_tables() -> None:
    """重复表名与忽略 token（如 `dual`）不重复产出。"""
    assert extract_tables("select a from org_item join org_item on 1") == ("org_item",)
    assert extract_tables("select a from dual") == ()


@pytest.mark.kiwi_id(2170)
def test_exceptions_load_error_paths(tmp_path: Path) -> None:
    """白名单加载异常路径：JSON / 根 / 版本 / 结构 / 条目 / 字段。"""
    bad = tmp_path / "bad.json"
    cases = (
        ("{not json", "JSON"),
        ("[]", "根须为对象"),
        ('{"version": 2, "exceptions": []}', "版本"),
        ('{"version": 1, "exceptions": {}}', "exceptions"),
        ('{"version": 1, "exceptions": [1]}', "须为对象"),
        ('{"version": 1, "exceptions": [{}]}', "字段缺失"),
    )
    for content, match in cases:
        bad.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match=match):
            load_exceptions(bad)


@pytest.mark.kiwi_id(2170)
def test_validate_exceptions_prefix_and_date() -> None:
    """前缀未登记与登记日期格式非法。"""
    problems = validate_exceptions(
        (_exception(target_prefix="zzz_"), _exception(registered_at="2026/09/23")),
        known_tables=frozenset({"org_item"}),
        known_prefixes=frozenset({"org_"}),
        known_services=frozenset({"report"}),
    )
    assert any("目标" in item for item in problems)
    assert any("registered_at" in item for item in problems)


@pytest.mark.kiwi_id(2171)
def test_guard_invalid_mode() -> None:
    """非法运行模式拒构造。"""
    with pytest.raises(ConfigError):
        TableOwnershipGuard("report", mode="bad")


@pytest.mark.kiwi_id(2171)
async def test_guard_setup_aclose_idempotent() -> None:
    """装配 / 释放幂等（重复 install / uninstall 不重复挂载）。"""
    guard = TableOwnershipGuard("report", mode="warn")
    await guard.setup()
    guard.install()
    await guard.aclose()
    guard.uninstall()


@pytest.mark.kiwi_id(2171)
async def test_guard_skips_off_and_empty_service() -> None:
    """`off` 模式与空服务标识均不检测语句。"""
    off = TableOwnershipGuard("report", mode="off")
    empty = TableOwnershipGuard("", mode="warn")
    engine = create_async_engine("sqlite+aiosqlite://")
    off.install()
    empty.install()
    try:
        async with engine.connect() as conn:
            with pytest.raises(OperationalError):
                await conn.execute(text("select * from sys_tenant"))
    finally:
        off.uninstall()
        empty.uninstall()
        await engine.dispose()
    assert off.snapshot().statements == 0
    assert empty.snapshot().statements == 0


@pytest.mark.kiwi_id(2171)
async def test_guard_reports_metric_with_loop() -> None:
    """有事件循环且配置指标器时上报越界计数（不阻断 warn）。"""
    guard = TableOwnershipGuard("report", mode="warn", metrics=NullMetrics())
    engine = create_async_engine("sqlite+aiosqlite://")
    guard.install()
    try:
        async with engine.connect() as conn:
            with pytest.raises(OperationalError):
                await conn.execute(text("select * from sys_tenant"))
        await asyncio.sleep(0)
    finally:
        guard.uninstall()
        await engine.dispose()
    assert guard.snapshot().violations == 1


@pytest.mark.kiwi_id(2171)
def test_guard_metric_without_loop_degrades() -> None:
    """同步执行（无事件循环）时指标上报静默降级、检查仍计数。"""
    guard = TableOwnershipGuard("report", mode="warn", metrics=NullMetrics())
    engine = create_engine("sqlite://")
    guard.install()
    try:
        with engine.connect() as conn, pytest.raises(OperationalError):
            conn.execute(text("select * from sys_tenant"))
    finally:
        guard.uninstall()
        engine.dispose()
    assert guard.snapshot().violations == 1


@pytest.mark.kiwi_id(2171)
def test_guard_assess_failure_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    """守卫自身解析异常静默降级、不阻断数据库执行。"""
    guard = TableOwnershipGuard("report", mode="warn")

    def _boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(guard, "assess", _boom)
    engine = create_engine("sqlite://")
    guard.install()
    try:
        with engine.connect() as conn, pytest.raises(OperationalError):
            conn.execute(text("select * from sys_tenant"))
    finally:
        guard.uninstall()
        engine.dispose()
    assert guard.snapshot().violations == 0


@pytest.mark.kiwi_id(2171)
def test_get_data_ownership_guard_provider() -> None:
    """依赖注入提供者按配置解析守卫（空 provider → null 缺省）。"""
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=SimpleNamespace(data_ownership=SimpleNamespace(provider="")))
        ),
    )
    guard = get_data_ownership_guard(request)  # type: ignore[arg-type]
    assert isinstance(guard, NullDataOwnershipGuard)
