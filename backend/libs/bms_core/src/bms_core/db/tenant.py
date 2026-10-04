"""多租户上下文与解析链编排：租户上下文、数据源键助手与请求级依赖。

- 上下文：`TenantContext`（编码 / 库键 / 名称 / 主键 / 状态 / 域名）；`current_tenant` /
  `current_tenant_id` 上下文变量由租户全局中间件设置，供服务层与数据访问层取值；内部键
  （缓存 / 限流 / 幂等 / 锁）租户位经 `current_tenant_id_str()` 取（完整上下文优先、无主键为空）。
- 数据源键：`build_tenant_db_key` / `parse_tenant_db_key` 自 `bms_core/db/keys.py` **re-export**
  （键形态与库名单一来源归 `db/keys.py`，06_01）：上下文携带**相对键** `tenant_{code}`，
  随运行服务解析为 `bms_{service}_{code}`；**禁止全局单例持有租户引擎**，引擎一律经
  `EngineRegistry` 按库键取用。
- 解析链：子域名（按注册表 `domain` 查）→ `X-Tenant-ID`（按 `code` 查）→ 令牌租户位（雪花 id，
  按 `by_id` 查；认证阶段写入请求态即自然生效）；真实取数 / 缓存 / 停用回收见
  `app/db/tenant_source.py` 的 `TenantSource`。
- 无来源回落策略由调用方传入（`allow_demo_fallback`）：dev/test 兜底演示租户、prod 拒绝。
- **来源形态校验（06_04）**：子域名来源排除 IP 字面量（IPv4 / IPv6）与本机名，且须为 ≥ 三段合法域名；
  请求头来源须为合法租户编码形态、令牌来源须为合法租户主键形态（雪花 id）；形态非法一律视为未命中（不回退成 5xx）。
- `get_tenant`：请求级依赖，优先读请求态（全局中间件已解析），键缺失时就地按同一编排解析。
"""

import ipaddress
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from fastapi import Request

from bms_core.core.context import current_tenant, current_tenant_id, get_tenant_context
from bms_core.core.exceptions import ConfigError, TenantNotFoundError
from bms_core.core.objects import BaseTenantViewContract
from bms_core.db.keys import (
    TENANT_DB_KEY_PREFIX,
    build_tenant_db_key,
    parse_db_key,
)

__all__ = [
    "DEFAULT_DEFERRED_PATHS",
    "DEFAULT_EXEMPT_PATHS",
    "DEMO_TENANT",
    "TENANT_DB_KEY_PREFIX",
    "TenantContext",
    "TenantLookup",
    "build_tenant_db_key",
    "current_tenant_context",
    "current_tenant_id_str",
    "get_tenant",
    "is_deferred_path",
    "is_exempt_path",
    "is_local_hostname",
    "is_tenant_code",
    "is_tenant_domain",
    "is_tenant_id",
    "parse_tenant_db_key",
    "resolve_request_tenant",
    "tenant_hostname",
]

DEFAULT_EXEMPT_PATHS: tuple[str, ...] = (
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/healthz",
    "/readyz",
    "/metrics",
    "/.well-known/jwks.json",
)
"""租户解析豁免路径缺省集（正式取值见 `[tenant].exempt_paths`）。"""

DEFAULT_DEFERRED_PATHS: tuple[str, ...] = (
    "/api/v1/auth/login",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/captcha",
    "/api/v1/auth/sso",
)
"""免登录链路延迟解析路径缺省集（正式取值见 `[tenant].deferred_paths`）。

这些路径**有来源则正常解析上下文、无来源则不硬拒**（置空放行），由端点层按请求体 / 唯一启用租户
决定后续语义（如认证段 `20007`）。生产 `allow_demo_fallback=false` 时，若无延迟解析，登录等端点会
被中间件先行拒绝、无从返回可操作引导。匹配语义见 `is_deferred_path`。"""

_TENANT_CODE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
"""租户编码形态（与 `sys_tenant.code` 字段口径一致：字母开头、字母数字下划线、长度 ≤ 64）。"""

_TENANT_ID_PATTERN = re.compile(r"[0-9]{1,20}")
"""租户主键形态（雪花 id 十进制字符串：纯数字、长度 ≤ 20）。"""

_TENANT_DOMAIN_PATTERN = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
"""租户域名形态（≥ 两段 DNS 标签：字母数字与连字符、不以连字符起止、单段 ≤ 63）。"""

_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})
"""本机主机名（一律不参与租户子域名解析）。"""


@dataclass(frozen=True)
class TenantContext(BaseTenantViewContract):
    """租户上下文：租户编码、数据源键、名称与注册要素。"""

    code: str
    db_key: str
    name: str
    tenant_id: int | None = None
    """租户主键（雪花 id）；解析链经租户源产出后**必非空**（缺失即拒绝）；演示兜底可为 None。"""
    status: str = "active"
    domain: str | None = None


