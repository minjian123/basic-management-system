"""注册表仓储与服务用例（07B `02_06`；Kiwi 编号归 `05_01` 统一登记）。

用真 SQLite（临时库 + `BaseModel.metadata.create_all`）覆盖：
- 现状读取（空库 / 八类回读 / 损坏 JSON 即抛）；
- 对账落库（新增 / 覆盖 / 退役）与回读一致性；
- 注册服务（校验 → 对账 → 落库 → 投影）的成功、幂等与拒绝分支；
- 平台自注册载荷合并（纯函数分支）。
"""

from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.collaboration.usage import CapabilityUsage
from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList
from bms_core.core.exceptions import CatalogError
from bms_core.models.base import BaseModel
from bms_core.models.platform.declaration import SysCollaboration
from bms_core.registry.declarations import (
    DeclarationPayload,
    RegistrySnapshot,
    content_hash_of,
    from_manifest,
    plan_declarations,
)
from bms_core.registry.products import parse_manifest_text
from bms_core.services.module_registry import (
    CollaborationRecord,
    ModuleRecord,
    register_domain_services,
    reset_domain_services,
)
from bms_platform.domains.platform_registry.repositories.declaration_repository import DeclarationRepository
from bms_platform.domains.platform_registry.services.declaration_bootstrap import with_platform_services
from bms_platform.domains.platform_registry.services.declaration_registry import DeclarationRegistryService

