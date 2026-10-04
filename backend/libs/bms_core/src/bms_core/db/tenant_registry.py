"""租户注册快照与缓存口径（06_03）：跨服务读出口与本地源共用的数据结构与 key 规范。

- `TenantSnapshot`：租户注册快照（编码 / 名称 / 域名 / 状态 / 到期）；跨服务经 JSON 传递。
- 缓存：域 `tenant`（平台数据，key 租户位取 `global`）；**全局版本键** `bms:global:tenant:version`
  （写方 INCR，读方惰性比对；与字典版本键同模式）。
- `to_tenant_context`：快照 → `TenantContext`（库键由消费方按本地命名口径派生）。
"""

from dataclasses import dataclass
from typing import Any, cast

from bms_core.cache.base import build_cache_key
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.objects import BaseTenantViewContract
from bms_core.db.tenant import TenantContext, build_tenant_db_key

TENANT_CACHE_DOMAIN = "tenant"
"""租户注册缓存域（平台数据）。"""

TENANT_VERSION_KEY = build_cache_key(tenant=None, domain=TENANT_CACHE_DOMAIN, business_key="version")
"""租户注册全局版本键（`bms:global:tenant:version`；写方变更后 INCR）。"""

ACTIVE_STATUS = "active"
"""租户可用状态（其余状态一律按停用拒绝）。"""


@dataclass(frozen=True)
class TenantSnapshot(BaseTenantViewContract):
    """租户注册快照（可缓存 / 可跨服务传输）。"""

    code: str
    name: str
    domain: str | None = None
    status: str = ACTIVE_STATUS
    expire_at: str | None = None
    tenant_id: int | None = None
    db_basis: str | None = None
    """库名基（创建时冻结的租户编码；库键 / 库名由其派生，租户编码变更不随之变）。"""

    def to_payload(self, *, version: int | None = None) -> ConcurrentStableDict[str, Any]:
        """转可缓存字典（可选附版本戳）。

        Args:
            version: 记录时捕获的全局版本号；None 不带版本。

        Returns:
            ConcurrentStableDict[str, Any]: 载荷字典。
        """
        payload: ConcurrentStableDict[str, Any] = ConcurrentStableDict(
            {
                "code": self.code,
                "name": self.name,
                "domain": self.domain,
                "status": self.status,
                "expire_at": self.expire_at,
                "tenant_id": self.tenant_id,
                "db_basis": self.db_basis,
            }
        )
        if version is not None:
            payload.set("version", version)
        return payload

    @classmethod
    def from_payload(cls, payload: ConcurrentStableDict[str, object]) -> TenantSnapshot:
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
        db_basis = payload.get("db_basis")
        return cls(
            code=code,
            name=str(payload.get("name") or code),
            domain=cast("str | None", payload.get("domain")),
            status=str(payload.get("status") or ACTIVE_STATUS),
            expire_at=cast("str | None", payload.get("expire_at")),
            tenant_id=_tenant_id(tenant_id),
            db_basis=str(db_basis) if isinstance(db_basis, str) and db_basis else code,
        )


def _tenant_id(value: object) -> int | None:
    """归一租户主键（**字符串 id 必须接受**）。

    契约响应经 JSON 传输时雪花 id 会序列化为**十进制字符串**（大整数安全），而缓存载荷（`to_payload`）
    写的是 `int`——故两者都要接受；只认 `int` 会让「边界 code → id 解析」全部丢主键标识（登录 / 刷新 /
    SSO 等按 code 解析租户的链路随即失败）。

    Args:
        value: 载荷中的 `tenant_id`。

    Returns:
        int | None: 雪花 id；缺失 / 形态非法为 None。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def snapshot_cache_key(kind: str, value: str) -> str:
    """取租户注册缓存 key（平台数据：租户位取 `global`）。

    Args:
    kind: `code` / `domain` / `id`。
    value: 查询值。

    Returns:
        str: 缓存 key（`bms:global:tenant:{kind}:{value}`）。
    """
    return build_cache_key(tenant=None, domain=TENANT_CACHE_DOMAIN, business_key=f"{kind}:{value}")


def to_tenant_context(snapshot: TenantSnapshot) -> TenantContext:
    """快照 → 租户上下文（库键按**库名基 `db_basis`**派生）。

    Args:
        snapshot: 租户注册快照。

    Returns:
        TenantContext: 租户上下文。
    """
    return TenantContext(
        code=snapshot.code,
        db_key=build_tenant_db_key(snapshot.db_basis or snapshot.code),
        name=snapshot.name,
        tenant_id=snapshot.tenant_id,
        status=snapshot.status,
        domain=snapshot.domain,
    )
