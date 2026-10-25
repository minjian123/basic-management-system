"""业务域布局声明与域级基线契约（07C `03_01`）。

- `DomainEntry`：一条域布局（`domain_key` + 当前承载服务 + 状态 + 代码路径 + 域内公共出口）。
- `DomainLayout`：域布局全集（`deploy/boundaries/domain_layout.json`）——路径 → 域索引的唯一来源。
- `BaselineEntry` / `load_baseline` / `dump_baseline`：域级基线（存量跨域引用；**只减不增**）。
- `load_layout` / `validate` / `resolve_files`：载入（结构非法抛 `ValueError`）→ 语义校验（返回问题清单）
  → 展开路径为「文件 → 域」索引。

口径（《架构设计 · 产品与服务划分》「边界纪律」节、07C `03_01` 详细设计 §3.1 / §3.4）：

- 一条 = 一个业务域 + 其**全部实现文件**（`legacy` 逐文件声明，不用整目录兜底——域退化为服务即失效）；
- 同一路径不得归属两个域；`shared_paths` 为域外装配 / 基座 / 基础设施面，与域路径互斥；
- 基线记录**存量**跨域引用（`kind` ∈ `import` / `table_ref` / `table_declare`），新增即失败，迁移时逐项删除。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.objects import BaseFrameworkObject, BaseRegistryRecordContract

__all__ = [
    "BASELINE_KINDS",
    "DEFAULT_BASELINE_RELATIVE",
    "DEFAULT_LAYOUT_RELATIVE",
    "DOMAIN_STATUSES",
    "BaselineEntry",
    "DomainEntry",
    "DomainLayout",
    "dump_baseline",
    "load_baseline",
    "load_layout",
]

DEFAULT_LAYOUT_RELATIVE = "deploy/boundaries/domain_layout.json"
"""域布局声明默认相对仓库根路径。"""

DEFAULT_BASELINE_RELATIVE = "deploy/boundaries/domain_boundary_baseline.json"
"""域级基线默认相对仓库根路径。"""

DOMAIN_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(("placement", "legacy", "planned"))
"""域布局状态：`placement` 已分包到域子包 / `legacy` 仍在服务扁平目录（逐文件声明）/ `planned` 未落地。"""

BASELINE_KINDS: ConcurrentStableList[str] = ConcurrentStableList(("import", "table_ref", "table_declare"))
"""基线条目种类：跨域 import / 跨域表引用 / 跨域表声明（混域文件的主域债务）。"""

STATUS_PLACEMENT = "placement"
STATUS_LEGACY = "legacy"
STATUS_PLANNED = "planned"

_LAYOUT_VERSION = 1
_BASELINE_VERSION = 1
_DOMAIN_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""业务域标识形态（小写字母开头，仅小写字母、数字与下划线；登记型标识一律 snake_case）。"""


@dataclass(frozen=True)
class DomainEntry(BaseRegistryRecordContract):
    """一条域布局（`domain_layout.json` 的 `domains[]` 元素）。"""

    domain_key: str
    """业务域标识（与《业务域清单》一致；一经发布不改）。"""

    service_key: str
    """当前承载服务（分包前为服务包；分包后为该服务内的域子包）。"""

    status: str = STATUS_LEGACY
    """布局状态（`DOMAIN_STATUSES` 之一）。"""

    paths: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList[str]())
    """域实现文件路径（相对仓库根，posix；允许 glob）；`legacy` 须逐文件显式列出。"""

    public_api: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList[str]())
    """域内公共出口模块名（D2 允许的跨域引用面；分包前为空）。"""

    @classmethod
    def from_row(cls, row: object) -> DomainEntry:
        """按声明字段从 JSON 条目（或任意同构对象）构造布局条目。

        Args:
            row: 具备声明字段的对象（如 `domain_layout.json` 的条目字典）。

        Returns:
            DomainEntry: 域布局条目。

        Raises:
            ValueError: 字段缺失 / 类型非法。
        """
        data = _row_mapping(row)
        domain_key = _text_field(data, "domain_key")
        service_key = _text_field(data, "service_key")
        status = data.get("status", STATUS_LEGACY)
        if not isinstance(status, str) or status not in DOMAIN_STATUSES:
            raise ValueError(f"域布局条目状态非法（{status!r}；允许 {'、'.join(DOMAIN_STATUSES)}）")
        return cls(
            domain_key=domain_key,
            service_key=service_key,
            status=status,
            paths=_text_list(data, "paths"),
            public_api=_text_list(data, "public_api", required=False),
        )

    def to_dict(self) -> ConcurrentStableDict[str, object]:
        """转回声明形态（基线 / 报告输出用）。

        Returns:
            ConcurrentStableDict[str, object]: 声明条目字典。
        """
        return ConcurrentStableDict(
            {
                "domain_key": self.domain_key,
                "service_key": self.service_key,
                "status": self.status,
                "paths": list(self.paths),
                "public_api": list(self.public_api),
            }
        )


