"""权限三层进程内缓存仓（域 `permission`，需求 07-16 / 子任务 04-2）。

判定是每个接口、每次数据增删改查的必经路径，故三层缓存**全部在进程内单份**，不落 Redis 共享
（序列化与网络延迟不可接受）；一致性经**权限版本号**异步对齐——使用前查最新版本号，版本 +1 即换键失效：

1. **层1 基础数据**：用户聚合输入（角色 / 类型 / 授权行 / 数据范围规则 / 字段收窄）按
   「来源 + 租户 + 用户 + 权限版本」、元数据索引（菜单→表单、权限码 id→码）按「来源 + locale + 权限版本」；
2. **层2 规则物化**：数据范围规则求值结果按「字典类型 + 策略 + `config` 指纹」键控——键不含用户，
   同一规则被 N 个用户命中只有一份（集合经 `04-3` 去重物化为 `ConcurrentStableSet`）；
3. **层3 用户快照**：`PermissionSnapshot` 按「来源 + 租户 + 用户 + 权限版本」，仅活动用户持有——
   读写刷新最近活动时间，巡检任务按 `idle_timeout` 注销闲置快照（`sweep_idle`）。

**护栏**：三层各自条目上限 + 层2 元素总量预算（防单条大集合撑爆内存）。上限与 TTL 全经
`[permission].options` 配置（见 `OPTION_*` 常量），缺省保守。

**集合物化（`04-3`）**：层2 除条目与元素账目外，另维护**规则引用计数**（某规则当前被多少个层3 快照
持有）与**估算字节**——快照只持规则引用，集合本身按规则共享一份；淘汰时先回收最久未用的零引用规则，
全部被引用才退化为 LRU（后续命中重算）。元素按条件承载的**值元素总数**计量（`in` 集合大小 /
`between` 计 2 / 标量计 1），大集合不再被「一条只算 1」的旧口径漏算；`stats()` 输出集合条数 / 元素数 /
估算字节 / 被引用规则数 / 淘汰与超阈计数 / 各层上限，供运维判断是否接近上限。

**单份与隔离**：`current_permission_cache_store()` 返回进程内唯一实例（与数据来源注册表、插件注册表同构）；
`configure_permission_cache_store` 供校验器装配期按配置重建，`reset_permission_cache_store` 供用例隔离。
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Mapping, Sized
from threading import Lock
from time import monotonic
from typing import cast

from bms_core.cache.base import GLOBAL_TENANT
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject
from bms_core.permission.snapshot import PermissionSnapshot
from bms_core.permission.sources import PermissionMetadata, PermissionSubjectData
from bms_core.permission.version import (
    SUBJECT_LAYER,
    permission_metadata_key,
    permission_rule_key,
    permission_snapshot_key,
    permission_subject_key,
    permission_user_token,
)

_logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_TTL_SECONDS = 300
"""层1 用户条目与层3 快照的缺省 TTL（秒；与 `[permission].options.snapshot_ttl_seconds` 同源）。"""

DEFAULT_SNAPSHOT_CACHE_MAX_ITEMS = 5000
"""层3 用户快照条目上限（LRU）。"""

DEFAULT_SUBJECT_CACHE_MAX_ITEMS = 2000
"""层1 用户聚合输入条目上限（LRU）。"""

DEFAULT_METADATA_CACHE_MAX_ITEMS = 16
"""层1 元数据索引条目上限（按 locale 各一份，额度很小）。"""

DEFAULT_RULE_CACHE_MAX_ITEMS = 1000
"""层2 规则物化条目上限（LRU）。"""

DEFAULT_RULE_CACHE_MAX_ELEMENTS = 200_000
"""层2 元素总量预算（防单条大集合撑爆内存；超限淘汰最久未用规则并上报）。"""

RULE_ENTRY_OVERHEAD_BYTES = 256
"""每条层2 规则条目的估算固定开销（字节：键 + 条件对象 + 账目槽位）。"""

RULE_ELEMENT_BYTES = 48
"""每个值元素的估算字节（字符串 / 整数均摊 + 集合槽位）。"""

DEFAULT_METADATA_CACHE_TTL = 3600
"""层1 元数据索引 TTL（秒；元数据已由权限版本换键 + 写路径主动清理，TTL 只作兜底）。"""

DEFAULT_IDLE_TIMEOUT = 1800
"""活动用户闲置注销阈值（秒；30 分钟不活动即注销其快照）。"""

DEFAULT_IDLE_SWEEP_INTERVAL = 60
"""闲置注销巡检周期（秒）。"""

OPTION_SNAPSHOT_TTL = "snapshot_ttl_seconds"
OPTION_SNAPSHOT_CACHE_MAX_ITEMS = "snapshot_cache_max_items"
OPTION_SUBJECT_CACHE_MAX_ITEMS = "subject_cache_max_items"
OPTION_METADATA_CACHE_MAX_ITEMS = "metadata_cache_max_items"
OPTION_METADATA_CACHE_TTL = "metadata_cache_ttl_seconds"
OPTION_RULE_CACHE_MAX_ITEMS = "rule_cache_max_items"
OPTION_RULE_CACHE_MAX_ELEMENTS = "rule_cache_max_elements"
OPTION_IDLE_TIMEOUT = "idle_timeout_seconds"
OPTION_IDLE_SWEEP_INTERVAL = "idle_sweep_seconds"
"""`[permission].options` 的缓存键名（全部可选；缺省取本模块常量）。"""


def _layer_of(key: str) -> str:
    """取进程内键的层级段（`{来源}|{层}|…`）。

    Args:
        key: 进程内键。

    Returns:
        str: 层级段。
    """
    return key.split("|", 2)[1]


def _rule_fingerprint(key: str) -> str:
    """取层2 完整键的规则键段（`{来源}|rule|{规则键}` → `{规则键}`）。

    引用计数以规则键（指纹）为单位登记（快照侧推导时不知来源），故与层2 完整键对齐时
    取该尾段。

    Args:
        key: 层2 完整键。

    Returns:
        str: 规则键（含字典类型 / 策略 / 指纹）。
    """
    return key.split("|", 2)[2]


def int_option(options: object, key: str, default: int) -> int:
    """读整数选项（缺项 / 类型不符时回落缺省；布尔不算整数）。

    参数按 `object` 接收：调用方既可能传内建映射，也可能传基座集合类（`ConcurrentStableDict`）。

    Args:
        options: 选项容器（映射形态）。
        key: 选项键。
        default: 缺省值。

    Returns:
        int: 选项值。
    """
    if not isinstance(options, Mapping):
        return default
    raw = cast("Mapping[str, object]", options).get(key)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    return default


class _Layer(BaseFrameworkObject):
    """单层 LRU + TTL 容器（进程内；**调用方持锁**，本类不加锁）。"""

    def __init__(self, *, name: str, max_items: int, ttl: int) -> None:
        """初始化。

        Args:
            name: 层名（日志与排障用）。
            max_items: 条目上限（LRU 淘汰；最小 1）。
            ttl: 有效期（秒；<= 0 表示不过期）。
        """
        self.name = name
        self.max_items = max(1, max_items)
        self.ttl = max(0, ttl)
        self.items: OrderedDict[str, tuple[object, float | None]] = OrderedDict()

    def get(self, key: str, now: float) -> object | None:
        """读条目（过期即删；命中刷新 LRU 顺序）。

        Args:
            key: 条目键。
            now: 当前时刻（`monotonic`）。

        Returns:
            object | None: 条目值；未命中 / 过期返回 None。
        """
        entry = self.items.get(key)
        if entry is None:
            return None
        value, expires = entry
        if expires is not None and expires <= now:
            del self.items[key]
            return None
        self.items.move_to_end(key)
        return value

    def put(self, key: str, value: object, now: float) -> None:
        """写条目（**不做容量收敛**；供调用方按自身策略淘汰）。

        Args:
            key: 条目键。
            value: 条目值。
            now: 当前时刻（`monotonic`）。
        """
        expires = now + self.ttl if self.ttl > 0 else None
        self.items[key] = (value, expires)
        self.items.move_to_end(key)

    def holds(self, key: str) -> bool:
        """条目是否存在（不判 TTL；供调用方区分「未命中」与「刚过期」）。

        Args:
            key: 条目键。

        Returns:
            bool: 存在为 True。
        """
        return key in self.items

    def set(self, key: str, value: object, now: float) -> ConcurrentStableList[str]:
        """写条目（超上限按 LRU 淘汰）。

        Args:
            key: 条目键。
            value: 条目值。
            now: 当前时刻（`monotonic`）。

        Returns:
            ConcurrentStableList[str]: 因超上限被淘汰的键（供调用方同步账目）。
        """
        self.put(key, value, now)
        evicted: ConcurrentStableList[str] = ConcurrentStableList()
        while len(self.items) > self.max_items:
            oldest, _ = self.items.popitem(last=False)
            evicted.add(oldest)
        return evicted

    def delete(self, key: str) -> bool:
        """删除条目。

        Args:
            key: 条目键。

        Returns:
            bool: 删到为 True。
        """
        return self.items.pop(key, None) is not None

    def clear(self) -> int:
        """清空本层。

        Returns:
            int: 清理条数。
        """
        count = len(self.items)
        self.items.clear()
        return count

    def __len__(self) -> int:
        """当前条目数。

        Returns:
            int: 条目数。
        """
        return len(self.items)


class PermissionCacheStore(BaseFrameworkObject):
    """三层进程内缓存仓：限额 / TTL / 活动时间 / 元素预算 / 闲置注销。"""

    def __init__(
        self,
        *,
        snapshot_ttl: int = DEFAULT_SNAPSHOT_TTL_SECONDS,
        subject_max_items: int = DEFAULT_SUBJECT_CACHE_MAX_ITEMS,
        metadata_max_items: int = DEFAULT_METADATA_CACHE_MAX_ITEMS,
        metadata_ttl: int = DEFAULT_METADATA_CACHE_TTL,
        rule_max_items: int = DEFAULT_RULE_CACHE_MAX_ITEMS,
        rule_max_elements: int = DEFAULT_RULE_CACHE_MAX_ELEMENTS,
        snapshot_max_items: int = DEFAULT_SNAPSHOT_CACHE_MAX_ITEMS,
    ) -> None:
        """初始化。

        Args:
            snapshot_ttl: 层1 用户条目与层3 快照 TTL（秒）。
            subject_max_items: 层1 用户条目上限。
            metadata_max_items: 层1 元数据条目上限。
            metadata_ttl: 层1 元数据 TTL（秒）。
            rule_max_items: 层2 条目上限。
            rule_max_elements: 层2 元素总量预算。
            snapshot_max_items: 层3 条目上限。
        """
        self._max_elements = max(0, rule_max_elements)
        self._subjects = _Layer(name="subject", max_items=subject_max_items, ttl=snapshot_ttl)
        self._metadata = _Layer(name="metadata", max_items=metadata_max_items, ttl=metadata_ttl)
        self._rules = _Layer(name="rule", max_items=rule_max_items, ttl=snapshot_ttl)
        self._snapshots = _Layer(name="snapshot", max_items=snapshot_max_items, ttl=snapshot_ttl)
        self._activity: ConcurrentStableDict[str, float] = ConcurrentStableDict()
        self._user_keys: ConcurrentStableDict[str, ConcurrentStableSet[str]] = ConcurrentStableDict()
        self._rule_elements: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        self._rule_bytes: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        self._rule_refs: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        self._snapshot_rules: ConcurrentStableDict[str, ConcurrentStableList[str]] = ConcurrentStableDict()
        self._rule_total = 0
        self._rule_bytes_total = 0
        self._rule_evicted_total = 0
        self._oversized_rejections = 0
        self._lock = Lock()

    # ------------------------------------------------------------------ 内部

    def _keys_for(self, token: str) -> ConcurrentStableSet[str]:
        """取（或新建）用户键索引（调用方持锁）。

        Args:
            token: 用户键索引（`来源|租户|用户`）。

        Returns:
            ConcurrentStableSet[str]: 该用户名下的条目键集合。
        """
        keys = self._user_keys.get(token)
        if keys is None:
            created: ConcurrentStableSet[str] = ConcurrentStableSet()
            self._user_keys.set(token, created)
            return created
        return keys

    def _drop_user(self, token: str) -> int:
        """注销一个用户键索引下的全部条目（调用方持锁）。

        Args:
            token: 用户键索引。

        Returns:
            int: 清理条目数。
        """
        keys = self._user_keys.get(token)
        remaining: ConcurrentStableSet[str] = keys if keys is not None else ConcurrentStableSet()
        self._user_keys.delete(token)
        if token in self._activity:  # 仅层1 有条目（尚未算过快照）的用户没有活动记录
            self._activity.delete(token)
        removed = len(remaining)
        for key in remaining:
            self._subjects.delete(key)
            self._snapshots.delete(key)
            self._release_snapshot(key)
        return removed

    def _release_snapshot(self, key: str) -> None:
        """释放一个层3 条目持有的规则引用（调用方持锁；无引用记录即无操作）。

        Args:
            key: 层3 快照键。
        """
        rules = self._snapshot_rules.get(key)
        if rules is None:
            return
        self._snapshot_rules.delete(key)
        for rule_key in rules:
            remaining = (self._rule_refs.get(rule_key) or 0) - 1
            if remaining > 0:
                self._rule_refs.set(rule_key, remaining)
            else:
                self._rule_refs.pop(rule_key, None)

    def _retain_rules(self, key: str, snapshot: PermissionSnapshot) -> None:
        """登记某快照持有的规则引用（调用方持锁）。

        规则键由快照行（`data_source_key` / `policy_type` / `config`）推导，与层2 键控同源；行不是
        映射 / 缺策略类型 / 指纹不可算（`config` 含不可序列化值）时跳过——这些规则本就不进层2。

        Args:
            key: 层3 快照键。
            snapshot: 用户权限快照。
        """
        rule_keys: ConcurrentStableSet[str] = ConcurrentStableSet()
        for row in snapshot.data_scopes:
            policy_type = row.get("policy_type")
            if not isinstance(policy_type, str) or not policy_type:
                continue
            rule_key = permission_rule_key(
                data_source_key=str(row.get("data_source_key", "")),
                policy_type=policy_type,
                config=row.get("config"),
            )
            if rule_key is not None:
                rule_keys.add(rule_key)
        if not len(rule_keys):
            return
        keys = ConcurrentStableList[str](rule_keys)
        self._snapshot_rules.set(key, keys)
        for rule_key in keys:
            self._rule_refs.set(rule_key, (self._rule_refs.get(rule_key) or 0) + 1)

    def _matches(self, token: str, source: str | None) -> bool:
        """判定键索引是否属于指定来源（None 视为全部来源）。

        Args:
            token: 用户键索引（`来源|租户|用户`）。
            source: 数据来源标识；None 表示不限。

        Returns:
            bool: 匹配为 True。
        """
        return source is None or token.startswith(f"{source}|")

    # ------------------------------------------------------------------ 层1

    def get_subject(
        self, *, source: str, tenant_id: str | None, user_id: int, version: int
    ) -> PermissionSubjectData | None:
        """读层1 用户聚合输入（版本已含在键内，命中即同版本）。

        Args:
            source: 数据来源标识。
            tenant_id: 租户标识；None 为全局兜底位。
            user_id: 用户主键。
            version: 权限版本号。

        Returns:
            PermissionSubjectData | None: 聚合输入；未命中为 None。
        """
        key = permission_subject_key(source, tenant_id, user_id, version)
        with self._lock:
            value = self._subjects.get(key, monotonic())
        return cast("PermissionSubjectData | None", value)

    def set_subject(
        self, *, source: str, tenant_id: str | None, user_id: int, version: int, value: PermissionSubjectData
    ) -> None:
        """写层1 用户聚合输入（并登记该用户键索引，供闲置注销与失效清理）。

        Args:
            source: 数据来源标识。
            tenant_id: 租户标识；None 为全局兜底位。
            user_id: 用户主键。
            version: 权限版本号。
            value: 聚合输入。
        """
        key = permission_subject_key(source, tenant_id, user_id, version)
        token = permission_user_token(source, tenant_id, user_id)
        with self._lock:
            self._subjects.set(key, value, monotonic())
            self._keys_for(token).add(key)

    def get_metadata(self, *, source: str, locale: str, version: int) -> PermissionMetadata | None:
        """读层1 元数据索引（按来源 + locale + 权限版本）。

        Args:
            source: 数据来源标识。
            locale: 语言标识。
            version: 权限版本号。

        Returns:
            PermissionMetadata | None: 元数据索引；未命中为 None。
        """
        key = permission_metadata_key(source, locale, version)
        with self._lock:
            value = self._metadata.get(key, monotonic())
        return cast("PermissionMetadata | None", value)

    def set_metadata(self, *, source: str, locale: str, version: int, value: PermissionMetadata) -> None:
        """写层1 元数据索引。

        Args:
            source: 数据来源标识。
            locale: 语言标识。
            version: 权限版本号。
            value: 元数据索引。
        """
        key = permission_metadata_key(source, locale, version)
        with self._lock:
            self._metadata.set(key, value, monotonic())

    # ------------------------------------------------------------------ 层2

    def get_rule(self, *, source: str, rule_key: str) -> object | None:
        """读层2 规则求值结果（键已含字典类型 / 策略 / 指纹）。

        Args:
            source: 归属标识（`rbac`）。
            rule_key: 规则键（`permission_rule_key` 产物）。

        Returns:
            object | None: 求值结果（条件列表）；未命中为 None。
        """
        key = self._rule_full_key(source, rule_key)
        with self._lock:
            had = self._rules.holds(key)
            value = self._rules.get(key, monotonic())
            if value is None and had:  # TTL 过期：条目已删，账目一并回冲
                self._forget_rule_accounts(key)
        return value

    def set_rule(self, *, source: str, rule_key: str, value: object, elements: int | None = None) -> None:
        """写层2 规则求值结果（超条目上限或元素预算即按「零引用优先」淘汰并上报）。

        单条超预算的规则不会被缓存（写入即在同一轮收敛中出队），保证内存不被一条大集合撑爆。

        Args:
            source: 归属标识（`rbac`）。
            rule_key: 规则键（`permission_rule_key` 产物）。
            value: 求值结果（条件列表）。
            elements: 该规则承载的**值元素总数**（None 退化为条件条数）。
        """
        key = self._rule_full_key(source, rule_key)
        weight = len(cast("Sized", value)) if elements is None else max(0, elements)
        with self._lock:
            if self._max_elements <= 0:  # 预算置 0：不缓存规则结果
                return
            self._drop_rule_entry(key)  # 同键覆盖：先冲掉旧账（键不存在即无操作）
            self._rules.put(key, value, monotonic())
            self._rule_elements.set(key, weight)
            self._rule_bytes.set(key, RULE_ENTRY_OVERHEAD_BYTES + weight * RULE_ELEMENT_BYTES)
            self._rule_total += weight
            self._rule_bytes_total += RULE_ENTRY_OVERHEAD_BYTES + weight * RULE_ELEMENT_BYTES
            self._trim_rules(key)

    def record_oversized_rule(self) -> None:
        """累计一次「大集合 `in` 超阈拒绝」（数据范围 provider 调用；供 `stats()` 观测）。"""
        with self._lock:
            self._oversized_rejections += 1

    def _rule_full_key(self, source: str, rule_key: str) -> str:
        """层2 进程内完整键。

        Args:
            source: 归属标识。
            rule_key: 规则键。

        Returns:
            str: `{来源}|rule|{规则键}`。
        """
        return f"{source}|rule|{rule_key}"

    def _forget_rule_accounts(self, key: str) -> None:
        """回冲某条规则的元素 / 字节账目（调用方持锁）。

        Args:
            key: 层2 完整键。
        """
        self._rule_total -= cast("int", self._rule_elements.pop(key, 0))
        self._rule_bytes_total -= cast("int", self._rule_bytes.pop(key, 0))

    def _drop_rule_entry(self, key: str) -> bool:
        """移除层2 条目并回冲账目（调用方持锁）。

        Args:
            key: 层2 完整键。

        Returns:
            bool: 移除为 True；键不存在为 False。
        """
        if not self._rules.holds(key):
            return False
        self._rules.delete(key)
        self._forget_rule_accounts(key)
        return True

    def _trim_rules(self, keep: str) -> None:
        """收敛层2 容量：先淘汰最久未用的零引用规则，全部被引用才退化为 LRU（调用方持锁）。

        Args:
            keep: 本次刚写入的规则键（容量够时优先保留，避免写完即淘汰）。
        """
        dropped = 0
        while len(self._rules) > self._rules.max_items or self._rule_total > self._max_elements:
            self._drop_rule_entry(self._pick_rule_victim(keep))
            dropped += 1
        if dropped:
            self._rule_evicted_total += dropped
            _logger.warning(
                "权限规则缓存超限，淘汰规则 %s 条（条目上限 %s / 元素预算 %s）",
                dropped,
                self._rules.max_items,
                self._max_elements,
            )

    def _pick_rule_victim(self, keep: str) -> str:
        """取淘汰候选：最久未用的零引用规则（跳过本次写入者）；退化为最久未用规则。

        Args:
            keep: 本次刚写入的规则键。

        Returns:
            str: 层2 完整键（调用时层2 必非空）。
        """
        for key in self._rules.items:
            if key != keep and _rule_fingerprint(key) not in self._rule_refs:
                return key
        return next(iter(self._rules.items.items()))[0]

    # ------------------------------------------------------------------ 层3

    def get_snapshot(
        self, *, source: str, tenant_id: str | None, user_id: int, version: int
    ) -> PermissionSnapshot | None:
        """读层3 用户快照（命中即刷新该用户活动时间）。

        Args:
            source: 数据来源标识。
            tenant_id: 租户标识；None 为全局兜底位。
            user_id: 用户主键。
            version: 权限版本号。

        Returns:
            PermissionSnapshot | None: 快照；未命中为 None。
        """
        key = permission_snapshot_key(source, tenant_id, user_id, version)
        token = permission_user_token(source, tenant_id, user_id)
        now = monotonic()
        with self._lock:
            had = self._snapshots.holds(key)
            value = self._snapshots.get(key, now)
            if value is None:
                if had:  # TTL 过期：条目已删，释放其持有的规则引用
                    self._release_snapshot(key)
                return None
            self._activity.set(token, now)
            self._keys_for(token).add(key)
        return cast("PermissionSnapshot", value)

    def set_snapshot(
        self, *, source: str, tenant_id: str | None, user_id: int, version: int, value: PermissionSnapshot
    ) -> None:
        """写层3 用户快照（记录活动时间、用户键索引与规则引用）。

        Args:
            source: 数据来源标识。
            tenant_id: 租户标识；None 为全局兜底位。
            user_id: 用户主键。
            version: 权限版本号。
            value: 用户权限快照。
        """
        key = permission_snapshot_key(source, tenant_id, user_id, version)
        token = permission_user_token(source, tenant_id, user_id)
        now = monotonic()
        with self._lock:
            self._release_snapshot(key)  # 同键覆盖（版本回退 / 重算回填）：先释放旧引用
            for evicted in self._snapshots.set(key, value, now):
                self._release_snapshot(evicted)
            self._activity.set(token, now)
            self._keys_for(token).add(key)
            self._retain_rules(key, value)

    # ------------------------------------------------------------------ 维护

    def invalidate_user(self, *, tenant_id: str | None, user_id: int, source: str | None = None) -> int:
        """注销指定用户在本进程的层1 用户条目与层3 快照（版本 +1 之外的内存回收）。

        Args:
            tenant_id: 租户标识；None 为全局兜底位。
            user_id: 用户主键。
            source: 数据来源标识；None 表示清理该用户在所有来源下的条目。

        Returns:
            int: 清理条目数。
        """
        suffix = f"|{tenant_id or GLOBAL_TENANT}|{user_id}"
        with self._lock:
            tokens: ConcurrentStableList[str] = ConcurrentStableList()
            for token in self._user_keys:
                if token.endswith(suffix) and self._matches(token, source):
                    tokens.add(token)
            total = 0
            for token in tokens:
                total += self._drop_user(token)
            return total

    def invalidate_metadata(self) -> int:
        """清空层1 元数据索引（元数据变更即时生效 + 释放旧版本键）。

        Returns:
            int: 清理条目数。
        """
        with self._lock:
            return self._metadata.clear()

    def clear_snapshots(self) -> int:
        """清空层3 快照（租户级失效后释放内存；层1 用户条目保留）。

        Returns:
            int: 清理条目数。
        """
        with self._lock:
            count = self._snapshots.clear()
            for key in list(self._snapshot_rules.keys()):
                self._release_snapshot(key)
            for token, keys in list(self._user_keys.items()):
                remaining: ConcurrentStableSet[str] = ConcurrentStableSet()
                for key in keys:
                    if _layer_of(key) == SUBJECT_LAYER:
                        remaining.add(key)
                if len(remaining):
                    self._user_keys.set(token, remaining)
                else:
                    self._user_keys.delete(token)
                    self._activity.delete(token)  # 仅快照用户必有活动记录（set/get 快照同时登记）
            return count

    def sweep_idle(self, idle_seconds: int, *, now: float | None = None) -> int:
        """注销超过 `idle_seconds` 未活动的用户快照与层1 用户条目。

        Args:
            idle_seconds: 闲置阈值（秒）；<= 0 表示不注销。
            now: 当前时刻（`monotonic`；缺省取系统时钟，用例可注入）。

        Returns:
            int: 注销的用户数。
        """
        if idle_seconds <= 0:
            return 0
        current = monotonic() if now is None else now
        with self._lock:
            tokens: ConcurrentStableList[str] = ConcurrentStableList()
            for token, last in self._activity.items():
                if current - last >= idle_seconds:
                    tokens.add(token)
            for token in tokens:
                self._drop_user(token)
        return len(tokens)

    def stats(self) -> ConcurrentStableDict[str, int]:
        """取三层条目数 / 规则元素与内存度量（运维观测 / 用例断言）。

        规则层指标：`rule_items`（集合条数）、`rule_elements`（值元素总数）、`rule_estimated_bytes`
        （估算内存）、`rule_refs`（被快照引用的规则数）、`rule_evicted_total`（累计淘汰条数）、
        `oversized_rejections`（大集合超阈拒绝次数）；末尾附各层上限，供判断是否接近容量。

        Returns:
            ConcurrentStableDict[str, int]: 三层条目数、规则度量、超阈计数与各层上限。
        """
        with self._lock:
            result: ConcurrentStableDict[str, int] = ConcurrentStableDict()
            result.set("subject_items", len(self._subjects))
            result.set("metadata_items", len(self._metadata))
            result.set("rule_items", len(self._rules))
            result.set("rule_elements", self._rule_total)
            result.set("rule_estimated_bytes", self._rule_bytes_total)
            result.set("rule_refs", len(self._rule_refs))
            result.set("rule_evicted_total", self._rule_evicted_total)
            result.set("oversized_rejections", self._oversized_rejections)
            result.set("snapshot_items", len(self._snapshots))
            result.set("active_users", len(self._activity))
            result.set("subject_max_items", self._subjects.max_items)
            result.set("metadata_max_items", self._metadata.max_items)
            result.set("rule_max_items", self._rules.max_items)
            result.set("rule_max_elements", self._max_elements)
            result.set("snapshot_max_items", self._snapshots.max_items)
            return result

    def reset(self) -> None:
        """清空三层、活动记录与全部账目（保留当前容量配置；用例隔离用）。"""
        with self._lock:
            self._subjects.clear()
            self._metadata.clear()
            self._rules.clear()
            self._snapshots.clear()
            self._activity.clear()
            self._user_keys.clear()
            self._rule_elements.clear()
            self._rule_bytes.clear()
            self._rule_refs.clear()
            self._snapshot_rules.clear()
            self._rule_total = 0
            self._rule_bytes_total = 0
            self._rule_evicted_total = 0
            self._oversized_rejections = 0


_STORES: ConcurrentStableDict[str, PermissionCacheStore] = ConcurrentStableDict()
"""进程级单份缓存仓（惰性创建；与数据来源注册表、插件注册表同构）。"""

_STORE_KEY = "default"
"""进程级缓存仓的注册键（单实现；保留键位便于将来按服务隔离）。"""

_STORE_LOCK = Lock()


def current_permission_cache_store() -> PermissionCacheStore:
    """取进程级单份缓存仓（未创建即按缺省配置创建）。

    Returns:
        PermissionCacheStore: 进程内唯一实例。
    """
    with _STORE_LOCK:
        store = _STORES.get(_STORE_KEY)
        if store is None:
            store = PermissionCacheStore()
            _STORES.set(_STORE_KEY, store)
        return store


def configure_permission_cache_store(
    options: object, *, snapshot_ttl: int = DEFAULT_SNAPSHOT_TTL_SECONDS
) -> PermissionCacheStore:
    """按 `[permission].options` 重建进程级缓存仓（校验器装配期调用；幂等）。

    重建即清空既有条目：装配发生在进程启动期，此时缓存必为空；用例侧亦以重建代替逐键复位。

    Args:
        options: `[permission].options`（内建映射或基座集合类均可）。
        snapshot_ttl: 层1 用户条目与层3 快照 TTL（秒）。

    Returns:
        PermissionCacheStore: 新的进程级实例。
    """
    store = PermissionCacheStore(
        snapshot_ttl=snapshot_ttl,
        subject_max_items=int_option(options, OPTION_SUBJECT_CACHE_MAX_ITEMS, DEFAULT_SUBJECT_CACHE_MAX_ITEMS),
        metadata_max_items=int_option(options, OPTION_METADATA_CACHE_MAX_ITEMS, DEFAULT_METADATA_CACHE_MAX_ITEMS),
        metadata_ttl=int_option(options, OPTION_METADATA_CACHE_TTL, DEFAULT_METADATA_CACHE_TTL),
        rule_max_items=int_option(options, OPTION_RULE_CACHE_MAX_ITEMS, DEFAULT_RULE_CACHE_MAX_ITEMS),
        rule_max_elements=int_option(options, OPTION_RULE_CACHE_MAX_ELEMENTS, DEFAULT_RULE_CACHE_MAX_ELEMENTS),
        snapshot_max_items=int_option(options, OPTION_SNAPSHOT_CACHE_MAX_ITEMS, DEFAULT_SNAPSHOT_CACHE_MAX_ITEMS),
    )
    with _STORE_LOCK:
        _STORES.set(_STORE_KEY, store)
    return store


def reset_permission_cache_store() -> None:
    """清除进程级缓存仓（用例隔离用；下次访问按缺省配置重建）。"""
    with _STORE_LOCK:
        if _STORE_KEY in _STORES:
            _STORES.delete(_STORE_KEY)
