"""帮助包规格测试：清单 / includes / 校验和 / 结构校验（08_03）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import (
    HelpAnchorUnresolvedError,
    HelpCategoryPathUnresolvedError,
    HelpPackageChecksumMismatchError,
    HelpPackageInvalidError,
)
from bms_core.testing.namespace import Namespace
from bms_platform.domains.help.package_spec import (
    compute_checksum,
    filter_for_tenant,
    filter_unknown_targets,
    load_package,
    write_checksum,
)

from ._support import anchor_map, article_payload, module_key, write_package

pytestmark = pytest.mark.kiwi_id(2522)


def test_checksum_roundtrip_and_manifest_fields(tmp_path: Path, ns: Namespace) -> None:
    """校验和可复现；清单 / 分类 / 文章被正确解析。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    checksum = compute_checksum(package)
    spec = load_package(package)
    assert spec.checksum == checksum
    assert spec.product_key == ns.prefix
    assert spec.package_version == "1.0.0"
    assert spec.declared_article_count == 1
    assert len(spec.categories) == 2
    assert spec.categories[0].path == f"{ns.prefix}_cat"
    assert spec.articles[0].source_key.startswith(f"{ns.prefix}.")
    assert spec.articles[0].provenance.author == "manual"


def test_checksum_mismatch_is_rejected(tmp_path: Path, ns: Namespace) -> None:
    """篡改被引文件后校验和不符，整包拒收。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    article = package.parent / "articles" / "a0.yaml"
    article.write_text(article.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    with pytest.raises(HelpPackageChecksumMismatchError, match="checksum 不符"):
        load_package(package)


def test_manifest_validation(tmp_path: Path, ns: Namespace) -> None:
    """未知字段 / 版本 / 空 includes 均拒收。"""
    package = write_package(
        tmp_path / "unknown",
        product_key=ns.prefix,
        prefix=ns.prefix,
        extra_manifest=ConcurrentStableDict({"unexpected": True}),
    )
    with pytest.raises(HelpPackageInvalidError, match="未知字段"):
        load_package(package)

    package = write_package(tmp_path / "bad-version", product_key=ns.prefix, prefix=ns.prefix, version="1.0")
    with pytest.raises(HelpPackageInvalidError, match="package_version 非法"):
        load_package(package)

    package = write_package(tmp_path / "no-schema", product_key=ns.prefix, prefix=ns.prefix)
    manifest = package.read_text(encoding="utf-8").replace("schema_version: 1\n", "")
    package.write_text(manifest, encoding="utf-8")
    write_checksum(package)
    with pytest.raises(HelpPackageInvalidError, match="schema_version"):
        load_package(package)


def test_article_validation_and_lenient(tmp_path: Path, ns: Namespace) -> None:
    """无效文章严格模式拒收，宽松模式跳过并告警。"""
    bad = article_payload(ns.prefix, product_key=ns.prefix, suffix="bad")
    bad["targets"] = ConcurrentStableList([ConcurrentStableDict({"type": "module", "key": "not-a-key"})])
    good = article_payload(ns.prefix, product_key=ns.prefix)
    package = write_package(
        tmp_path / "pkg",
        product_key=ns.prefix,
        prefix=ns.prefix,
        articles=ConcurrentStableList([bad, good]),
    )
    with pytest.raises(HelpPackageInvalidError, match="targets"):
        load_package(package)
    spec = load_package(package, lenient=True)
    assert len(spec.articles) == 1
    assert spec.declared_article_count == 2
    assert spec.warnings


def test_duplicate_targets_are_rejected(tmp_path: Path, ns: Namespace) -> None:
    """包内两篇文章同目标 → 整包拒收。"""
    first = article_payload(ns.prefix, product_key=ns.prefix, suffix="one")
    second = article_payload(ns.prefix, product_key=ns.prefix, suffix="two")
    package = write_package(
        tmp_path / "pkg",
        product_key=ns.prefix,
        prefix=ns.prefix,
        articles=ConcurrentStableList([first, second]),
    )
    with pytest.raises(HelpPackageInvalidError, match="同一目标"):
        load_package(package)


def test_unknown_target_rejected_or_skipped(tmp_path: Path, ns: Namespace) -> None:
    """锚点不存在时严格拒收 / 宽松跳过。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    spec = load_package(package)
    anchors = anchor_map(ns.prefix)
    anchors.pop(module_key(ns.prefix))
    with pytest.raises(HelpAnchorUnresolvedError, match="锚点不存在"):
        filter_unknown_targets(spec, anchors, lenient=False)
    filtered = filter_unknown_targets(spec, anchors, lenient=True)
    assert not filtered.articles
    assert filtered.warnings