@dataclass(frozen=True)
class BaselineEntry(BaseRegistryRecordContract):
    """一条域级基线（存量跨域引用；只减不增）。"""

    kind: str
    """条目种类（`BASELINE_KINDS` 之一）。"""

    domain: str
    """源业务域（发生跨域引用的域）。"""

    target: str
    """目标业务域（`import` / 表引用 / 表声明指向的域）。"""

    file: str
    """源文件（相对仓库根，posix）。"""

    fingerprint: str
    """行指纹（跨域那一行的规范化文本摘要；行号漂移不影响匹配）。"""

    @classmethod
    def from_row(cls, row: object) -> BaselineEntry:
        """按声明字段从 JSON 条目（或任意同构对象）构造基线条目。

        Args:
            row: 具备声明字段的对象（如基线文件条目字典）。

        Returns:
            BaselineEntry: 基线条目。

        Raises:
            ValueError: 字段缺失 / 类型非法 / 种类非法。
        """
        data = _row_mapping(row)
        kind = _text_field(data, "kind")
        if kind not in BASELINE_KINDS:
            raise ValueError(f"基线条目种类非法（{kind!r}；允许 {'、'.join(BASELINE_KINDS)}）")
        return cls(
            kind=kind,
            domain=_text_field(data, "domain"),
            target=_text_field(data, "target"),
            file=_text_field(data, "file"),
            fingerprint=_text_field(data, "fingerprint"),
        )

    def to_dict(self) -> ConcurrentStableDict[str, object]:
        """转回声明形态。

        Returns:
            ConcurrentStableDict[str, object]: 条目的典。
        """
        return ConcurrentStableDict(
            {
                "kind": self.kind,
                "domain": self.domain,
                "target": self.target,
                "file": self.file,
                "fingerprint": self.fingerprint,
            }
        )


