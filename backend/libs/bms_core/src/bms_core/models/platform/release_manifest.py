"""发布清单模型（`sys_release_manifest` / `sys_release_manifest_domain`，07C `04_01`）：平台服务自有。

- **一行主表 = 一次发布**：记录「某个部署单元（某租户范围内）这次发布了哪些域、各自到哪个版本」，
  是**回滚的原子单位**与版本对账的依据；发布单元 = 部署单元（合并部署时一次发布覆盖多域）；
- **明细一域一行**：`schema_revision`（清单版本记录表当前值）/ `service_version` / `contract_version`
  三者在明细同时落盘，既是三方一致校验的载体，也是回滚的最小信息单元（漏一行就有一个域回不去）；
- **不可变**：发布记录写入后不修改——回滚另起一行 `status=rolled_back` 并用 `rolled_back_from`
  指向被回滚清单，历史始终可追溯；
- **失败也留痕**：发布失败写 `status=failed` 的主表行（不写明细），便于排查；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_release_manifest.md` /
  `sys_release_manifest_domain.md`），字段级口径不在本文件重复。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.models.base import BaseModel

RELEASE_STATUS_RELEASED = "released"
"""状态：已发布（正常发布成功）。"""

RELEASE_STATUS_ROLLED_BACK = "rolled_back"
"""状态：已回滚（本行由回滚产生，内容为回滚后的实际版本）。"""

RELEASE_STATUS_FAILED = "failed"
"""状态：发布失败（无明细，仅留痕）。"""

RELEASE_STATUSES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (RELEASE_STATUS_RELEASED, RELEASE_STATUS_ROLLED_BACK, RELEASE_STATUS_FAILED)
)
"""合法状态取值（写入与查询校验用）。"""

GLOBAL_TENANT_SCOPE = 0
"""作用范围哨兵：`0` = 全局（默认拓扑下的单元）；非 0 = 该租户专属单元。"""


class SysReleaseManifest(BaseModel):
    """发布清单主表（`sys_release_manifest`）：一次发布一行。

    唯一键 `(unit_key, tenant_scope, manifest_version, deleted_at)` —— 一单元一范围一版本一行，
    版本不许重复也不许回退；第二索引 `(unit_key, released_at)` 供「查某单元最近发布」（回滚目标定位）。
    """

    __tablename__ = "sys_release_manifest"
    __table_args__ = (
        UniqueConstraint(
            "unit_key",
            "tenant_scope",
            "manifest_version",
            "deleted_at",
            name="uq_sys_release_manifest_unit_scope_version_deleted_at",
        ),
        Index("idx_sys_release_manifest_unit_released_at", "unit_key", "released_at"),
    )

    unit_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="部署单元标识（跨库逻辑外键 → sys_tenant_topology.unit_key，只持值）"
    )
    tenant_scope: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=GLOBAL_TENANT_SCOPE,
        comment="作用范围（0 = 全局 / 默认拓扑；非 0 = 租户主键）",
    )
    manifest_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="发布批次号（同单元同范围内递增，不允许回退）"
    )
    topology_version: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="本次发布对应的拓扑版本（取自 sys_tenant_topology）"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RELEASE_STATUS_RELEASED, comment="状态（released / rolled_back / failed）"
    )
    released_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="发布时间（UTC）")
    released_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="发布人（sys_user.id；自动化发布为空）"
    )
    rolled_back_from: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="回滚来源清单主键（本行由回滚产生时填写，指向被回滚的那次发布）"
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="说明（发布摘要 / 回滚原因）")


class SysReleaseManifestDomain(BaseModel):
    """发布清单明细表（`sys_release_manifest_domain`）：一次发布中每个业务域一行。

    唯一键 `(manifest_id, domain_key, deleted_at)` —— 一次发布内一域一行；
    第二索引 `(domain_key, created_at)` 供「查某域的发布历史」（逐域回滚目标定位）。
    """

    __tablename__ = "sys_release_manifest_domain"
    __table_args__ = (
        UniqueConstraint(
            "manifest_id",
            "domain_key",
            "deleted_at",
            name="uq_sys_release_manifest_domain_manifest_domain_deleted_at",
        ),
        Index("idx_sys_release_manifest_domain_domain_created", "domain_key", "created_at"),
    )

    manifest_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="发布清单主键（同库逻辑外键 → sys_release_manifest.id，只持值）"
    )
    domain_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="业务域标识（跨库逻辑外键 → 业务域清单，只持值）"
    )
    schema_revision: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="本次发布后该域「表结构变更记录表」的 revision（无表结构的域为空）"
    )
    service_version: Mapped[str] = mapped_column(String(32), nullable=False, comment="承载该域的服务版本")
    contract_version: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="该域所属服务的契约版本（能力契约随服务契约）"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RELEASE_STATUS_RELEASED, comment="状态（released / rolled_back）"
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="说明（如「本次仅契约兼容变更」）")
