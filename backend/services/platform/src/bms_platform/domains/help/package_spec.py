"""帮助包规格：清单 / includes / 校验和 / 结构校验（08_03）。

装载器只认 `help/package.yaml`，其余文件由清单 `includes` 显式引用。本模块只做**文件层**
校验与值对象化，不碰数据库、不判断租户默认语言与分类是否存在（那两件事按租户在
`services/package.py` 完成）。

口径（详细设计 §5.1 / §5.2）：

- 清单 / `includes` / 校验和 / 分类声明属整包级错误，任何模式都拒收；
- 文章级结构错误默认拒收整包，显式宽松模式才跳过该篇并记告警；
- 锚点存在性与节点类型匹配由 `filter_unknown_targets` 在拿到平台锚点清单后判定；
- 校验和覆盖「清单去 checksum 后的规范化 JSON + 按声明顺序的被引文件全文」。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.exceptions import (
    HelpAnchorUnresolvedError,
    HelpCategoryPathUnresolvedError,
    HelpPackageChecksumMismatchError,
    HelpPackageInvalidError,
    MenuHelpKeyInvalidError,
)
from bms_core.core.objects import BaseValueObject
from bms_core.help.anchors import HelpAnchorKind, validate_help_key
from bms_core.help.values import (
    ARTICLE_SOURCE_BUILTIN,
    ARTICLE_SOURCE_PRODUCT,
    ARTICLE_STATUS_OFFLINE,
    ARTICLE_STATUS_PUBLISHED,
    GENERATED_BY_AI,
    GENERATED_BY_MANUAL,
    TARGET_TYPE_ACTION,
    TARGET_TYPE_FIELD,
    TARGET_TYPE_FORM,
    TARGET_TYPE_GLOBAL,
    TARGET_TYPE_MODULE,
    source_for_product,
)
from bms_core.i18n.rules import is_locale_code_valid, normalize_locale
from bms_core.richtext.sanitize import sanitize_html
from bms_platform.domains.help.constants import (
    HELP_PACKAGE_MANIFEST,
    MAX_ARTICLE_CONTENT_BYTES,
    MAX_ARTICLE_COUNT,
    MAX_CATEGORY_COUNT,
    MAX_LOCALE_COUNT,
    MAX_PACKAGE_FILE_BYTES,
    MAX_SOURCE_KEY_LENGTH,
    MAX_TITLE_LENGTH,
    SUPPORTED_SCHEMA_VERSIONS,
)

__all__ = [
    "HelpArticleSpec",
    "HelpCategorySpec",
    "HelpLocaleText",
    "HelpPackageSpec",
    "HelpProvenance",
    "HelpTargetSpec",
    "compute_checksum",
    "filter_for_tenant",
    "filter_unknown_targets",
    "load_package",
    "write_checksum",
]

_MANIFEST_KEYS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (
        "schema_version",
        "product_key",
        "package_version",
        "generated_at",
        "checksum",
        "includes",
        "categories",
    )
)
"""清单允许键（未知键拒收）。"""

_INCLUDES_KEYS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("categories", "articles"))
"""`includes` 允许键。"""

_ARTICLE_KEYS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    ("source_key", "title", "category_path", "status", "is_top", "targets", "locales", "provenance")
)
"""文章文件允许键（`title` 仅人读提示，不落库）。"""

_TARGET_KEYS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("type", "key"))
"""目标允许键。"""

_LOCALE_KEYS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("title", "content"))
"""语言文案允许键。"""

_PROVENANCE_KEYS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("author", "model", "reviewed_by"))
"""来源留痕允许键。"""

_CATEGORY_KEYS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("path", "sort"))
"""分类允许键。"""

_PRODUCT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
"""产品键形态（与清单 `product_key`、库名基同口径）。"""

_SOURCE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
"""包内稳定键形态（至少两段点分小写）。"""

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
"""语义化版本形态（`X.Y.Z`）。"""

_CHECKSUM_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
"""校验和形态。"""

_CHECKSUM_LINE_RE = re.compile(r"(?m)^(checksum\s*:\s*).*$")
"""清单 `checksum:` 行（回写用）。"""

_PACKAGE_DOMAIN = b"bms-help-package-v1\0"
"""校验和域分隔前缀（防跨协议哈希碰撞）。"""

_ARTICLE_TARGET_KINDS: ConcurrentStableFrozenDict[str, ConcurrentStableFrozenList[HelpAnchorKind]] = (
    ConcurrentStableFrozenDict(
        {
            TARGET_TYPE_MODULE: ConcurrentStableFrozenList((HelpAnchorKind.MENU,)),
            TARGET_TYPE_FORM: ConcurrentStableFrozenList((HelpAnchorKind.FORM,)),
            TARGET_TYPE_FIELD: ConcurrentStableFrozenList((HelpAnchorKind.FIELD,)),
            TARGET_TYPE_ACTION: ConcurrentStableFrozenList((HelpAnchorKind.BUTTON, HelpAnchorKind.ACTION)),
        }
    )
)
"""目标类型 → 允许的锚点节点类型（`global` 不引用锚点，不在表内）。"""


@dataclass(frozen=True)
class HelpTargetSpec(BaseValueObject):
    """一个文章目标（锚点）。

    Attributes:
        target_type: 目标类型（global/module/form/field/action）。
        target_key: 锚点原值；`global` 为空串。
    """

    target_type: str
    target_key: str


@dataclass(frozen=True)
class HelpLocaleText(BaseValueObject):
    """一篇文的单语言文案（已清洗）。

    Attributes:
        title: 标题。
        content: 正文 HTML。
    """

    title: str
    content: str


@dataclass(frozen=True)
class HelpProvenance(BaseValueObject):
    """内容来源留痕。

    Attributes:
        author: `manual` / `ai`。
        model: AI 模型（`author=ai` 时必填）。
        reviewed_by: 人工审核人（`author=ai` 时必填）。
    """

    author: str
    model: str | None = None
    reviewed_by: str | None = None


@dataclass(frozen=True)
class HelpCategorySpec(BaseValueObject):
    """包内声明的一个分类。

    Attributes:
        path: `/` 分隔的分类路径。
        sort: 同级排序。
    """

    path: str
    sort: int


@dataclass(frozen=True)
class HelpArticleSpec(BaseValueObject):
    """包内一篇已通过结构校验的文章（尚未校验锚点存在性 / 租户默认语言 / 分类存在性）。

    Attributes:
        source_key: 包内稳定键。
        category_path: 分类路径。
        status: `published` / `offline`。
        is_top: 是否置顶。
        targets: 目标清单（至少 1 个）。
        locales: 语言 → 文案（至少 1 个，键已归一）。
        provenance: 来源留痕。
    """

    source_key: str
    category_path: str
    status: str
    is_top: bool
    targets: ConcurrentStableFrozenList[HelpTargetSpec]
    locales: ConcurrentStableFrozenDict[str, HelpLocaleText]
    provenance: HelpProvenance


@dataclass(frozen=True)
class HelpPackageSpec(BaseValueObject):
    """已通过文件层校验的帮助包规格。

    Attributes:
        schema_version: 包格式版本。
        product_key: 产品键。
        package_version: 语义化版本。
        checksum: 清单声明的校验和。
        generated_at: 清单生成时间（UTC；可空）。
        categories: 分类声明（内联在前、文件在后）。
        articles: 通过结构校验的文章（宽松模式可能已剔除无效篇）。
        declared_article_count: 清单内文章文件总数（不受宽松剔除影响）。
        warnings: 宽松模式跳过的文章告警。
        source: 由 `product_key` 派生的文章来源。
    """

    schema_version: int
    product_key: str
    package_version: str
    checksum: str
    generated_at: datetime | None
    categories: ConcurrentStableFrozenList[HelpCategorySpec]
    articles: ConcurrentStableFrozenList[HelpArticleSpec]
    declared_article_count: int
    warnings: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList())
    source: str = ARTICLE_SOURCE_PRODUCT

    @property
    def version_tuple(self) -> tuple[int, int, int]:
        """版本元组（升级 / 降级比较用）。

        Returns:
            tuple[int, int, int]: `(主, 次, 修订)`。
        """
        return parse_version(self.package_version)

    @property
    def is_builtin(self) -> bool:
        """是否平台内建包。

        Returns:
            bool: `product_key = platform` 为 True。
        """
        return self.source == ARTICLE_SOURCE_BUILTIN


def load_package(path: str | Path, *, lenient: bool = False) -> HelpPackageSpec:
    """读取并校验帮助包（文件层）。

    Args:
        path: 包目录或 `package.yaml` 路径。
        lenient: 是否跳过无效文章（False 时任一文章级错误整包拒收）。

    Returns:
        HelpPackageSpec: 已校验的包规格。

    Raises:
        HelpPackageInvalidError: 清单 / includes / 分类 / 文章结构非法（40009）。
        HelpPackageChecksumMismatchError: 校验和格式非法或与实际内容不符（40010）。
    """
    manifest_path = _manifest_path(path)
    root = manifest_path.parent.resolve()
    manifest = _read_yaml(manifest_path)
    _check_keys(manifest, _MANIFEST_KEYS, HELP_PACKAGE_MANIFEST)

    schema_version = _int_field(manifest, "schema_version", HELP_PACKAGE_MANIFEST)
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise HelpPackageInvalidError(f"不支持的包格式版本：{schema_version}（当前仅支持 1）")

    product_key = _text_field(manifest, "product_key", HELP_PACKAGE_MANIFEST)
    if not _PRODUCT_KEY_RE.match(product_key) or len(product_key) > 64:
        raise HelpPackageInvalidError(f"product_key 非法：{product_key!r}（小写字母开头，仅小写字母 / 数字 / 下划线）")

    package_version = _text_field(manifest, "package_version", HELP_PACKAGE_MANIFEST)
    parse_version(package_version)

    checksum = _text_field(manifest, "checksum", HELP_PACKAGE_MANIFEST)
    if not _CHECKSUM_RE.match(checksum):
        raise HelpPackageChecksumMismatchError(f"checksum 格式非法：{checksum!r}（须为 sha256:<64 位小写十六进制>）")

    generated_at = _optional_datetime(manifest.get("generated_at"), "generated_at")
    includes = _mapping(manifest.get("includes"), "includes")
    _check_keys(includes, _INCLUDES_KEYS, "includes")
    article_paths = _include_paths(root, includes)
    category_paths = _category_include_paths(root, includes)

    actual = _checksum_for(manifest, root, category_paths, article_paths)
    if actual != checksum:
        raise HelpPackageChecksumMismatchError(f"checksum 不符：清单为 {checksum}，实际为 {actual}")

    categories = _load_categories(manifest, root, category_paths)
    articles, warnings = _load_articles(root, article_paths, lenient=lenient)

    return HelpPackageSpec(
        schema_version=schema_version,
        product_key=product_key,
        package_version=package_version,
        checksum=checksum,
        generated_at=generated_at,
        categories=categories,
        articles=articles,
        declared_article_count=len(article_paths),
        warnings=warnings,
        source=source_for_product(product_key),
    )


def filter_unknown_targets(
    spec: HelpPackageSpec,
    anchors: ConcurrentStableDict[str, HelpAnchorKind],
    *,
    lenient: bool,
) -> HelpPackageSpec:
    """按平台锚点清单过滤文章（锚点不存在或类型不匹配）。

    Args:
        spec: 已通过文件层校验的包规格。
        anchors: `help_key` → 锚点节点类型（`list_help_anchors` 归集）。
        lenient: 是否跳过无效文章（False 时抛 `HelpAnchorUnresolvedError`）。

    Returns:
        HelpPackageSpec: 过滤后的规格（可能带新告警）。

    Raises:
        HelpAnchorUnresolvedError: 严格模式下存在不可解析锚点（40008）。
    """
    kept: ConcurrentStableList[HelpArticleSpec] = ConcurrentStableList()
    warnings: ConcurrentStableList[str] = ConcurrentStableList(spec.warnings)
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    anchor_map = anchors

    for article in spec.articles:
        problem = _article_target_problem(article, anchor_map)
        if problem is None:
            kept.add(article)
            continue
        message = f"{article.source_key}：{problem}"
        if lenient:
            warnings.add(message)
        else:
            errors.add(message)

    if errors:
        raise HelpAnchorUnresolvedError("帮助包锚点不可解析：" + "；".join(errors), data=errors)
    if len(kept) == len(spec.articles) and len(warnings) == len(spec.warnings):
        return spec
    return replace(spec, articles=ConcurrentStableFrozenList(kept), warnings=ConcurrentStableFrozenList(warnings))


def filter_for_tenant(
    spec: HelpPackageSpec,
    *,
    default_locale: str,
    category_paths: ConcurrentStableList[str] | ConcurrentStableSet[str],
    lenient: bool,
) -> HelpPackageSpec:
    """按租户默认语言与既有分类过滤文章。

    Args:
        spec: 包规格。
        default_locale: 租户默认语言（`sys_i18n_locale.is_default`）。
        category_paths: 可解析的分类路径（包内声明 ∪ 租户既有）。
        lenient: 是否跳过无效文章（False 时分别抛 40009 / 40013）。

    Returns:
        HelpPackageSpec: 过滤后的规格（可能带新告警）。

    Raises:
        HelpPackageInvalidError: 文章不含租户默认语言（40009）。
        HelpCategoryPathUnresolvedError: 分类路径不可解析（40013）。
    """
    locale_key = normalize_locale(default_locale)
    known_paths = ConcurrentStableSet(category_paths)
    kept: ConcurrentStableList[HelpArticleSpec] = ConcurrentStableList()
    warnings: ConcurrentStableList[str] = ConcurrentStableList(spec.warnings)
    locale_errors: ConcurrentStableList[str] = ConcurrentStableList()
    category_errors: ConcurrentStableList[str] = ConcurrentStableList()

    for article in spec.articles:
        if locale_key not in article.locales:
            message = f"{article.source_key}：locales 缺少租户默认语言 {default_locale}"
            if lenient:
                warnings.add(message)
            else:
                locale_errors.add(message)
            continue
        if article.category_path not in known_paths:
            message = f"{article.source_key}：分类路径不可解析 {article.category_path}"
            if lenient:
                warnings.add(message)
            else:
                category_errors.add(message)
            continue
        kept.add(article)

    if locale_errors:
        raise HelpPackageInvalidError("帮助包文章缺少租户默认语言：" + "；".join(locale_errors), data=locale_errors)
    if category_errors:
        raise HelpCategoryPathUnresolvedError(
            "帮助分类路径不可解析：" + "；".join(category_errors), data=category_errors
        )
    if len(kept) == len(spec.articles) and len(warnings) == len(spec.warnings):
        return spec
    return replace(spec, articles=ConcurrentStableFrozenList(kept), warnings=ConcurrentStableFrozenList(warnings))


def compute_checksum(path: str | Path) -> str:
    """计算帮助包的校验和（不要求清单已填写 checksum）。

    Args:
        path: 包目录或 `package.yaml` 路径。

    Returns:
        str: `sha256:<64 位小写十六进制>`。

    Raises:
        HelpPackageInvalidError: 清单不可解析或 includes 不合法（40009）。
    """
    manifest_path = _manifest_path(path)
    root = manifest_path.parent.resolve()
    manifest = _read_yaml(manifest_path)
    includes = _mapping(manifest.get("includes"), "includes")
    _check_keys(includes, _INCLUDES_KEYS, "includes")
    article_paths = _include_paths(root, includes)
    category_paths = _category_include_paths(root, includes)
    return _checksum_for(manifest, root, category_paths, article_paths)


def write_checksum(path: str | Path) -> str:
    """计算校验和并回写 `package.yaml` 的 `checksum:` 行（保留其余内容与换行风格）。

    Args:
        path: 包目录或 `package.yaml` 路径。

    Returns:
        str: 写入的校验和。

    Raises:
        HelpPackageInvalidError: 清单不可解析或 includes 不合法（40009）。
    """
    manifest_path = _manifest_path(path)
    checksum = compute_checksum(manifest_path)
    raw = manifest_path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    normalized = raw.replace("\r\n", "\n")
    replacement = f"checksum: {checksum}"
    if _CHECKSUM_LINE_RE.search(normalized):
        updated = _CHECKSUM_LINE_RE.sub(replacement, normalized, count=1)
    else:
        updated = normalized.rstrip("\n") + "\n" + replacement + "\n"
    manifest_path.write_text(updated.replace("\n", newline), encoding="utf-8", newline="")
    return checksum


def parse_version(value: str) -> tuple[int, int, int]:
    """解析 `X.Y.Z` 语义化版本。

    Args:
        value: 版本字符串。

    Returns:
        tuple[int, int, int]: `(主, 次, 修订)`。

    Raises:
        HelpPackageInvalidError: 形态非法（40009）。
    """
    matched = _VERSION_RE.match(value)
    if matched is None:
        raise HelpPackageInvalidError(f"package_version 非法：{value!r}（须为 X.Y.Z 三段数字）")
    return int(matched.group(1)), int(matched.group(2)), int(matched.group(3))


def _manifest_path(path: str | Path) -> Path:
    """把目录 / 文件路径归一为清单路径。

    Args:
        path: 包目录或 `package.yaml` 路径。

    Returns:
        Path: 清单路径。

    Raises:
        HelpPackageInvalidError: 路径不存在（40009）。
    """
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / HELP_PACKAGE_MANIFEST
    if not candidate.is_file():
        raise HelpPackageInvalidError(f"帮助包清单不存在：{candidate}")
    return candidate


def _read_yaml(path: Path) -> ConcurrentStableDict[str, Any]:
    """读取 YAML 映射文件（大小上限 + 语法错误转业务异常）。

    Args:
        path: 文件路径。

    Returns:
        ConcurrentStableDict[str, Any]: 文件内容（顶层须为映射）。

    Raises:
        HelpPackageInvalidError: 文件过大 / 语法错误 / 顶层非映射（40009）。
    """
    if path.stat().st_size > MAX_PACKAGE_FILE_BYTES:
        raise HelpPackageInvalidError(f"文件超出大小上限（{MAX_PACKAGE_FILE_BYTES} 字节）：{path.name}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise HelpPackageInvalidError(f"YAML 语法错误（{path.name}）：{exc}") from exc
    if not isinstance(data, dict):
        raise HelpPackageInvalidError(f"YAML 顶层须为映射：{path.name}")
    return cast("ConcurrentStableDict[str, Any]", data)


def _mapping(value: object, where: str) -> ConcurrentStableDict[str, Any]:
    """校验值为映射。

    Args:
        value: 原始值。
        where: 字段位置（错误信息用）。

    Returns:
        ConcurrentStableDict[str, Any]: 映射。

    Raises:
        HelpPackageInvalidError: 非映射（40009）。
    """
    if not isinstance(value, dict):
        raise HelpPackageInvalidError(f"{where} 须为映射")
    return cast("ConcurrentStableDict[str, Any]", value)


def _as_list(value: object, where: str) -> ConcurrentStableList[object]:
    """校验值为数组并规整为插入序列表。

    Args:
        value: 原始值。
        where: 字段位置（错误信息用）。

    Returns:
        ConcurrentStableList[object]: 元素清单。

    Raises:
        HelpPackageInvalidError: 非数组（40009）。
    """
    if not isinstance(value, list):
        raise HelpPackageInvalidError(f"{where} 须为数组")
    return ConcurrentStableList(cast("list[object]", value))


def _check_keys(data: ConcurrentStableDict[str, Any], allowed: ConcurrentStableFrozenList[str], where: str) -> None:
    """拒绝未知键（防拼写错误被静默忽略）。

    Args:
        data: 映射。
        allowed: 允许键。
        where: 字段位置。

    Raises:
        HelpPackageInvalidError: 存在未知键（40009）。
    """
    unknown = [key for key in data if key not in allowed]
    if unknown:
        raise HelpPackageInvalidError(f"{where} 存在未知字段：{'、'.join(str(item) for item in unknown)}")


def _text_field(data: ConcurrentStableDict[str, Any], key: str, where: str) -> str:
    """取必填非空字符串。

    Args:
        data: 映射。
        key: 字段名。
        where: 字段位置。

    Returns:
        str: 去首尾空白的字符串。

    Raises:
        HelpPackageInvalidError: 缺失 / 非字符串 / 空串（40009）。
    """
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HelpPackageInvalidError(f"{where}.{key} 必填且须为非空字符串")
    return value.strip()


def _int_field(data: ConcurrentStableDict[str, Any], key: str, where: str) -> int:
    """取必填整数（拒绝布尔）。

    Args:
        data: 映射。
        key: 字段名。
        where: 字段位置。

    Returns:
        int: 整数值。

    Raises:
        HelpPackageInvalidError: 缺失 / 非整数（40009）。
    """
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise HelpPackageInvalidError(f"{where}.{key} 必填且须为整数")
    return value


def _optional_datetime(value: object, where: str) -> datetime | None:
    """解析可选 ISO 8601 时间（UTC）。

    Args:
        value: 原始值（字符串或 YAML 已解析的日期时间）。
        where: 字段位置。

    Returns:
        datetime | None: UTC 时间（naive）；未提供为 None。

    Raises:
        HelpPackageInvalidError: 形态非法（40009）。
    """
    if value is None:
        return None
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day, tzinfo=UTC)
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise HelpPackageInvalidError(f"{where} 非法：{value!r}（须为 ISO 8601）") from exc
    else:
        raise HelpPackageInvalidError(f"{where} 非法：{value!r}（须为 ISO 8601）")
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _include_paths(root: Path, includes: ConcurrentStableDict[str, Any]) -> ConcurrentStableFrozenList[Path]:
    """解析 `includes.articles` 为文件路径（越界 / 缺失 / 重复即拒收）。

    Args:
        root: 包根目录。
        includes: 清单 `includes` 映射。

    Returns:
        ConcurrentStableFrozenList[Path]: 文章文件路径（声明顺序）。

    Raises:
        HelpPackageInvalidError: 列表缺失 / 为空 / 越界 / 重复 / 超上限（40009）。
    """
    raw = _as_list(includes.get("articles"), "includes.articles")
    if not raw:
        raise HelpPackageInvalidError("includes.articles 必填且须为非空数组")
    if len(raw) > MAX_ARTICLE_COUNT:
        raise HelpPackageInvalidError(f"文章数超出上限：{len(raw)} > {MAX_ARTICLE_COUNT}")
    paths: ConcurrentStableList[Path] = ConcurrentStableList()
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    for index, item in enumerate(raw):
        relative = _relative_text(item, f"includes.articles[{index}]")
        if relative in seen:
            raise HelpPackageInvalidError(f"includes.articles 重复引用：{relative}")
        seen.add(relative)
        paths.add(_resolve_include(root, relative))
    return ConcurrentStableFrozenList(paths)


def _category_include_paths(root: Path, includes: ConcurrentStableDict[str, Any]) -> ConcurrentStableFrozenList[Path]:
    """解析 `includes.categories`（可选）。

    Args:
        root: 包根目录。
        includes: 清单 `includes` 映射。

    Returns:
        ConcurrentStableFrozenList[Path]: 分类文件路径（0 或 1 个）。

    Raises:
        HelpPackageInvalidError: 路径非法 / 缺失（40009）。
    """
    raw = includes.get("categories")
    if raw is None:
        return ConcurrentStableFrozenList()
    relative = _relative_text(raw, "includes.categories")
    return ConcurrentStableFrozenList((_resolve_include(root, relative),))


def _relative_text(value: object, where: str) -> str:
    """校验 includes 项为非空相对路径字符串。

    Args:
        value: 原始值。
        where: 字段位置。

    Returns:
        str: 相对路径（POSIX 分隔）。

    Raises:
        HelpPackageInvalidError: 非字符串 / 绝对路径 / 含 `..`（40009）。
    """
    if not isinstance(value, str) or not value.strip():
        raise HelpPackageInvalidError(f"{where} 必填且须为非空字符串")
    text = value.strip().replace("\\", "/")
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise HelpPackageInvalidError(f"{where} 不得为绝对路径：{value!r}")
    if ".." in Path(text).parts:
        raise HelpPackageInvalidError(f"{where} 不得包含 '..'：{value!r}")
    return text


def _resolve_include(root: Path, relative: str) -> Path:
    """把相对引用解析为包内文件（存在性 + 越界校验）。

    Args:
        root: 包根目录。
        relative: 相对路径。

    Returns:
        Path: 文件路径。

    Raises:
        HelpPackageInvalidError: 文件不存在 / 越出包根（40009）。
    """
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise HelpPackageInvalidError(f"includes 路径越出包根：{relative}")
    if not candidate.is_file():
        raise HelpPackageInvalidError(f"includes 文件不存在：{relative}")
    return candidate


def _checksum_for(
    manifest: ConcurrentStableDict[str, Any],
    root: Path,
    category_paths: ConcurrentStableFrozenList[Path],
    article_paths: ConcurrentStableFrozenList[Path],
) -> str:
    """按详细设计 §5.2 计算校验和。

    Args:
        manifest: 清单原始映射。
        root: 包根目录。
        category_paths: 分类文件路径。
        article_paths: 文章文件路径。

    Returns:
        str: `sha256:<hex>`。
    """
    payload = bytearray(_PACKAGE_DOMAIN)
    payload.extend(_canonical_json(manifest).encode("utf-8"))
    for path in (*category_paths, *article_paths):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        payload.extend(b"\0")
        payload.extend(relative)
        payload.extend(b"\0")
        payload.extend(len(data).to_bytes(8, "big"))
        payload.extend(data)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_json(manifest: ConcurrentStableDict[str, Any]) -> str:
    """清单去 checksum 后的规范化 JSON（键排序 / UTF-8 / 紧凑分隔符）。

    Args:
        manifest: 清单原始映射。

    Returns:
        str: 规范化 JSON 文本。
    """
    payload = {key: value for key, value in manifest.items() if key != "checksum"}
    return json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _jsonable(value: object) -> object:
    """把 YAML 解析出的日期 / 时间递归转成 ISO 字符串（供 JSON 序列化）。

    Args:
        value: 原始值。

    Returns:
        object: 可 JSON 序列化的值。
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        mapping = cast("dict[str, object]", value)
        return {str(key): _jsonable(item) for key, item in mapping.items()}
    if isinstance(value, list | tuple):
        items = cast("list[object]", value)
        return [_jsonable(item) for item in items]
    return value


