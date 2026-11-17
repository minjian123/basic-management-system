"""用户偏好仓储（`sys_user_preference`）：按用户 / 键读写与计数。"""

from __future__ import annotations

import json

from sqlalchemy import func, select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.platform.user import SysUserPreference
from bms_core.repositories.base_db_repository import BaseDbRepository

__all__ = ["PreferenceRepository"]


class PreferenceRepository(BaseDbRepository[SysUserPreference]):
    """用户偏好仓储（软删除由基座 `_select()` 统一过滤）。"""

    model = SysUserPreference

    async def get_value(self, user_id: int, key: str) -> SysUserPreference | None:
        """按用户与键取活行。

        Args:
            user_id: 用户主键。
            key: 偏好键。

        Returns:
            SysUserPreference | None: 偏好行；不存在 None。
        """
        statement = self._select().where(SysUserPreference.user_id == user_id).where(SysUserPreference.pref_key == key)
        return (await self._session.execute(statement)).scalars().first()

    async def get_many(self, user_id: int, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, object]:
        """批量取偏好值（仅返回存在的键）。

        Args:
            user_id: 用户主键。
            keys: 偏好键清单。

        Returns:
            ConcurrentStableDict[str, object]: 键 → 已解析值（解析失败跳过）。
        """
        result: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        if not keys:
            return result
        statement = (
            self._select().where(SysUserPreference.user_id == user_id).where(SysUserPreference.pref_key.in_(list(keys)))
        )
        for row in (await self._session.execute(statement)).scalars():
            try:
                result.set(row.pref_key, json.loads(row.pref_value))
            except json.JSONDecodeError:
                continue
        return result

    async def count_for_user(self, user_id: int) -> int:
        """统计用户当前偏好键数（活行）。

        Args:
            user_id: 用户主键。

        Returns:
            int: 键数。
        """
        statement = (
            select(func.count())
            .select_from(SysUserPreference)
            .where(SysUserPreference.user_id == user_id, SysUserPreference.deleted_at.is_(None))
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def upsert(self, user_id: int, key: str, value_json: str) -> SysUserPreference:
        """写入 / 覆盖偏好值。

        Args:
            user_id: 用户主键。
            key: 偏好键。
            value_json: JSON 字符串。

        Returns:
            SysUserPreference: 已 flush 的偏好行。
        """
        row = await self.get_value(user_id, key)
        if row is None:
            row = SysUserPreference(user_id=user_id, pref_key=key, pref_value=value_json)
            self._session.add(row)
        else:
            row.pref_value = value_json
        await self._session.flush()
        return row

    async def reset(self, user_id: int, key: str) -> bool:
        """重置偏好（软删除该键活行）。

        Args:
            user_id: 用户主键。
            key: 偏好键。

        Returns:
            bool: 是否删除到既有键。
        """
        row = await self.get_value(user_id, key)
        if row is None:
            return False
        row.soft_delete()
        await self._session.flush()
        return True
