"""用例级写锁的声明与持锁口径（2026-11-15 收窄）。

为什么收窄：`serial_db_write` 曾是**函数级**夹具，持锁区间覆盖「夹具准备 → 用例调用 → 清理」。
实测（`services/platform/tests/import_export`，`-n 8`）：持锁合计 97.9s，其中约 88.7s 花在夹具
准备（建表 / 造种子 / 装配应用），而准备阶段的写入本身已有专用保护——建表走
`ddl-<库摘要>`、内置角色种子走 `permission-admin-seed`，import 作业的会话还一开事务就
`BEGIN IMMEDIATE`。把准备阶段一并塞进写锁，等于让整轮用例串行（8 个 worker 平均各等锁 83s）。

现行口径：

- **按库拆两把**：`platform-db-write` / `tenant-db-write`。两者是不同 SQLite 文件，写不同库的
  用例互不阻塞（此前一把 `shared-db-write` 让平台库与租户库用例互相排队）；
- **持锁区间 = 用例调用阶段**：`platform_db_write` / `tenant_db_write` 两个夹具**只做声明**，
  真正的取锁 / 放锁由插件在 `pytest_runtest_call` 前后完成——夹具的生命周期天然横跨准备与清理，
  没法只包调用阶段；
- **保守出口**：`serial_db_write` 仍然整条用例持锁，且同时取两把（固定「平台 → 租户」顺序，
  避免死锁）。只在「准备阶段就动到别人数据」的极端场景局部退回使用，默认不用。

口径出处：《测试规范》「并行与隔离」节。
"""

from collections.abc import Iterator
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing.locks import file_lock

PLATFORM_WRITE_LOCK = "platform-db-write"
"""平台库写锁名（`shared_platform_engine` / `platform_db_url` 上的「先读后写」）。"""

TENANT_WRITE_LOCK = "tenant-db-write"
"""租户库写锁名（`shared_tenant_engine` / `shared_tenant_db_url` 上的「先读后写」）。"""

DECLARED_LOCKS_ATTR = "bms_declared_write_locks"
"""用例节点上记录「已声明写锁」的属性名（夹具写入、插件读取）。"""


def declare(request: pytest.FixtureRequest, *names: str) -> None:
    """把写锁名登记到当前用例节点（夹具调用；同用例可声明多次）。

    Args:
        request: 夹具请求对象（取当前用例节点）。
        *names: 写锁名。
    """
    item = cast("pytest.Item", cast("Any", request).node)
    locks = declared_locks(item)
    for name in names:
        if name not in locks:
            locks.append(name)


def declared_locks(item: pytest.Item) -> ConcurrentStableList[str]:
    """取当前用例节点上的写锁名清单（不存在则建空清单并挂回节点）。

    Args:
        item: 用例节点。

    Returns:
        ConcurrentStableList[str]: 已声明的写锁名（就地可变）。
    """
    located: object = getattr(item, DECLARED_LOCKS_ATTR, None)
    if isinstance(located, ConcurrentStableList):
        return cast("ConcurrentStableList[str]", located)
    created: ConcurrentStableList[str] = ConcurrentStableList()
    setattr(item, DECLARED_LOCKS_ATTR, created)
    return created


@pytest.fixture
def platform_db_write(request: pytest.FixtureRequest) -> None:
    """声明本用例写**平台库**（实际持锁区间为调用阶段，见模块文档）。

    Args:
        request: 夹具请求对象。
    """
    declare(request, PLATFORM_WRITE_LOCK)


@pytest.fixture
def tenant_db_write(request: pytest.FixtureRequest) -> None:
    """声明本用例写**租户库**（实际持锁区间为调用阶段，见模块文档）。

    Args:
        request: 夹具请求对象。
    """
    declare(request, TENANT_WRITE_LOCK)


@pytest.fixture
def serial_db_write() -> Iterator[None]:
    """保守出口：整条用例持锁，并同时取平台库 / 租户库两把写锁。

    仅用于「准备阶段就清理或改写别人数据」的极端场景；常规用例用 `platform_db_write` /
    `tenant_db_write`（只包调用阶段）。

    Yields:
        None: 持锁区间（准备 + 调用 + 清理）。
    """
    with file_lock(PLATFORM_WRITE_LOCK), file_lock(TENANT_WRITE_LOCK):
        yield


@pytest.fixture
def platform_db_write_whole() -> Iterator[None]:
    """整条用例持**平台库**写锁（准备 / 调用 / 清理全过程）。

    为什么需要：`rollback_session` 类套件在**夹具准备阶段**就 `BEGIN IMMEDIATE`，写事务
    从准备一直持有到清理——只包调用阶段等于让准备阶段的写事务裸奔。高并行（`-n auto`）下
    多个 worker 同时开写事务，`busy_timeout` 30s 等满即 `database is locked`（实测 10 errors）。

    Yields:
        None: 持锁区间。
    """
    with file_lock(PLATFORM_WRITE_LOCK):
        yield


@pytest.fixture
def tenant_db_write_whole() -> Iterator[None]:
    """整条用例持**租户库**写锁（口径同 `platform_db_write_whole`）。

    Yields:
        None: 持锁区间。
    """
    with file_lock(TENANT_WRITE_LOCK):
        yield
