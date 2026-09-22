"""查询方案真实存储用例（Kiwi 963，02-4-27）：落库 CRUD / 三级默认解析 / 个人方案 owner 过滤。

测试库：临时 SQLite 文件（跑 Alembic 首个迁移建表）。
"""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config

from alembic import command
from bms_core.core.config import get_settings
from bms_core.core.context import current_user_id
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.listing.base import QueryScheme, QuerySchemeScope, QuerySchemeTarget
from bms_core.listing.store import SqlQuerySchemeStore


def _run_migrations(url: str) -> None:
    """对目标库执行 Alembic 首个迁移。

    Args:
        url: 数据库 URL。
    """
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.cmd_opts = SimpleNamespace(x=[f"url={url}"])  # pyright: ignore[reportAttributeAccessIssue]
    command.upgrade(cfg, "head")


@contextmanager
def _as_user(user_id: int | None) -> Generator[None]:
    """切换当前用户上下文（个人方案归属）。

    Args:
        user_id: 用户 ID（None 表示未登录）。

    Yields:
        None: 作用域内用户生效。
    """
    token = current_user_id.set(user_id)
    try:
        yield
    finally:
        current_user_id.reset(token)


@pytest.fixture
def scheme_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SqlQuerySchemeStore]:
    """临时库 + 查询方案真实存储。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Returns:
        SqlQuerySchemeStore: 存储实例。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'scheme_test.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    get_settings.cache_clear()
    _run_migrations(url)
    store = SqlQuerySchemeStore(engines=EngineRegistry(EngineFactory(get_settings())))
    yield store
    get_settings.cache_clear()


@pytest.mark.kiwi_id(963)
async def test_query_scheme_crud_and_default_resolution(scheme_store: SqlQuerySchemeStore) -> None:
    """方案 CRUD 与三级默认解析（个人 > 租户 > 平台）与 owner 过滤。"""
    with _as_user(1001):
        personal = await scheme_store.save(
            QueryScheme(
                name="我的常用",
                scope=QuerySchemeScope.USER,
                target=QuerySchemeTarget.ITEMS,
                dict_type="region",
                conditions={"logic": "AND", "children": []},
                is_default=True,
            )
        )
        assert personal.id is not None
        listed = await scheme_store.list(QuerySchemeTarget.ITEMS)
        assert [scheme.name for scheme in listed] == ["我的常用"]
        resolved = await scheme_store.resolve_default(QuerySchemeTarget.ITEMS)
        assert resolved is not None
        assert resolved.name == "我的常用"

        platform = await scheme_store.save(
            QueryScheme(
                name="平台默认",
                scope=QuerySchemeScope.PLATFORM,
                target=QuerySchemeTarget.ITEMS,
                dict_type="region",
                is_default=True,
            )
        )
        assert platform.id is not None
        # 个人优先于平台
        resolved2 = await scheme_store.resolve_default(QuerySchemeTarget.ITEMS)
        assert resolved2 is not None
        assert resolved2.name == "我的常用"
        # 更新（乐观锁正常路径）与删除
        personal.name = "我的常用改"
        updated = await scheme_store.save(personal)
        assert updated.name == "我的常用改"
        assert await scheme_store.get(personal.id or 0) is not None
        assert await scheme_store.delete(personal.id or 0) is True
        assert await scheme_store.get(personal.id or 0) is None

    with _as_user(2002):
        # 他人个人方案不可见；平台方案可见
        listed_other = await scheme_store.list(QuerySchemeTarget.ITEMS)
        assert [scheme.name for scheme in listed_other] == ["平台默认"]
        resolved_other = await scheme_store.resolve_default(QuerySchemeTarget.ITEMS)
        assert resolved_other is not None
        assert resolved_other.name == "平台默认"
