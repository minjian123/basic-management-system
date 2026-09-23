"""租户注册快照与缓存口径（06_03）：跨服务读出口与本地源共用的数据结构与 key 规范。

- `TenantSnapshot`：租户注册快照（编码 / 名称 / 域名 / 状态 / 到期）；跨服务经 JSON 传递。
- 缓存：域 `tenant`（平台数据，key 租户位取 `global`）；**全局版本键** `bms:global:tenant:version`
  （写方 INCR，读方惰性比对；与字典版本键同模式）。
- `to_tenant_context`：快照 → `TenantContext`（库键由消费方按本地命名口径派生）。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from bms_core.cache.base import build_cache_key
from bms_core.core.base import BaseObject
from bms_core.db.tenant import TenantContext, build_tenant_db_key

TENANT_CACHE_DOMAIN = "tenant"
"""租户注册缓存域（平台数据）。"""

TENANT_VERSION_KEY = build_cache_key(tenant=None, domain=TENANT_CACHE_DOMAIN, business_key="version")
"""租户注册全局版本键（`bms:global:tenant:version`；写方变更后 INCR）。"""

ACTIVE_STATUS = "active"
"""租户可用状态（其余状态一律按停用拒绝）。"""


@dataclass(frozen=True)
class TenantSnapshot(BaseObject):
    """租户注册快照（可缓存 / 可跨服务传输）。"""

    code: str
    name: str
    domain: str | None = None
    status: str = ACTIVE_STATUS
    expire_at: str | None = None
    tenant_id: int | None = None

    def to_payload(self, *, version: int | None = None) -> dict[str, Any]:
        """转可缓存字典（可选附版本戳）。

        Args:
            version: 记录时捕获的全局版本号；None 不带版本。

        Returns:
            dict[str, Any]: 载荷字典。
        """
        payload: dict[str, Any] = {
            "code": self.code,
            "name": self.name,
            "domain": self.domain,
            "status": self.status,
            "expire_at": self.expire_at,
            "tenant_id": self.tenant_id,
        }
        if version is not None:
            payload["version"] = version
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> TenantSnapshot:
        """由载荷字典构造快照（字段宽松读取）。

        Args:
            payload: 载荷字典（缓存载荷或契约响应 data）。

        Returns:
            TenantSnapshot: 快照。

        Raises:
            KeyError: 缺少 `code` 字段。
        """
        code = payload["code"]
        if not isinstance(code, str) or not code:
            raise KeyError("租户注册快照缺少 code")
        tenant_id = payload.get("tenant_id")
        return cls(
            code=code,
            name=str(payload.get("name") or code),
            domain=cast("str | None", payload.get("domain")),
            status=str(payload.get("status") or ACTIVE_STATUS),
            expire_at=cast("str | None", payload.get("expire_at")),
            tenant_id=int(tenant_id) if isinstance(tenant_id, int) else None,
        )


def snapshot_cache_key(kind: str, value: str) -> str:
    """取租户注册缓存 key（平台数据：租户位取 `global`）。

    Args:
        kind: `code` / `domain`。
        value: 查询值。

    Returns:
        str: 缓存 key（`bms:global:tenant:{kind}:{value}`）。
    """
    return build_cache_key(tenant=None, domain=TENANT_CACHE_DOMAIN, business_key=f"{kind}:{value}")


def to_tenant_context(snapshot: TenantSnapshot) -> TenantContext:
    """快照 → 租户上下文（库键按本地命名口径派生）。

    Args:
        snapshot: 租户注册快照。

    Returns:
        TenantContext: 租户上下文。
    """
    return TenantContext(
        tenant_code=snapshot.code,
        db_key=build_tenant_db_key(snapshot.code),
        name=snapshot.name,
        tenant_id=snapshot.tenant_id,
        status=snapshot.status,
        domain=snapshot.domain,
    )