def _load_categories(
    manifest: ConcurrentStableDict[str, Any], root: Path, category_paths: ConcurrentStableFrozenList[Path]
) -> ConcurrentStableFrozenList[HelpCategorySpec]:
    """合并内联分类与 `categories.yaml`，校验路径 / 排序 / 父级顺序。

    Args:
        manifest: 清单原始映射。
        root: 包根目录。
        category_paths: 分类文件路径。

    Returns:
        ConcurrentStableFrozenList[HelpCategorySpec]: 分类声明（内联在前）。

    Raises:
        HelpPackageInvalidError: 结构 / 重复 / 父级顺序非法（40009）。
    """
    raw_items: ConcurrentStableList[tuple[ConcurrentStableDict[str, Any], str]] = ConcurrentStableList()
    inline = manifest.get("categories")
    if inline is not None:
        for index, item in enumerate(_as_list(inline, "categories")):
            raw_items.add((_mapping(item, f"categories[{index}]"), f"categories[{index}]"))
    for path in category_paths:
        data = _read_yaml(path)
        items = _as_list(data.get("categories"), f"{path.name}.categories")
        for index, item in enumerate(items):
            raw_items.add((_mapping(item, f"{path.name}.categories[{index}]"), f"{path.name}.categories[{index}]"))
    if len(raw_items) > MAX_CATEGORY_COUNT:
        raise HelpPackageInvalidError(f"分类数超出上限：{len(raw_items)} > {MAX_CATEGORY_COUNT}")

    categories: ConcurrentStableList[HelpCategorySpec] = ConcurrentStableList()
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    for index, (item, where) in enumerate(raw_items):
        _check_keys(item, _CATEGORY_KEYS, where)
        path = _text_field(item, "path", where)
        _validate_category_path(path, where)
        if path in seen:
            raise HelpPackageInvalidError(f"分类路径重复声明：{path}")
        sort = item.get("sort", index + 1)
        if isinstance(sort, bool) or not isinstance(sort, int):
            raise HelpPackageInvalidError(f"{where}.sort 须为整数")
        seen.add(path)
        categories.add(HelpCategorySpec(path=path, sort=sort))
    ordered_paths: ConcurrentStableList[str] = ConcurrentStableList(spec.path for spec in categories)
    for index, category in enumerate(categories):
        if "/" not in category.path:
            continue
        parent = category.path.rsplit("/", 1)[0]
        if parent in ordered_paths and ordered_paths.index(parent) > index:
            raise HelpPackageInvalidError(f"分类父级未先出现：{category.path}（父级 {parent}）")
    return ConcurrentStableFrozenList(categories)


