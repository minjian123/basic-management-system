"""用户偏好 SQL 实现（`sql`，平台服务数据权威侧）：当前用户读写 `sys_user_preference`。

- 用户维度取 `current_user_id` 上下文；无上下文（后台任务）直接回落默认值 / 拒绝写入。
- 读路径解析失败回落 `default` 并告警；写路径按 `preference/rules.py` 校验键 / 大小 / 数量。
- 事务边界归调用方（路由工作单元）；本实现自行开会话时按单次操作提交。
"""

from __future__ import annotations

import json

from bms_core.core.context import get_current_user_id
from bms_core.core.exceptions import PreferenceKeyLimitError
from bms_core.core.logging import get_logger
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import session_scope
from bms_core.preference.base import PREF_MAX_KEYS, BasePreferenceStore
from bms_core.preference.repository import PreferenceRepository
from bms_core.preference.rules import validate_pref_value

__all__ = ["SqlPreferenceStore"]

_LOGGER = get_logger("bms")


class SqlPreferenceStore(BasePreferenceStore):
    """真实用户偏好存储（平台服务租户库）。"""

    plugin_name: str = "sql"

    def __init__(self, *, engines: EngineRegistry) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表（按当前租户上下文取租户库）。
        """
        self._engines = engines

    async def get(self, key: str, *, default: object = None) -> object | None:
        """读取当前用户偏好值。

        Args:
            key: 偏好键。
            default: 未设置 / 解析失败时的回退值。

        Returns:
            object | None: 偏好值；未设置或解析失败为 `default`。
        """
        user_id = get_current_user_id()
        if user_id is None:
            return default
        async with session_scope(self._engines) as session:
            row = await PreferenceRepository(session).get_value(user_id, key)
        if row is None:
            return default
        try:
            return json.loads(row.pref_value)
        except json.JSONDecodeError:
            _LOGGER.warning("偏好值 JSON 解析失败（回落默认）", user_id=user_id, key=key)
            return default

    async def set(self, key: str, value: object) -> None:
        """写入 / 覆盖当前用户偏好值。

        Args:
            key: 偏好键。
            value: 偏好值。

        Raises:
            PreferenceKeyInvalidError: 键不在允许范围（`30021`）。
            PreferenceValueInvalidError: 值非法或超限（`30022`）。
            PreferenceDndInvalidError: 免打扰结构非法（`30024`）。
            PreferenceKeyLimitError: 键数超限（`30023`）。
        """
        user_id = _require_user()
        serialized = validate_pref_value(key, value)
        async with session_scope(self._engines) as session, session.begin():
            repository = PreferenceRepository(session)
            existing = await repository.get_value(user_id, key)
            if existing is None and await repository.count_for_user(user_id) >= PREF_MAX_KEYS:
                raise PreferenceKeyLimitError(f"偏好键数量超过上限 {PREF_MAX_KEYS}")
            await repository.upsert(user_id, key, serialized)

    async def reset(self, key: str) -> bool:
        """重置当前用户偏好（软删除该键）。

        Args:
            key: 偏好键。

        Returns:
            bool: 是否删除到既有键。
        """
        user_id = _require_user()
        async with session_scope(self._engines) as session, session.begin():
            return await PreferenceRepository(session).reset(user_id, key)


def _require_user() -> int:
    """取当前用户主键。

    Returns:
        int: 用户主键。

    Raises:
        RuntimeError: 无用户上下文（编码错误，写入接口必有登录态）。
    """
    user_id = get_current_user_id()
    if user_id is None:
        raise RuntimeError("偏好写入缺少当前用户上下文")
    return user_id
