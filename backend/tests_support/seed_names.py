"""种子自然键 → 中文名（测试造数的唯一取名口径）。

为什么要有这一层：播种对**已存在**的业务码 / 动作码只跳过主表、仍然补写 i18n 附表，若测试先建行
时把主表 `name` 写成 `code` 或自造文案，播种的「主表默认文案 ≡ 附表默认语言文案」校验会直接失败
（CI 全量实测两条：`sys_business#…：主表 name='log' ≠ 附表 zh-CN='审计日志'`、
`sys_action#…：主表 name='管理' ≠ 附表 zh-CN='管理（含查询与维护）'`）。

种子表是文案的唯一来源，测试侧不写第二份字面量副本；自造码两边同值（回落 `code` 或调用方名称），
仍满足派生化口径。
"""

from __future__ import annotations

from bms_core.tenant.seed.menu import ACTION_SEEDS, BUSINESS_SEEDS


def seed_name(code: str, *, kind: str, fallback: str | None = None) -> str:
    """取种子里该编码的中文名。

    Args:
        code: 业务码 / 动作码。
        kind: 码类型（`business` / `action`）。
        fallback: 非种子码的返回值（缺省回落 `code`）。

    Returns:
        str: 主表默认文案。

    Raises:
        ValueError: `kind` 非 `business` / `action`。
    """
    if kind == "business":
        seeds = BUSINESS_SEEDS
    elif kind == "action":
        seeds = ACTION_SEEDS
    else:
        raise ValueError(f"未知码类型：{kind!r}（应为 business / action）")
    for item_code, zh, _en in seeds:
        if item_code == code:
            return zh
    return code if fallback is None else fallback
