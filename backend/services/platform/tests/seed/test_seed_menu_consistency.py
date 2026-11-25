"""菜单元数据种子「派生化口径」用例（`06_08`）：主表默认文案 ≡ 附表默认语言文案。

覆盖：播种回报派生一致性校验行数、重复执行不新增；漂移判定用**纯函数**验证。

读写共享库一律走 `tests_support.shared_access` 的统一读写门（`shared_write`：操作级写门、
立即提交），不自建引擎、不走 `seed_menu(url)`——后者内部 `create_async_engine` 不取门，
会与走门的写者抢 SQLite 写锁（13_08 已记录）。表结构由初始化阶段建好，用例不建表、不跑 DDL。

漂移场景**不在共享库上造漂移行**（回滚式隔离已作废；造故障态会让并行 worker 的播种一并失败）：
校验实现已抽成纯函数 `_name_mismatch`，直接喂「一致 / 不一致」两组数据断言返回值。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.tenant.seed.menu import (
    _name_mismatch,  # pyright: ignore[reportPrivateUsage]
    _seed_menu_in_session,  # pyright: ignore[reportPrivateUsage]
)
from ops.seed_menu import ACTION_SEEDS, BUSINESS_SEEDS, FIELD_SEEDS, MENU_SEEDS
from tests_support.shared_access import shared_write

pytestmark = pytest.mark.kiwi_id(2242)

# `/sys/users` 与 `/sys/account-locks` 同挂业务码 `user`（表单 1:1 共享），`username` 字段键重复
# 使实际字段行数比 FIELD_SEEDS 少 1；其余三类种子与行数一一对应。
_EXPECTED = len(BUSINESS_SEEDS) + len(ACTION_SEEDS) + len(MENU_SEEDS) + len(FIELD_SEEDS) - 1


async def test_seed_menu_reports_derived_name_consistency(shared_platform_engine: AsyncEngine) -> None:
    """播种回报「主表默认文案 ≡ 附表默认语言文案」校验行数；重复执行不新增且校验行数不变。"""
    async with shared_write(shared_platform_engine) as session:
        _created, _skipped, checked = await _seed_menu_in_session(session)
        await session.commit()
    assert checked == _EXPECTED

    async with shared_write(shared_platform_engine) as session:
        again_created, again_skipped, again_checked = await _seed_menu_in_session(session)
        await session.commit()
    assert again_created == 0
    assert again_skipped > 0
    assert again_checked == _EXPECTED


def test_derived_name_mismatch_is_reported() -> None:
    """主表默认文案与附表默认语言不一致：给出可定位描述（表名 + 主键 + 两侧文案）。"""
    problem = _name_mismatch("sys_menu", 7, "用户管理", "被单独改写的名称")
    assert problem is not None
    assert "sys_menu#7" in problem
    assert "用户管理" in problem
    assert "被单独改写的名称" in problem


def test_derived_name_match_is_clean() -> None:
    """两边文案一致：不报问题（校验通过）。"""
    assert _name_mismatch("sys_menu", 7, "用户管理", "用户管理") is None
