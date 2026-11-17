"""帮助包测试支撑：临时包构造 / 锚点清单 / 会话开合口。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import yaml

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.serialization import normalize_collections
from bms_core.db.session import DbSession
from bms_core.help.anchors import HelpAnchorKind
from bms_platform.domains.help.package_spec import write_checksum

__all__ = [
    "anchor_map",
    "article_payload",
    "session_opener",
    "write_package",
]

_DEFAULT_CONTENT = "<h2>适用场景</h2><p>这是帮助正文。</p>"


def anchor_map(prefix: str) -> ConcurrentStableDict[str, HelpAnchorKind]:
    """构造五类锚点清单（键带用例命名空间，避免跨用例冲突）。

    Args:
        prefix: 用例命名空间前缀。

    Returns:
        ConcurrentStableDict[str, HelpAnchorKind]: `help_key` → 节点类型。
    """
    return ConcurrentStableDict(
        {
            module_key(prefix): HelpAnchorKind.MENU,
            form_key(prefix): HelpAnchorKind.FORM,
            field_key(prefix): HelpAnchorKind.FIELD,
            button_key(prefix): HelpAnchorKind.BUTTON,
            action_key(prefix): HelpAnchorKind.ACTION,
        }
    )


def module_key(prefix: str) -> str:
    """模块级锚点键。

    Args:
        prefix: 命名空间前缀。

    Returns:
        str: 五段式锚点。
    """
    return f"platform:{prefix}:::"


def form_key(prefix: str) -> str:
    """表单级锚点键。

    Args:
        prefix: 命名空间前缀。

    Returns:
        str: 五段式锚点。
    """
    return f"platform:{prefix}:user::"


def field_key(prefix: str) -> str:
    """字段级锚点键。

    Args:
        prefix: 命名空间前缀。

    Returns:
        str: 五段式锚点。
    """
    return f"platform:{prefix}:user:username:"


def button_key(prefix: str) -> str:
    """按钮级锚点键。

    Args:
        prefix: 命名空间前缀。

    Returns:
        str: 五段式锚点。
    """
    return f"platform:{prefix}:user::create"


def action_key(prefix: str) -> str:
    """动作码全局兜底锚点键。

    Args:
        prefix: 命名空间前缀。

    Returns:
        str: 五段式锚点。
    """
    return f"platform::::{prefix}"


def article_payload(
    prefix: str,
    *,
    product_key: str,
    suffix: str = "create",
    title: str | None = None,
    content: str = _DEFAULT_CONTENT,
    category_path: str | None = None,
    status: str = "published",
    target_type: str = "module",
    target_key: str | None = None,
    locales: ConcurrentStableFrozenList[str] | None = None,
    provenance: ConcurrentStableDict[str, object] | None = None,
    is_top: bool = False,
) -> ConcurrentStableDict[str, object]:
    """构造一篇文章的 YAML 内容。

    Args:
        prefix: 用例命名空间前缀。
        product_key: 产品键（`source_key` 首段）。
        suffix: 稳定键末段。
        title: 标题（缺省带前缀）。
        content: 正文 HTML。
        category_path: 分类路径（缺省根分类）。
        status: `published` / `offline`。
        target_type: 目标类型。
        target_key: 目标键（缺省模块级）。
        locales: 语言清单（缺省 zh-CN / en-US）。
        provenance: 来源留痕（缺省 manual）。
        is_top: 是否置顶。

    Returns:
        ConcurrentStableDict[str, object]: 文章 YAML 内容。
    """
    locale_codes = locales or ConcurrentStableFrozenList(("zh-CN", "en-US"))
    texts: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for locale in locale_codes:
        locale_title = title or f"{prefix} 标题"
        locale_content = content if locale == "zh-CN" else content.replace("这是帮助正文。", "This is help content.")
        if locale != "zh-CN":
            locale_title = f"{locale_title} (EN)"
        texts.set(locale, {"title": locale_title, "content": locale_content})
    target: ConcurrentStableDict[str, object] = ConcurrentStableDict({"type": target_type})
    if target_type != "global":
        target.set("key", target_key or module_key(prefix))
    return ConcurrentStableDict(
        {
            "source_key": f"{product_key}.{prefix}.obj.{suffix}",
            "category_path": category_path or f"{prefix}_cat",
            "status": status,
            "is_top": is_top,
            "targets": [dict(target)],
            "locales": dict(texts),
            "provenance": dict(provenance or ConcurrentStableDict({"author": "manual"})),
        }
    )


def write_package(
    root: Path,
    *,
    product_key: str,
    version: str = "1.0.0",
    prefix: str,
    articles: ConcurrentStableList[ConcurrentStableDict[str, object]] | None = None,
    categories: ConcurrentStableList[ConcurrentStableDict[str, object]] | None = None,
    extra_manifest: ConcurrentStableDict[str, object] | None = None,
) -> Path:
    """写入一个最小帮助包并回写校验和。

    Args:
        root: 包目录（不存在则创建）。
        product_key: 产品键。
        version: 包版本。
        prefix: 用例命名空间前缀（默认分类路径 / 标题用）。
        articles: 文章（缺省一篇模块级文章）。
        categories: 分类（缺省根分类）。
        extra_manifest: 追加 / 覆盖清单字段。

    Returns:
        Path: `package.yaml` 路径。
    """
    root.mkdir(parents=True, exist_ok=True)
    categories_dir = root / "categories.yaml"
    articles_dir = root / "articles"
    articles_dir.mkdir(exist_ok=True)

    default_categories = [
        {"path": f"{prefix}_cat", "sort": 10},
        {"path": f"{prefix}_cat/{prefix}_child", "sort": 11},
    ]
    categories_dir.write_text(
        yaml.safe_dump(
            normalize_collections({"categories": categories or default_categories}),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    payloads = articles or [
        article_payload(prefix, product_key=product_key, category_path=f"{prefix}_cat/{prefix}_child")
    ]
    article_paths: ConcurrentStableList[str] = ConcurrentStableList()
    for index, payload in enumerate(payloads):
        relative = f"articles/a{index}.yaml"
        (root / relative).write_text(
            yaml.safe_dump(normalize_collections(payload), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        article_paths.append(relative)

    manifest: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "schema_version": 1,
            "product_key": product_key,
            "package_version": version,
            "includes": {"categories": "categories.yaml", "articles": article_paths},
        }
    )
    if extra_manifest:
        manifest.update(extra_manifest)
    manifest_path = root / "package.yaml"
    manifest_path.write_text(
        yaml.safe_dump(normalize_collections(manifest), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    write_checksum(manifest_path)
    return manifest_path


@asynccontextmanager
async def session_opener(session: DbSession) -> AsyncGenerator[DbSession]:
    """测试用会话开合口（复用共享事务会话）。

    Args:
        session: 共享租户库会话。

    Yields:
        DbSession: 同一会话。
    """
    yield session
