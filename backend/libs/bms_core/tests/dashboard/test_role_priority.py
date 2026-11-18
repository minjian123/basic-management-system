"""角色层级命中规则：类型优先级 + 取首个非空候选（Kiwi 2528）。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.permission.role_priority import ROLE_TYPE_PRIORITY, pick_role_candidate, role_rank

pytestmark = pytest.mark.kiwi_id(2528)


def test_role_rank_known_and_unknown() -> None:
    """内置类型按固定序；未登记类型排最后。"""
    assert [role_rank(item) for item in ROLE_TYPE_PRIORITY] == list(range(len(ROLE_TYPE_PRIORITY)))
    assert role_rank("platform_admin") == 0
    assert role_rank("custom") == len(ROLE_TYPE_PRIORITY) - 1
    assert role_rank("unknown_type") == len(ROLE_TYPE_PRIORITY)


def test_pick_prefers_type_then_role_id() -> None:
    """同配置下按类型优先级取；同类型按角色主键升序。"""
    candidates: ConcurrentStableList[tuple[str, int, str | None]] = ConcurrentStableList(
        (
            ("custom", 9, "custom-9"),
            ("system", 7, "system-7"),
            ("platform_admin", 3, "admin-3"),
        )
    )
    role_id, payload = pick_role_candidate(candidates)
    assert (role_id, payload) == (3, "admin-3")

    same_type: ConcurrentStableList[tuple[str, int, str | None]] = ConcurrentStableList(
        (("custom", 9, "custom-9"), ("custom", 5, "custom-5"))
    )
    assert pick_role_candidate(same_type) == (5, "custom-5")


def test_pick_skips_none_and_empty() -> None:
    """`None` 与 `is_empty` 判定为空的候选一律跳过，继续下一个。"""
    candidates: ConcurrentStableList[tuple[str, int, str | None]] = ConcurrentStableList(
        (("platform_admin", 1, None), ("system", 2, ""), ("custom", 3, "ok"))
    )
    assert pick_role_candidate(candidates, is_empty=lambda value: value == "") == (3, "ok")


def test_pick_returns_none_when_all_empty() -> None:
    """全部候选为空 → `(None, None)`。"""
    candidates: ConcurrentStableList[tuple[str, int, str | None]] = ConcurrentStableList(
        (("system", 1, None), ("custom", 2, None))
    )
    assert pick_role_candidate(candidates) == (None, None)
    assert pick_role_candidate(ConcurrentStableList[tuple[str, int, str | None]]()) == (None, None)
