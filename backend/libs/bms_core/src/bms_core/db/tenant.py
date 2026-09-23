"""多租户上下文与解析链编排：租户上下文、数据源键助手与请求级依赖。

- 上下文：`TenantContext`（编码 / 库键 / 名称 / 主键 / 状态 / 域名）；`current_tenant` 上下文变量由
  租户全局中间件设置，供服务层与数据访问层取值。
- 数据源键：`build_tenant_db_key` / `parse_tenant_db_key` 自 `bms_core/db/keys.py` **re-export**
  （键形态与库名单一来源归 `db/keys.py`，06_01）：上下文携带**相对键** `tenant_{code}`，
  随运行服务解析为 `bms_{service}_{code}`；**禁止全局单例持有租户引擎**，引擎一律经
  `EngineRegistry` 按库键取用。
- 解析链：子域名（按注册表 `domain` 查）→ `X-Tenant-ID`（按 `code` 查）→ token 租户位（请求态，
  认证阶段写入即自然生效）；真实取数 / 缓存 / 停用回收见 `app/db/tenant_source.py` 的 `TenantSource`。
- 无来源回落策略由调用方传入（`allow_demo_fallback`）：dev/test 兜底演示租户、prod 拒绝。
- `get_tenant`：请求级依赖，优先读请求态（全局中间件已解析），键缺失时就地按同一编排解析。
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.context import current_tenant, get_tenant_context
from bms_core.core.exceptions import ConfigError, TenantNotFoundError
from bms_core.db.keys import (
    TENANT_DB_KEY_PREFIX,
    build_tenant_db_key,
    parse_db_key,
)

__all__ = [
    "DEFAULT_EXEMPT_PATHS",
    "DEMO_TENANT",
    "TENANT_DB_KEY_PREFIX",
    "TenantContext",
    "TenantLookup",
    "build_tenant_db_key",
    "current_tenant_context",
    "get_tenant",
    "is_exempt_path",
    "parse_tenant_db_key",
    "resolve_request_tenant",
    "tenant_hostname",
]

DEFAULT_EXEMPT_PATHS: tuple[str, ...] = ("/", "/docs", "/redoc", "/openapi.json", "/healthz", "/readyz")
"""租户解析豁免路径缺省集（正式取值见 `[tenant].exempt_paths`）。"""


@dataclass(frozen=True)
class TenantContext(BaseObject):
    """租户上下文：租户编码、数据源键、名称与注册要素。"""

    tenant_code: str
    db_key: str
    name: str
    tenant_id: int | None = None
    status: str = "active"
    domain: str | None = None


DEMO_TENANT = TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户")
"""内置演示租户（仅租户源不可用的兜底路径使用；正常路径经租户源取真实注册记录）。"""


class TenantLookup(Protocol):
    """租户源契约：按编码 / 子域名取租户上下文（实现见 `TenantSource`）。"""

    async def by_code(self, code: str) -> TenantContext:
        """按租户编码取上下文。

        Args:
            code: 租户编码（全小写）。

        Returns:
            TenantContext: 租户上下文。
        """
        ...

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取上下文。

        Args:
            domain: 子域名（如 `demo.bms.example.com`）。

        Returns:
            TenantContext: 租户上下文。
        """
        ...


def parse_tenant_db_key(db_key: str) -> str:
    """由数据源键反解租户编码（键形态见 `bms_core/db/keys.py`）。

    兼容两种形态：相对键 `tenant_{code}` 与全限定键 `tenant_{service}_{code}`
    （后者剥离服务段，服务段判定见 `db/keys.py::parse_db_key`）。

    Args:
        db_key: 数据源键。

    Returns:
        str: 租户编码。

    Raises:
        ConfigError: 非租户库键或编码为空。
    """
    key = parse_db_key(db_key)
    if key.kind != "tenant" or not key.tenant_code:
        raise ConfigError(f"非租户数据源键：{db_key}（应为 tenant_{{code}} 或 tenant_{{service}}_{{code}}）")
    return key.tenant_code


def tenant_hostname(host: str | None) -> str | None:
    """从 Host 头提取带租户前缀的主机名（去端口；仅三段及以上域名视为带子域名）。

    子域名来源按**完整主机名**匹配注册表 `domain`（如 `demo.bms.example.com`），
    无匹配再回落请求头 / token 来源。

    Args:
        host: Host 头（可含端口）。

    Returns:
        str | None: 主机名；无子域名前缀则 None。
    """
    if not host:
        return None
    hostname = host.split(":", 1)[0]
    return hostname if len(hostname.split(".")) >= 3 else None


