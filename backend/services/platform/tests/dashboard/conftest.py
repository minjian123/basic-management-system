"""工作台用例夹具：会话级共享平台默认模板（scope=platform 全租户唯一，只能有一份）。

**为什么放会话级**：`sys_dashboard_template` 的 `(scope, role_id, deleted_at)` 复合唯一使平台层级
**全库仅一份**；各用例若各建一份必然撞唯一键。这里在会话开始（每 worker 各一次）幂等确保：
一张探针内置卡 + 一份引用它的平台默认模板。用例只读它，不改不删（改删分支在服务级事务用例里覆盖）。
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from tests_support.dashboard import ensure_card, ensure_dashboard_tables, find_platform_template, seed_template

PLATFORM_PROBE_CARD = "zz_platform_probe"
"""会话级探针卡片标识（无命名空间：平台默认模板全库唯一，引用它的卡片也必须全库唯一）。"""


def _platform_layout() -> ConcurrentStableDict[str, object]:
    """平台默认模板布局（引用探针卡片）。

    Returns:
        ConcurrentStableDict[str, object]: 布局配置。
    """
    card: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    card.set("code", PLATFORM_PROBE_CARD)
    card.set("x", 0)
    card.set("y", 0)
    card.set("w", 4)
    card.set("h", 2)
    card.set("visible", True)
    cards: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    cards.add(card)
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    payload.set("cards", cards)
    return payload


@pytest.fixture(scope="session", autouse=True)
async def shared_platform_template(shared_tenant_db_url: str) -> None:
    """幂等确保「探针卡 + 平台默认模板」存在（跨 worker 并发时容忍唯一键冲突）。

    Args:
        shared_tenant_db_url: 共享租户库连接串（会话级）。
    """
    await ensure_dashboard_tables(shared_tenant_db_url)
    await ensure_card(
        shared_tenant_db_url,
        PLATFORM_PROBE_CARD,
        card_type="builtin",
        render_key="probe",
        name="平台探针卡",
        sort=999,
    )
    if await find_platform_template(shared_tenant_db_url) is not None:
        return
    try:
        await seed_template(
            shared_tenant_db_url, name="平台默认布局（用例）", layout=_platform_layout()
        )
    except IntegrityError:
        return
