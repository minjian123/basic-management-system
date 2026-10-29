"""租户部署拓扑模型（`sys_tenant_topology`，07C `02_01`）：平台服务自有。

- **一行 = 某租户的某业务域由哪个部署单元承载**；库由部署单元派生，不在本表重复存库名
  （否则本表会成为库名的第二份事实源）；
- **平台级默认拓扑**：`tenant_id = 0`，未单独配置的租户沿用；租户一旦有自身记录则**整体覆盖**默认；
- **发布时生效**：同一批次写同一个 `topology_version`，解析只取该租户**最大版本**的未删除行，
  故写入必须整批替换（软删旧行 + 插新行）而非逐行改；
- **不落租户库名基**：租户库键 `tenant_{unit}_{db_basis}` 由调用方以自身 `db_basis` 派生
  （`db_basis` 属 `tenant` 域表，跨域读被 D1/D3 拦截）。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_tenant_topology.md`），字段级口径不在本文件重复。
"""

from sqlalchemy import BigInteger, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

TOPOLOGY_STATUS_ENABLED = "enabled"
"""状态：本租户启用该业务域（参与解析）。"""

TOPOLOGY_STATUS_DISABLED = "disabled"
"""状态：本租户停用该业务域（解析报 `not_enabled`，业务态而非配置缺失）。"""

TOPOLOGY_STATUSES: tuple[str, ...] = (TOPOLOGY_STATUS_ENABLED, TOPOLOGY_STATUS_DISABLED)
"""合法状态取值（写入校验用）。"""

DEFAULT_TOPOLOGY_TENANT_ID = 0
"""平台级默认拓扑的租户主键（未单独配置的租户沿用其行集合）。"""


class SysTenantTopology(BaseModel):
    """租户部署拓扑表（`sys_tenant_topology`）：租户 × 业务域 → 部署单元。

    唯一键 `(tenant_id, domain_key, deleted_at)` —— 一租户一域一条当前映射（禁止长期双活）；
    第二索引 `(tenant_id, unit_key)` 供「某单元承载哪些域」的反查（部署编排用）。
    """

    __tablename__ = "sys_tenant_topology"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "domain_key",
            "deleted_at",
            name="uq_sys_tenant_topology_tenant_domain_deleted_at",
        ),
        Index("idx_sys_tenant_topology_tenant_unit", "tenant_id", "unit_key"),
    )

    tenant_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="租户主键（同库逻辑外键 → sys_tenant.id，只持值；0=默认拓扑）"
    )
    domain_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="业务域标识（逻辑外键 → 业务域登记，只持值；写入前校验已登记）"
    )
    unit_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="部署单元标识（同一租户内由本表定义；写入前校验命名合法）"
    )
    topology_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="拓扑版本（同租户同版本号；解析取最大版本）"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TOPOLOGY_STATUS_ENABLED, comment="状态（enabled / disabled）"
    )
    note: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="说明（如“按业务重心拆分”“模板：分组型”）"
    )