def is_exempt_path(path: str, exempt_paths: Iterable[str] = DEFAULT_EXEMPT_PATHS) -> bool:
    """是否为租户解析豁免路径（精确匹配）。

    Args:
        path: 请求路径。
        exempt_paths: 豁免路径集合（`[tenant].exempt_paths`；缺省取内置集）。

    Returns:
        bool: 豁免 True。
    """
    return path in frozenset(exempt_paths)


def current_tenant_context() -> TenantContext:
    """取当前请求上下文租户（服务 / 仓储在请求外调用时的统一入口）。

    - 上下文未设置（后台任务 / 测试直调）回落演示租户；
    - 上下文已设置（全局中间件解析通过）时优先取完整上下文（含主键 / 状态，供租户过滤注入）；
      仅有编码的旧调用面按编码派生库键构造上下文。

    Returns:
        TenantContext: 租户上下文。
    """
    context = get_tenant_context()
    if context is not None:
        return context
    code = current_tenant.get()
    if not code:
        return DEMO_TENANT
    return TenantContext(tenant_code=code, db_key=build_tenant_db_key(code), name=code)


async def resolve_request_tenant(
    *,
    path: str,
    host: str | None = None,
    header: str | None = None,
    token_tenant: str | None = None,
    source: TenantLookup | None = None,
    exempt_paths: Iterable[str] = DEFAULT_EXEMPT_PATHS,
    allow_demo_fallback: bool = True,
) -> TenantContext | None:
    """按解析链解析请求租户（子域名 → 请求头 → token 租户位）。

    Args:
        path: 请求路径（豁免判定）。
        host: Host 头（子域名来源）。
        header: `X-Tenant-ID` 请求头。
        token_tenant: token 内租户编码（认证阶段写入请求态）。
        source: 租户源（真实查库）；None 时仅内置演示租户可用（未经中间件装配的场景）。
        exempt_paths: 豁免路径集合。
        allow_demo_fallback: 无来源时是否回落演示租户。

    Returns:
        TenantContext | None: 租户上下文；豁免路径为 None。

    Raises:
        TenantNotFoundError: 来源命中但未知租户 / 无来源且不允许回落。
        TenantSuspendedError: 来源命中但租户已停用（由租户源抛出）。
    """
    if is_exempt_path(path, exempt_paths):
        return None
    hostname = tenant_hostname(host)
    for kind, value in (("domain", hostname), ("code", header), ("code", token_tenant)):
        if not value:
            continue
        if source is None:
            return _builtin_lookup(value)
        return await (source.by_domain(value) if kind == "domain" else source.by_code(value))
    if not allow_demo_fallback:
        raise TenantNotFoundError("未提供租户标识（子域名 / X-Tenant-ID / 令牌）")
    if source is None:
        return DEMO_TENANT
    try:
        return await source.by_code(DEMO_TENANT.tenant_code)
    except TenantNotFoundError:
        return DEMO_TENANT


def _builtin_lookup(code: str) -> TenantContext:
    """内置兜底查询（仅演示租户；租户源未装配的单测 / 非标准装配场景）。

    Args:
        code: 租户编码。

    Returns:
        TenantContext: 演示租户上下文。

    Raises:
        TenantNotFoundError: 非演示租户。
    """
    if code == DEMO_TENANT.tenant_code:
        return DEMO_TENANT
    raise TenantNotFoundError(f"未知租户：{code}")


async def get_tenant(request: Request) -> TenantContext | None:
    """请求级租户依赖：优先读请求态（全局中间件已解析），键缺失时就地解析。

    Args:
        request: 当前请求。

    Returns:
        TenantContext | None: 租户上下文；豁免路径为 None。

    Raises:
        TenantNotFoundError: 未知租户（全局处理器转 404 / 80001）。
        TenantSuspendedError: 租户停用（全局处理器转 403 / 80002）。
    """
    state = request.scope.get("state", {})
    if "tenant" in state:
        return state.get("tenant")  # type: ignore[return-value]
    settings = getattr(request.app.state, "settings", None)
    source = getattr(request.app.state, "tenant_source", None)
    return await resolve_request_tenant(
        path=request.url.path,
        host=request.headers.get("host"),
        header=request.headers.get("X-Tenant-ID"),
        token_tenant=state.get("tenant_id"),  # type: ignore[arg-type]
        source=source,
        exempt_paths=settings.tenant.exempt_paths if settings is not None else DEFAULT_EXEMPT_PATHS,
        allow_demo_fallback=settings.tenant.allow_demo_fallback if settings is not None else True,
    )
