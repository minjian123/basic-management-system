"""平台自注册启动钩子用例（07B `02_06`；Kiwi 编号归 `05_01` 统一登记）。

用临时 SQLite + 临时清单覆盖：开关关闭跳过、清单缺失 / 归属不符拒启、注册成功（含警示输出）、
库不可用降级放行、注册异常转 `CatalogError`。
"""

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.datasource.registry import reset_data_source_records
from bms_core.models.base import BaseModel
from bms_core.services.module_registry import (
    reset_collaboration_records,
    reset_domain_services,
    reset_error_code_records,
    reset_product_records,
    reset_product_routes,
    reset_seed_records,
    reset_service_records,
)
from bms_platform.domains.platform_registry.services import declaration_bootstrap as module

_MANIFEST = """
product_key = "platform"

[[products]]
product_key = "platform"
name = "平台自注册"

[[services]]
module_key = "pextra"
name = "平台扩展服务"
table_prefix = "pextra_"
event_domain = "platform"
service_group = "product"
status = "enabled"
"""


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """临时 SQLite 会话（建全部注册表）。

    Args:
        tmp_path: 临时目录。

    Yields:
        AsyncSession: 会话。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bootstrap.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(BaseModel.metadata.create_all)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


def _app() -> Any:
    """构造应用替身（只读 `state.settings` / 引擎注册表 / 会话工厂）。

    Returns:
        Any: 应用替身。
    """
    return SimpleNamespace(
        state=SimpleNamespace(
            settings=SimpleNamespace(
                registry=SimpleNamespace(register_on_startup=True),
                app=SimpleNamespace(service="platform"),
            ),
            engine_registry=None,
            session_factory=None,
            declaration_register_degraded=False,
        )
    )


def _manifest_file(tmp_path: Path, *, product_key: str = "platform") -> Path:
    """写一份临时平台清单。

    Args:
        tmp_path: 临时目录。
        product_key: 清单归属（用于构造归属不符场景）。

    Returns:
        Path: 清单路径。
    """
    path = tmp_path / "platform.toml"
    text = _MANIFEST
    if product_key != "platform":
        # 归属不符场景：整份替换产品键（含产品档案段，避免先被清单结构校验拦下）
        text = text.replace('product_key = "platform"', f'product_key = "{product_key}"')
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _patch_session_scope(monkeypatch: pytest.MonkeyPatch, session: AsyncSession) -> None:
    """把 `session_scope` 替身指向临时会话。

    Args:
        monkeypatch: 打桩器。
        session: 目标会话。
    """

    @asynccontextmanager
    async def _scope(*_args: object, **_kwargs: object) -> AsyncGenerator[AsyncSession]:
        """返回既有会话（事务由用例控制）。

        Args:
            *_args: 位置参数（未使用）。
            **_kwargs: 关键字参数（未使用）。

        Yields:
            AsyncSession: 会话。
        """
        yield session

    monkeypatch.setattr(module, "session_scope", _scope)


def test_manifest_path_requires_platform_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """清单定位：命中返回路径；缺失抛 `CatalogError`。"""
    other = tmp_path / "demo.toml"
    other.write_text('product_key = "demo"\n', encoding="utf-8")
    monkeypatch.setattr(module, "local_manifest_paths", lambda: ConcurrentStableList([other]))

    with pytest.raises(CatalogError, match="平台自身声明缺失"):
        module._platform_manifest_path("platform")  # pyright: ignore[reportPrivateUsage]

    monkeypatch.setattr(module, "local_manifest_paths", lambda: ConcurrentStableList([_manifest_file(tmp_path)]))
    assert module._platform_manifest_path("platform").name == "platform.toml"  # pyright: ignore[reportPrivateUsage]


async def test_bootstrap_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """开关关闭：直接返回（单测 / 单仓自检）。"""
    app = _app()
    app.state.settings.registry.register_on_startup = False

    await module.bootstrap_platform_declarations(app)

    assert app.state.declaration_register_degraded is False


async def test_bootstrap_rejects_product_key_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session: AsyncSession
) -> None:
    """清单归属与服务标识不一致：拒启。"""
    monkeypatch.setattr(
        module, "local_manifest_paths", lambda: ConcurrentStableList([_manifest_file(tmp_path, product_key="demo")])
    )

    with pytest.raises(CatalogError, match="平台清单归属与服务标识不一致"):
        await module.bootstrap_platform_declarations(_app())


async def test_bootstrap_registers_and_logs_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session: AsyncSession
) -> None:
    """注册成功：落库 + 警示输出（未装载对端能力时降为警示）。"""
    monkeypatch.setattr(module, "local_manifest_paths", lambda: ConcurrentStableList([_manifest_file(tmp_path)]))
    _patch_session_scope(monkeypatch, session)

    app = _app()
    await module.bootstrap_platform_declarations(app)

    assert app.state.declaration_register_degraded is False


async def test_bootstrap_logs_report_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session: AsyncSession
) -> None:
    """注册回执含警示：逐条记日志（不吞、不阻断启动）。"""
    monkeypatch.setattr(module, "local_manifest_paths", lambda: ConcurrentStableList([_manifest_file(tmp_path)]))
    _patch_session_scope(monkeypatch, session)

    class _Warned:
        """注册服务替身：回执含一条警示。"""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            """忽略构造参数。

            Args:
                *_args: 位置参数（未使用）。
                **_kwargs: 关键字参数（未使用）。
            """

        async def register(self, *_args: object, **_kwargs: object) -> Any:
            """返回带警示的回执。

            Args:
                *_args: 位置参数（未使用）。
                **_kwargs: 关键字参数（未使用）。

            Returns:
                Any: 回执替身。
            """
            return SimpleNamespace(
                product_key="platform",
                created={"services": 1},
                updated={},
                retired={},
                warnings=ConcurrentStableFrozenList(("单仓告警",)),
            )

    monkeypatch.setattr(module, "DeclarationRegistryService", _Warned)

    app = _app()
    await module.bootstrap_platform_declarations(app)

    assert app.state.declaration_register_degraded is False


async def test_startup_hook_registers_platform_declarations(service_app: Any, client: Any) -> None:
    """真启动链：钩子把本仓平台声明写进库，快照出口随即能看到平台服务行。

    单测环境默认关掉该钩子（避免「声明即全量」退役夹具行），这里显式打开并**手动触发一次**，
    验证「钩子 → 注册表 → 快照出口」这条生产路径真实可用。

    Args:
        service_app: 平台应用实例。
        client: 带认证头的异步客户端。
    """
    service_app.state.settings.registry.register_on_startup = True

    await module.bootstrap_platform_declarations(service_app)

    assert getattr(service_app.state, "declaration_register_degraded", False) is False
    from bms_core.db.keys import PLATFORM_DB_KEY
    from bms_core.db.session import session_scope
    from bms_platform.domains.platform_registry.repositories.declaration_repository import (
        DeclarationRepository,
    )

    async with session_scope(
        service_app.state.engine_registry,
        db_key=PLATFORM_DB_KEY,
        factory=service_app.state.session_factory,
    ) as session:
        view = await DeclarationRepository(session).load_snapshot()
    assert "sys" in [record.module_key for record in view.of("services")]


async def test_bootstrap_degrades_when_db_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """库不可用（SQLAlchemyError）：降级放行并打标记，不拒启。"""
    monkeypatch.setattr(module, "local_manifest_paths", lambda: ConcurrentStableList([_manifest_file(tmp_path)]))

    @asynccontextmanager
    async def _broken(*_args: object, **_kwargs: object) -> AsyncGenerator[None]:
        """模拟库不可用。

        Args:
            *_args: 位置参数（未使用）。
            **_kwargs: 关键字参数（未使用）。

        Raises:
            OperationalError: 始终抛出（模拟未初始化库）。
        """
        raise OperationalError("select 1", {}, Exception("no such table"))
        yield  # pragma: no cover - 不可达，保持生成器语义

    monkeypatch.setattr(module, "session_scope", _broken)

    app = _app()
    await module.bootstrap_platform_declarations(app)

    assert app.state.declaration_register_degraded is True


async def test_bootstrap_propagates_catalog_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session: AsyncSession
) -> None:
    """注册抛 `CatalogError`（校验不过 / 撞键）：原样上抛（拒启，不改写成通用错误）。"""
    monkeypatch.setattr(module, "local_manifest_paths", lambda: ConcurrentStableList([_manifest_file(tmp_path)]))
    _patch_session_scope(monkeypatch, session)

    class _Rejected:
        """注册服务替身：固定抛 `CatalogError`。"""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            """忽略构造参数。

            Args:
                *_args: 位置参数（未使用）。
                **_kwargs: 关键字参数（未使用）。
            """

        async def register(self, *_args: object, **_kwargs: object) -> None:
            """固定抛错。

            Args:
                *_args: 位置参数（未使用）。
                **_kwargs: 关键字参数（未使用）。

            Raises:
                CatalogError: 始终抛出。
            """
            raise CatalogError("绑定校验未通过")

    monkeypatch.setattr(module, "DeclarationRegistryService", _Rejected)

    with pytest.raises(CatalogError, match="绑定校验未通过"):
        await module.bootstrap_platform_declarations(_app())


async def test_bootstrap_wraps_unexpected_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session: AsyncSession
) -> None:
    """注册过程抛出非 `CatalogError` 异常：转 `CatalogError`（拒启）。"""
    monkeypatch.setattr(module, "local_manifest_paths", lambda: ConcurrentStableList([_manifest_file(tmp_path)]))
    _patch_session_scope(monkeypatch, session)

    class _Broken:
        """注册服务替身：固定抛 RuntimeError。"""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            """忽略构造参数。

            Args:
                *_args: 位置参数（未使用）。
                **_kwargs: 关键字参数（未使用）。
            """

        async def register(self, *_args: object, **_kwargs: object) -> None:
            """固定抛错。

            Args:
                *_args: 位置参数（未使用）。
                **_kwargs: 关键字参数（未使用）。

            Raises:
                RuntimeError: 始终抛出。
            """
            raise RuntimeError("boom")

    monkeypatch.setattr(module, "DeclarationRegistryService", _Broken)

    with pytest.raises(CatalogError, match="平台声明注册失败"):
        await module.bootstrap_platform_declarations(_app())


@pytest.fixture(autouse=True)
def _restore_views() -> Iterator[None]:
    """用例后复位全局登记视图（本模块向视图写入合成声明，避免污染其他用例）。

    Yields:
        None: 用例运行期。
    """
    yield
    for reset in (
        reset_collaboration_records,
        reset_data_source_records,
        reset_domain_services,
        reset_error_code_records,
        reset_product_records,
        reset_product_routes,
        reset_seed_records,
        reset_service_records,
    ):
        reset()


@pytest.fixture(autouse=True)
def _quiet(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """静默日志（避免用例输出噪声）。

    Args:
        monkeypatch: 打桩器。

    Yields:
        None: 用例运行期。
    """
    del monkeypatch
    yield
