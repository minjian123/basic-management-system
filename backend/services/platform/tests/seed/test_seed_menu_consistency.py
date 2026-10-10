"""菜单元数据种子「派生化口径」用例（`06_08`）：主表默认文案 ≡ 附表默认语言文案。

覆盖：播种回报派生一致性校验行数、重复执行幂等、主表默认文案被单独改写时重跑即失败
（暴露「同一文案两处编辑」的漂移，而不是静默留不一致数据）。
"""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_platform.models.menu import SysMenu
from ops.seed_menu import ACTION_SEEDS, BUSINESS_SEEDS, FIELD_SEEDS, MENU_SEEDS, seed_menu


@pytest.mark.kiwi_id(2242)
async def test_seed_menu_reports_derived_name_consistency(tmp_path: Path) -> None:
    """播种回报「主表默认文案 ≡ 附表默认语言文案」校验行数；重复执行幂等且校验行数不变。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'menu.db'}"
    # `/sys/users` 与 `/sys/account-locks` 同挂业务码 `user`（表单 1:1 共享），`username` 字段键重复
    # 使实际字段行数比 FIELD_SEEDS 少 1；其余三类种子与行数一一对应。
    expected = len(BUSINESS_SEEDS) + len(ACTION_SEEDS) + len(MENU_SEEDS) + len(FIELD_SEEDS) - 1

    created, _skipped, checked = await seed_menu(url)
    assert created > 0
    assert checked == expected

    again_created, again_skipped, again_checked = await seed_menu(url)
    assert again_created == 0
    assert again_skipped > 0
    assert again_checked == expected


@pytest.mark.kiwi_id(2242)
async def test_seed_menu_rejects_drifted_default_name(tmp_path: Path) -> None:
    """主表默认文案被单独改写（附表未同步）后重跑：直接失败并指出漂移行。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'menu.db'}"
    await seed_menu(url)

    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = (await session.execute(select(SysMenu).where(SysMenu.path == "/sys/users"))).scalars().first()
            assert row is not None
            row.name = "被单独改写的名称"
            await session.commit()
    finally:
        await engine.dispose()

    with pytest.raises(RuntimeError, match="主表默认文案与派生结果不一致"):
        await seed_menu(url)
