"""系统参数管理接口契约：条目 / 分页 / 新增 / 修改请求。

- 条目对外统一暴露 `config_key`（DB 列名 `code`），并附派生字段 `group` / `source` / `is_sensitive`；
- `source`：`platform`（平台默认值，`is_overridden=false`）/ `tenant`（租户覆盖或租户自建）；
- `version` 为乐观锁版本，修改时必须回传详情里的当前值。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from bms_core.schemas.base import BaseSchema
from bms_core.schemas.pagination import BasePageResponse

__all__ = [
    "ConfigCreateRequest",
    "ConfigItem",
    "ConfigPage",
    "ConfigUpdateRequest",
]


class ConfigItem(BaseSchema):
    """系统参数条目（列表 / 详情同构）。"""

    id: int = Field(description="参数主键")
    config_key: str = Field(description="参数键（点分小写，如 password.max_age_days）")
    name: str = Field(description="参数名称（缺省取参数键）")
    value: str = Field(description="参数值（文本承载）")
    remark: str | None = Field(default=None, description="备注")
    status: str = Field(description="状态（enabled/disabled）")
    group: str = Field(description="分组（参数键首段，如 password）")
    source: str = Field(description="取值来源（platform=平台默认 / tenant=租户覆盖）")
    is_sensitive: bool = Field(description="是否安全敏感参数（页面提示 + 审计留痕）")
    version: int = Field(description="乐观锁版本")
    updated_at: datetime | None = Field(default=None, description="最后更新时间（UTC）")
    deleted_at: datetime | None = Field(default=None, description="软删除时间（回收站视图非空）")


class ConfigPage(BasePageResponse[ConfigItem]):
    """系统参数分页响应。"""


class ConfigCreateRequest(BaseSchema):
    """新增系统参数（租户自建；平台默认项已由种子下发）。"""

    config_key: str = Field(min_length=1, max_length=128, description="参数键（点分小写）")
    value: str = Field(max_length=20000, description="参数值")
    name: str | None = Field(default=None, max_length=128, description="参数名称（缺省取参数键）")
    remark: str | None = Field(default=None, max_length=255, description="备注")
    status: str = Field(default="enabled", description="状态（enabled/disabled）")


class ConfigUpdateRequest(BaseSchema):
    """修改系统参数（乐观锁：`version` 必填）。"""

    value: str | None = Field(default=None, max_length=20000, description="参数值")
    name: str | None = Field(default=None, max_length=128, description="参数名称")
    remark: str | None = Field(default=None, max_length=255, description="备注")
    status: str | None = Field(default=None, description="状态（enabled/disabled）")
    version: int = Field(ge=1, description="乐观锁版本（取详情里的当前值）")
