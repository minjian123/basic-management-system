"""首页工作台布局：结构归一 / 严格校验 / 最小布局（框架无关纯函数，11_01）。

**为什么要独立成纯函数模块**：模板与个人布局共用同一份 `layout_config` 结构，保存期要严格拒非法配置、
读取期要容错不白屏；两处若各写一套必然漂移。本模块只依赖值对象与并发集合，服务层 / 种子 / 测试共用。

口径：

- 结构 `{"cards": [{code, x, y, w, h, visible}]}`，`code` 引用卡片注册表业务键；
- 网格 12 列，宽 2~12、高 2~6（《布局设计 · 首页工作台》§3）；`visible=false` 的卡片不占网格；
- **保存期严格**（`parse_layout`）：越界 / 重叠 / 重复码 / 超量一律产出问题项，由服务层转 `40304`；
- **读取期容错**（`normalize_layout`）：缺省补默认尺寸、越界夹取、重复保首个、非法项丢弃，绝不抛错；
- **空回退**（`minimal_layout`）：按 `sort` 行流式排布全部启用卡片，作为「三级均为空」的最小布局。
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.objects import BaseValueObject

__all__ = [
    "CARD_CODE_PATTERN",
    "CHART_TYPES",
    "DEFAULT_CARD_HEIGHT",
    "DEFAULT_CARD_WIDTH",
    "GRID_COLUMNS",
    "MAX_CARD_HEIGHT",
    "MAX_CARD_WIDTH",
    "MAX_LAYOUT_CARDS",
    "MIN_CARD_HEIGHT",
    "MIN_CARD_WIDTH",
    "CardPlacement",
    "CardSize",
    "DashboardLayout",
    "LayoutIssue",
    "filter_placements",
    "is_layout_empty",
    "is_valid_card_code",
    "layout_json",
    "load_layout_config",
    "minimal_layout",
    "normalize_layout",
    "parse_layout",
]

CARD_CODE_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
"""卡片标识形态：小写字母开头，仅小写字母 / 数字 / 下划线，2~64 位。"""

_CARD_CODE_RE = re.compile(CARD_CODE_PATTERN)

GRID_COLUMNS = 12
"""网格列数（PC 口径；断点收窄由前端处理，后端只存 12 列布局）。"""

MIN_CARD_WIDTH = 2
"""卡片最小宽（列）。"""

MAX_CARD_WIDTH = 12
"""卡片最大宽（列）。"""

MIN_CARD_HEIGHT = 2
"""卡片最小高（行）。"""

MAX_CARD_HEIGHT = 6
"""卡片最大高（行）。"""

DEFAULT_CARD_WIDTH = 4
"""卡片缺省宽（注册表未给默认尺寸时）。"""

DEFAULT_CARD_HEIGHT = 2
"""卡片缺省高（注册表未给默认尺寸时）。"""

MAX_LAYOUT_CARDS = 24
"""单份布局卡片数上限（防超长配置与偏好值 64KB 上限）。"""

CHART_TYPES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (
        "line",
        "area",
        "bar",
        "hbar",
        "stacked_bar",
        "pie",
        "doughnut",
        "scatter",
        "funnel",
        "radar",
        "gauge",
        "table",
        "map",
    )
)
"""数据集卡图表类型白名单（与前端 `CHART_KINDS` 同值，《组件设计 · 图表卡》）。"""


@dataclass(frozen=True)
class CardSize(BaseValueObject):
    """卡片尺寸（注册表默认尺寸快照；归一 / 最小布局的输入）。"""

    code: str
    """卡片标识。"""
    width: int = DEFAULT_CARD_WIDTH
    """默认宽（列）。"""
    height: int = DEFAULT_CARD_HEIGHT
    """默认高（行）。"""


@dataclass(frozen=True)
class CardPlacement(BaseValueObject):
    """布局中的一张卡片（网格位置与尺寸）。"""

    code: str
    """卡片标识（引用注册表 `code`）。"""
    x: int = 0
    """列偏移（0 ~ 12-w）。"""
    y: int = 0
    """行偏移（≥ 0）。"""
    w: int = DEFAULT_CARD_WIDTH
    """宽（列）。"""
    h: int = DEFAULT_CARD_HEIGHT
    """高（行）。"""
    visible: bool = True
    """是否可见（不可见卡片不占网格、不参与重叠判定）。"""


@dataclass(frozen=True)
class DashboardLayout(BaseValueObject):
    """工作台布局（模板与个人布局同形）。"""

    cards: ConcurrentStableFrozenList[CardPlacement] = field(
        default_factory=lambda: ConcurrentStableFrozenList[CardPlacement](())
    )
    """卡片放置清单（插入序）。"""


@dataclass(frozen=True)
class LayoutIssue(BaseValueObject):
    """布局问题项（保存期拒收原因 / 读取期剔除告警）。"""

    code: str
    """涉及的卡片标识（结构级问题为空串）。"""
    reason: str
    """原因：`structure` / `too-many-cards` / `code-invalid` / `duplicate-code` / `size-invalid` /
    `width-out-of-range` / `height-out-of-range` / `position-out-of-range` / `overlap` /
    `card_unknown` / `card_disabled`。"""


def is_valid_card_code(code: str) -> bool:
    """校验卡片标识形态。

    Args:
        code: 卡片标识。

    Returns:
        bool: 合法为 True。
    """
    return bool(_CARD_CODE_RE.fullmatch(code))


def _as_int(value: object) -> int | None:
    """把 JSON 值转整数（布尔一律视为非法；整数值浮点与数字字符串接受）。

    Args:
        value: 原始值。

    Returns:
        int | None: 整数；非法为 None。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def _as_bool(value: object, *, default: bool) -> bool:
    """把 JSON 值转布尔（缺省 / 非布尔取默认）。

    Args:
        value: 原始值。
        default: 缺省值。

    Returns:
        bool: 布尔值。
    """
    return value if isinstance(value, bool) else default


