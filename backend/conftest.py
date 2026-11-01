"""后端工程根 pytest 夹具入口（04-6-2）：共享测试库的**准备集接线**。

为什么必须在工程根提供：`shared_platform_db_url` / `shared_tenant_db_url` 是会话级夹具，
其准备回调（`{数据源}_db_prepare`）只有从**根级**可见才稳定——否则回调取自「哪个套件先
跑到」，同一会话换一个 worker 先到就换一套种子，违背「并行与串行结果一致」。

各服务子工程自成 rootdir 时（`services/*/pyproject.toml`）本文件不参与，由该套件 conftest
的同名薄壳兜底（同一实现，见 `tests_support.shared_db`，不复制逻辑）。

准备集内容与口径见《[测试规范]「测试数据」节》与任务 04-6-2 详细设计 §4。
"""

from collections.abc import Callable

import pytest


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
