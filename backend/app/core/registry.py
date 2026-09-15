"""core 层兼容模块：`BaseProviderRegistry` 已归位 `app/core/provider.py`。

保留过渡导出（既有导入零改动）；清理随后续阶段（无外部引用后）。
"""

from app.core.provider import BaseProviderRegistry

__all__ = ["BaseProviderRegistry"]
