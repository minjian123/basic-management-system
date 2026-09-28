"""值对象体系 · LLM 链层：模型调用结果。

**链结构（按公共段成层，本次 1 层）**：

- `BaseLlmResultContract`（公共段 `model` + `provider_key`）——对话 / 向量 / 识别三类结果共用
  「模型 + 提供者」溯源位。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseLlmResultContract"]


@dataclass(frozen=True)
class BaseLlmResultContract(BaseValueObject):
    """LLM 结果契约（角色链层）：模型调用结果的**溯源位**统一读面。

    公共段：`model`（模型名）+ `provider_key`（提供者键）——对话（`ChatResult`）、向量
    （`EmbeddingResult`）、识别（`OcrResult`）三类结果共用；用量统计与提供者路由按同一对字段归因。
    结果载荷（正文 / 向量 / 文本）由成员各自声明，不入公共段。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("model", "provider_key")