def test_ai_provenance_requires_reviewer(tmp_path: Path, ns: Namespace) -> None:
    """AI 来源缺 model / reviewed_by 拒收。"""
    article = article_payload(
        ns.prefix,
        product_key=ns.prefix,
        provenance=ConcurrentStableDict({"author": "ai", "model": "m"}),
    )
    package = write_package(
        tmp_path / "pkg",
        product_key=ns.prefix,
        prefix=ns.prefix,
        articles=ConcurrentStableList([article]),
    )
    with pytest.raises(HelpPackageInvalidError, match="reviewed_by"):
        load_package(package)


def test_category_parent_order(tmp_path: Path, ns: Namespace) -> None:
    """子分类先于父级声明 → 拒收。"""
    package = write_package(
        tmp_path / "pkg",
        product_key=ns.prefix,
        prefix=ns.prefix,
        categories=ConcurrentStableList(
            [
                ConcurrentStableDict({"path": f"{ns.prefix}_cat/{ns.prefix}_child", "sort": 2}),
                ConcurrentStableDict({"path": f"{ns.prefix}_cat", "sort": 1}),
            ]
        ),
    )
    with pytest.raises(HelpPackageInvalidError, match="父级未先出现"):
        load_package(package)


def test_locale_normalization_and_frozen_collections(tmp_path: Path, ns: Namespace) -> None:
    """语言标识归一为 IETF 标准形态。"""
    article = article_payload(ns.prefix, product_key=ns.prefix, locales=ConcurrentStableFrozenList(("zh-cn",)))
    package = write_package(
        tmp_path / "pkg",
        product_key=ns.prefix,
        prefix=ns.prefix,
        articles=ConcurrentStableList([article]),
    )
    spec = load_package(package)
    assert list(spec.articles[0].locales) == ["zh-CN"]


def test_generated_at_is_parsed_and_checksum_stable(tmp_path: Path, ns: Namespace) -> None:
    """清单 generated_at（YAML 日期时间）可参与规范化校验和。"""
    package = write_package(
        tmp_path / "pkg",
        product_key=ns.prefix,
        prefix=ns.prefix,
        extra_manifest=ConcurrentStableDict({"generated_at": "2026-11-17T00:00:00Z"}),
    )
    spec = load_package(package)
    assert spec.generated_at is not None
    assert spec.generated_at.year == 2026


