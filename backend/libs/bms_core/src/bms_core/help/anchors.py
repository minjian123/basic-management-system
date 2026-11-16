"""帮助锚点（`help_key`）段式标识：格式、形状与归一（08_01）。

这里是 `help_key` 的**唯一校验实现**：元数据写接口与种子装载助手都经本模块，不得各写一份。

口径（2026-11-17 拍板，见任务 08_01 详细设计 §5.1）：

- 五段冒号式 `{product}:{module}:{form}:{field}:{action}`，本级段非空、右侧缺省段留空但保留分隔符；
- 每个非空段 `[a-z][a-z0-9_]*`、≤64 字符；整串 ≤255 字符；
- 空串 / 纯空白归一为 `None`（落库 `NULL` = 未登记）；
- 节点类型由**非空段位置**判定：菜单（模块级）1/2、表单 1/2/3、字段 1/2/3/4、
  按钮 1/2/3/5、动作码 1/5（首段须 `platform`）；
- 唯一性不在本模块判定（需数据库跨五表查询，见 `bms_core/repositories/help_anchor.py`）。
"""

from __future__ import annotations

import re
from enum import StrEnum

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import MenuHelpKeyInvalidError

__all__ = [
    "ANCHOR_TABLES",
    "HELP_KEY_MAX_LENGTH",
    "HELP_KEY_MAX_SEGMENT_LENGTH",
    "HELP_KEY_SEGMENT_COUNT",
    "HELP_KEY_SEGMENT_NAMES",
    "HelpAnchorKind",
    "help_key_segment",
    "help_key_segments",
    "normalize_help_key",
    "validate_help_key",
]

HELP_KEY_SEGMENT_COUNT = 5
"""段数（固定五段、四个分隔符）。"""

HELP_KEY_MAX_LENGTH = 255
"""整串最大长度（与列宽 `VARCHAR(255)` 一致）。"""

HELP_KEY_MAX_SEGMENT_LENGTH = 64
"""单段最大长度（与 `module_key` / `form_key` / `field_key` / 动作码的最大长度一致）。"""

PLATFORM_PRODUCT_KEY = "platform"
"""平台内建锚点的产品段取值（与 `deploy/registry/platform.toml` 的 `product_key` 一致）。"""