DEMO_TENANT = TenantContext(code="demo", db_key="tenant_demo", name="演示租户")
"""内置演示租户（仅租户源不可用的兜底路径使用；正常路径经租户源取真实注册记录）。

演示租户 `tenant_id` 为 None——仅开发 / 测试的无来源兜底路径，不参与内部 id 键（缓存 / 会话等
按全局或省略处理）；生产要求租户源可达、解析链必出真实雪花 id。
"""


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

    async def by_id(self, tenant_id: str) -> TenantContext:
        """按租户主键取上下文（雪花 id 十进制字符串）。

        Args:
            tenant_id: 租户主键字符串。

        Returns:
            TenantContext: 租户上下文。
        """
        ...

    async def single_active(self) -> TenantContext | None:
        """解析唯一启用租户（免登录链路无来源时兜底）。

        启用租户判定与既有解析链一致：`status == active` 且未软删（**不判到期时间**）。

        Returns:
            TenantContext | None: 恰 1 个启用租户 → 其上下文；0 个 → `None`。

        Raises:
            MultipleActiveTenantsError: ≥ 2 个启用租户（`80004` / 409；不携带租户清单）。
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


def is_tenant_code(value: str) -> bool:
    """是否为形态合法的租户编码。

    Args:
        value: 待校验值（`X-Tenant-ID` / 兜底来源值）。

    Returns:
        bool: 合法 True。
    """
    return bool(value) and _TENANT_CODE_PATTERN.fullmatch(value) is not None


def is_tenant_id(value: str) -> bool:
    """是否为形态合法的租户主键（雪花 id 十进制字符串）。

    Args:
        value: 待校验值（令牌租户位）。

    Returns:
        bool: 合法 True。
    """
    return bool(value) and _TENANT_ID_PATTERN.fullmatch(value) is not None


def is_tenant_domain(value: str) -> bool:
    """是否为形态合法的域名（≥ 两段 DNS 标签，总长 ≤ 253）。

    Args:
        value: 待校验值（Host 提取结果）。

    Returns:
        bool: 合法 True。
    """
    return bool(value) and len(value) <= 253 and _TENANT_DOMAIN_PATTERN.fullmatch(value) is not None


def is_local_hostname(hostname: str) -> bool:
    """是否为本机 / IP 字面量主机名（IPv4、IPv6、`localhost`）。

    这类主机名**不是租户域名**：本地开发、CI（`Host: 127.0.0.1:8000`）、Compose 内直连与探活
    都会用到 IP 直连；若按子域名解析会取到「IP 当作租户编码」的脏值，进而派生出非法库名
    （如 `bms_platform_127.0.0.1`）并冒泡 5xx。

    Args:
        hostname: 已去端口 / 去方括号的主机名。

    Returns:
        bool: 本机名或 IP 字面量 True。
    """
    if not hostname:
        return True
    if hostname.lower() in _LOCAL_HOSTNAMES:
        return True
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def tenant_hostname(host: str | None) -> str | None:
    """从 Host 头提取带租户前缀的主机名（去端口；仅三段及以上**合法域名**视为带子域名）。

    子域名来源按**完整主机名**匹配注册表 `domain`（如 `demo.bms.example.com`），
    无匹配再回落请求头 / token 来源。**IP 字面量（IPv4 / IPv6）与 `localhost` 一律返回 None**
    ——IP 直连不是租户域名；域名形态非法的取值同样返回 None（等同未提供来源，由
    `resolve_request_tenant` 按 `allow_demo_fallback` 决定回落演示租户或拒绝），
    避免请求侧脏值派生出非法库名而冒泡 5xx。

    Args:
        host: Host 头（可含端口；IPv6 可含方括号）。

    Returns:
        str | None: 主机名；非租户域名 / 形态非法则 None。
    """
    if not host:
        return None
    hostname = host.split(":", 1)[0].strip().strip("[]")
    if is_local_hostname(hostname) or not is_tenant_domain(hostname):
        return None
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


def is_deferred_path(path: str, deferred_paths: Iterable[str] = DEFAULT_DEFERRED_PATHS) -> bool:
    """是否为免登录链路延迟解析路径（前缀匹配）。

    命中延迟路径时无租户来源不硬拒（置空放行），由端点层再解析。匹配语义：与清单项**相等**或
    以「清单项 + `/`」为前缀（如清单项 `/api/v1/captcha` 命中 `/api/v1/captcha/scenes/login/policy`）。

    Args:
        path: 请求路径。
        deferred_paths: 延迟路径集合（`[tenant].deferred_paths`；缺省取内置集）。

    Returns:
        bool: 延迟解析 True。
    """
    return any(path == item or path.startswith(f"{item}/") for item in deferred_paths)


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
    return TenantContext(code=code, db_key=build_tenant_db_key(code), name=code)


def current_tenant_id_str() -> str | None:
    """取当前请求上下文租户主键字符串（内部键租户位；无主键为空）。

    - 完整租户上下文（含解析链产出的雪花主键）优先；
    - 仅有编码的旧调用面 / 演示兜底返回空（内部 id 键按全局处理）。

    Returns:
        str | None: 租户主键（雪花 id 十进制字符串）；无完整上下文 / 无主键为空。
    """
    context = get_tenant_context()
    if context is not None and context.tenant_id is not None:
        return str(context.tenant_id)
    return current_tenant_id.get()


def _usable_code(value: str | None) -> str | None:
    """来源值可用作租户编码时原样返回，否则 None（形态非法等同未提供来源）。

    Args:
        value: 来源值（`X-Tenant-ID`）。

    Returns:
        str | None: 可用值；缺失或形态非法 None。
    """
    return value if value and is_tenant_code(value) else None


def _usable_id(value: str | None) -> str | None:
    """来源值可用作租户主键时原样返回，否则 None（形态非法等同未提供来源）。

    Args:
        value: 来源值（令牌租户位）。

    Returns:
        str | None: 可用值；缺失或形态非法 None。
    """
    return value if value and is_tenant_id(value) else None


async def resolve_request_tenant(
    *,
    path: str,
    host: str | None = None,
    header: str | None = None,
    token_tenant_id: str | None = None,
    source: TenantLookup | None = None,
    exempt_paths: Iterable[str] = DEFAULT_EXEMPT_PATHS,
    deferred_paths: Iterable[str] = DEFAULT_DEFERRED_PATHS,
    allow_demo_fallback: bool = True,
) -> TenantContext | None:
    """按解析链解析请求租户（子域名 → 请求头 → 令牌租户位）。

    **形态先于取数**：子域名来源经 `tenant_hostname`（IP 字面量 / `localhost` / 非法域名一律 None），
    请求头来源经 `is_tenant_code`、令牌来源经 `is_tenant_id` 校验——形态非法的来源值**等同未提供**
    （不送入租户源），从而不会派生出非法库名、也不会由请求侧脏值触发 5xx。

    Args:
        path: 请求路径（豁免判定）。
        host: Host 头（子域名来源）。
        header: `X-Tenant-ID` 请求头（租户**编码**）。
        token_tenant_id: 令牌内租户主键（雪花 id 字符串；认证阶段写入请求态）。
        source: 租户源（真实查库）；None 时仅内置演示租户可用（未经中间件装配的场景）。
        exempt_paths: 豁免路径集合。
        deferred_paths: 免登录链路延迟解析路径集合（无来源时置空放行，不做演示回落、不硬拒）。
        allow_demo_fallback: 无来源时是否回落演示租户。

    Returns:
        TenantContext | None: 租户上下文；豁免路径为 None；延迟路径无来源且不回落演示租户时为 None。

    Raises:
        TenantNotFoundError: 来源命中但未知租户 / 无来源且不允许回落。
        TenantSuspendedError: 来源命中但租户已停用（由租户源抛出）。
    """
    if is_exempt_path(path, exempt_paths):
        return None
    hostname = tenant_hostname(host)
    for kind, value in (
        ("domain", hostname),
        ("code", _usable_code(header)),
        ("id", _usable_id(token_tenant_id)),
    ):
        if not value:
            continue
        if source is None:
            if kind != "code":
                raise TenantNotFoundError(f"缺少租户源，无法解析令牌租户主键：{value}")
            return _builtin_lookup(value)
        if kind == "domain":
            return await source.by_domain(value)
        if kind == "id":
            return await source.by_id(value)
        return await source.by_code(value)
    if is_deferred_path(path, deferred_paths) and not allow_demo_fallback:
        # 免登录链路（生产）：无来源不硬拒，置空放行由端点层按请求体 / 唯一启用租户解析。
        # 开发 / 测试（allow_demo_fallback=true）沿用演示回落，保持既有本地登录便利。
        return None
    if not allow_demo_fallback:
        raise TenantNotFoundError("未提供租户标识（子域名 / X-Tenant-ID / 令牌）")
    if source is None:
        return DEMO_TENANT
    try:
        return await source.by_code(DEMO_TENANT.code)
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
    if code == DEMO_TENANT.code:
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
        token_tenant_id=state.get("tenant_id"),  # type: ignore[arg-type]
        source=source,
        exempt_paths=settings.tenant.exempt_paths if settings is not None else DEFAULT_EXEMPT_PATHS,
        deferred_paths=settings.tenant.deferred_paths if settings is not None else DEFAULT_DEFERRED_PATHS,
        allow_demo_fallback=settings.tenant.allow_demo_fallback if settings is not None else True,
    )
