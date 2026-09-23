"""服务目录本地权威读取器（06_02）：平台服务读**本服务平台服务库**的 `sys_module`。

- 平台服务是服务目录的单一权威，`sys_module` / `sys_module_i18n` 归其所有（链 `platform:platform`）；
- 共享基座库不再静态依赖服务包：本读取器由 `bms_platform/main.py::configure_service` 在装配期经
  `bms_core.catalog.loader.register_catalog_reader` 登记，供启动接库校验与 `catalog` 健康项消费。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.services.module_registry import ModuleRecord
from bms_platform.repositories.module_repository import ModuleRepository


async def read_catalog(session: AsyncSession) -> list[ModuleRecord]:
    """读本服务平台服务库的服务目录（未软删行）。

    Args:
        session: 平台服务库会话（由调用方按库键 `platform` 取）。

    Returns:
        list[ModuleRecord]: 服务目录清单（`id` 升序）。
    """
    rows = await ModuleRepository(session).list_catalog()
    return [ModuleRecord.from_row(row) for row in rows]
