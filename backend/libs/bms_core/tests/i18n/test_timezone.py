"""时区能力（Kiwi 2405）：IANA 校验 / 缺省派生 / UTC 换算 / 配置校验。

口径：时区只收 IANA 标识（`zoneinfo.available_timezones()` 白名单），不接受 `UTC+08:00` 固定偏移；
未设置时按「生效语言 → 时区」映射派生，映射缺失回落配置兜底值；配置里的非法时区**启动期即拒**。
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bms_core.core.config import I18nSettings
from bms_core.i18n.timezone import (
    DEFAULT_DATETIME_PATTERN,
    format_datetime,
    is_valid_timezone,
    resolve_timezone,
    to_local,
)

pytestmark = pytest.mark.kiwi_id(2405)

_MAP = {"zh-CN": "Asia/Shanghai", "en-US": "UTC"}


def test_is_valid_timezone_whitelist() -> None:
    """IANA 白名单命中 / 未命中 / 空值 / 固定偏移一律非法。"""
    assert is_valid_timezone("Asia/Shanghai")
    assert is_valid_timezone("UTC")
    assert not is_valid_timezone("Mars/Base")
    assert not is_valid_timezone("Asia/Beijing")
    assert not is_valid_timezone("")
    assert not is_valid_timezone(None)


def test_resolve_timezone_by_locale() -> None:
    """按生效语言取映射时区（键大小写不敏感）；未映射回落兜底值。"""
    assert resolve_timezone("zh-CN", _MAP, "UTC") == "Asia/Shanghai"
    assert resolve_timezone("en-us", _MAP, "Asia/Shanghai") == "UTC"
    assert resolve_timezone("ja-JP", _MAP, "Asia/Shanghai") == "Asia/Shanghai"
    assert resolve_timezone("", _MAP, "UTC") == "UTC"


def test_resolve_timezone_skips_invalid_mapping_value() -> None:
    """映射值非法时视为未命中，回落兜底值（不把脏值传给前端）。"""
    assert resolve_timezone("zh-CN", {"zh-CN": "Mars/Base"}, "UTC") == "UTC"


def test_to_local_converts_utc_naive() -> None:
    """UTC naive → 指定时区 aware（东八区 +8 小时）。"""
    local = to_local(datetime(2026, 1, 1, 0, 0), "Asia/Shanghai")
    assert local.utcoffset() is not None
    assert local.hour == 8
    assert local.date() == datetime(2026, 1, 1).date()


def test_to_local_accepts_aware_input() -> None:
    """已带 tzinfo 的输入先归一到 UTC 再换算。"""
    aware = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    assert to_local(aware, "UTC").hour == 8
    assert to_local(aware, "Asia/Shanghai").hour == 16


def test_to_local_rejects_invalid_timezone() -> None:
    """非法时区抛 ValueError（防御性：API 层已先校验）。"""
    with pytest.raises(ValueError, match="非法时区"):
        to_local(datetime(2026, 1, 1, 0, 0), "Mars/Base")


def test_format_datetime_default_and_custom_pattern() -> None:
    """按缺省 / 自定义格式串格式化本地时间。"""
    stamp = datetime(2026, 1, 1, 0, 0)
    assert format_datetime(stamp, "Asia/Shanghai") == "2026-01-01 08:00"
    assert format_datetime(stamp, "UTC", pattern="%Y/%m/%d") == "2026/01/01"
    assert DEFAULT_DATETIME_PATTERN == "%Y-%m-%d %H:%M"


def test_config_rejects_invalid_default_timezone() -> None:
    """配置兜底时区非法时启动期即失败。"""
    with pytest.raises(ValidationError):
        I18nSettings(default_timezone="Mars/Base")


def test_config_rejects_invalid_map_value() -> None:
    """语言 → 时区映射里出现非法时区时启动期即失败。"""
    with pytest.raises(ValidationError):
        I18nSettings(timezone_by_locale={"zh-CN": "Mars/Base"})


def test_config_accepts_valid_timezones() -> None:
    """合法配置通过校验并保留原值。"""
    settings = I18nSettings(default_timezone="UTC", timezone_by_locale={"ja-JP": "Asia/Tokyo"})
    assert settings.default_timezone == "UTC"
    assert settings.timezone_by_locale.get("ja-JP") == "Asia/Tokyo"
