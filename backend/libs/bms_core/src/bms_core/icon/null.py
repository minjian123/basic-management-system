"""icon_registry 能力域缺省实现（Null Object）：空清单 / 恒定未命中 / 回显占位，不落库、不清洗 SVG。

- `NullIconRegistry`：清单固定为空（不臆造图标）；取图标恒定未命中（`10002` / 404）；
  新增与更新固定回显入参（标识由图标键派生、图标键派生值经统一助手生成）；删除恒返回 True。
"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import NotFoundError
from bms_core.icon.base import (
    DEFAULT_ICON_STATUS,
    ICON_CUSTOM_SOURCE,
    NULL_ICON_ID_PREFIX,
    BaseIconRegistry,
    IconDraft,
    IconInfo,
    IconPatch,
    build_icon_key,
)

__all__ = ["NullIconRegistry"]


class NullIconRegistry(BaseIconRegistry, BaseNullObject):
    """占位图标注册表：空清单、恒定未命中、写入回显（不落库、不清洗 SVG）。"""

    async def list(
        self,
        *,
        category: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> list[IconInfo]:
        """取图标清单（占位固定空清单，不区分过滤参数）。

        Args:
            category: 图标分组（占位忽略）。
            status: 图标状态（占位忽略）。
            keyword: 关键字（占位忽略）。

        Returns:
            list[IconInfo]: 空清单。
        """
        return []

    async def get(self, code: str) -> IconInfo:
        """取单图标定义（占位恒定未命中）。

        Args:
            code: 图标键。

        Raises:
            NotFoundError: 图标键未命中（10002 / 404）。
        """
        raise NotFoundError(f"图标不存在：{code}")

    async def create(self, draft: IconDraft) -> IconInfo:
        """新增图标（占位回显入参，不落库、不校验唯一性）。

        Args:
            draft: 新增入参。

        Returns:
            IconInfo: 占位图标定义（标识由图标键派生、状态缺省启用）。
        """
        return self._placeholder(
            code=draft.code,
            name=draft.name,
            category=draft.category,
            tags=list(draft.tags),
            svg=draft.svg,
            status=DEFAULT_ICON_STATUS,
        )

    async def update(self, code: str, patch: IconPatch) -> IconInfo:
        """更新图标（占位回显入参，未提供字段回落占位值）。

        Args:
            code: 图标键。
            patch: 更新入参（全字段可选）。

        Returns:
            IconInfo: 占位图标定义（名称回落图标键、分组与 SVG 回落空串、标签回落空列表、状态回落缺省）。
        """
        return self._placeholder(
            code=code,
            name=patch.name or code,
            category=patch.category or "",
            tags=list(patch.tags or []),
            svg=patch.svg or "",
            status=patch.status or DEFAULT_ICON_STATUS,
        )

    async def delete(self, code: str) -> bool:
        """删除图标（占位恒返回 True，不校验存在性、不做引用检查）。

        Args:
            code: 图标键（占位忽略）。

        Returns:
            bool: True。
        """
        return True

    @staticmethod
    def _placeholder(*, code: str, name: str, category: str, tags: list[str], svg: str, status: str) -> IconInfo:
        """构造占位图标定义（新增与更新共用）。

        Args:
            code: 图标键。
            name: 图标名称。
            category: 图标分组。
            tags: 标签。
            svg: SVG 内容。
            status: 状态。

        Returns:
            IconInfo: 占位图标定义。
        """
        return IconInfo(
            id=f"{NULL_ICON_ID_PREFIX}{code}",
            code=code,
            name=name,
            category=category,
            tags=tags,
            svg=svg,
            status=status,
            icon_key=build_icon_key(code, source=ICON_CUSTOM_SOURCE),
        )