def _clamp(value: int, minimum: int, maximum: int) -> int:
    """夹取到区间。

    Args:
        value: 原值。
        minimum: 下界。
        maximum: 上界。

    Returns:
        int: 夹取结果。
    """
    return max(minimum, min(value, maximum))


def _clamp_size(size: CardSize) -> tuple[int, int]:
    """夹取卡片尺寸到合法区间。

    Args:
        size: 卡片默认尺寸。

    Returns:
        tuple[int, int]: （宽, 高）。
    """
    return _clamp(size.width, MIN_CARD_WIDTH, MAX_CARD_WIDTH), _clamp(size.height, MIN_CARD_HEIGHT, MAX_CARD_HEIGHT)


def _size_of(sizes: ConcurrentStableFrozenDict[str, CardSize], code: str) -> CardSize:
    """取卡片默认尺寸（未登记回退全局缺省）。

    Args:
        sizes: 卡片标识 → 默认尺寸。
        code: 卡片标识。

    Returns:
        CardSize: 默认尺寸。
    """
    size = sizes.get(code)
    return CardSize(code=code) if size is None else size


def _overlaps(a: CardPlacement, b: CardPlacement) -> bool:
    """判断两张可见卡片是否网格重叠。

    Args:
        a: 卡片 A。
        b: 卡片 B。

    Returns:
        bool: 重叠为 True。
    """
    if not a.visible or not b.visible:
        return False
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def _raw_items(raw: object) -> ConcurrentStableList[object] | None:
    """取 `cards` 原始清单（结构非法返回 None）。

    Args:
        raw: 原始布局值（任意 JSON）。

    Returns:
        ConcurrentStableList[object] | None: 卡片原始项；结构非法为 None。
    """
    if not isinstance(raw, Mapping):
        return None
    mapping = cast("Mapping[str, object]", raw)
    items = mapping.get("cards", [])
    if isinstance(items, str | bytes) or not isinstance(items, Sequence):
        return None
    return ConcurrentStableList(cast("Sequence[object]", items))


