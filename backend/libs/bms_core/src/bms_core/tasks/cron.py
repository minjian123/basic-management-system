"""cron 表达式解析与下次触发时刻计算（标准 5 段、分钟粒度、UTC）。

- 段位：`分 时 日 月 周`；值域 分 `0-59`、时 `0-23`、日 `1-31`、月 `1-12`、周 `0-6`（`7` 归一为周日）；
- 语法：`*`、`n`、`a-b`、`*/n`、`a-b/n`、逗号列表；月份支持 `JAN`~`DEC`、周支持 `SUN`~`SAT`；
- 语义：`日` 与 `周` **同时受限时取「或」**（标准 cron 口径，不是「与」）；
- 时区：一律按 **UTC** 解释（不随服务器本地时区漂移；按租户时区调度见详细设计开放项）；
- 计算：`next_fire` 严格晚于入参（先截断到分钟再 `+1 分钟`起找），上界 **4 年**，
  超出即判「永不触发」并抛 `TaskCronInvalidError`（`70002`）——`0 0 30 2 *` 这类表达式在建任务时暴露，
  不留到调度期空转。

本模块为**纯函数层**（无 IO、无时钟依赖）：同 `(spec, after)` 结果稳定，可直接单测到边界。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenSet, ConcurrentStableSet
from bms_core.core.exceptions import TaskCronInvalidError
from bms_core.core.roots import BaseValueObject

__all__ = ["CronSpec", "is_valid_cron", "next_fire", "parse_cron"]

FIELD_COUNT = 5
"""段数（分 时 日 月 周）；`@daily` 类别名不支持，避免两套语法并存。"""

_MAX_SEARCH_DAYS = 1462
"""向上搜索上界（天）：4 年余量，覆盖 2 月 29 日跨闰年。"""

_MONTH_NAMES: ConcurrentStableFrozenDict[str, int] = ConcurrentStableFrozenDict(
    {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AUG": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }
)
"""月份英文缩写（大小写不敏感）。"""

_WEEKDAY_NAMES: ConcurrentStableFrozenDict[str, int] = ConcurrentStableFrozenDict(
    {"SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6}
)
"""周英文缩写（大小写不敏感；`SUN` = 0）。"""


@dataclass(frozen=True)
class CronSpec(BaseValueObject):
    """cron 语法树（解析结果，不可变）。"""

    expression: str
    """原始表达式（回显与排障用）。"""

    minutes: ConcurrentStableFrozenSet[int]
    """分钟集合（`0-59`）。"""

    hours: ConcurrentStableFrozenSet[int]
    """小时集合（`0-23`）。"""

    days: ConcurrentStableFrozenSet[int]
    """日集合（`1-31`）。"""

    months: ConcurrentStableFrozenSet[int]
    """月集合（`1-12`）。"""

    weekdays: ConcurrentStableFrozenSet[int]
    """周集合（`0-6`，`0` = 周日）。"""

    day_restricted: bool = False
    """日字段是否显式受限（非 `*`）；与 `weekday_restricted` 共同决定「或」语义。"""

    weekday_restricted: bool = False
    """周字段是否显式受限（非 `*`）。"""


def _range_of(index: int) -> tuple[int, int]:
    """取字段值域下上界。

    Args:
        index: 字段序位（0 分 / 1 时 / 2 日 / 3 月 / 4 周）。

    Returns:
        tuple[int, int]: (下界, 上界)；周上界取 `7` 以接受「7 = 周日」写法，解析后归一为 `0`。
    """
    if index == 0:
        return (0, 59)
    if index == 1:
        return (0, 23)
    if index == 2:
        return (1, 31)
    if index == 3:
        return (1, 12)
    return (0, 7)


def _replace_names(field: str, names: ConcurrentStableFrozenDict[str, int], label: str) -> str:
    """把月份 / 周英文缩写替换为数字（其余字符原样保留）。

    Args:
        field: 原始字段串。
        names: 缩写 → 数值映射。
        label: 字段中文名（报错用）。

    Returns:
        str: 替换后的字段串。

    Raises:
        TaskCronInvalidError: 出现未登记的英文缩写（`70002`）。
    """
    if field.isdigit() or not any(ch.isalpha() for ch in field):
        return field
    tokens: ConcurrentStableSet[str] = ConcurrentStableSet()
    for chunk in field.upper().replace("-", ",").replace("/", ",").split(","):
        if chunk and any(ch.isalpha() for ch in chunk):
            tokens.add(chunk)
    replaced = field
    for token in tokens:
        if token not in names:
            raise TaskCronInvalidError(f"cron {label}字段含未登记缩写：{token}")
        replaced = replaced.upper().replace(token, str(names[token]))
    return replaced


def _parse_field(field: str, index: int) -> ConcurrentStableFrozenSet[int]:
    """解析单个字段为取值集合。

    Args:
        field: 字段串（已做名称替换）。
        index: 字段序位（0 分 / 1 时 / 2 日 / 3 月 / 4 周）。

    Returns:
        ConcurrentStableFrozenSet[int]: 取值集合（周字段的 `7` 已归一为 `0`）。

    Raises:
        TaskCronInvalidError: 语法、步长或越界非法（`70002`）。
    """
    low, high = _range_of(index)
    values: ConcurrentStableSet[int] = ConcurrentStableSet()
    for part in field.split(","):
        if not part:
            raise TaskCronInvalidError(f"cron 第 {index + 1} 段存在空项")
        step = 1
        span = part
        if "/" in part:
            span, step_text = part.split("/", 1)
            if not step_text.isdigit() or int(step_text) <= 0:
                raise TaskCronInvalidError(f"cron 第 {index + 1} 段步长非法：{part}")
            step = int(step_text)
            if span in {"", "*"}:
                span = f"{low}-{high}"
        if span == "*":
            start, end = low, high
        elif "-" in span:
            start_text, end_text = span.split("-", 1)
            start, end = _to_int(start_text, index), _to_int(end_text, index)
        else:
            start = _to_int(span, index)
            end = high if step > 1 else start
        if start < low or end > high or start > end:
            raise TaskCronInvalidError(f"cron 第 {index + 1} 段越界：{part}（允许 {low}-{high}）")
        current = start
        while current <= end:
            values.add(current)
            current += step
    if index == 4 and 7 in values:
        values.discard(7)
        values.add(0)
    return ConcurrentStableFrozenSet(values)


def _to_int(text: str, index: int) -> int:
    """字段串片段转整数。

    Args:
        text: 数字片段。
        index: 字段序位（报错用）。

    Returns:
        int: 数值。

    Raises:
        TaskCronInvalidError: 非纯数字（`70002`）。
    """
    if not text.isdigit():
        raise TaskCronInvalidError(f"cron 第 {index + 1} 段非数字：{text}")
    return int(text)


def parse_cron(expression: str) -> CronSpec:
    """解析 5 段 cron 表达式。

    Args:
        expression: cron 表达式（如 `0 3 * * *`）。

    Returns:
        CronSpec: 解析结果。

    Raises:
        TaskCronInvalidError: 段数、语法、值域或名称非法（`70002`）。
    """
    text = expression.strip()
    fields = text.split()
    if len(fields) != FIELD_COUNT:
        raise TaskCronInvalidError(f"cron 须为 5 段（分 时 日 月 周），实际 {len(fields)} 段：{expression}")
    month_field = _replace_names(fields[3], _MONTH_NAMES, "月")
    weekday_field = _replace_names(fields[4], _WEEKDAY_NAMES, "周")
    return CronSpec(
        expression=text,
        minutes=_parse_field(fields[0], 0),
        hours=_parse_field(fields[1], 1),
        days=_parse_field(fields[2], 2),
        months=_parse_field(month_field, 3),
        weekdays=_parse_field(weekday_field, 4),
        day_restricted=fields[2] != "*",
        weekday_restricted=fields[4] != "*",
    )


def is_valid_cron(expression: str) -> bool:
    """表达式是否合法（供接口校验，不抛错）。

    Args:
        expression: cron 表达式。

    Returns:
        bool: 合法 True；解析失败 False。
    """
    try:
        spec = parse_cron(expression)
    except TaskCronInvalidError:
        return False
    try:
        next_fire(spec, datetime.now(UTC))
    except TaskCronInvalidError:
        return False
    return True


def _cron_weekday(moment: datetime) -> int:
    """取 cron 口径的周几（周日 = 0）。

    Args:
        moment: 时刻。

    Returns:
        int: 周几（0~6，周日为 0）。
    """
    return (moment.weekday() + 1) % 7


def _day_matches(spec: CronSpec, moment: datetime) -> bool:
    """日字段是否命中（日 / 周同时受限时取「或」）。

    Args:
        spec: 解析结果。
        moment: 待判定时刻。

    Returns:
        bool: 命中 True。
    """
    day_ok = moment.day in spec.days
    weekday_ok = _cron_weekday(moment) in spec.weekdays
    if spec.day_restricted and spec.weekday_restricted:
        return day_ok or weekday_ok
    if spec.day_restricted:
        return day_ok
    if spec.weekday_restricted:
        return weekday_ok
    return True


def _first_of_next_month(moment: datetime) -> datetime:
    """取下月 1 日 00:00（月份未命中时的跳进）。

    Args:
        moment: 当前时刻。

    Returns:
        datetime: 下月首日零点。
    """
    if moment.month == 12:
        return moment.replace(year=moment.year + 1, month=1, day=1, hour=0, minute=0)
    return moment.replace(month=moment.month + 1, day=1, hour=0, minute=0)


def next_fire(spec: CronSpec, after: datetime) -> datetime:
    """计算严格晚于 `after` 的首个到期时刻（UTC、分钟粒度）。

    Args:
        spec: 解析结果。
        after: 基准时刻（naive 视作 UTC）。

    Returns:
        datetime: 下次到期时刻（带 UTC 时区）。

    Raises:
        TaskCronInvalidError: 4 年内无命中（表达式永不触发，`70002`）。
    """
    base = after.replace(tzinfo=UTC) if after.tzinfo is None else after.astimezone(UTC)
    candidate = base.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = candidate + timedelta(days=_MAX_SEARCH_DAYS)
    while candidate <= limit:
        if candidate.month not in spec.months:
            candidate = _first_of_next_month(candidate)
            continue
        if not _day_matches(spec, candidate):
            candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if candidate.hour not in spec.hours:
            candidate = (candidate + timedelta(hours=1)).replace(minute=0)
            continue
        if candidate.minute not in spec.minutes:
            candidate = candidate + timedelta(minutes=1)
            continue
        return candidate
    raise TaskCronInvalidError(f"cron 表达式 {spec.expression} 在 4 年内无触发时刻")
