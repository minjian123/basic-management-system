"""产品声明注册协议模型（07B `02_06`）：上报请求。

- **上报**：产品启动时携带**自身清单文本**（与本地装载同一解析器，避免协议与清单结构漂移）；
- **响应**：注册结果与快照以结构化字典返回（逐类计数 / 八类要素），不引入第二套 DTO 形状。
"""

from bms_core.schemas.base import BaseSchema

__all__ = ["DeclarationSubmitRequest"]


class DeclarationSubmitRequest(BaseSchema):
    """全量上报请求（单次全量，服务端按「本产品维度整体对账」）。"""

    product_key: str
    """声明方产品键（注册只能写自己名下记录）。"""

    service_key: str
    """注册方服务键（须与服务 JWT 的 `sub` 一致）。"""

    manifest_toml: str
    """产品自持清单的 TOML 文本（八段；与本地装载同一解析器）。"""