def _validate_category_path(path: str, where: str) -> None:
    """校验分类路径形态（无空段 / 单段长度 / 总长）。

    Args:
        path: 分类路径。
        where: 字段位置。

    Raises:
        HelpPackageInvalidError: 形态非法（40009）。
    """
    if len(path) > 255:
        raise HelpPackageInvalidError(f"{where}.path 超出 255 字符：{path}")
    segments = path.split("/")
    if any(not segment.strip() or len(segment) > 64 for segment in segments):
        raise HelpPackageInvalidError(f"{where}.path 非法（空段或单段超过 64 字符）：{path}")


def _load_articles(
    root: Path, article_paths: ConcurrentStableFrozenList[Path], *, lenient: bool
) -> tuple[ConcurrentStableFrozenList[HelpArticleSpec], ConcurrentStableFrozenList[str]]:
    """逐篇读取并校验文章；宽松模式跳过无效篇。

    Args:
        root: 包根目录。
        article_paths: 文章文件路径。
        lenient: 是否跳过无效文章。

    Returns:
        tuple[ConcurrentStableFrozenList[HelpArticleSpec], ConcurrentStableFrozenList[str]]:
            有效文章与宽松模式告警。

    Raises:
        HelpPackageInvalidError: 严格模式下文章结构非法 / `source_key` 重复（40009）。
    """
    articles: ConcurrentStableList[HelpArticleSpec] = ConcurrentStableList()
    warnings: ConcurrentStableList[str] = ConcurrentStableList()
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    seen_keys: ConcurrentStableList[str] = ConcurrentStableList()

    for path in article_paths:
        where = path.name
        try:
            data = _read_yaml(path)
            article = _parse_article(data, where)
        except HelpPackageInvalidError as exc:
            message = f"{path.name}：{exc}"
            if lenient:
                warnings.add(message)
                continue
            errors.add(message)
            continue
        if article.source_key in seen_keys:
            message = f"{path.name}：source_key 重复 {article.source_key}"
            if lenient:
                warnings.add(message)
                continue
            errors.add(message)
            continue
        seen_keys.add(article.source_key)
        articles.add(article)

    if errors:
        raise HelpPackageInvalidError("帮助包文章非法：" + "；".join(errors), data=errors)
    owners: ConcurrentStableDict[tuple[str, str], str] = ConcurrentStableDict()
    for article in articles:
        for target in article.targets:
            pair = (target.target_type, target.target_key)
            previous = owners.get(pair)
            if previous is not None:
                raise HelpPackageInvalidError(
                    "包内多篇文章指向同一目标："
                    f"{target.target_type}:{target.target_key}（{previous} / {article.source_key}）"
                )
            owners.set(pair, article.source_key)
    return ConcurrentStableFrozenList(articles), ConcurrentStableFrozenList(warnings)


