"""启动接库服务目录校验测试（Kiwi 2163）：清单 / 契约 / 拒启 / 空库容错 / 只读快照 / 降级。

- 覆盖 `service_lifespan` 的接库校验链路（`_validate_service_catalog` + `validate_catalog`）：
  正常种子库启动通过、空目录告警放行、冲突逐项拒启（`CatalogError` 码 40003）、
  库不可读拒启、启动前后目录行快照一致（运行时只读边界）；
- **06_01 取数路径**：`platform` 本地读本服务平台库（权威，读失败拒启）；
  其余服务经契约取快照 → 用例以桩替换快照源；**契约不可达时降级放行**（`catalog_degraded`）。
"""

import logging
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.application import BaseServiceApplicationFactory, service_lifespan
from bms_core.core.config import get_settings
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import CatalogError, ServiceUnavailableError
from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRecord, ServiceGroup
from bms_platform.models.catalog import SysModule

_FIELDS = (
    "module_key",
    "service_key",
    "name",
    "table_prefix",
    "business_code",
    "errcode_segment",
    "event_domain",
    "service_group",
    "build_batch",
    "service_version",
    "contract_version",
    "product_key",
    "status",
)


class _LogCapture(logging.Handler):
    """捕获 `bms` 日志器事件消息（断言 critical / warning 告警事件）。"""

    def __init__(self) -> None:
        """初始化捕获列表。"""
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """收集日志消息。

        Args:
            record: 日志记录。
        """
        self.messages.append(record.getMessage())


@contextmanager
def _capture_bms_logs() -> Generator[_LogCapture]:
    """临时挂接 `bms` 日志器捕获器（退出移除，不影响其他用例）。

    Yields:
        _LogCapture: 捕获器（`messages` 为事件消息列表）。
    """
    capture = _LogCapture()
    logger = logging.getLogger("bms")
    logger.addHandler(capture)
    try:
        yield capture
    finally:
        logger.removeHandler(capture)


def _create_app(*, service: str = "platform", contract: str = "0.1.0") -> FastAPI:
    """构造以指定服务名 / 自报契约版本运行的测试应用。

    Args:
        service: 运行服务标识。
        contract: 运行服务自报契约版本。

    Returns:
        FastAPI: 应用实例（接库校验所需 state 由工厂装配）。
    """

    class _Factory(BaseServiceApplicationFactory):
        """测试用服务工厂（只声明身份，不挂业务路由）。"""

        key: str = "application_factory"
        service_name: str = service
        service_title: str = "BMS 目录校验测试服务"
        version: str = "0.1.0"
        contract_version: str = contract

    return _Factory().create(None)


async def _write_records(url: str, records: Sequence[ModuleRecord]) -> None:
    """建表并写入目录记录（测试种子）。

    Args:
        url: 平台库连接串。
        records: 待写入记录。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(cast("Table", SysModule.__table__).create, checkfirst=True)
        async with factory() as session:
            for record in records:
                session.add(SysModule(**{field: getattr(record, field) for field in _FIELDS}))
            await session.commit()
    finally:
        await engine.dispose()


async def _snapshot(url: str) -> list[tuple[object, ...]]:
    """目录行快照（只读边界断言用）。

    Args:
        url: 平台库连接串。

    Returns:
        list[tuple[object, ...]]: 关键列快照（按 id 升序）。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysModule).order_by(SysModule.id)
            rows = (await session.execute(statement)).scalars().all()
            return [(row.module_key, row.table_prefix, row.contract_version, row.status) for row in rows]
    finally:
        await engine.dispose()


