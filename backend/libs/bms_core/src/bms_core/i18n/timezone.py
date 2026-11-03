"""用户时区能力（校验 / 缺省派生 / UTC 换算与格式化）。

口径（《数据库设计 · 数据规范》§4、《概要设计 · 国际化管理》§2.2）：

- 时间一律 **UTC 存储**（naive），接口契约不变；展示按用户偏好时区换算，前端用 `Intl`。
- 用户偏好 `sys_user.timezone` 必须是 **IANA 时区标识**（`Asia/Shanghai` / `UTC` …），
  以 `zoneinfo.available_timezones()` 为白名单判定——**不接受** `UTC+08:00` 之类固定偏移
  （无夏令时、无法反推 IANA 名，前后端口径会分叉）。
- 未设置时区时按「生效语言 → 时区」映射派生，缺映射回落部署期兜底时区。

本模块只放**纯函数**（无 IO、不依赖 Settings、不抛业务异常）：业务异常（`44009`）由 API 层在
校验失败时抛出，避免能力域与错误码体系互相依赖。
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

__all__ = [
    "DEFAULT_DATETIME_PATTERN",
    "format_datetime",
    "is_valid_timezone",
    "resolve_timezone",
    "to_local",
]

DEFAULT_DATETIME_PATTERN: Final[str] = "%Y-%m-%d %H:%M"
"""后端产物（导出 / PDF / 通知内容）的缺省时间格式（展示格式仍由前端 `Intl` 决定）。"""


@lru_cache(maxsize=1)
def _timezone_names() -> frozenset[str]:
    """取 IANA 时区名全集（进程内缓存，避免每次重建集合）。

    Returns:
        frozenset[str]: 可用时区标识集合。
    """
    return frozenset(available_timezones())


def is_valid_timezone(name: str | None) -> bool:
    """判定时区标识是否合法（IANA 白名单）。

    Args:
        name: 时区标识（可空）。

    Returns:
        bool: 合法为 True（空值视为非法，由调用方决定「未设置」语义）。
    """
    if not name:
        return False
    return name.strip() in _timezone_names()


def resolve_timezone(locale: str, by_locale: Mapping[str, str], default: str) -> str:
    """按语言派生缺省时区（未设置偏好时使用）。

    Args:
        locale: 生效语言（如 `zh-CN`）。
        by_locale: 「语言 → 时区」映射（键大小写不敏感）。
        default: 兜底时区（映射未命中时用）。

    Returns:
        str: 时区标识。
    """
    target = (locale or "").strip().lower()
    for code, zone in by_locale.items():
        if (code or "").strip().lower() == target and is_valid_timezone(zone):
            return zone
    return default


def to_local(utc_naive: datetime, timezone_name: str) -> datetime:
    """把 UTC 时间换算到指定时区（aware）。

    Args:
        utc_naive: UTC 时间（可带 tzinfo，naive 视为 UTC）。
        timezone_name: 时区标识。

    Returns:
        datetime: 该时区的 aware 时间。

    Raises:
        ValueError: 时区标识非法。
    """
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"非法时区：{timezone_name}") from exc
    base = utc_naive.replace(tzinfo=UTC) if utc_naive.tzinfo is None else utc_naive.astimezone(UTC)
    return base.astimezone(zone)


def format_datetime(
    utc_naive: datetime,
    timezone_name: str,
    *,
    pattern: str = DEFAULT_DATETIME_PATTERN,
) -> str:
    """把 UTC 时间按指定时区格式化（供后端产物渲染，不参与接口契约）。

    Args:
        utc_naive: UTC 时间。
        timezone_name: 时区标识。
        pattern: `strftime` 格式串。

    Returns:
        str: 本地化时间文本。

    Raises:
        ValueError: 时区标识非法。
    """
    return to_local(utc_naive, timezone_name).strftime(pattern)