def _parse_article(data: ConcurrentStableDict[str, Any], where: str) -> HelpArticleSpec:
    """校验单篇文章结构并转值对象。

    Args:
        data: 文章映射。
        where: 文件位置（错误信息用）。

    Returns:
        HelpArticleSpec: 文章规格。

    Raises:
        HelpPackageInvalidError: 结构 / 内容非法（40009）。
    """
    _check_keys(data, _ARTICLE_KEYS, where)
    source_key = _text_field(data, "source_key", where)
    if len(source_key) > MAX_SOURCE_KEY_LENGTH or not _SOURCE_KEY_RE.match(source_key):
        raise HelpPackageInvalidError(f"{where}.source_key 非法：{source_key!r}")
    category_path = _text_field(data, "category_path", where)
    _validate_category_path(category_path, where)
    status = _text_field(data, "status", where)
    if status not in (ARTICLE_STATUS_PUBLISHED, ARTICLE_STATUS_OFFLINE):
        raise HelpPackageInvalidError(f"{where}.status 非法：{status!r}（包内只允许 published/offline）")
    is_top = data.get("is_top", False)
    if not isinstance(is_top, bool):
        raise HelpPackageInvalidError(f"{where}.is_top 须为布尔")
    targets = _parse_targets(data.get("targets"), where)
    locales = _parse_locales(data.get("locales"), where)
    provenance = _parse_provenance(data.get("provenance"), where)
    return HelpArticleSpec(
        source_key=source_key,
        category_path=category_path,
        status=status,
        is_top=is_top,
        targets=targets,
        locales=locales,
        provenance=provenance,
    )


