"""仓储层用例共用夹具：帮助锚点 / 帮助覆盖探测数据的串行与清场。

为什么需要：`sys_business` / `sys_action` / `sys_menu` / `sys_form` / `sys_button` / `sys_field`
上的 `probe` 行被多个仓储用例文件共用，写入已改为立即落库；并行时 A 文件的清场会删掉
B 文件刚造的行（表现为「索引少一条 / 多一条」）。本目录用例统一在同一把文件锁内串行，
并在用例前后按 `probe` 特征清掉探测行——这些行只由测试造，不触碰真实登记数据。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.db.gate import GATE_CRITICAL_WAIT
from bms_core.testing.locks import file_lock
from bms_core.testing.transaction import write_session

_PROBE_FORM = (
    "form_id IN ("
    "SELECT id FROM sys_form WHERE "
    "business_id IN (SELECT id FROM sys_business WHERE code LIKE 'probe%') "
    "OR component LIKE 'probe%' OR help_key LIKE '%probe%' "
    "OR help_key IN ('platform:platform:::', 'platform:deleted:::', 'platform:one:::', 'platform:dup:::')"
    ")"
)
"""探测表单的行条件（按钮 / 字段 / 表单-菜单关联共用）。"""

_PURGE_STATEMENTS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (
        "DELETE FROM sys_menu_form WHERE form_id IN (SELECT id FROM sys_form WHERE "
        "business_id IN (SELECT id FROM sys_business WHERE code LIKE 'probe%') "
        "OR component LIKE 'probe%' OR help_key LIKE '%probe%') "
        "OR menu_id IN (SELECT id FROM sys_menu WHERE path LIKE '/probe/%')",
        f"DELETE FROM sys_button WHERE help_key LIKE '%probe%' OR {_PROBE_FORM}",
        f"DELETE FROM sys_field WHERE field_key LIKE 'probe%' OR {_PROBE_FORM}",
        "DELETE FROM sys_permission WHERE business_id IN (SELECT id FROM sys_business WHERE code LIKE 'probe%') "
        "OR action_id IN (SELECT id FROM sys_action WHERE code LIKE 'probe%')",
        "DELETE FROM sys_form WHERE business_id IN (SELECT id FROM sys_business WHERE code LIKE 'probe%') "
        "OR component LIKE 'probe%' OR help_key LIKE '%probe%' "
        "OR help_key IN ('platform:platform:::', 'platform:deleted:::', 'platform:one:::', 'platform:dup:::')",
        "DELETE FROM sys_menu WHERE path LIKE '/probe/%'",
        "DELETE FROM sys_action WHERE code LIKE 'probe%'",
        "DELETE FROM sys_business WHERE code LIKE 'probe%'",
    )
)
"""清场语句（子表先删；原生 SQL 显式带 WHERE，护栏要求）。"""


@pytest.fixture(autouse=True)
def _serial_probe_metadata() -> Iterator[None]:
    """探测元数据整份目录串行：清场与用例必须原子。

    Yields:
        None: 用例运行期。
    """
    with file_lock("repository-probe-metadata", timeout=180.0):
        yield


@pytest.fixture(autouse=True)
async def _clean_probe_metadata(
    _serial_probe_metadata: None, shared_platform_engine: AsyncEngine
) -> AsyncIterator[None]:
    """用例前后清掉本目录造的 `probe` 元数据行。

    Args:
        _serial_probe_metadata: 保证清场与用例在同一个串行区间。
        shared_platform_engine: 共享平台库引擎。

    Yields:
        None: 用例运行期。
    """
    await _purge_probe(shared_platform_engine)
    yield
    await _purge_probe(shared_platform_engine)


async def _purge_probe(engine: AsyncEngine) -> None:
    """删除探测行（子表先删）。

    Args:
        engine: 共享平台库引擎。
    """
    async with write_session(engine, wait=GATE_CRITICAL_WAIT) as session:
        for statement in _PURGE_STATEMENTS:
            await session.execute(text(statement))
