"""权限版本与权限缓存键构造（域 `permission`）。

**共享缓存键**（版本号走 Redis / 内存缓存域）：

- 权限版本号：`bms:{租户}:permission:version`（**按租户**计数器，授权 / 角色分配 / 元数据变更后递增）；
- 用户权限缓存（**历史键**，`04-2` 起快照改进程内，键保留供兼容清理与排障）：`bms:{租户}:perm:{用户 ID}:{版本}`。

**进程内三层缓存的键**（`04-2`；不复用 `bms:` 前缀，避免与共享缓存键空间混淆）：

- 层1 用户聚合输入：`{来源}|subject|{租户|global}|{用户}|{版本}`
- 层1 元数据索引：`{来源}|meta|{locale}|{版本}`
- 层2 规则物化结果：`{来源}|rule|{字典类型}|{策略}|{指纹}`
- 层3 用户快照：`{来源}|snapshot|{租户|global}|{用户}|{版本}`

与菜单版本（全局 `bms:global:menu:version`）区分：授权与元数据失效同以**权限版本**为准（`04-2` 起元数据
写路径一并递增权限版本），某租户的授权变更不影响其它租户。
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import cast

from bms_core.cache.base import GLOBAL_TENANT, build_cache_key

PERMISSION_CACHE_DOMAIN = "permission"
"""权限版本缓存域名（键第二段）。"""

PERMISSION_CACHE_BUSINESS_DOMAIN = "perm"
"""用户权限缓存域名（历史键第二段；`04-2` 起快照改进程内）。"""

PERMISSION_VERSION_BUSINESS_KEY = "version"
"""权限版本业务键（键第三段）。"""

SUBJECT_LAYER = "subject"
"""进程内键层级：层1 用户聚合输入。"""

METADATA_LAYER = "meta"
"""进程内键层级：层1 元数据索引。"""

RULE_LAYER = "rule"
"""进程内键层级：层2 规则物化结果。"""

SNAPSHOT_LAYER = "snapshot"
"""进程内键层级：层3 用户快照。"""

RULE_FINGERPRINT_LENGTH = 16
"""规则指纹长度（SHA-1 十六进制前若干位；足够避免同进程内碰撞且便于排障）。"""


def permission_version_key(tenant_id: str | None) -> str:
    """权限版本号键（按租户）。

    Args:
        tenant_id: 租户标识；None 表示全局（兜底）。

    Returns:
        str: `bms:{租户|global}:permission:version`。
    """
    return build_cache_key(
        tenant=tenant_id, domain=PERMISSION_CACHE_DOMAIN, business_key=PERMISSION_VERSION_BUSINESS_KEY
    )


def permission_user_cache_key(tenant_id: str | None, user_id: int | str, version: int) -> str:
    """用户权限缓存键（按租户 + 用户 + 版本；历史键，兼容清理用）。

    Args:
        tenant_id: 租户标识；None 表示全局。
        user_id: 用户主键。
        version: 权限版本号（变更即 +1，旧版本键自然失效）。

    Returns:
        str: `bms:{租户|global}:perm:{用户 ID}:{版本}`。
    """
    return build_cache_key(
        tenant=tenant_id, domain=PERMISSION_CACHE_BUSINESS_DOMAIN, business_key=f"{user_id}:{version}"
    )


def permission_subject_key(source: str, tenant_id: str | None, user_id: int | str, version: int) -> str:
    """层1 用户聚合输入的进程内键。

    Args:
        source: 数据来源标识（`BasePermissionDataSource.key`）。
        tenant_id: 租户标识；None 为全局兜底位。
        user_id: 用户主键。
        version: 权限版本号。

    Returns:
        str: `{来源}|subject|{租户|global}|{用户}|{版本}`。
    """
    return f"{source}|{SUBJECT_LAYER}|{tenant_id or GLOBAL_TENANT}|{user_id}|{version}"


def permission_metadata_key(source: str, locale: str, version: int) -> str:
    """层1 元数据索引的进程内键。

    Args:
        source: 数据来源标识。
        locale: 语言标识。
        version: 权限版本号。

    Returns:
        str: `{来源}|meta|{locale}|{版本}`。
    """
    return f"{source}|{METADATA_LAYER}|{locale}|{version}"


def permission_snapshot_key(source: str, tenant_id: str | None, user_id: int | str, version: int) -> str:
    """层3 用户快照的进程内键。

    Args:
        source: 数据来源标识。
        tenant_id: 租户标识；None 为全局兜底位。
        user_id: 用户主键。
        version: 权限版本号。

    Returns:
        str: `{来源}|snapshot|{租户|global}|{用户}|{版本}`。
    """
    return f"{source}|{SNAPSHOT_LAYER}|{tenant_id or GLOBAL_TENANT}|{user_id}|{version}"


def permission_user_token(source: str, tenant_id: str | None, user_id: int | str) -> str:
    """用户键索引（层1 + 层3 条目按用户聚合，供闲置注销与失效清理）。

    Args:
        source: 数据来源标识。
        tenant_id: 租户标识；None 为全局兜底位。
        user_id: 用户主键。

    Returns:
        str: `{来源}|{租户|global}|{用户}`。
    """
    return f"{source}|{tenant_id or GLOBAL_TENANT}|{user_id}"


def permission_rule_key(*, data_source_key: str, policy_type: str, config: object) -> str | None:
    """层2 规则键（字典类型 + 策略 + `config` 内容指纹；不含用户，故多用户共享一份）。

    指纹按**内容**而非规则行主键计算（中性数据契约不含规则 id）：键排序、集合保序、不可序列化值转
    `str`；规范化失败（含不可序列化对象）返回 None，调用方退化为「不缓存、直接求值」。

    Args:
        data_source_key: 字典类型主键。
        policy_type: 策略类型。
        config: 规则行（`Sequence[Mapping]`，可为基座集合类）。

    Returns:
        str | None: `{字典类型}|{策略}|{指纹}`；无法计算指纹时为 None。
    """
    try:
        payload = json.dumps(_canonical(config), ensure_ascii=False, sort_keys=True, default=str)
    except TypeError, ValueError:
        return None
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:RULE_FINGERPRINT_LENGTH]
    return f"{data_source_key}|{policy_type}|{digest}"


def _canonical(value: object) -> object:
    """把规则行规范化为可稳定序列化的结构（键排序由 `json.dumps(sort_keys=True)` 承担）。

    Args:
        value: 任意值（映射 / 序列 / 标量）。

    Returns:
        object: 规范化值。

    Raises:
        TypeError: 含不可序列化的对象（调用方据此放弃缓存）。
    """
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in cast("Mapping[object, object]", value).items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_canonical(item) for item in cast("Sequence[object]", value)]
    raise TypeError(f"不可规范化的规则值：{type(value).__name__}")


__all__ = [
    "GLOBAL_TENANT",
    "METADATA_LAYER",
    "RULE_LAYER",
    "SNAPSHOT_LAYER",
    "SUBJECT_LAYER",
    "permission_metadata_key",
    "permission_rule_key",
    "permission_snapshot_key",
    "permission_subject_key",
    "permission_user_cache_key",
    "permission_user_token",
    "permission_version_key",
]
