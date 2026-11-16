"""帮助内容侧缺省实现（Null Object）：恒定未命中、不查库、无副作用（08_02）。

帮助内容表归帮助内容维护任务；在该实现接入前，解析链仍可完整运行——命中判据自然落到
「未命中 + 分类为空」，前端据此隐藏帮助按钮（不出现「点了没反应」）。
"""

from fastapi import Request

from bms_core.core.capability import BaseNullObject
from bms_core.help.content import BaseHelpContentResolver, HelpContentQuery, HelpContentResult

__all__ = ["NullHelpContentResolver"]


class NullHelpContentResolver(BaseHelpContentResolver, BaseNullObject):
    """占位帮助内容解析：任何候选都返回空结果。"""

    async def resolve(self, query: HelpContentQuery, *, request: Request | None = None) -> HelpContentResult:
        """恒定未命中（占位实现忽略入参）。

        Args:
            query: 解析请求（占位忽略）。
            request: 当前请求（占位忽略）。

        Returns:
            HelpContentResult: 空结果（未命中）。
        """
        return HelpContentResult()