@pytest.fixture
def catalog_db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """独立平台库：覆盖平台库连接串（用例内自行播种）。

    Returns:
        str: 平台库连接串（指向临时 SQLite 文件）。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'catalog_startup.db'}"
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", url)
    get_settings.cache_clear()
    return url


@pytest.mark.kiwi_id(2163)
async def test_lifespan_accepts_seeded_catalog(catalog_db_url: str) -> None:
    """正常种子库：启动通过；身份携带自报契约版本；启动前后目录行快照一致（只读）。"""
    await _write_records(catalog_db_url, list(SERVICE_CATALOG))
    before = await _snapshot(catalog_db_url)
    app = _create_app()
    assert app.state.service_identity.contract_version == "0.1.0"
    async with service_lifespan(app):
        assert app.state.startup_complete is True
    assert await _snapshot(catalog_db_url) == before


@pytest.mark.kiwi_id(2163)
async def test_lifespan_tolerates_empty_catalog(catalog_db_url: str) -> None:
    """空目录（未播种）：仅告警放行，不阻断启动。"""
    await _write_records(catalog_db_url, [])
    app = _create_app()
    with _capture_bms_logs() as logs:
        async with service_lifespan(app):
            assert app.state.startup_complete is True
    assert any("service_catalog_empty" in message for message in logs.messages)


def _duplicate_prefix(records: list[ModuleRecord]) -> list[ModuleRecord]:
    """重复表前缀（identity 行改为 sys_）。"""
    records[1] = replace(records[1], table_prefix="sys_")
    return records


def _missing_row(records: list[ModuleRecord]) -> list[ModuleRecord]:
    """缺行（移除 identity 行）。"""
    del records[1]
    return records


def _extra_row(records: list[ModuleRecord]) -> list[ModuleRecord]:
    """清单外登记行。"""
    records.append(
        ModuleRecord(
            module_key="ghost",
            name="幽灵模块",
            table_prefix="ghost_",
            event_domain="ghost",
            service_group=ServiceGroup.CAPABILITY,
        )
    )
    return records


def _field_mismatch(records: list[ModuleRecord]) -> list[ModuleRecord]:
    """字段与清单不符（identity 名称被改）。"""
    records[1] = replace(records[1], name="改过的名字")
    return records


def _contract_major_mismatch(records: list[ModuleRecord]) -> list[ModuleRecord]:
    """库中契约版本主版本不符（identity 升 1.0.0）。"""
    records[1] = replace(records[1], contract_version="1.0.0")
    return records


@pytest.mark.kiwi_id(2163)
@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (_duplicate_prefix, "table_prefix 重复"),
        (_missing_row, "库中缺登记行：identity"),
        (_extra_row, "库中登记行不在清单：ghost"),
        (_field_mismatch, "name 与清单不一致"),
        (_contract_major_mismatch, "契约版本主版本不兼容"),
    ],
)
async def test_lifespan_rejects_catalog_conflicts(
    catalog_db_url: str,
    mutate: Callable[[list[ModuleRecord]], list[ModuleRecord]],
    match: str,
) -> None:
    """接库冲突：重复 / 缺行 / 清单外 / 字段不符 / 契约主版本不符均拒启（码 40003）并 critical 告警。"""
    await _write_records(catalog_db_url, mutate(list(SERVICE_CATALOG)))
    app = _create_app()
    with _capture_bms_logs() as logs, pytest.raises(CatalogError, match=match) as excinfo:
        async with service_lifespan(app):
            pass
    assert excinfo.value.code == ErrorCode.CATALOG
    assert any("service_catalog_invalid" in message for message in logs.messages)


def _stub_snapshot(monkeypatch: pytest.MonkeyPatch, records: Sequence[ModuleRecord]) -> None:
    """以桩替换快照取数（模拟非目录权威服务经契约取到的清单）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        records: 桩返回的服务目录记录。
    """

    async def _load(app: object) -> list[ModuleRecord]:  # pragma: no cover - 桩内联
        return list(records)

    monkeypatch.setattr("bms_core.application.load_catalog_snapshot", _load)


@pytest.mark.kiwi_id(2163)
async def test_lifespan_rejects_unregistered_running_service(
    catalog_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """运行服务未登记：清单中 workflow 行服务位缺失时以 workflow 身份启动被拒。

    非目录权威服务经契约取快照（06_01），故用例注入桩快照（内容取自播种库）保留原断言语义。
    """
    records = [
        replace(record, service_key=None) if record.service_key == "workflow" else record for record in SERVICE_CATALOG
    ]
    await _write_records(catalog_db_url, records)
    _stub_snapshot(monkeypatch, records)
    app = _create_app(service="workflow")
    with pytest.raises(CatalogError, match="运行服务未登记：workflow"):
        async with service_lifespan(app):
            pass


@pytest.mark.kiwi_id(2163)
async def test_lifespan_degrades_when_snapshot_unavailable(
    catalog_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非目录权威服务：快照契约不可达 → 告警放行 + `catalog_degraded`（不拒启）。"""

    async def _unreachable(app: object) -> list[ModuleRecord]:  # pragma: no cover - 桩内联
        raise ServiceUnavailableError("服务目录快照契约调用失败（503）")

    monkeypatch.setattr("bms_core.application.load_catalog_snapshot", _unreachable)
    app = _create_app(service="org")
    with _capture_bms_logs() as logs:
        async with service_lifespan(app):
            assert app.state.startup_complete is True
            assert app.state.catalog_degraded is True
    assert any("service_catalog_snapshot_unavailable" in message for message in logs.messages)


@pytest.mark.kiwi_id(2163)
async def test_lifespan_rejects_self_reported_major_mismatch(catalog_db_url: str) -> None:
    """服务自报契约版本主版本不符：自报 1.0.0 vs 登记 0.1.0 拒启。"""
    await _write_records(catalog_db_url, list(SERVICE_CATALOG))
    app = _create_app(contract="1.0.0")
    with pytest.raises(CatalogError, match="运行服务契约版本主版本不兼容：platform"):
        async with service_lifespan(app):
            pass


@pytest.mark.kiwi_id(2163)
async def test_lifespan_rejects_missing_catalog_table(catalog_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """库不可读（表缺失，自动建表关闭）：提示先执行平台库迁移并拒启。"""
    monkeypatch.setenv("BMS_DATABASE__AUTO_CREATE", "false")
    get_settings.cache_clear()
    app = _create_app()
    with pytest.raises(CatalogError, match="服务目录不可读"):
        async with service_lifespan(app):
            pass
