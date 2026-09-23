"""数据源键与库名单一来源（06_01 每服务每租户建库与路由）。

- **键形态**（两种，同前缀）：
  - **相对键**：`platform`（本服务平台库）、`tenant_{code}`（本服务的该租户库）——缺省补**当前服务**；
  - **全限定键**：`platform_{service}`、`tenant_{service}_{code}`——显式指向某服务，用于越界判定与运维跨服务；
  - 归档库键 `archive` 为单键（架构定 `bms_archive` 统一收存，不服务化）。
- **反解歧义消解**：`tenant_` 之后按 `_` 切分，**首段命中已知服务标识即视为全限定键**（服务段 = 首段、
  其余为租户编码）；否则整体为租户编码（相对键）。服务标识集合取自归属登记（`known_service_keys`，
  懒导入避免 db ← services 的导入期耦合）。
- **库名单一来源**：平台服务库 `bms_{service}`、服务租户库 `bms_{service}_{code}`、归档库 `bms_archive`
  （生成连接串的 `{database}` 占位与 `ops` 建库目标均经此派生）。
- **归属校验**：`resolve_db_key` 在语法解析之上判定服务归属——全限定键服务段非当前服务且未豁免时抛
  `DataOwnershipError`（10008，数据所有权）；**相对键恒属当前服务**。运维侧（`ops`）经
  `allow_cross_service=True` 显式豁免（仅放宽归属，不放宽键形态合法性）。
- 严格禁止在业务代码里拼接库键或库名：一律经本模块派生（见《后端开发规范》「模块边界与数据所有权」节）。
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import ConfigError, DataOwnershipError

__all__ = [
    "ARCHIVE_DATABASE",
    "ARCHIVE_DB_KEY",
    "DB_KEY_KINDS",
    "DB_KIND_ARCHIVE",
    "DB_KIND_PLATFORM",
    "DB_KIND_TENANT",
    "PLATFORM_DB_KEY",
    "PLATFORM_DB_KEY_PREFIX",
    "PLATFORM_SERVICE_KEY",
    "TENANT_DB_KEY_PREFIX",
    "DbKey",
    "build_platform_db_key",
    "build_tenant_db_key",
    "database_name",
    "parse_db_key",
    "platform_database_name",
    "resolve_db_key",
    "tenant_database_name",
]

PLATFORM_SERVICE_KEY = "platform"
"""平台服务标识（服务目录中的 `service_key`；与平台库相对键同字面）。"""

PLATFORM_DB_KEY = "platform"
"""平台库**相对键**（本服务平台库；`db/engine.py` re-export）。"""

PLATFORM_DB_KEY_PREFIX = "platform_"
"""平台库**全限定键**前缀（`platform_{service}`）。"""

TENANT_DB_KEY_PREFIX = "tenant_"
"""租户库键前缀（相对键 `tenant_{code}` 与全限定键 `tenant_{service}_{code}` 共用）。"""

ARCHIVE_DB_KEY = "archive"
"""归档库键（不服务化，架构定统一收存）。"""

ARCHIVE_DATABASE = "bms_archive"
"""归档库名。"""

DB_KIND_PLATFORM = "platform"
"""库类别：平台服务库。"""

DB_KIND_TENANT = "tenant"
"""库类别：服务租户库。"""

DB_KIND_ARCHIVE = "archive"
"""库类别：归档库。"""

DB_KEY_KINDS: frozenset[str] = frozenset({DB_KIND_PLATFORM, DB_KIND_TENANT, DB_KIND_ARCHIVE})
"""合法库类别集合。"""

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
"""库名 / 模式名合法形态（与 `db/admin.py` 同口径：防拼接注入、长度限 63 字符）。"""


@dataclass(frozen=True)
class DbKey(BaseObject):
    """数据源键解析结果（键原文 / 库类别 / 服务段 / 租户编码）。"""

    raw: str
    """键原文（用于错误信息与缓存键）。"""

    kind: str
    """库类别（`platform` / `tenant` / `archive`）。"""

    service: str | None = None
    """全限定键的服务段；相对键（`platform` / `tenant_{code}`）为 `None`。"""

    tenant_code: str | None = None
    """租户编码（`kind == tenant` 时必有）。"""

    @property
    def is_qualified(self) -> bool:
        """是否全限定键（显式带服务段）。

        Returns:
            bool: 全限定键 True。
        """
        return self.service is not None


@lru_cache(maxsize=1)
def _known_service_keys() -> frozenset[str]:
    """已知服务标识集合（归属登记导出；懒导入避免 db ← services 导入期耦合）。

    Returns:
        frozenset[str]: 服务标识集合。
    """
    from bms_core.services.table_registry import known_service_keys

    return known_service_keys()


def build_platform_db_key(service: str | None = None) -> str:
    """构造平台库键（`service` 为空取相对键）。

    Args:
        service: 目标服务标识；`None` / 空串表示本服务平台库。

    Returns:
        str: 平台库键（`platform` 或 `platform_{service}`）。
    """
    return PLATFORM_DB_KEY if not service else f"{PLATFORM_DB_KEY_PREFIX}{service}"


def build_tenant_db_key(code: str, *, service: str | None = None) -> str:
    """构造租户库键（`service` 为空取相对键）。

    Args:
        code: 租户编码（全小写）。
        service: 目标服务标识；`None` / 空串表示本服务的该租户库。

    Returns:
        str: 租户库键（`tenant_{code}` 或 `tenant_{service}_{code}`）。

    Raises:
        ConfigError: 租户编码为空。
    """
    if not code:
        raise ConfigError("租户编码不得为空（租户库键形如 tenant_{code}）")
    return f"{TENANT_DB_KEY_PREFIX}{code}" if not service else f"{TENANT_DB_KEY_PREFIX}{service}_{code}"


def parse_db_key(db_key: str) -> DbKey:
    """按语法解析数据源键（**不做归属校验**，归属判定见 `resolve_db_key`）。

    Args:
        db_key: 数据源键。

    Returns:
        DbKey: 解析结果。

    Raises:
        ConfigError: 键为空或非三种合法形态。
    """
    raw = db_key.strip()
    if not raw:
        raise ConfigError("数据源键不得为空")
    if raw == ARCHIVE_DB_KEY:
        return DbKey(raw=raw, kind=DB_KIND_ARCHIVE)
    if raw == PLATFORM_DB_KEY:
        return DbKey(raw=raw, kind=DB_KIND_PLATFORM)
    if raw.startswith(PLATFORM_DB_KEY_PREFIX):
        service = raw[len(PLATFORM_DB_KEY_PREFIX) :]
        if not service:
            raise ConfigError(f"平台库全限定键缺少服务标识：{db_key}（应为 platform_{{service}}）")
        return DbKey(raw=raw, kind=DB_KIND_PLATFORM, service=service)
    if raw.startswith(TENANT_DB_KEY_PREFIX):
        rest = raw[len(TENANT_DB_KEY_PREFIX) :]
        if not rest:
            raise ConfigError(f"租户库键缺少编码：{db_key}（应为 tenant_{{code}} 或 tenant_{{service}}_{{code}}）")
        head, separator, tail = rest.partition("_")
        if separator and tail and head in _known_service_keys():
            return DbKey(raw=raw, kind=DB_KIND_TENANT, service=head, tenant_code=tail)
        return DbKey(raw=raw, kind=DB_KIND_TENANT, tenant_code=rest)
    raise ConfigError(
        f"非法的数据源键：{db_key}（允许 platform / platform_{{service}} / tenant_{{code}} / "
        f"tenant_{{service}}_{{code}} / archive）"
    )


def platform_database_name(service: str) -> str:
    """平台服务库名（`bms_{service}`）。

    Args:
        service: 服务标识。

    Returns:
        str: 平台服务库名。

    Raises:
        ConfigError: 服务标识为空或库名形态非法。
    """
    return _checked_database_name(f"bms_{service}", service=service)


def tenant_database_name(service: str, code: str) -> str:
    """服务租户库名（`bms_{service}_{code}`）。

    Args:
        service: 服务标识。
        code: 租户编码。

    Returns:
        str: 服务租户库名。

    Raises:
        ConfigError: 服务标识 / 租户编码为空或库名形态非法。
    """
    if not code:
        raise ConfigError("租户编码不得为空（服务租户库名形如 bms_{service}_{tenant}）")
    return _checked_database_name(f"bms_{service}_{code}", service=service)


def database_name(key: DbKey, *, service: str) -> str:
    """按库键取库名（相对键用传入的当前服务补全服务段）。

    Args:
        key: 库键解析结果。
        service: 当前服务标识（相对键补全用）。

    Returns:
        str: 库名（`bms_{service}` / `bms_{service}_{code}` / `bms_archive`）。

    Raises:
        ConfigError: 相对键缺当前服务标识或库名形态非法。
    """
    if key.kind == DB_KIND_ARCHIVE:
        return ARCHIVE_DATABASE
    effective = key.service or service
    if not effective:
        raise ConfigError(
            f"数据源键 {key.raw} 为相对键，派生库名需要服务标识："
            "请配置 [app].service（服务包声明回写）或改用全限定键 platform_{service} / tenant_{service}_{code}"
        )
    if key.kind == DB_KIND_PLATFORM:
        return platform_database_name(effective)
    return tenant_database_name(effective, key.tenant_code or "")


def resolve_db_key(db_key: str, *, service: str, allow_cross_service: bool = False) -> DbKey:
    """解析数据源键并校验服务归属（取引擎入口的统一前置）。

    Args:
        db_key: 数据源键。
        service: 当前服务标识（相对键归属方）。
        allow_cross_service: 是否允许跨服务键（**仅运维通道**使用；`False` 时越界即拒）。

    Returns:
        DbKey: 解析结果。

    Raises:
        ConfigError: 键形态非法或全限定键的服务标识未登记。
        DataOwnershipError: 全限定键服务段非当前服务且未开启跨服务豁免（10008）。
    """
    key = parse_db_key(db_key)
    if key.service is None:
        return key
    if key.service not in _known_service_keys():
        raise ConfigError(f"数据源键 {db_key} 的服务标识未登记：{key.service}")
    if key.service != service and not allow_cross_service:
        raise DataOwnershipError(
            f"禁止访问他服务数据库：键 {db_key} 归属服务 {key.service}，当前服务 {service or '未声明'}"
        )
    return key


def _checked_database_name(name: str, *, service: str) -> str:
    """校验库名形态（防拼接注入；与 `db/admin.py` 同口径）。

    Args:
        name: 待校验库名。
        service: 服务标识（错误信息用）。

    Returns:
        str: 校验通过的库名。

    Raises:
        ConfigError: 服务标识为空或库名形态非法。
    """
    if not service:
        raise ConfigError("服务标识不得为空（库名形如 bms_{service} / bms_{service}_{tenant}）")
    if not _IDENTIFIER_RE.match(name):
        raise ConfigError(f"库名形态非法：{name}（须以字母或下划线开头、仅字母数字下划线、长度 ≤ 63）")
    return name