def _parse(
    raw: object,
    *,
    sizes: ConcurrentStableFrozenDict[str, CardSize],
    strict: bool,
) -> tuple[DashboardLayout, ConcurrentStableList[LayoutIssue]]:
    """解析布局（严格 / 容错两态共用实现）。

    Args:
        raw: 原始布局值（任意 JSON）。
        sizes: 卡片标识 → 默认尺寸。
        strict: 严格模式（越界与结构问题记为问题项、不夹取）；False 时夹取并丢弃非法项。

    Returns:
        tuple[DashboardLayout, ConcurrentStableList[LayoutIssue]]: （布局, 问题项）。
    """
    issues: ConcurrentStableList[LayoutIssue] = ConcurrentStableList()
    items = _raw_items(raw)
    if items is None:
        issues.add(LayoutIssue(code="", reason="structure"))
        return DashboardLayout(), issues
    if len(items) > MAX_LAYOUT_CARDS:
        issues.add(LayoutIssue(code="", reason="too-many-cards"))
        if strict:
            return DashboardLayout(), issues
    placements: ConcurrentStableList[CardPlacement] = ConcurrentStableList()
    seen: ConcurrentStableSet[str] = ConcurrentStableSet()
    cursor_x = 0
    cursor_y = 0
    row_height = 0
    for item in items:
        if not isinstance(item, Mapping):
            issues.add(LayoutIssue(code="", reason="structure"))
            continue
        record = cast("Mapping[str, object]", item)
        code = str(record.get("code") or "").strip()
        if not is_valid_card_code(code):
            issues.add(LayoutIssue(code=code, reason="code-invalid"))
            continue
        if code in seen:
            issues.add(LayoutIssue(code=code, reason="duplicate-code"))
            continue
        seen.add(code)
        default_w, default_h = _clamp_size(_size_of(sizes, code))
        raw_w = record.get("w")
        raw_h = record.get("h")
        parsed_w = default_w if raw_w is None else _as_int(raw_w)
        parsed_h = default_h if raw_h is None else _as_int(raw_h)
        if parsed_w is None or parsed_h is None:
            issues.add(LayoutIssue(code=code, reason="size-invalid"))
            if strict:
                continue
        width = default_w if parsed_w is None else parsed_w
        height = default_h if parsed_h is None else parsed_h
        if strict and not (MIN_CARD_WIDTH <= width <= MAX_CARD_WIDTH):
            issues.add(LayoutIssue(code=code, reason="width-out-of-range"))
        if strict and not (MIN_CARD_HEIGHT <= height <= MAX_CARD_HEIGHT):
            issues.add(LayoutIssue(code=code, reason="height-out-of-range"))
        width = _clamp(width, MIN_CARD_WIDTH, MAX_CARD_WIDTH)
        height = _clamp(height, MIN_CARD_HEIGHT, MAX_CARD_HEIGHT)
        raw_x = record.get("x")
        raw_y = record.get("y")
        x = None if raw_x is None else _as_int(raw_x)
        y = None if raw_y is None else _as_int(raw_y)
        if raw_x is not None and x is None:
            issues.add(LayoutIssue(code=code, reason="position-out-of-range"))
        if raw_y is not None and y is None:
            issues.add(LayoutIssue(code=code, reason="position-out-of-range"))
        if x is None:
            if cursor_x + width > GRID_COLUMNS:
                cursor_x = 0
                cursor_y += row_height
                row_height = 0
            x = cursor_x
        if y is None:
            y = cursor_y
        if strict and not (0 <= x <= GRID_COLUMNS - width):
            issues.add(LayoutIssue(code=code, reason="position-out-of-range"))
        if strict and y < 0:
            issues.add(LayoutIssue(code=code, reason="position-out-of-range"))
        x = _clamp(x, 0, GRID_COLUMNS - width)
        y = max(y, 0)
        placements.add(
            CardPlacement(
                code=code,
                x=x,
                y=y,
                w=width,
                h=height,
                visible=_as_bool(record.get("visible"), default=True),
            )
        )
        if x + width >= GRID_COLUMNS:
            cursor_x = 0
            cursor_y = max(cursor_y, y + height)
            row_height = 0
        else:
            cursor_x = x + width
            row_height = max(row_height, height)
    layout = DashboardLayout(cards=ConcurrentStableFrozenList(placements))
    if strict:
        cards = ConcurrentStableList(layout.cards)
        for left in range(len(cards)):
            for right in range(left + 1, len(cards)):
                if _overlaps(cards[left], cards[right]):
                    issues.add(LayoutIssue(code=cards[left].code, reason="overlap"))
    return layout, issues


def parse_layout(
    raw: object,
    *,
    sizes: ConcurrentStableFrozenDict[str, CardSize],
) -> tuple[DashboardLayout, ConcurrentStableList[LayoutIssue]]:
    """严格解析布局（保存期）：越界 / 重叠 / 重复 / 超量记为问题项，服务层据此拒收。

    Args:
        raw: 原始布局值（请求体或模板配置）。
        sizes: 卡片标识 → 默认尺寸。

    Returns:
        tuple[DashboardLayout, ConcurrentStableList[LayoutIssue]]: （布局, 问题项）。
    """
    return _parse(raw, sizes=sizes, strict=True)


