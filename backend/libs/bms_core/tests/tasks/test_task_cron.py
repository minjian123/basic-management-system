"""cron 解析与下次触发时刻护栏：语法 / 值域 / 日周「或」语义 / UTC / 4 年上界。"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from bms_core.core.exceptions import TaskCronInvalidError
from bms_core.tasks.cron import CronSpec, is_valid_cron, next_fire, parse_cron

pytestmark = pytest.mark.kiwi_id(2371)


def test_parse_wildcard_expands_full_range() -> None:
    """全通配：各字段展开为完整值域，日 / 周均不视为受限。"""
    spec = parse_cron("* * * * *")
    assert len(spec.minutes) == 60
    assert len(spec.hours) == 24
    assert len(spec.days) == 31
    assert len(spec.months) == 12
    assert len(spec.weekdays) == 7
    assert spec.day_restricted is False
    assert spec.weekday_restricted is False
    assert spec.expression == "* * * * *"


def test_parse_step_from_star_and_from_number() -> None:
    """`*/n` 从下界起算；`n/m` 从 n 起到上界按步长取。"""
    assert sorted(parse_cron("*/15 * * * *").minutes) == [0, 15, 30, 45]
    assert sorted(parse_cron("5/10 * * * *").minutes) == [5, 15, 25, 35, 45, 55]


def test_parse_range_with_step() -> None:
    """`a-b/n` 在区间内按步长取。"""
    assert sorted(parse_cron("1-5/2 * * * *").minutes) == [1, 3, 5]


def test_parse_weekday_seven_normalizes_to_sunday() -> None:
    """周字段 `7` 归一为 `0`（周日）。"""
    assert sorted(parse_cron("0 0 * * 7").weekdays) == [0]
    assert sorted(parse_cron("0 0 * * 0-7").weekdays) == [0, 1, 2, 3, 4, 5, 6]


def test_parse_month_and_weekday_names() -> None:
    """月份 / 周英文缩写（大小写不敏感）替换为数值。"""
    assert sorted(parse_cron("0 0 * JAN-MAR *").months) == [1, 2, 3]
    assert sorted(parse_cron("0 0 * * mon-fri").weekdays) == [1, 2, 3, 4, 5]


def test_parse_weekday_name_inside_list() -> None:
    """逗号列表内的英文缩写也能替换。"""
    assert sorted(parse_cron("0 0 * * SUN,WED/2").weekdays) == [0, 3, 5]


@pytest.mark.parametrize(
    "expression",
    [
        "0 0 * *",
        "0 0 * * * *",
        "0 0 , * *",
        "*/0 * * * *",
        "*/x * * * *",
        "1-x * * * *",
        "60 * * * *",
        "0 0 0 * *",
        "5-1 * * * *",
        "0 0 * FOO *",
        "0 0 * * FOO",
        "0 24 * * *",
    ],
)
def test_parse_rejects_invalid_expressions(expression: str) -> None:
    """段数 / 空项 / 步长 / 非数字 / 越界 / 未登记缩写一律 `70002`。"""
    with pytest.raises(TaskCronInvalidError):
        parse_cron(expression)


def test_next_fire_is_strictly_after_and_minute_granular() -> None:
    """严格晚于入参：命中同一分钟也不返回同一时刻，且秒 / 微秒归零。"""
    spec = parse_cron("0 3 * * *")
    base = datetime(2026, 10, 31, 3, 0, 30, 123456, tzinfo=UTC)
    assert next_fire(spec, base) == datetime(2026, 11, 1, 3, 0, tzinfo=UTC)


def test_next_fire_same_day_when_still_ahead() -> None:
    """未到点则当日触发。"""
    spec = parse_cron("0 3 * * *")
    assert next_fire(spec, datetime(2026, 10, 31, 2, 30, tzinfo=UTC)) == datetime(2026, 10, 31, 3, 0, tzinfo=UTC)


def test_next_fire_minute_stepping() -> None:
    """分钟未命中时逐分钟推进到下个命中分钟。"""
    spec = parse_cron("*/15 * * * *")
    assert next_fire(spec, datetime(2026, 10, 31, 10, 7, tzinfo=UTC)) == datetime(2026, 10, 31, 10, 15, tzinfo=UTC)


def test_next_fire_hour_stepping() -> None:
    """小时未命中时推进到下一个命中小时（跨日归零分钟）。"""
    spec = parse_cron("0 9-17 * * *")
    assert next_fire(spec, datetime(2026, 10, 31, 18, 0, tzinfo=UTC)) == datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def test_next_fire_day_restricted_only() -> None:
    """仅日受限：跳到下一个命中日。"""
    spec = parse_cron("0 0 15 * *")
    assert next_fire(spec, datetime(2026, 10, 31, 12, 0, tzinfo=UTC)) == datetime(2026, 11, 15, 0, 0, tzinfo=UTC)


def test_next_fire_month_jump_and_year_rollover() -> None:
    """月未命中时跳到下月 1 日；跨年（12 月）正确进位。"""
    spec = parse_cron("0 0 1 1 *")
    assert next_fire(spec, datetime(2026, 10, 15, 0, 0, tzinfo=UTC)) == datetime(2027, 1, 1, 0, 0, tzinfo=UTC)


def test_next_fire_weekday_restricted_only() -> None:
    """仅周受限：命中周一零点，且落在一周之内。"""
    spec = parse_cron("0 0 * * MON")
    base = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    result = next_fire(spec, base)
    assert result.weekday() == 0
    assert (result.hour, result.minute) == (0, 0)
    assert 1 <= (result - base).days <= 7


def test_next_fire_day_or_weekday_when_both_restricted() -> None:
    """日与周同时受限取「或」：先到的那个命中即可（这里是 11 月 1 日）。"""
    spec = parse_cron("0 0 1 * MON")
    assert next_fire(spec, datetime(2026, 10, 31, 12, 0, tzinfo=UTC)) == datetime(2026, 11, 1, 0, 0, tzinfo=UTC)


def test_next_fire_never_triggers_raises() -> None:
    """2 月 30 日永不触发：4 年上界内无命中即 `70002`。"""
    spec = parse_cron("0 0 30 2 *")
    with pytest.raises(TaskCronInvalidError):
        next_fire(spec, datetime(2026, 10, 31, tzinfo=UTC))


def test_next_fire_treats_naive_as_utc() -> None:
    """naive 入参视作 UTC，返回带时区时刻。"""
    spec = parse_cron("0 3 * * *")
    result = next_fire(spec, datetime(2026, 10, 31, 2, 30))
    assert result.tzinfo is not None
    assert result == datetime(2026, 10, 31, 3, 0, tzinfo=UTC)


def test_next_fire_converts_non_utc_input() -> None:
    """带偏移入参先换算到 UTC 再计算（东八区 10:30 = UTC 02:30）。"""
    spec = parse_cron("0 3 * * *")
    base = datetime(2026, 10, 31, 10, 30, tzinfo=timezone(timedelta(hours=8)))
    assert next_fire(spec, base) == datetime(2026, 10, 31, 3, 0, tzinfo=UTC)


def test_is_valid_cron() -> None:
    """接口校验入口：合法 True；语法非法与永不触发均 False。"""
    assert is_valid_cron("* * * * *") is True
    assert is_valid_cron("bad cron") is False
    assert is_valid_cron("0 0 30 2 *") is False


def test_cron_spec_is_frozen_value_object() -> None:
    """解析结果是不可变值对象（同参等值、可哈希比较）。"""
    first = parse_cron("0 3 * * *")
    second = parse_cron("0 3 * * *")
    assert isinstance(first, CronSpec)
    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.expression = "changed"  # pyright: ignore[reportAttributeAccessIssue] - 故意验证 frozen
