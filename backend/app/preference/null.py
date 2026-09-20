"""preference 能力域缺省实现（Null Object）：固定回退默认值、不落库、无副作用。"""

from app.core.capability import BaseNullObject
from app.preference.base import BasePreferenceStore

__all__ = ["NullPreferenceStore"]


class NullPreferenceStore(BasePreferenceStore, BaseNullObject):
    """占位用户偏好存储：读恒回退默认值、写 / 重置空操作（不落库、不连缓存）。"""

    async def get(self, key: str, *, default: object = None) -> object | None:
        """读取偏好（占位恒回退默认值）。

        Args:
            key: 偏好键（占位忽略）。
            default: 回退值。

        Returns:
            object | None: `default`。
        """
        return default

    async def set(self, key: str, value: object) -> None:
        """写入偏好（占位空操作）。

        Args:
            key: 偏好键（占位忽略）。
            value: 偏好值（占位忽略）。
        """

    async def reset(self, key: str) -> bool:
        """重置偏好（占位恒无既有键）。

        Args:
            key: 偏好键（占位忽略）。

        Returns:
            bool: False。
        """
        return False