class DomainLayout(BaseFrameworkObject):
    """域布局全集：域清单 + 文件归属索引 + 域外路径（`domain_layout.json` 的内存形态）。"""

    def __init__(self, entries: ConcurrentStableList[DomainEntry], shared_paths: ConcurrentStableList[str]) -> None:
        """初始化。

        Args:
            entries: 域布局条目（声明序）。
            shared_paths: 域外路径（装配 / 基座 / 基础设施面）。
        """
        self._entries = ConcurrentStableList(entries)
        self._shared = ConcurrentStableList(_normalize(path) for path in shared_paths)

    @property
    def entries(self) -> ConcurrentStableList[DomainEntry]:
        """域布局条目快照（声明序）。

        Returns:
            ConcurrentStableList[DomainEntry]: 条目。
        """
        return ConcurrentStableList(self._entries)

    @property
    def shared_paths(self) -> ConcurrentStableList[str]:
        """域外路径快照（声明序）。

        Returns:
            ConcurrentStableList[str]: 路径。
        """
        return ConcurrentStableList(self._shared)

    def domain_keys(self) -> ConcurrentStableSet[str]:
        """全部业务域标识（声明序）。

        Returns:
            ConcurrentStableSet[str]: 域标识集合。
        """
        return ConcurrentStableSet(entry.domain_key for entry in self._entries)

    def service_of(self, domain_key: str) -> str | None:
        """取域承载服务（未登记返回 None）。

        Args:
            domain_key: 业务域标识。

        Returns:
            str | None: 承载服务标识。
        """
        entry = self.entry_of(domain_key)
        return None if entry is None else entry.service_key

    def entry_of(self, domain_key: str) -> DomainEntry | None:
        """取域布局条目（未登记返回 None）。

        Args:
            domain_key: 业务域标识。

        Returns:
            DomainEntry | None: 域布局条目。
        """
        return next((entry for entry in self._entries if entry.domain_key == domain_key), None)

    def domain_services(self) -> ConcurrentStableDict[str, str]:
        """域 → 承载服务映射（表归属双字段一致性校验用）。

        Returns:
            ConcurrentStableDict[str, str]: 域标识到承载服务标识。
        """
        return ConcurrentStableDict((entry.domain_key, entry.service_key) for entry in self._entries)

    def public_api_of(self, domain_key: str) -> ConcurrentStableSet[str]:
        """取域内公共出口模块名集合（D2 放行面）。

        Args:
            domain_key: 业务域标识。

        Returns:
            ConcurrentStableSet[str]: 模块名集合。
        """
        entry = self.entry_of(domain_key)
        return ConcurrentStableSet(() if entry is None else entry.public_api)

    def domain_of(self, path: str) -> str | None:
        """路径 → 业务域（域外路径与未声明路径返回 None）。

        Args:
            path: 相对仓库根的 posix 路径。

        Returns:
            str | None: 业务域标识。
        """
        target = _normalize(path)
        for entry in self._entries:
            if target in (_normalize(item) for item in entry.paths):
                return entry.domain_key
        return None

    def is_shared(self, path: str) -> bool:
        """是否域外路径（装配 / 基座 / 基础设施面）。

        Args:
            path: 相对仓库根的 posix 路径。

        Returns:
            bool: 域外声明 True。
        """
        return _normalize(path) in self._shared

    def resolve_files(self, root: Path) -> tuple[ConcurrentStableDict[str, str], ConcurrentStableList[str]]:
        """展开声明路径为「文件 → 域」索引（glob 按 `Path.glob` 展开）。

        Args:
            root: 仓库根。

        Returns:
            tuple: （文件 → 域映射，问题清单）。
        """
        mapping: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        problems: ConcurrentStableList[str] = ConcurrentStableList()
        for entry in self._entries:
            for declared in entry.paths:
                matched = _expand(root, declared)
                if not matched:
                    problems.add(f"[域布局] {entry.domain_key} 的路径未命中文件：{declared}")
                    continue
                for path in matched:
                    existing = mapping.get(path)
                    if existing is not None and existing != entry.domain_key:
                        problems.add(f"[域布局] {path} 同时归属 {existing} 与 {entry.domain_key}")
                        continue
                    mapping.set(path, entry.domain_key)
        return mapping, problems

    def validate(self, root: Path) -> ConcurrentStableList[str]:
        """语义校验：路径重复归属 / 与域外路径冲突 / 文件是否存在 / 空域与公共出口形态。

        Args:
            root: 仓库根（文件存在性断言用）。

        Returns:
            ConcurrentStableList[str]: 问题清单（空列表表示通过）。
        """
        problems: ConcurrentStableList[str] = ConcurrentStableList()
        declared: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        shared = ConcurrentStableSet(self._shared)
        for entry in self._entries:
            if entry.status != STATUS_PLANNED and not entry.paths:
                problems.add(f"[域布局] {entry.domain_key} 状态 {entry.status} 但未声明代码路径")
            for path in entry.paths:
                target = _normalize(path)
                if target in shared:
                    problems.add(f"[域布局] {entry.domain_key} 的路径同时登记为域外路径：{target}")
                owner = declared.get(target)
                if owner is not None:
                    problems.add(f"[域布局] {target} 同时归属 {owner} 与 {entry.domain_key}")
                    continue
                declared.set(target, entry.domain_key)
        for declared_path in declared:
            if not _expand(root, declared_path):
                problems.add(f"[域布局] 路径未命中文件：{declared_path}")
        for shared_path in self._shared:
            if not _expand(root, shared_path):
                problems.add(f"[域布局] 域外路径未命中文件：{shared_path}")
        return problems


def load_layout(path: Path) -> DomainLayout:
    """载入域布局声明（缺文件视为空布局；结构非法抛 `ValueError`）。

    Args:
        path: 声明文件路径。

    Returns:
        DomainLayout: 域布局。

    Raises:
        ValueError: JSON 非法 / 根结构非法 / 版本非法 / 条目非法 / 域标识重复。
    """
    if not path.is_file():
        return DomainLayout(ConcurrentStableList(), ConcurrentStableList())
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"域布局 JSON 非法：{path}（{exc}）") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"域布局根须为对象：{path}")
    data = ConcurrentStableDict(cast("dict[str, object]", parsed))
    if data.get("version") != _LAYOUT_VERSION:
        raise ValueError(f"域布局版本非法（应为 {_LAYOUT_VERSION}）：{path}")
    raw_domains = data.get("domains")
    if not isinstance(raw_domains, list):
        raise ValueError(f"域布局 domains 须为数组：{path}")
    entries: ConcurrentStableList[DomainEntry] = ConcurrentStableList()
    seen: ConcurrentStableSet[str] = ConcurrentStableSet()
    for index, item in enumerate(cast("list[object]", raw_domains), start=1):
        try:
            entry = DomainEntry.from_row(item)
        except ValueError as exc:
            raise ValueError(f"域布局第 {index} 条非法：{exc}") from exc
        if not _DOMAIN_KEY_RE.match(entry.domain_key):
            raise ValueError(f"域布局第 {index} 条 domain_key 非法：{entry.domain_key}")
        if entry.domain_key in seen:
            raise ValueError(f"域布局 domain_key 重复：{entry.domain_key}")
        seen.add(entry.domain_key)
        entries.add(entry)
    return DomainLayout(entries, _text_list(data, "shared_paths", required=False))