def normalize_layout(raw: object, *, sizes: ConcurrentStableFrozenDict[str, CardSize]) -> DashboardLayout:
    """容错归一布局（读取期）：夹取、去重、丢弃非法项，绝不抛错。

    Args:
        raw: 原始布局值（个人偏好或模板 `layout_config` 解析结果）。
        sizes: 卡片标识 → 默认尺寸。

    Returns:
        DashboardLayout: 归一后的布局（可能为空）。
    """
    layout, _issues = _parse(raw, sizes=sizes, strict=False)
    return layout


def minimal_layout(sizes: ConcurrentStableFrozenList[CardSize]) -> DashboardLayout:
    """空回退最小布局：按给定顺序（通常为 `sort` 升序）行流式排布。

    Args:
        sizes: 启用卡片的默认尺寸（顺序即排布顺序）。

    Returns:
        DashboardLayout: 行流式布局（每行 ≤ 12 列）。
    """
    placements: ConcurrentStableList[CardPlacement] = ConcurrentStableList()
    cursor_x = 0
    cursor_y = 0
    row_height = 0
    for size in sizes:
        width, height = _clamp_size(size)
        if cursor_x + width > GRID_COLUMNS:
            cursor_x = 0
            cursor_y += row_height
            row_height = 0
        placements.add(CardPlacement(code=size.code, x=cursor_x, y=cursor_y, w=width, h=height, visible=True))
        cursor_x += width
        row_height = max(row_height, height)
    return DashboardLayout(cards=ConcurrentStableFrozenList(placements))


def is_layout_empty(layout: DashboardLayout) -> bool:
    """布局是否为空（无可见卡片即视为空，继续回退下一级）。

    Args:
        layout: 布局。

    Returns:
        bool: 空为 True。
    """
    return not any(placement.visible for placement in layout.cards)


def filter_placements(
    layout: DashboardLayout,
    *,
    enabled: ConcurrentStableFrozenDict[str, bool],
) -> tuple[DashboardLayout, ConcurrentStableList[LayoutIssue]]:
    """按卡片注册表状态过滤布局（解析期：剔除未注册与已停用卡片，不报错）。

    Args:
        layout: 归一后的布局。
        enabled: 卡片标识 → 是否启用（仅含已注册卡片）。

    Returns:
        tuple[DashboardLayout, ConcurrentStableList[LayoutIssue]]: （过滤后布局, 剔除告警）。
    """
    issues: ConcurrentStableList[LayoutIssue] = ConcurrentStableList()
    kept: ConcurrentStableList[CardPlacement] = ConcurrentStableList()
    for placement in layout.cards:
        if placement.code not in enabled:
            issues.add(LayoutIssue(code=placement.code, reason="card_unknown"))
            continue
        if not enabled.get(placement.code):
            issues.add(LayoutIssue(code=placement.code, reason="card_disabled"))
            continue
        kept.add(placement)
    return DashboardLayout(cards=ConcurrentStableFrozenList(kept)), issues


def layout_json(layout: DashboardLayout) -> str:
    """布局转 JSON 文本（落库 `layout_config` / 偏好值统一形态）。

    **为什么要转文本**：基座并发集合类不参与 `json.dumps`（非内置容器），落库与偏好写入一律先转
    JSON 字符串，读侧经 `load_layout_config` + `normalize_layout` 还原。

    Args:
        layout: 布局。

    Returns:
        str: `{"cards": [{code, x, y, w, h, visible}]}` 的 JSON 文本。
    """
    payload = {
        "cards": [
            {"code": placement.code, "x": placement.x, "y": placement.y, "w": placement.w, "h": placement.h,
             "visible": placement.visible}
            for placement in layout.cards
        ]
    }
    return json.dumps(payload, ensure_ascii=False)


def load_layout_config(text: str) -> object:
    """解析库内布局 JSON 文本（解析失败返回空布局，绝不抛错）。

    Args:
        text: `layout_config` 列的值。

    Returns:
        object: 解析结果；非法 JSON 返回 `{}`（由 `normalize_layout` 归一为空布局）。
    """
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {}