_MANIFEST = """
product_key = "demo"

[[products]]
product_key = "demo"
name = "演示产品"
status = "enabled"

[[services]]
module_key = "demo"
service_key = "demo"
name = "演示服务"
table_prefix = "demo_"
event_domain = "demo"
service_group = "product"
product_key = "demo"
status = "enabled"
errcode_segment = "88"

[[collaborations]]
name = "demo.demo_op.roles"
domain = "demo_op"
kind = "read"
path = "/api/v1/demo/roles"
frontend_prefix = "demo"
contract_version = "0.1.0"

[[seeds]]
name = "demo-seed"
module = "demo.seeds"
entry = "seed_demo"
service = "demo"
db_key = "platform_platform"

[seeds.tables]
demo = "id"

[[errcodes]]
code = 880001
domain = "demo"
http_status = 200
message_key = "demo.error.bad"
severity = "warning"
description = "说明"

[[usages]]
name = "demo.demo_op.roles"
degrade = "empty"
reason = "断链按无角色"
"""


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """临时 SQLite 会话（建全部注册表）。

    Args:
        tmp_path: 临时目录。

    Yields:
        AsyncSession: 数据库会话。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'registry.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(BaseModel.metadata.create_all)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.fixture(autouse=True)
def _demo_domain() -> Iterator[None]:
    """登记用例专用业务域（能力名第二段须是已登记域）。

    Yields:
        None: 用例运行期。
    """
    register_domain_services(ConcurrentStableFrozenDict({"demo_op": "demo"}))
    yield
    reset_domain_services()


def _payload(path: str = "/api/v1/demo/roles") -> DeclarationPayload:
    """解析用例清单为注册载荷（可替换能力访问面路径）。

    Args:
        path: 能力访问面路径。

    Returns:
        DeclarationPayload: 载荷。
    """
    payload = from_manifest(parse_manifest_text(_MANIFEST, source="<test>"))
    if path == "/api/v1/demo/roles":
        return payload
    return replace(
        payload,
        collaborations=ConcurrentStableFrozenList((_capability_with_path(path),)),
    )


def _capability_with_path(path: str) -> CollaborationRecord:
    """构造指定路径的能力记录。

    Args:
        path: 访问面路径。

    Returns:
        CollaborationRecord: 能力记录。
    """
    return CollaborationRecord(
        name="demo.demo_op.roles",
        domain="demo_op",
        kind="read",
        contract_version="0.1.0",
        path=path,
        product_key="demo",
        frontend_prefix="demo",
    )


async def _apply(repository: DeclarationRepository, payload: DeclarationPayload) -> None:
    """按当前库现状对账并落库。

    Args:
        repository: 仓储。
        payload: 注册载荷。
    """
    current = await repository.load_snapshot()
    plan, conflicts = plan_declarations(payload, current)
    assert list(conflicts) == []
    await repository.apply(plan, product_key=payload.product_key)


async def test_load_snapshot_empty(session: AsyncSession) -> None:
    """空库：八类皆空、无声明方。"""
    snapshot = await DeclarationRepository(session).load_snapshot()

    assert snapshot.of("collaborations") == []
    assert snapshot.owner_of("collaborations", "x") is None


async def test_apply_then_snapshot_roundtrip(session: AsyncSession) -> None:
    """落库后回读：八类记录、指纹与声明方一致。"""
    repository = DeclarationRepository(session)

    await _apply(repository, _payload())

    snapshot = await repository.load_snapshot()
    assert [item.name for item in snapshot.of("collaborations")] == ["demo.demo_op.roles"]
    assert [item.code for item in snapshot.of("errcodes")] == [880001]
    assert [item.name for item in snapshot.of("seeds")] == ["demo-seed"]
    assert [item.product_key for item in snapshot.of("products")] == ["demo"]
    assert [item.module_key for item in snapshot.of("services")] == ["demo"]
    assert [item.name for item in snapshot.of("usages")] == ["demo.demo_op.roles"]
    assert snapshot.owner_of("collaborations", "demo.demo_op.roles") == "demo"
    assert snapshot.is_retired("collaborations", "demo.demo_op.roles") is False


async def test_apply_retires_absent_rows(session: AsyncSession) -> None:
    """本次未声明：置退役（不删行），回读识别为退役。"""
    repository = DeclarationRepository(session)
    await _apply(repository, _payload())

    await _apply(repository, DeclarationPayload(product_key="demo", service_key="demo"))

    snapshot = await repository.load_snapshot()
    assert snapshot.is_retired("collaborations", "demo.demo_op.roles") is True


async def test_apply_updates_changed_content(session: AsyncSession) -> None:
    """同键换内容：覆盖写入，指纹随之变化。"""
    repository = DeclarationRepository(session)
    await _apply(repository, _payload())

    await _apply(repository, _payload("/api/v1/demo/roles-v2"))

    snapshot = await repository.load_snapshot()
    record = snapshot.of("collaborations")[0]
    assert record.path == "/api/v1/demo/roles-v2"
    assert snapshot.hash_of("collaborations", "demo.demo_op.roles") == content_hash_of("collaborations", record)


async def test_corrupt_json_raises(session: AsyncSession) -> None:
    """库内 JSON 字段损坏：抛 `CatalogError`（不静默退化为空）。"""
    repository = DeclarationRepository(session)
    await _apply(repository, _payload())
    await session.execute(update(SysCollaboration).values(default_consumers="not-json"))
    await session.commit()

    with pytest.raises(CatalogError, match="JSON 字段损坏"):
        await repository.load_snapshot()


async def test_service_register_and_snapshot(session: AsyncSession) -> None:
    """注册服务：全量注册返回计数；重复注册幂等；快照可取回。"""
    service = DeclarationRegistryService(session)

    report = await service.register(_payload())
    assert report.created["collaborations"] == 1

    again = await service.register(_payload())
    assert again.created["collaborations"] == 0
    assert again.unchanged["collaborations"] == 1

    snapshot = await service.snapshot()
    assert len(snapshot.of("collaborations")) == 1


async def test_service_rejects_unregistered_domain(session: AsyncSession) -> None:
    """校验不过（提供方业务域未登记）：抛 `CatalogError`，不写库。"""
    payload = replace(
        _payload(),
        collaborations=ConcurrentStableFrozenList(
            (
                CollaborationRecord(
                    name="demo.unknown.roles",
                    domain="nowhere",
                    kind="read",
                    contract_version="0.1.0",
                    path="/api/v1/demo/x",
                    product_key="demo",
                    frontend_prefix="demo",
                ),
            )
        ),
        usages=ConcurrentStableFrozenList(),
    )

    with pytest.raises(CatalogError, match="提供方业务域未登记"):
        await DeclarationRegistryService(session).register(payload)


async def test_service_rejects_cross_product_conflict(session: AsyncSession) -> None:
    """跨产品撞键：抛 `CatalogError`（声明方不得覆盖他人记录）。"""
    service = DeclarationRegistryService(session)
    await service.register(_payload())
    other = DeclarationPayload(
        product_key="other",
        service_key="other",
        collaborations=ConcurrentStableFrozenList((_capability_with_path("/api/v1/demo/roles-v3"),)),
    )

    with pytest.raises(CatalogError, match="注册冲突"):
        await service.register(other)


def test_platform_payload_merges_service_catalog() -> None:
    """平台载荷合并：`SERVICE_CATALOG` 服务行在前、清单独有行追加在后。"""
    extra = ModuleRecord(
        module_key="extra",
        name="扩展服务",
        table_prefix="extra_",
        event_domain="extra",
        service_key="extra",
        service_group="product",
        product_key="platform",
    )
    payload = DeclarationPayload(
        product_key="platform",
        service_key="platform",
        services=ConcurrentStableFrozenList((extra,)),
    )

    merged = with_platform_services(payload)

    keys = [record.module_key for record in merged.services]
    assert keys[0] == "sys"
    assert keys[-1] == "extra"


def test_usage_only_payload_keeps_snapshot_shape() -> None:
    """只声明使用项的载荷：对空快照对账时只产生使用类新增（其余类别为空）。"""
    payload = DeclarationPayload(
        product_key="demo",
        service_key="demo",
        usages=ConcurrentStableFrozenList((CapabilityUsage(name="demo.demo_op.roles"),)),
    )

    plan, conflicts = plan_declarations(payload, RegistrySnapshot())

    assert list(conflicts) == []
    assert len(plan.created.get("usages") or ()) == 1
    assert plan.created.get("collaborations") == []