def load_baseline(path: Path) -> ConcurrentStableList[BaselineEntry]:
    """载入域级基线（缺文件返回空集）。

    Args:
        path: 基线文件路径。

    Returns:
        ConcurrentStableList[BaselineEntry]: 基线条目（文件序）。

    Raises:
        ValueError: JSON 非法 / 根结构非法 / 版本非法 / 条目非法。
    """
    if not path.is_file():
        return ConcurrentStableList()
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"域级基线 JSON 非法：{path}（{exc}）") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"域级基线根须为对象：{path}")
    data = ConcurrentStableDict(cast("dict[str, object]", parsed))
    if data.get("version") != _BASELINE_VERSION:
        raise ValueError(f"域级基线版本非法（应为 {_BASELINE_VERSION}）：{path}")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError(f"域级基线 entries 须为数组：{path}")
    entries: ConcurrentStableList[BaselineEntry] = ConcurrentStableList()
    for index, item in enumerate(cast("list[object]", raw_entries), start=1):
        try:
            entries.add(BaselineEntry.from_row(item))
        except ValueError as exc:
            raise ValueError(f"域级基线第 {index} 条非法：{exc}") from exc
    return entries


def dump_baseline(path: Path, entries: ConcurrentStableList[BaselineEntry]) -> int:
    """写出域级基线（按 `kind` / `file` / `domain` / `target` 稳定排序）。

    Args:
        path: 基线文件路径。
        entries: 基线条目。

    Returns:
        int: 写入条目数。
    """
    ordered = sorted(entries, key=lambda entry: (entry.kind, entry.file, entry.domain, entry.target, entry.fingerprint))
    payload = {"version": _BASELINE_VERSION, "entries": [dict(entry.to_dict()) for entry in ordered]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(ordered)


def _row_mapping(row: object) -> ConcurrentStableDict[str, object]:
    """把 JSON 条目（映射）转成基座映射集合类（非对象即报错）。

    Args:
        row: JSON 条目。

    Returns:
        ConcurrentStableDict[str, object]: 字段映射。

    Raises:
        ValueError: 条目非对象。
    """
    if not isinstance(row, dict):
        raise ValueError("条目须为对象")
    return ConcurrentStableDict(cast("dict[str, object]", row))


def _text_field(data: ConcurrentStableDict[str, object], key: str) -> str:
    """取必填字符串字段（缺失 / 空 / 非字符串抛 `ValueError`）。

    Args:
        data: 条目字段映射。
        key: 字段名。

    Returns:
        str: 去空白后的字段值。

    Raises:
        ValueError: 字段缺失 / 非字符串 / 为空。
    """
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"字段缺失或为空：{key}")
    return value.strip()


def _text_list(
    data: ConcurrentStableDict[str, object], key: str, *, required: bool = True
) -> ConcurrentStableFrozenList[str]:
    """取字符串数组字段（缺失按空；元素非字符串抛 `ValueError`）。

    Args:
        data: 条目字典。
        key: 字段名。
        required: True 时缺失即非法。

    Returns:
        ConcurrentStableFrozenList[str]: 规范化路径 / 标识列表。

    Raises:
        ValueError: 字段缺失（required）或非数组 / 元素非字符串。
    """
    raw = data.get(key)
    if raw is None and not required:
        return ConcurrentStableFrozenList()
    if not isinstance(raw, list):
        raise ValueError(f"字段须为数组：{key}")
    for item in cast("list[object]", raw):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"字段 {key} 的元素须为非空字符串")
    normalize = key in ("paths", "shared_paths")
    return ConcurrentStableFrozenList(
        _normalize(item) if normalize else item.strip() for item in cast("list[str]", raw)
    )


def _normalize(path: str) -> str:
    """路径规范化（去 `./` / 反斜杠转 posix / 去首尾空白）。

    Args:
        path: 原始路径。

    Returns:
        str: 规范化路径。
    """
    return path.strip().replace("\\", "/").removeprefix("./")


def _expand(root: Path, declared: str) -> ConcurrentStableList[str]:
    """展开声明路径为文件列表（含 glob；相对仓库根 posix）。

    Args:
        root: 仓库根。
        declared: 声明路径（可含 `**` / `*`）。

    Returns:
        ConcurrentStableList[str]: 命中的文件路径（相对仓库根 posix，稳定序）。
    """
    target = _normalize(declared)
    if any(char in target for char in "*?["):
        matched = sorted(path for path in root.glob(target) if path.is_file())
    else:
        direct = root / target
        matched = [direct] if direct.is_file() else []
    return ConcurrentStableList(path.relative_to(root).as_posix() for path in matched)