def test_invalid_checksum_format_and_include_errors(tmp_path: Path, ns: Namespace) -> None:
    """校验和格式 / includes 越界 / 缺失文件分别拒收。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    raw = package.read_text(encoding="utf-8")
    package.write_text(raw.replace("sha256:", "sha256:bad", 1), encoding="utf-8")
    with pytest.raises(HelpPackageChecksumMismatchError, match="格式非法"):
        load_package(package)

    bad_include = write_package(tmp_path / "bad-include", product_key=ns.prefix, prefix=ns.prefix)
    manifest = bad_include.read_text(encoding="utf-8").replace("articles/a0.yaml", "../evil.yaml")
    bad_include.write_text(manifest, encoding="utf-8")
    with pytest.raises(HelpPackageInvalidError, match="不得包含"):
        compute_checksum(bad_include)

    missing = write_package(tmp_path / "missing", product_key=ns.prefix, prefix=ns.prefix)
    manifest = missing.read_text(encoding="utf-8").replace("articles/a0.yaml", "articles/missing.yaml")
    missing.write_text(manifest, encoding="utf-8")
    with pytest.raises(HelpPackageInvalidError, match="不存在"):
        compute_checksum(missing)


def test_top_level_not_mapping(tmp_path: Path) -> None:
    """清单顶层不是映射 → 拒收。"""
    manifest = tmp_path / "package.yaml"
    manifest.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(HelpPackageInvalidError, match="顶层须为映射"):
        load_package(manifest)


def test_article_field_errors(tmp_path: Path, ns: Namespace) -> None:
    """文章字段非法逐个拒收。"""
    cases: ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]] = ConcurrentStableList()
    unknown = article_payload(ns.prefix, product_key=ns.prefix)
    unknown["unexpected"] = True
    cases.add(("未知字段", unknown))
    bad_source = article_payload(ns.prefix, product_key=ns.prefix)
    bad_source["source_key"] = "Bad.Key"
    cases.add(("source_key", bad_source))
    bad_status = article_payload(ns.prefix, product_key=ns.prefix)
    bad_status["status"] = "draft"
    cases.add(("status", bad_status))
    bad_top = article_payload(ns.prefix, product_key=ns.prefix)
    bad_top["is_top"] = "yes"
    cases.add(("is_top", bad_top))
    bad_locale = article_payload(ns.prefix, product_key=ns.prefix, locales=ConcurrentStableFrozenList(("bad_locale",)))
    cases.add(("语言", bad_locale))
    empty = article_payload(ns.prefix, product_key=ns.prefix, content="")
    cases.add(("content", empty))
    bad_author = article_payload(
        ns.prefix,
        product_key=ns.prefix,
        provenance=ConcurrentStableDict({"author": "robot"}),
    )
    cases.add(("author", bad_author))
    empty_locales = article_payload(ns.prefix, product_key=ns.prefix)
    empty_locales["locales"] = ConcurrentStableDict()
    cases.add(("locales", empty_locales))

    for index, (label, payload) in enumerate(cases):
        package = write_package(
            tmp_path / f"case-{index}",
            product_key=ns.prefix,
            prefix=ns.prefix,
            articles=ConcurrentStableList([payload]),
        )
        try:
            load_package(package)
        except HelpPackageInvalidError as exc:
            assert label in str(exc), f"case {index} {label} 报错不含标签：{exc}"
            continue
        raise AssertionError(f"case {index} {label} 未拒收")


def test_filter_for_tenant_locale_and_category(tmp_path: Path, ns: Namespace) -> None:
    """租户默认语言缺失 / 分类不可解析的严格与宽松分支。"""
    article = article_payload(
        ns.prefix,
        product_key=ns.prefix,
        locales=ConcurrentStableFrozenList(("zh-CN",)),
        category_path=f"{ns.prefix}_cat",
    )
    package = write_package(
        tmp_path / "pkg",
        product_key=ns.prefix,
        prefix=ns.prefix,
        articles=ConcurrentStableList([article]),
    )
    spec = load_package(package)
    with pytest.raises(HelpPackageInvalidError, match="默认语言"):
        filter_for_tenant(
            spec, default_locale="en-US", category_paths=ConcurrentStableList([f"{ns.prefix}_cat"]), lenient=False
        )
    assert not filter_for_tenant(
        spec, default_locale="en-US", category_paths=ConcurrentStableList([f"{ns.prefix}_cat"]), lenient=True
    ).articles
    with pytest.raises(HelpCategoryPathUnresolvedError, match="分类路径"):
        filter_for_tenant(spec, default_locale="zh-CN", category_paths=ConcurrentStableList(), lenient=False)
    assert not filter_for_tenant(
        spec, default_locale="zh-CN", category_paths=ConcurrentStableList(), lenient=True
    ).articles
