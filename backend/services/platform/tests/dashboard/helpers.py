"""工作台用例共用助手：准备集 / 造数入口 / 命名空间编码。

**建引擎能力全部下沉 `tests_support/dashboard.py`**：测试库隔离护栏只放行共享基座建引擎，
用例侧只调函数（单库叠加口径，见《测试规范》「测试数据」节）。

**隔离口径**：卡片 `code` 与角色 `code` 由 `ns.prefix` 派生；个人布局按测试主体精确清除。
"""

from __future__ import annotations

from typing import cast

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing.namespace import Namespace
from tests_support.dashboard import (
    assign_role,
    clear_dashboard_pref,
    delete_role,
    ensure_dashboard_tables,
    read_pref,
    role_id_by_code,
    seed_card,
    seed_role,
    seed_template,
    tenant_url,
)
from tests_support.permission_admin import SYSTEM_ADMIN_CODE, setup_min_tenant

__all__ = [
    "SYSTEM_ADMIN_CODE",
    "assign_role",
    "card_code",
    "clear_dashboard_pref",
    "delete_role",
    "ensure_dashboard_tables",
    "prepare",
    "read_pref",
    "role_id_by_code",
    "role_template_layout",
    "seed_card",
    "seed_role",
    "seed_template",
    "tenant_url",
]

DEFAULT_USER_ID = 1001
"""测试主体（`tests_support.auth.TEST_SUBJECT`）。"""


async def prepare() -> None:
    """真实权限校验所需租户库 + 内置系统管理员主体 + 工作台三表存在性。"""
    url = tenant_url()
    await setup_min_tenant(url)
    await ensure_dashboard_tables(url)


def card_code(ns: Namespace, suffix: str) -> str:
    """生成命名空间内的卡片标识（合法形态：小写字母开头、下划线分隔）。

    Args:
        ns: 用例命名空间。
        suffix: 后缀（小写字母 / 数字 / 下划线）。

    Returns:
        str: 卡片标识。
    """
    return f"{ns.prefix}_{suffix}"


def role_template_layout(code: str, *, x: int = 0) -> object:
    """构造引用单张卡片的布局配置（返回内置结构，便于直接作为请求体 / JSON 序列化）。

    Args:
        code: 卡片标识。
        x: 列偏移。

    Returns:
        object: 布局配置（`{"cards": [...]}`）。
    """
    return {"cards": [{"code": code, "x": x, "y": 0, "w": 4, "h": 2, "visible": True}]}


def positions(layout: object) -> ConcurrentStableList[tuple[str, int, int]]:
    """取布局卡片位置清单（`(code, x, y)`）。

    Args:
        layout: 布局载荷（响应 `data.layout`）。

    Returns:
        ConcurrentStableList[tuple[str, int, int]]: 卡片位置清单。
    """
    result: ConcurrentStableList[tuple[str, int, int]] = ConcurrentStableList()
    payload = cast("dict[str, list[dict[str, object]]]", layout)
    for item in payload["cards"]:
        result.add((str(item["code"]), int(cast("int", item["x"])), int(cast("int", item["y"]))))
    return result
