"""边缘身份头契约常量：网关注入 / 后端信任的身份头与剥除清单（两端唯一来源）。

- 网关注入、后端信任的身份头：`X-User-Id` / `X-Tenant-Id` / `X-User-Scopes` / `X-Service-Identity`；
- 网关专属标记头 `X-Gateway-Identity`（值 `GATEWAY_IDENTITY_VALUE`，非密钥；判定「来自可信边缘」）；
- `STRIPPED_HEADERS`：客户端伪造身份头一律剥除的清单（网关 `global_rules` 与后端
  `EdgeGuardMiddleware` 各做一遍，纵深防御）。

本模块**仅标准库、无导入**：网关生成器（`backend/ops/gateway_config.py` 精简 CI 环境）与后端
`bms_core.edge.base` 共同引用，避免 CI 拉入后端重依赖。
"""

from __future__ import annotations

__all__ = [
    "DEFAULT_EDGE_EXEMPT_PATHS",
    "GATEWAY_IDENTITY_HEADER",
    "GATEWAY_IDENTITY_VALUE",
    "IDENTITY_HEADERS",
    "SERVICE_IDENTITY_HEADER",
    "STRIPPED_HEADERS",
    "TENANT_ID_HEADER",
    "USER_ID_HEADER",
    "USER_SCOPES_HEADER",
    "USER_SUBJECT_HEADER",
]

GATEWAY_IDENTITY_HEADER = "X-Gateway-Identity"
"""网关专属标记头：网关注入、后端据此判定「来自可信边缘」。"""

GATEWAY_IDENTITY_VALUE = "bms-edge"
"""网关专属标记头期望值（非密钥，仅结构占位；真实防旁路靠服务 JWT / 网络隔离）。"""

USER_ID_HEADER = "X-User-Id"
"""网关注入的内部用户标识头（数字 id；外部身份映射后填充，07_03 起暂不注入）。"""

USER_SUBJECT_HEADER = "X-User-Subject"
"""网关注入的外部用户主体头（IdP `sub`，字符串；阶段六映射前唯一用户标识，07_03 新增）。"""

TENANT_ID_HEADER = "X-Tenant-Id"
"""网关注入的租户编码头（与租户解析链既有 `X-Tenant-ID` 同头，大小写不敏感）。"""

USER_SCOPES_HEADER = "X-User-Scopes"
"""网关注入的 scope 集合头（逗号分隔）。"""

SERVICE_IDENTITY_HEADER = "X-Service-Identity"
"""网关注入的服务身份头（服务间调用，07_03）。"""

IDENTITY_HEADERS: tuple[str, ...] = (
    USER_ID_HEADER,
    USER_SUBJECT_HEADER,
    TENANT_ID_HEADER,
    USER_SCOPES_HEADER,
    SERVICE_IDENTITY_HEADER,
)
"""网关注入 / 后端信任的身份头（客户端伪造一律剥除）。"""

STRIPPED_HEADERS: tuple[str, ...] = (GATEWAY_IDENTITY_HEADER, *IDENTITY_HEADERS)
"""客户端伪造头剥除清单（含网关标记头：只能由网关注入，客户端传入即丢弃）。"""

DEFAULT_EDGE_EXEMPT_PATHS: tuple[str, ...] = (
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/healthz",
    "/readyz",
    "/metrics",
)
"""边缘旁路拒绝 / 租户净化豁免路径缺省集（编排探针、指标端点与文档可达）。"""
