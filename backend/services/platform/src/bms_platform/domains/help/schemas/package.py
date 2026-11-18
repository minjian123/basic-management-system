"""帮助包管理面请求 / 响应模型（`/help/packages*`，12_01）。

- `package_path` 只接受 `[help_package].root` 内的相对路径（POSIX 分隔），越界 / 绝对路径拒绝；
- `dry_run` 缺省 true：只返回计划计数，不写库；与命令行 `--apply` 共用同一计划器。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_LIST,
    BaseSchema,
    SnowflakeIdStr,
)

__all__ = [
    "HelpPackageItem",
    "HelpPackageLoadCounts",
    "HelpPackageLoadRequest",
    "HelpPackageLoadResult",
    "HelpPackagePage",
    "HelpPackageUnloadCounts",
    "HelpPackageUnloadRequest",
    "HelpPackageUnloadResult",
]


class HelpPackageItem(BaseSchema):
    """已装载帮助包登记行。"""

    id: SnowflakeIdStr = Field(description="包登记主键")
    product_key: str = Field(description="产品键")
    package_version: str = Field(description="包版本（X.Y.Z）")
    schema_version: int = Field(description="包格式版本")
    checksum: str = Field(description="装载时校验通过的校验和")
    article_count: int = Field(ge=0, description="该版本清单文章总数")
    generated_at: datetime | None = Field(default=None, description="清单生成时间（UTC）")
    loaded_at: datetime = Field(description="本次装载时间（UTC）")
    status: str = Field(description="状态（loaded / outdated / unloaded）")


class HelpPackagePage(BaseSchema):
    """帮助包分页响应。"""

    list: Annotated[ConcurrentStableList[HelpPackageItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="包登记行（装载时间倒序）"
    )
    total: int = Field(ge=0, description="总数")
    page: int = Field(ge=1, description="页码")
    size: int = Field(ge=1, description="每页条数")


class HelpPackageLoadRequest(BaseSchema):
    """装载 / 升级请求。"""

    package_path: str = Field(
        min_length=1, max_length=512, description="包目录或 package.yaml 的相对路径（限制在配置根目录内）"
    )
    dry_run: bool = Field(default=True, description="是否只预演（缺省 true；实跑传 false）")
    lenient: bool = Field(default=False, description="是否跳过无效文章并告警（缺省严格）")


class HelpPackageLoadCounts(BaseSchema):
    """装载计数（与命令行输出一致）。"""

    articles_new: int = Field(default=0, ge=0, description="新增文章数")
    articles_updated: int = Field(default=0, ge=0, description="更新文章数")
    articles_offline: int = Field(default=0, ge=0, description="下线文章数")
    articles_skipped: int = Field(default=0, ge=0, description="跳过总数（本地覆盖 + 目标冲突）")
    articles_skipped_override: int = Field(default=0, ge=0, description="因本地覆盖跳过")
    articles_skipped_conflict: int = Field(default=0, ge=0, description="因目标冲突跳过")
    articles_unchanged: int = Field(default=0, ge=0, description="不变文章数")
    categories_created: int = Field(default=0, ge=0, description="新增分类数")
    categories_updated: int = Field(default=0, ge=0, description="更新分类数")
    categories_unchanged: int = Field(default=0, ge=0, description="不变分类数")


class HelpPackageLoadResult(BaseSchema):
    """装载结果。"""

    applied: bool = Field(description="是否已写库（False = 预演）")
    package_action: str = Field(description="包状态迁移（created / upgraded / restored / unchanged）")
    product_key: str = Field(description="产品键")
    package_version: str = Field(description="包版本")
    counts: HelpPackageLoadCounts = Field(description="计数快照")
    warnings: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="告警（宽松模式跳过项等）"
    )


class HelpPackageUnloadRequest(BaseSchema):
    """卸载请求。"""

    dry_run: bool = Field(default=True, description="是否只预演（缺省 true；实跑传 false）")


class HelpPackageUnloadCounts(BaseSchema):
    """卸载计数。"""

    articles_offline: int = Field(default=0, ge=0, description="本次下线文章数")
    articles_unchanged: int = Field(default=0, ge=0, description="已下线文章数")
    packages_unloaded: int = Field(default=0, ge=0, description="置为已卸载的包行数")


class HelpPackageUnloadResult(BaseSchema):
    """卸载结果。"""

    applied: bool = Field(description="是否已写库（False = 预演）")
    counts: HelpPackageUnloadCounts = Field(description="计数快照")
