"""发布清单 DTO（07C `04_01`）：发布单元快照、预检结论与回滚计划。

本模块是平台注册域对内的**不可变数据形态**：

- 发布清单本身落两表（主表 + 域明细），DTO 只做「行 → 快照」的字段拷贝，不查询、不遍历关系；
- 预检结论与回滚计划是**计算产物**（不落库）：结论逐项可读（校验 / 结果 / 详情），计划逐域可读
  （从哪个 revision 到哪个 revision），供运维与流水线直接输出；
- 命名一律带 `Release` / `Rollback` 前缀，避免与响应模型（`schemas/release.py`）同名——
  基座的类形态索引按**类名**聚合，同名会让 Pydantic 契约被当成「值对象未冻结」。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.models.platform.release_manifest import SysReleaseManifest, SysReleaseManifestDomain

__all__ = [
    "ReleaseCheckItem",
    "ReleaseDomainEntry",
    "ReleaseManifestSnapshot",
    "ReleasePrecheckResult",
    "RollbackPlan",
    "RollbackStep",
]


@dataclass(frozen=True)
class ReleaseDomainEntry(BaseValueObject):
    """发布清单的一行明细（某业务域本次发布到哪个版本）。"""

    domain_key: str
    """业务域标识。"""

    service_key: str
    """承载该域的服务标识。"""

    service_version: str
    """服务版本（代码版本快照）。"""

    contract_version: str
    """契约版本（能力契约随服务契约）。"""

    schema_revision: str | None = None
    """表结构 revision（该域版本记录表当前值；无表结构的域为空）。"""

    note: str = ""
    """说明。"""

    @classmethod
    def from_model(cls, row: SysReleaseManifestDomain) -> ReleaseDomainEntry:
        """由明细行构造条目。

        Args:
            row: 明细 ORM 记录。

        Returns:
            ReleaseDomainEntry: 域明细条目。
        """
        return cls(
            domain_key=row.domain_key,
            service_key="",
            service_version=row.service_version,
            contract_version=row.contract_version,
            schema_revision=row.schema_revision,
            note=row.note or "",
        )


@dataclass(frozen=True)
class ReleaseCheckItem(BaseValueObject):
    """一项发布前置校验的结论（逐项可读：校验 / 结果 / 详情）。"""

    key: str
    """校验标识（`unit_complete` / `version_consistent` / …）。"""

    title: str
    """校验名称（中文，输出给人看）。"""

    passed: bool
    """是否通过。"""

    detail: str = ""
    """详情（失败时给出定位信息：域 / 期望值 / 实际值）。"""


@dataclass(frozen=True)
class ReleasePrecheckResult(BaseValueObject):
    """发布前置校验的整体结论（任一不过即整体失败，且不改变任何状态）。"""

    unit_key: str
    """部署单元标识。"""

    tenant_scope: int
    """作用范围（`0` = 全局）。"""

    manifest_version: int
    """本次发布的批次号（校验后确定的取值）。"""

    topology_version: int
    """本次发布绑定的拓扑版本。"""

    entries: ConcurrentStableList[ReleaseDomainEntry]
    """按单元域集派生的明细（校验通过时即为将写入的明细）。"""

    items: ConcurrentStableList[ReleaseCheckItem]
    """逐项校验结论（顺序与设计 §3.3 一致）。"""

    @property
    def passed(self) -> bool:
        """整体是否通过（全部校验项通过）。

        Returns:
            bool: 全部通过 True。
        """
        return all(item.passed for item in self.items)

    def failures(self) -> ConcurrentStableList[ReleaseCheckItem]:
        """取未通过的校验项。

        Returns:
            ConcurrentStableList[ReleaseCheckItem]: 未通过项（通过时为空清单）。
        """
        return ConcurrentStableList(item for item in self.items if not item.passed)


@dataclass(frozen=True)
class ReleaseManifestSnapshot(BaseValueObject):
    """一次发布的完整快照（主表字段 + 逐域明细）。"""

    id: int
    """清单主键。"""

    unit_key: str
    """部署单元标识。"""

    tenant_scope: int
    """作用范围（`0` = 全局）。"""

    manifest_version: int
    """发布批次号。"""

    topology_version: int
    """本次发布对应的拓扑版本。"""

    status: str
    """状态（`released` / `rolled_back` / `failed`）。"""

    released_at: datetime
    """发布时间（UTC）。"""

    rolled_back_from: int | None
    """回滚来源清单主键（本行由回滚产生时非空）。"""

    note: str
    """说明。"""

    domains: ConcurrentStableList[ReleaseDomainEntry]
    """逐域明细（失败行没有明细，为空清单）。"""

    @classmethod
    def from_models(
        cls,
        row: SysReleaseManifest,
        domains: ConcurrentStableList[ReleaseDomainEntry],
    ) -> ReleaseManifestSnapshot:
        """由主表行 + 明细条目构造快照。

        Args:
            row: 主表 ORM 记录。
            domains: 明细条目（按域升序）。

        Returns:
            ReleaseManifestSnapshot: 发布快照。
        """
        return cls(
            id=row.id,
            unit_key=row.unit_key,
            tenant_scope=row.tenant_scope,
            manifest_version=row.manifest_version,
            topology_version=row.topology_version,
            status=row.status,
            released_at=row.released_at,
            rolled_back_from=row.rolled_back_from,
            note=row.note or "",
            domains=domains,
        )


@dataclass(frozen=True)
class RollbackStep(BaseValueObject):
    """回滚计划中的一步（某业务域从当前版本回到目标版本）。"""

    domain_key: str
    """业务域标识。"""

    from_revision: str | None
    """当前发布中的结构 revision。"""

    to_revision: str | None
    """目标发布中的结构 revision。"""

    @property
    def changes(self) -> bool:
        """该域是否需要回退（revision 不同即需要）。

        Returns:
            bool: 需要回退 True。
        """
        return self.from_revision != self.to_revision


@dataclass(frozen=True)
class RollbackPlan(BaseValueObject):
    """批次回滚计划（按清单整体回退，不做部分回滚）。"""

    unit_key: str
    """部署单元标识。"""

    tenant_scope: int
    """作用范围（`0` = 全局）。"""

    source: ReleaseManifestSnapshot
    """被回滚的当前发布。"""

    target: ReleaseManifestSnapshot
    """回退目标（同单元同范围上一次成功发布）。"""

    steps: ConcurrentStableList[RollbackStep]
    """逐域回退步骤（按域升序）。"""

    blocked_reasons: ConcurrentStableList[str]
    """阻断原因（目标发布缺少某域记录等；非空即不可执行）。"""

    @property
    def requires_confirmation(self) -> bool:
        """是否需要人工确认（任一域的结构 revision 需要回退即需要）。

        结构回退若涉及删列（原升级是加列的反向），默认**拒绝自动执行**——数据丢失不可召回。

        Returns:
            bool: 需要显式确认 True。
        """
        return any(step.changes for step in self.steps)

    @property
    def executable(self) -> bool:
        """是否可执行（无阻断原因）。

        Returns:
            bool: 可执行 True。
        """
        return not self.blocked_reasons
