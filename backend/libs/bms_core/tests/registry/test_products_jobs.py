"""产品清单作业声明用例：字段校验与跨清单对账。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.registry import products
from bms_core.registry.products import CatalogError, ProductManifest

pytestmark = pytest.mark.kiwi_id(2375)


def _job(**overrides: object) -> ConcurrentStableDict[str, object]:
    """构造作业声明原始映射。"""
    data: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "job_type": "demo.echo",
            "service": "demo",
            "domain": "demo",
            "handler": "bms_demo.jobs:handler",
            "description": "演示作业",
        }
    )
    data.update(overrides)
    return data


def test_job_record_rejects_empty_description() -> None:
    """description 只有空白：拒绝（运营侧无法识别）。"""
    with pytest.raises(CatalogError, match="description 不得为空"):
        products._job_record(_job(description="  "), scope="jobs")  # pyright: ignore[reportPrivateUsage]


def test_job_record_rejects_bad_payload_version() -> None:
    """payload_version 非 X.Y.Z：拒绝。"""
    with pytest.raises(CatalogError, match=r"payload_version 须为 X\.Y\.Z"):
        products._job_record(_job(payload_version="1.0"), scope="jobs")  # pyright: ignore[reportPrivateUsage]


def test_positive_and_non_negative_int_reject_invalid() -> None:
    """数值配置：正整数字段拒 0；非负整数字段拒负数。"""
    with pytest.raises(CatalogError, match="须为正整数"):
        products._positive_int(ConcurrentStableDict({"n": 0}), "n", 1, scope="x")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(CatalogError, match="须为非负整数"):
        products._non_negative_int(ConcurrentStableDict({"n": -1}), "n", 0, scope="x")  # pyright: ignore[reportPrivateUsage]


def test_validate_jobs_reports_undeclared_service_and_domain() -> None:
    """对账：提供方服务 / 业务域未在清单声明即报错。"""
    manifest = SimpleNamespace(
        product_key="demo",
        services=[SimpleNamespace(service_key="other")],
        domains=[SimpleNamespace(domain_key="other_domain")],
        jobs=[SimpleNamespace(job_type="demo.echo", service="demo", domain="demo")],
    )
    errors = products._validate_jobs(  # pyright: ignore[reportPrivateUsage]
        cast("ConcurrentStableList[ProductManifest]", ConcurrentStableList([manifest])),
        ConcurrentStableList([Path("demo.toml")]),
    )
    assert any("提供方服务未在本清单" in item for item in errors)
    assert any("提供方业务域未在本清单" in item for item in errors)


def test_validate_jobs_reports_cross_product_conflict() -> None:
    """对账：同一作业类型被不同产品 / 服务声明即撞键。"""
    first = SimpleNamespace(
        product_key="demo",
        services=[SimpleNamespace(service_key="demo")],
        domains=[SimpleNamespace(domain_key="demo")],
        jobs=[SimpleNamespace(job_type="demo.echo", service="demo", domain="demo")],
    )
    second = SimpleNamespace(
        product_key="other",
        services=[SimpleNamespace(service_key="other")],
        domains=[SimpleNamespace(domain_key="other")],
        jobs=[SimpleNamespace(job_type="demo.echo", service="other", domain="other")],
    )
    errors = products._validate_jobs(  # pyright: ignore[reportPrivateUsage]
        cast("ConcurrentStableList[ProductManifest]", ConcurrentStableList([first, second])),
        ConcurrentStableList([Path("a.toml"), Path("b.toml")]),
    )
    assert any("跨产品撞键" in item for item in errors)


def test_validate_jobs_reports_duplicate_in_same_manifest() -> None:
    """对账：同一清单内重复声明作业类型即报错。"""
    job = SimpleNamespace(job_type="demo.echo", service="demo", domain="demo")
    manifest = SimpleNamespace(
        product_key="demo",
        services=[SimpleNamespace(service_key="demo")],
        domains=[SimpleNamespace(domain_key="demo")],
        jobs=[job, job],
    )
    errors = products._validate_jobs(  # pyright: ignore[reportPrivateUsage]
        cast("ConcurrentStableList[ProductManifest]", ConcurrentStableList([manifest])),
        ConcurrentStableList([Path("demo.toml")]),
    )
    assert any("同一清单内作业类型重复声明" in item for item in errors)


def test_validate_jobs_accepts_consistent_manifest() -> None:
    """对账：声明一致时无错误。"""
    manifest = SimpleNamespace(
        product_key="demo",
        services=[SimpleNamespace(service_key="demo")],
        domains=[SimpleNamespace(domain_key="demo")],
        jobs=[SimpleNamespace(job_type="demo.echo", service="demo", domain="demo")],
    )
    errors = products._validate_jobs(  # pyright: ignore[reportPrivateUsage]
        cast("ConcurrentStableList[ProductManifest]", ConcurrentStableList([manifest])),
        ConcurrentStableList([Path("demo.toml")]),
    )
    assert errors == []
