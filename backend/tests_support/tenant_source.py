"""跨服务测试共用**假租户源**：以固定雪花主键映射演示 / 示例租户，屏蔽真实租户源外呼。

内部租户标识由 `code` 改为雪花 id 后，受保护路由的令牌租户位（id）经 `tenant_source.by_id`
解析；单测不应真实外呼租户注册契约，故以本替身统一返回带主键的 `TenantContext`。

- 映射（与 `services/identity/tests` 口径一致）：`demo ↔ "1001"`、`acme ↔ "2002"`；
- 实现 `TenantLookup` 三路：`by_code` / `by_domain` / `by_id`；
- `install_fake_tenant_source` 把应用装配入口 `build_tenant_lookup` 替换为返回本替身，
  `ApplicationFactory.create` 直接创建应用（不经 `service_app` 夹具）的用例同样生效。
"""

from __future__ import annotations

from bms_core.cache.base import CacheRegion
from bms_core.db.keys import build_tenant_db_key
from bms_core.db.tenant import TenantContext, TenantNotFoundError

DEMO_TENANT_CODE = "demo"
"""演示租户编码。"""

DEMO_TENANT_ID = "1001"
"""演示租户主键（雪花 id 字符串）。"""

ACME_TENANT_CODE = "acme"
"""示例租户编码。"""

ACME_TENANT_ID = "2002"
"""示例租户主键（雪花 id 字符串）。"""


class FakeTenantSource:
    """测试替身租户源：`demo ↔ 1001`、`acme ↔ 2002` 三路（编码 / 域名 / 主键）解析。"""

    cache: CacheRegion | None = None
    """无缓存（`clear_tenant_cache` 对 None 跳过）。"""

    def __init__(self) -> None:
        """初始化固定租户映射。"""
        self._tenants: tuple[TenantContext, ...] = (
            TenantContext(
                code=DEMO_TENANT_CODE,
                db_key=build_tenant_db_key(DEMO_TENANT_CODE),
                name="演示租户",
                domain="demo.bms.example.com",
                tenant_id=int(DEMO_TENANT_ID),
            ),
            TenantContext(
                code=ACME_TENANT_CODE,
                db_key=build_tenant_db_key(ACME_TENANT_CODE),
                name="示例租户",
                domain="acme.bms.example.com",
                tenant_id=int(ACME_TENANT_ID),
            ),
        )

    async def by_code(self, code: str) -> TenantContext:
        """按编码取租户上下文。

        Args:
            code: 租户编码（demo / acme）。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 未知租户编码。
        """
        for tenant in self._tenants:
            if tenant.code == code:
                return tenant
        raise TenantNotFoundError(f"未知租户：{code}")

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取租户上下文。

        Args:
            domain: 子域名（demo / acme 域名）。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 未知租户域名。
        """
        for tenant in self._tenants:
            if tenant.domain == domain:
                return tenant
        raise TenantNotFoundError(f"未知租户域名：{domain}")

    async def by_id(self, tenant_id: str) -> TenantContext:
        """按租户主键（雪花 id 字符串）取租户上下文。

        Args:
            tenant_id: 租户主键字符串。

        Returns:
            TenantContext: 租户上下文。

        Raises:
            TenantNotFoundError: 未知租户主键。
        """
        for tenant in self._tenants:
            if tenant.tenant_id is not None and str(tenant.tenant_id) == tenant_id:
                return tenant
        raise TenantNotFoundError(f"未知租户主键：{tenant_id}")


def install_fake_tenant_source(monkeypatch: object) -> None:
    """把应用装配入口 `build_tenant_lookup` 替换为返回 `FakeTenantSource`（进程内单测用）。

    平台 / 报告 / 搜索 / 租户等服务的用例既有经 `service_app` 夹具创建应用，也有测试内
    直接 `ApplicationFactory().create(None)`；替换装配入口可同时覆盖两类，避免逐用例改应用态。

    Args:
        monkeypatch: pytest `monkeypatch` 夹具（仅用其 `setattr`）。
    """
    from bms_core import application

    monkeypatch.setattr(application, "build_tenant_lookup", lambda *_args, **_kwargs: FakeTenantSource())
