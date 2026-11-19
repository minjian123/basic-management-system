"""帮助包装载 / 卸载测试：幂等 / 升级 / 覆盖层 / 下线 / 冲突（08_03）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    HelpCategoryPathUnresolvedError,
    HelpPackageInvalidError,
    HelpPackageNotLoadedError,
    HelpPackageVersionConflictError,
)
from bms_core.help.values import (
    ARTICLE_SOURCE_TENANT,
    ARTICLE_STATUS_OFFLINE,
    ARTICLE_STATUS_PUBLISHED,
    PACKAGE_STATUS_UNLOADED,
)
from bms_core.models.platform.help import SysHelpArticle, SysHelpCategory, SysHelpPackage
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import write_session
from bms_platform.domains.help.package_spec import load_package
from bms_platform.domains.help.repositories.content import HelpContentRepository
from bms_platform.domains.help.services.package import HelpLoadCounts, HelpPackageService

from ._support import anchor_map, article_payload, button_key, form_key, module_key, write_package

pytestmark = pytest.mark.kiwi_id(2522)


async def test_same_version_reload_is_noop(shared_tenant_engine: AsyncEngine, tmp_path: Path, ns: Namespace) -> None:
    """同版本同校验和重复装载零变更。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    spec = load_package(package)
    async with write_session(shared_tenant_engine) as session:
        service = HelpPackageService(session)
        first = await service.load(spec, anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        assert first.counts == HelpLoadCounts(
            articles_new=1,
            categories_created=2,
        )
        again = await service.load(spec, anchors=anchor_map(ns.prefix), apply=False, lenient=False)
        assert again.package_action == "unchanged"
        assert again.counts == HelpLoadCounts()
        rows = await HelpContentRepository(session).load_package_articles(spec.product_key)
        assert len(rows) == 1


async def test_upgrade_counts_match_dry_run(shared_tenant_engine: AsyncEngine, tmp_path: Path, ns: Namespace) -> None:
    """升级计数与 dry-run 一致；新增 / 更新 / 下线各一。"""
    category = f"{ns.prefix}_cat/{ns.prefix}_child"
    first = article_payload(ns.prefix, product_key=ns.prefix, suffix="create", title="v1", category_path=category)
    removed = article_payload(
        ns.prefix,
        product_key=ns.prefix,
        suffix="old",
        title="old",
        category_path=category,
        target_type="form",
        target_key=form_key(ns.prefix),
    )
    v1 = write_package(
        tmp_path / "v1",
        product_key=ns.prefix,
        prefix=ns.prefix,
        articles=ConcurrentStableList([first, removed]),
    )
    updated = article_payload(ns.prefix, product_key=ns.prefix, suffix="create", title="v2", category_path=category)
    added = article_payload(
        ns.prefix,
        product_key=ns.prefix,
        suffix="new",
        title="new",
        category_path=category,
        target_type="action",
        target_key=button_key(ns.prefix),
    )
    v2 = write_package(
        tmp_path / "v2",
        product_key=ns.prefix,
        version="2.0.0",
        prefix=ns.prefix,
        articles=ConcurrentStableList([updated, added]),
    )
    async with write_session(shared_tenant_engine) as session:
        service = HelpPackageService(session)
        await service.load(load_package(v1), anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        dry = await service.load(load_package(v2), anchors=anchor_map(ns.prefix), apply=False, lenient=False)
        applied = await service.load(load_package(v2), anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        assert dry.counts == applied.counts
        assert applied.counts.articles_new == 1
        assert applied.counts.articles_updated == 1
        assert applied.counts.articles_offline == 1
        assert applied.counts.articles_skipped == 0
        rows = await HelpContentRepository(session).load_package_articles(ns.prefix)
        by_key = {record.article.source_key: record.article for record in rows}
        assert by_key[f"{ns.prefix}.{ns.prefix}.obj.create"].title == "v2"
        assert by_key[f"{ns.prefix}.{ns.prefix}.obj.old"].status == ARTICLE_STATUS_OFFLINE
        assert by_key[f"{ns.prefix}.{ns.prefix}.obj.new"].status == ARTICLE_STATUS_PUBLISHED


async def test_local_override_is_kept(shared_tenant_engine: AsyncEngine, tmp_path: Path, ns: Namespace) -> None:
    """local_override 文章升级不覆盖，计 skipped_override。"""
    first = write_package(tmp_path / "v1", product_key=ns.prefix, prefix=ns.prefix)
    spec = load_package(first)
    updated = article_payload(
        ns.prefix, product_key=ns.prefix, title="v2", category_path=f"{ns.prefix}_cat/{ns.prefix}_child"
    )
    second = write_package(
        tmp_path / "v2",
        product_key=ns.prefix,
        version="2.0.0",
        prefix=ns.prefix,
        articles=ConcurrentStableList([updated]),
    )
    async with write_session(shared_tenant_engine) as session:
        service = HelpPackageService(session)
        await service.load(spec, anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        record = (await HelpContentRepository(session).load_package_articles(ns.prefix))[0]
        record.article.local_override = True
        await session.flush()
        outcome = await service.load(load_package(second), anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        assert outcome.counts.articles_skipped_override == 1
        assert record.article.title != "v2"


async def test_unload_keeps_tenant_articles(shared_tenant_engine: AsyncEngine, tmp_path: Path, ns: Namespace) -> None:
    """卸载按产品下线来源文章，租户自建保留。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    spec = load_package(package)
    async with write_session(shared_tenant_engine) as session:
        service = HelpPackageService(session)
        await service.load(spec, anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        category = (
            (await session.execute(select(SysHelpCategory).where(SysHelpCategory.name == f"{ns.prefix}_cat")))
            .scalars()
            .first()
        )
        assert category is not None
        tenant_article = SysHelpArticle(
            category_id=int(category.id),
            title="租户自建",
            content="<p>tenant</p>",
            status=ARTICLE_STATUS_PUBLISHED,
            source=ARTICLE_SOURCE_TENANT,
            source_key=None,
            package_id=None,
            local_override=False,
            generated_by="manual",
        )
        session.add(tenant_article)
        await session.flush()
        outcome = await service.unload(ns.prefix, apply=True)
        assert outcome.counts.articles_offline == 1
        assert tenant_article.status == ARTICLE_STATUS_PUBLISHED
        packages = (
            (await session.execute(select(SysHelpPackage).where(SysHelpPackage.product_key == ns.prefix)))
            .scalars()
            .all()
        )
        assert all(row.status == PACKAGE_STATUS_UNLOADED for row in packages)
        assert (await service.unload(ns.prefix, apply=False)).counts.articles_offline == 0


async def test_target_conflicts(shared_tenant_engine: AsyncEngine, tmp_path: Path, ns: Namespace) -> None:
    """产品包遇平台内建同目标跳过；跨产品同优先级跳过。"""
    builtin = write_package(tmp_path / "builtin", product_key="platform", prefix=ns.prefix)
    product_a = write_package(tmp_path / "a", product_key=ns.prefix, prefix=ns.prefix)
    anchors = anchor_map(ns.prefix)
    async with write_session(shared_tenant_engine) as session:
        service = HelpPackageService(session)
        await service.load(load_package(builtin), anchors=anchors, apply=True, lenient=False)
        skipped = await service.load(load_package(product_a), anchors=anchors, apply=True, lenient=False)
        assert skipped.counts.articles_skipped_conflict == 1
        assert skipped.counts.articles_new == 0
        # 内建之外另取一个目标，让产品 A 先占、产品 B 再撞
        another = module_key(f"{ns.prefix}_x")
        anchors.set(another, anchors[module_key(ns.prefix)])
        first = article_payload(
            ns.prefix,
            product_key=ns.prefix,
            suffix="x",
            category_path=f"{ns.prefix}_cat/{ns.prefix}_child",
            target_key=another,
        )
        second = article_payload(
            f"{ns.prefix}_b",
            product_key=f"{ns.prefix}_b",
            suffix="x",
            category_path=f"{ns.prefix}_cat/{ns.prefix}_child",
            target_key=another,
        )
        package_a = write_package(
            tmp_path / "ax",
            product_key=ns.prefix,
            version="2.0.0",
            prefix=ns.prefix,
            articles=ConcurrentStableList([first]),
        )
        package_b = write_package(
            tmp_path / "bx",
            product_key=f"{ns.prefix}_b",
            prefix=ns.prefix,
            articles=ConcurrentStableList([second]),
        )
        await service.load(load_package(package_a), anchors=anchors, apply=True, lenient=False)
        conflict = await service.load(load_package(package_b), anchors=anchors, apply=True, lenient=False)
        assert conflict.counts.articles_skipped_conflict == 1


async def test_version_and_category_errors(shared_tenant_engine: AsyncEngine, tmp_path: Path, ns: Namespace) -> None:
    """同版本不同校验和 / 低版本 / 分类不可解析 / 未装载分别报对应错误。"""
    v1 = write_package(tmp_path / "v1", product_key=ns.prefix, prefix=ns.prefix)
    changed = article_payload(
        ns.prefix, product_key=ns.prefix, title="changed", category_path=f"{ns.prefix}_cat/{ns.prefix}_child"
    )
    same_version = write_package(
        tmp_path / "same",
        product_key=ns.prefix,
        prefix=ns.prefix,
        articles=ConcurrentStableList([changed]),
    )
    lower = write_package(tmp_path / "lower", product_key=ns.prefix, version="0.9.0", prefix=ns.prefix)
    missing_category = article_payload(
        ns.prefix,
        product_key=ns.prefix,
        suffix="missing",
        category_path=f"{ns.prefix}_missing",
    )
    valid = article_payload(
        ns.prefix,
        product_key=ns.prefix,
        suffix="valid",
        target_type="form",
        target_key=form_key(ns.prefix),
    )
    bad_category = write_package(
        tmp_path / "bad-cat",
        product_key=ns.prefix,
        version="3.0.0",
        prefix=ns.prefix,
        articles=ConcurrentStableList([missing_category, valid]),
    )
    async with write_session(shared_tenant_engine) as session:
        service = HelpPackageService(session)
        await service.load(load_package(v1), anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        with pytest.raises(HelpPackageVersionConflictError, match="同版本校验和不同"):
            await service.load(load_package(same_version), anchors=anchor_map(ns.prefix), apply=False, lenient=False)
        with pytest.raises(HelpPackageVersionConflictError, match="不允许降级"):
            await service.load(load_package(lower), anchors=anchor_map(ns.prefix), apply=False, lenient=False)
        with pytest.raises(HelpCategoryPathUnresolvedError, match="分类路径不可解析"):
            await service.load(load_package(bad_category), anchors=anchor_map(ns.prefix), apply=False, lenient=False)
        lenient = await service.load(
            load_package(bad_category), anchors=anchor_map(ns.prefix), apply=False, lenient=True
        )
        assert lenient.counts.articles_new == 1
        assert lenient.warnings
        with pytest.raises(HelpPackageNotLoadedError):
            await service.unload(f"{ns.prefix}_none", apply=False)


async def test_categories_upsert_by_path(shared_tenant_engine: AsyncEngine, tmp_path: Path, ns: Namespace) -> None:
    """分类已存在只更新 sort，不新建重复行。"""
    v1 = write_package(tmp_path / "v1", product_key=ns.prefix, prefix=ns.prefix)
    v2 = write_package(
        tmp_path / "v2",
        product_key=ns.prefix,
        version="2.0.0",
        prefix=ns.prefix,
        categories=ConcurrentStableList(
            [
                ConcurrentStableDict({"path": f"{ns.prefix}_cat", "sort": 20}),
                ConcurrentStableDict({"path": f"{ns.prefix}_cat/{ns.prefix}_child", "sort": 21}),
            ]
        ),
    )
    async with write_session(shared_tenant_engine) as session:
        service = HelpPackageService(session)
        await service.load(load_package(v1), anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        outcome = await service.load(load_package(v2), anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        assert outcome.counts.categories_updated == 2
        assert outcome.counts.categories_created == 0
        rows = (
            (
                await session.execute(
                    select(SysHelpCategory).where(SysHelpCategory.name.in_([f"{ns.prefix}_cat", f"{ns.prefix}_child"]))
                )
            )
            .scalars()
            .all()
        )
        assert sorted(row.sort for row in rows) == [20, 21]


async def test_lenient_all_invalid_is_rejected(
    shared_tenant_engine: AsyncEngine, tmp_path: Path, ns: Namespace
) -> None:
    """宽松模式过滤后无有效文章时拒绝装载，避免误下线全部文章。"""
    article = article_payload(ns.prefix, product_key=ns.prefix, category_path=f"{ns.prefix}_missing")
    package = write_package(
        tmp_path / "pkg",
        product_key=ns.prefix,
        prefix=ns.prefix,
        articles=ConcurrentStableList([article]),
    )
    async with write_session(shared_tenant_engine) as session:
        with pytest.raises(HelpPackageInvalidError, match="无有效文章"):
            await HelpPackageService(session).load(
                load_package(package), anchors=anchor_map(ns.prefix), apply=False, lenient=True
            )
