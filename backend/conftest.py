"""后端工程根 pytest 夹具入口（04-6-2）：共享测试库的**准备集接线**。

为什么必须在工程根提供：`shared_platform_db_url` / `shared_tenant_db_url` 是会话级夹具，
其准备回调（`{数据源}_db_prepare`）只有从**根级**可见才稳定——否则回调取自「哪个套件先
跑到」，同一会话换一个 worker 先到就换一套种子，违背「并行与串行结果一致」。

各服务子工程自成 rootdir 时（`services/*/pyproject.toml`）本文件不参与，由该套件 conftest
的同名薄壳兜底（同一实现，见 `tests_support.shared_db`，不复制逻辑）。

准备集内容与口径见《[测试规范]「测试数据」节》与任务 04-6-2 详细设计 §4。
"""

from collections.abc import Callable, Iterator

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """覆盖率入口守卫（工程根最早执行）：`pytest --cov` 或换落点立即退出（code=2）。

    本仓**禁止手工采集覆盖率**：门禁只认 `[coverage].data_file`（engkit 采集）。
    走错入口不报错会让「假缺口」反复误导排障，故在跑用例前直接终止；查缺口的唯一出口是
    `scripts/tools/preflight/coverage_report.py`（`--module` 模块级 / `--changed` 改动行）。
    口径见 `bms_core.testing.coverage_guard` 与《AI开发规范》「覆盖率要求」节。

    Args:
        config: pytest 配置对象。
    """
    from bms_core.testing.coverage_guard import assert_entrypoint

    assert_entrypoint(config)


@pytest.fixture
def serial_db_write() -> Iterator[None]:
    """共享库**写路径**跨进程串行（单库叠加下「先读后写」必须排队）。

    为什么需要：SQLite 的延迟事务里「先 SELECT 再 INSERT/UPDATE」会把读锁升级为写锁，
    此时若另一进程正持写锁，升级一律立即 `database is locked`——`busy_timeout` 对**升级死锁**
    不生效（等待也无法推进）。共享库上所有「读-改-写」用例（回滚会话里的仓储 / 服务写入）
    统一经本夹具排队，避免靠「重跑就过」掩盖。

    集成口径：同一把锁名（`shared-db-write`）的用例跨 worker / 跨文件串行；只读用例不受影响。

    Yields:
        None: 持锁区间。
    """
    from tests_support.locks import file_lock

    with file_lock("shared-db-write"):
        yield


@pytest.fixture(scope="session")
def platform_db_prepare() -> Callable[[str], None]:
    """平台库准备集回调（种子租户 → 主键对齐 → 服务目录与产品档案）。

    Returns:
        Callable[[str], None]: 接受连接串的准备函数。
    """
    from tests_support.shared_db import prepare_platform

    return prepare_platform


@pytest.fixture(scope="session")
def tenant_db_prepare() -> Callable[[str], None]:
    """租户库准备集回调（租户侧建表集 → 系统参数种子）。

    Returns:
        Callable[[str], None]: 接受连接串的准备函数。
    """
    from tests_support.shared_db import prepare_tenant

    return prepare_tenant