def _parse_targets(value: object, where: str) -> ConcurrentStableFrozenList[HelpTargetSpec]:
    """校验文章目标列表。

    Args:
        value: 原始值。
        where: 文件位置。

    Returns:
        ConcurrentStableFrozenList[HelpTargetSpec]: 目标清单。

    Raises:
        HelpPackageInvalidError: 缺失 / 为空 / 重复 / 类型未知 / 锚点形态非法（40009）。
    """
    items = _as_list(value, f"{where}.targets")
    if not items:
        raise HelpPackageInvalidError(f"{where}.targets 必填且须为非空数组")
    targets: ConcurrentStableList[HelpTargetSpec] = ConcurrentStableList()
    seen: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
    for index, item in enumerate(items):
        target_data = _mapping(item, f"{where}.targets[{index}]")
        _check_keys(target_data, _TARGET_KEYS, f"{where}.targets[{index}]")
        target_type = _text_field(target_data, "type", f"{where}.targets[{index}]")
        if target_type == TARGET_TYPE_GLOBAL:
            key = ""
        else:
            key = _text_field(target_data, "key", f"{where}.targets[{index}]")
            _validate_target_key(key, target_type, f"{where}.targets[{index}]")
        pair = (target_type, key)
        if pair in seen:
            raise HelpPackageInvalidError(f"{where}.targets 重复：{target_type}:{key}")
        seen.add(pair)
        targets.add(HelpTargetSpec(target_type=target_type, target_key=key))
    return ConcurrentStableFrozenList(targets)