_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""非空段形态：小写字母开头，仅小写字母 / 数字 / 下划线。"""


class HelpAnchorKind(StrEnum):
    """锚点节点类型（由元数据表决定）。"""

    MENU = "menu"
    FORM = "form"
    FIELD = "field"
    BUTTON = "button"
    ACTION = "action"


ANCHOR_TABLES: ConcurrentStableDict[HelpAnchorKind, str] = ConcurrentStableDict(
    {
        HelpAnchorKind.MENU: "sys_menu",
        HelpAnchorKind.FORM: "sys_form",
        HelpAnchorKind.FIELD: "sys_field",
        HelpAnchorKind.BUTTON: "sys_button",
        HelpAnchorKind.ACTION: "sys_action",
    }
)
"""节点类型 → 逻辑表名（唯一性读助手与覆盖率台账共用）。"""

HELP_KEY_SEGMENT_NAMES: ConcurrentStableList[str] = ConcurrentStableList(
    ("product", "module", "form", "field", "action")
)
"""各段名称（下标即段位；错误信息按名称提示）。"""

_ANCHOR_SHAPES: ConcurrentStableDict[HelpAnchorKind, ConcurrentStableList[int]] = ConcurrentStableDict(
    {
        HelpAnchorKind.MENU: ConcurrentStableList((0, 1)),
        HelpAnchorKind.FORM: ConcurrentStableList((0, 1, 2)),
        HelpAnchorKind.FIELD: ConcurrentStableList((0, 1, 2, 3)),
        HelpAnchorKind.BUTTON: ConcurrentStableList((0, 1, 2, 4)),
        HelpAnchorKind.ACTION: ConcurrentStableList((0, 4)),
    }
)
"""各节点类型必须非空的段位（其余段必须为空）。"""


def normalize_help_key(raw: str | None) -> str | None:
    """归一 `help_key` 原始值（去首尾空白；空串 / 纯空白 → `None`）。

    Args:
        raw: 原始值（请求 / 声明 / 数据库读出值）。

    Returns:
        str | None: 归一后的值；未登记返回 `None`。
    """
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def help_key_segments(value: str) -> ConcurrentStableList[str]:
    """拆分 `help_key` 为五段（保留空段，下标即段位）。

    Args:
        value: 已归一的 `help_key`（非空）。

    Returns:
        ConcurrentStableList[str]: 五段值（空段为空串）。

    Raises:
        MenuHelpKeyInvalidError: 段数不是五段（40211）。
    """
    parts = value.split(":")
    if len(parts) != HELP_KEY_SEGMENT_COUNT:
        raise MenuHelpKeyInvalidError(f"help_key 段数须为 {HELP_KEY_SEGMENT_COUNT}：{value!r}（实际 {len(parts)} 段）")
    return ConcurrentStableList(parts)


def help_key_segment(value: str, index: int) -> str | None:
    """取指定段位的值（供解析侧按需读取）。

    Args:
        value: 已归一的 `help_key`（非空）。
        index: 段位下标（0 ~ 4）。

    Returns:
        str | None: 该段值；空段返回 `None`。

    Raises:
        MenuHelpKeyInvalidError: 段数不是五段或下标越界（40211）。
    """
    if index < 0 or index >= HELP_KEY_SEGMENT_COUNT:
        raise MenuHelpKeyInvalidError(f"help_key 段位越界：{index}（须 0 ~ {HELP_KEY_SEGMENT_COUNT - 1}）")
    part = help_key_segments(value)[index]
    return part or None


def validate_help_key(
    raw: str | None,
    *,
    kind: HelpAnchorKind,
    declaring_product: str | None = None,
) -> str | None:
    """校验并归一 `help_key`（写接口与装载声明共用）。

    Args:
        raw: 原始值；`None` / 空串 / 纯空白表示未登记。
        kind: 节点类型（决定非空段位置）。
        declaring_product: 声明方产品标识（装载声明时传入，校验首段一致）；`None` 不做产品归属校验。

    Returns:
        str | None: 归一后的 `help_key`；未登记返回 `None`。

    Raises:
        MenuHelpKeyInvalidError: 段数 / 字符集 / 长度 / 非空段位置 / 产品段非法（40211）。
    """
    value = normalize_help_key(raw)
    if value is None:
        return None
    if len(value) > HELP_KEY_MAX_LENGTH:
        raise MenuHelpKeyInvalidError(f"help_key 超长：{len(value)} 字符（上限 {HELP_KEY_MAX_LENGTH}）：{value!r}")
    parts = help_key_segments(value)
    for index, part in enumerate(parts):
        if not part:
            continue
        if len(part) > HELP_KEY_MAX_SEGMENT_LENGTH:
            raise MenuHelpKeyInvalidError(
                f"help_key 段 {HELP_KEY_SEGMENT_NAMES[index]} 超长：{len(part)} 字符"
                f"（上限 {HELP_KEY_MAX_SEGMENT_LENGTH}）：{part!r}"
            )
        if not _SEGMENT_RE.match(part):
            raise MenuHelpKeyInvalidError(
                f"help_key 段 {HELP_KEY_SEGMENT_NAMES[index]} 格式非法：{part!r}"
                "（须小写字母开头，仅小写字母 / 数字 / 下划线）"
            )
    product = parts[0]
    if not product:  # pragma: no cover - 首段在形状校验中已要求非空，此处为防御性断言
        raise MenuHelpKeyInvalidError(f"help_key 缺少产品段：{value!r}")
    if declaring_product is not None and product != declaring_product:
        raise MenuHelpKeyInvalidError(
            f"help_key 产品段与声明方不一致：{product!r} ≠ {declaring_product!r}（{value!r}）"
        )
    if kind is HelpAnchorKind.ACTION and product != PLATFORM_PRODUCT_KEY:
        raise MenuHelpKeyInvalidError(f"动作码锚点的产品段须为 {PLATFORM_PRODUCT_KEY!r}（全局动词兜底）：{value!r}")
    required = _ANCHOR_SHAPES[kind]
    for index in range(HELP_KEY_SEGMENT_COUNT):
        filled = bool(parts[index])
        if filled != (index in required):
            expected = "非空段位 " + "/".join(str(position + 1) for position in required)
            raise MenuHelpKeyInvalidError(f"help_key 形状非法（{kind.value}）：{value!r}（要求{expected}，其余段留空）")
    return value
