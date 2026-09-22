"""用户偏好能力域：通用偏好读写契约、键规范与依赖注入提供者（真实持久化随通用能力阶段回补）。

- `PREF_*` 常量：键分隔符 / 单键长度上限 / 单键值字节上限 / 单用户键数上限（对齐《概要设计 · 用户喜好》）。
- `is_valid_pref_key` / `domain_of`：键规范 `{域}.{键}` 校验与域名提取。
- `BasePreferenceStore`：能力域中间层契约（`key = "preference"`）——异步 `get` / `set` / `reset`。
- `get_preference_store`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：偏好只作**展示与交互**状态（向导开关 / 列配置 / 通知偏好 / 工作台布局），不承载业务事实、不参与权限
计算与审计链；键规范 `{域}.{键}`（列表偏好为 `list.{form_key}`），单键上限统一；跨端同步与本地回退由消费方
决定。真实实现（`sys_user_preference` 落库 upsert + 缓存 + key 白名单 + 批量接口）随通用能力阶段回补。
"""

import re
from abc import ABC, abstractmethod
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "PREF_KEY_MAX_LENGTH",
    "PREF_KEY_SEPARATOR",
    "PREF_MAX_KEYS",
    "PREF_VALUE_MAX_BYTES",
    "BasePreferenceStore",
    "domain_of",
    "get_preference_store",
    "is_valid_pref_key",
]

PREF_KEY_SEPARATOR = "."
"""偏好键分隔符（规范 `{域}.{键}`）。"""

PREF_KEY_MAX_LENGTH = 128
"""单键长度上限（字符）。"""

PREF_VALUE_MAX_BYTES = 65536
"""单键值 JSON 字节上限（64KB，对齐概要 `pref.key_max_size` 默认）。"""

PREF_MAX_KEYS = 200
"""单用户偏好键数上限（对齐概要 `pref.max_keys` 默认）。"""

_PREF_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
"""键规范：首段域名以字母开头，点分至少两段，各段小写字母 / 数字 / 下划线（如 `list.user_form`）。"""


def is_valid_pref_key(key: str) -> bool:
    """校验偏好键是否符合 `{域}.{键}` 规范。

    Args:
        key: 偏好键。

    Returns:
        bool: 合法为 True。
    """
    if not key or len(key) > PREF_KEY_MAX_LENGTH:
        return False
    return bool(_PREF_KEY_RE.fullmatch(key))


def domain_of(key: str) -> str:
    """取偏好键域名（首段；供分域缓存 / 日志）。

    Args:
        key: 偏好键。

    Returns:
        str: 域名（首段）；无分隔符时返回原串。
    """
    return key.split(PREF_KEY_SEPARATOR, 1)[0]


class BasePreferenceStore(BasePluggable, ABC):
    """用户偏好存储契约：异步读取 / 写入 / 重置。"""

    key: str = "preference"
    plugin_key: str = "preference"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def get(self, key: str, *, default: object = None) -> object | None:
        """读取偏好值（未设置返回 `default`）。

        Args:
            key: 偏好键（`{域}.{键}`）。
            default: 未设置时的回退值。

        Returns:
            object | None: 偏好值；未设置为 `default`。
        """

    @abstractmethod
    async def set(self, key: str, value: object) -> None:
        """写入 / 覆盖偏好值（upsert；值须 JSON 可序列化）。

        Args:
            key: 偏好键（`{域}.{键}`）。
            value: 偏好值。
        """

    @abstractmethod
    async def reset(self, key: str) -> bool:
        """重置偏好（清除该键，恢复默认）。

        Args:
            key: 偏好键（`{域}.{键}`）。

        Returns:
            bool: 是否删除了既有键。
        """


def get_preference_store(request: Request) -> BasePreferenceStore:
    """取应用级用户偏好存储（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BasePreferenceStore: 应用装配的偏好存储实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BasePreferenceStore",
        resolve_plugin(
            "preference",
            settings.preference.provider,
            expected_version=BasePreferenceStore.contract_version,
        ),
    )