def _validate_target_key(key: str, target_type: str, where: str) -> None:
    """校验锚点键形态与目标类型匹配（存在性留给 `filter_unknown_targets`）。

    Args:
        key: 锚点键。
        target_type: 目标类型。
        where: 字段位置。

    Raises:
        HelpPackageInvalidError: 类型未知或锚点形态非法（40009）。
    """
    kinds = _ARTICLE_TARGET_KINDS.get(target_type)
    if kinds is None:
        raise HelpPackageInvalidError(f"{where}.type 非法：{target_type!r}")
    last_error: MenuHelpKeyInvalidError | None = None
    for kind in kinds:
        try:
            validate_help_key(key, kind=kind)
            return
        except MenuHelpKeyInvalidError as exc:
            last_error = exc
    raise HelpPackageInvalidError(f"{where}.key 与目标类型不匹配：{key!r}") from last_error


def _parse_locales(value: object, where: str) -> ConcurrentStableFrozenDict[str, HelpLocaleText]:
    """校验并清洗文章语言文案。

    Args:
        value: 原始值。
        where: 文件位置。

    Returns:
        ConcurrentStableFrozenDict[str, HelpLocaleText]: 语言 → 文案（键已归一）。

    Raises:
        HelpPackageInvalidError: 缺失 / 为空 / 语言非法 / 文案非法（40009）。
    """
    locales_data = _mapping(value, f"{where}.locales")
    if not locales_data or len(locales_data) > MAX_LOCALE_COUNT:
        raise HelpPackageInvalidError(f"{where}.locales 须为 1~{MAX_LOCALE_COUNT} 个语言")
    locales: ConcurrentStableList[tuple[str, HelpLocaleText]] = ConcurrentStableList()
    for raw_locale, raw_text in locales_data.items():
        locale = normalize_locale(str(raw_locale))
        if not is_locale_code_valid(locale):
            raise HelpPackageInvalidError(f"{where}.locales 语言非法：{raw_locale!r}")
        text = _mapping(raw_text, f"{where}.locales.{locale}")
        _check_keys(text, _LOCALE_KEYS, f"{where}.locales.{locale}")
        title = _text_field(text, "title", f"{where}.locales.{locale}")
        if len(title) > MAX_TITLE_LENGTH:
            raise HelpPackageInvalidError(f"{where}.locales.{locale}.title 超出 {MAX_TITLE_LENGTH} 字符")
        content_raw = _text_field(text, "content", f"{where}.locales.{locale}")
        content = sanitize_html(content_raw).strip()
        if not content:
            raise HelpPackageInvalidError(f"{where}.locales.{locale}.content 清洗后为空")
        if len(content.encode("utf-8")) > MAX_ARTICLE_CONTENT_BYTES:
            raise HelpPackageInvalidError(
                f"{where}.locales.{locale}.content 超出 {MAX_ARTICLE_CONTENT_BYTES} 字节（清洗后）"
            )
        if any(existing == locale for existing, _ in locales):
            raise HelpPackageInvalidError(f"{where}.locales 语言重复（归一后）：{locale}")
        locales.add((locale, HelpLocaleText(title=title, content=content)))
    return ConcurrentStableFrozenDict(locales)


