"""国际化管理接口契约：语言清单 / 语言包 / 运行时下发。

- locale 一律 IETF 标准形态（`zh-CN` / `en-US` / `ar-SA`），比较大小写不敏感；
- 语言包维护列表的 `module` 由 `msg_key` 首段**派生**（不落列），供按模块筛选；
- 批量保存为差异三段（`adds` / `updates` / `deletes`），`updates` 必须回传行 `version`（乐观锁）。
- 集合字段一律插入序集合类 + `CONTRACT_COLLECTION` 注解（不用裸 `list` / `dict`）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    CONTRACT_STABLE_LIST,
    BaseSchema,
    SnowflakeIdStr,
)
from bms_core.schemas.pagination import BasePageResponse

__all__ = [
    "CacheInvalidateResult",
    "EnabledLocaleItem",
    "LocaleCreateRequest",
    "LocaleDeleteResult",
    "LocaleItem",
    "LocaleListPayload",
    "LocalePage",
    "LocaleUpdateRequest",
    "MessageAddItem",
    "MessageItem",
    "MessagePage",
    "MessageSaveRequest",
    "MessageSaveResult",
    "MessageUpdateItem",
    "MessagesPayload",
]


class LocaleItem(BaseSchema):
    """语言清单条目（维护列表 / 详情同构）。"""

    id: SnowflakeIdStr = Field(description="语言主键")
    code: str = Field(description="语言标识（IETF 标准形态，如 zh-CN）")
    name: str = Field(description="语言名称（本地名）")
    rtl: bool = Field(description="是否从右到左（驱动前端布局方向）")
    status: str = Field(description="状态（enabled/disabled）")
    is_default: bool = Field(description="是否系统默认语言（全清单恰一条）")
    sort: int = Field(description="排序（升序）")
    is_overridden: bool = Field(description="是否被租户改过（false=平台默认行）")
    version: int = Field(description="乐观锁版本")
    updated_at: datetime | None = Field(default=None, description="最后更新时间（UTC）")
    deleted_at: datetime | None = Field(default=None, description="软删除时间（回收站视图非空）")


class LocalePage(BasePageResponse[LocaleItem]):
    """语言清单分页响应。"""


class EnabledLocaleItem(BaseSchema):
    """启用语言清单条目（登录即可读；供多语言文案字段渲染语言格）。"""

    code: str = Field(description="语言标识")
    name: str = Field(description="语言名称")
    rtl: bool = Field(description="是否从右到左")
    is_default: bool = Field(description="是否系统默认语言")
    sort: int = Field(description="排序（升序）")


class LocaleCreateRequest(BaseSchema):
    """新增语言。"""

    code: str = Field(min_length=2, max_length=16, description="语言标识（IETF，如 ar-SA）")
    name: str = Field(min_length=1, max_length=64, description="语言名称（本地名）")
    rtl: bool = Field(default=False, description="是否从右到左")
    status: str = Field(default="enabled", description="状态（enabled/disabled）")
    sort: int = Field(default=0, description="排序（升序）")
    is_default: bool = Field(default=False, description="是否设为系统默认语言")


class LocaleUpdateRequest(BaseSchema):
    """修改语言（乐观锁：`version` 必填）。"""

    name: str | None = Field(default=None, min_length=1, max_length=64, description="语言名称")
    rtl: bool | None = Field(default=None, description="是否从右到左")
    status: str | None = Field(default=None, description="状态（enabled/disabled）")
    sort: int | None = Field(default=None, description="排序（升序）")
    is_default: bool | None = Field(default=None, description="是否设为系统默认语言")
    version: int = Field(ge=1, description="乐观锁版本（取详情里的当前值）")


class MessageItem(BaseSchema):
    """语言包维护条目（一行 = 一个 key 的一种语言）。"""

    id: SnowflakeIdStr = Field(description="文案主键")
    msg_key: str = Field(description="文案 key（模块.页面.字段）")
    module: str = Field(description="模块前缀（msg_key 首段，派生）")
    locale: str = Field(description="语言标识")
    value: str = Field(description="该语言文案（空白即缺失）")
    remark: str | None = Field(default=None, description="备注")
    is_overridden: bool = Field(description="是否被租户改过（false=平台默认行）")
    version: int = Field(description="乐观锁版本")


class MessagePage(BasePageResponse[MessageItem]):
    """语言包维护分页响应。"""


class MessageAddItem(BaseSchema):
    """新增文案行（已存在同 `(msg_key, locale)` 时转为更新，幂等）。"""

    msg_key: str = Field(min_length=3, max_length=128, description="文案 key（点分小写，至少两段）")
    locale: str = Field(min_length=2, max_length=16, description="语言标识")
    value: str = Field(default="", max_length=4000, description="该语言文案")
    remark: str | None = Field(default=None, max_length=255, description="备注")


class MessageUpdateItem(BaseSchema):
    """修改文案行（乐观锁）。"""

    id: SnowflakeIdStr = Field(description="文案主键")
    value: str = Field(default="", max_length=4000, description="该语言文案")
    remark: str | None = Field(default=None, max_length=255, description="备注")
    version: int = Field(ge=1, description="乐观锁版本")


class MessageSaveRequest(BaseSchema):
    """语言包批量保存（差异三段 + 幂等键）。"""

    adds: Annotated[ConcurrentStableList[MessageAddItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="新增行"
    )
    updates: Annotated[ConcurrentStableList[MessageUpdateItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="修改行"
    )
    deletes: Annotated[ConcurrentStableList[SnowflakeIdStr], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="删除行（仅租户自建行可删）"
    )


class MessageSaveResult(BaseSchema):
    """语言包批量保存结果。"""

    created: int = Field(description="新增行数")
    updated: int = Field(description="修改行数")
    deleted: int = Field(description="删除行数")
    version: int = Field(description="失效后的缓存版本号（0 = 失效失败 / 降级）")


class MessagesPayload(BaseSchema):
    """语言包下发载荷。"""

    locale: str = Field(description="生效语言（请求语言未启用时为默认语言）")
    fallback: bool = Field(description="是否发生回退（请求语言未启用 / 未登记）")
    version: int = Field(description="缓存版本号")
    messages: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="key → 文案"
    )


class CacheInvalidateResult(BaseSchema):
    """缓存主动失效结果。"""

    version: int = Field(description="失效后的版本号（0 = 失效失败）")
    degraded: bool = Field(description="是否降级（Redis 不可用时 true，不阻断保存）")


class LocaleListPayload(BaseSchema):
    """启用语言清单载荷（只读出口）。"""

    items: Annotated[ConcurrentStableList[EnabledLocaleItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="启用语言清单（按 sort 升序）"
    )


class LocaleDeleteResult(BaseSchema):
    """语言删除结果。"""

    deleted: bool = Field(description="是否已删除")