def _parse_provenance(value: object, where: str) -> HelpProvenance:
    """校验内容来源留痕。

    Args:
        value: 原始值。
        where: 文件位置。

    Returns:
        HelpProvenance: 来源留痕。

    Raises:
        HelpPackageInvalidError: 缺失 / 作者非法 / AI 缺模型或审核人（40009）。
    """
    data = _mapping(value, f"{where}.provenance")
    _check_keys(data, _PROVENANCE_KEYS, f"{where}.provenance")
    author = _text_field(data, "author", f"{where}.provenance")
    if author not in (GENERATED_BY_MANUAL, GENERATED_BY_AI):
        raise HelpPackageInvalidError(f"{where}.provenance.author 非法：{author!r}（manual/ai）")
    model = _optional_text(data.get("model"))
    reviewed_by = _optional_text(data.get("reviewed_by"))
    if author == GENERATED_BY_AI and (model is None or reviewed_by is None):
        raise HelpPackageInvalidError(f"{where}.provenance.author=ai 时 model 与 reviewed_by 必填")
    return HelpProvenance(author=author, model=model, reviewed_by=reviewed_by)


def _optional_text(value: object) -> str | None:
    """取可选字符串（去空白；空串视为未提供）。

    Args:
        value: 原始值。

    Returns:
        str | None: 归一值。

    Raises:
        HelpPackageInvalidError: 值不是字符串（40009）。
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise HelpPackageInvalidError(f"可选文本须为字符串：{value!r}")
    text = value.strip()
    return text or None


def _article_target_problem(article: HelpArticleSpec, anchors: ConcurrentStableDict[str, HelpAnchorKind]) -> str | None:
    """检查一篇文章的目标是否可解析。

    Args:
        article: 文章规格。
        anchors: `help_key` → 锚点节点类型。

    Returns:
        str | None: 问题描述；全部可解析返回 None。
    """
    for target in article.targets:
        if target.target_type == TARGET_TYPE_GLOBAL:
            continue
        entry_kind = anchors.get(target.target_key)
        if entry_kind is None:
            return f"锚点不存在 {target.target_type}:{target.target_key}"
        allowed = _ARTICLE_TARGET_KINDS[target.target_type]
        if entry_kind not in allowed:
            return f"锚点类型不匹配 {target.target_type}:{target.target_key}（实际 {entry_kind.value}）"
    return None
