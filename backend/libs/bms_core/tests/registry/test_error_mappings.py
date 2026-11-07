"""错误码映射声明（07D 需求 02-2）：`[[errcodes]].maps_from` 的装载期校验。

覆盖详细设计 §3.5 用例 1~8：
- 合法声明解析与字段回读；
- M1 源码须为已登记 5 位平台码；M2 非自映射；M3 状态语义一致；M4 系统性失败禁止表；
- 同源唯一（跨产品撞码）与同清单重复声明。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.registry.products import SKIP_CONTRACT_ENV, inspect_product_manifests

_SERVICES = """\
[[services]]
module_key = "{product}"
service_key = "{product}"
name = "演示服务"
table_prefix = "{product}_"
errcode_segment = "{segment}"
event_domain = "{product}"
service_group = "product"
product_key = "{product}"
"""


pytestmark = pytest.mark.kiwi_id(2450)


def _manifest(*, product: str = "demo", segment: str = "39", body: str = "") -> str:
    """拼一份最小清单（产品档案 + 服务行 + 追加段）。

    Args:
        product: 产品键。
        segment: 服务行段位。
        body: 追加段文本。

    Returns:
        str: 清单 TOML 文本。
    """
    text = f'product_key = "{product}"\n\n[[products]]\nproduct_key = "{product}"\nname = "演示产品"\n\n'
    return text + _SERVICES.format(product=product, segment=segment) + "\n" + body


def _errcode(
    *,
    code: int = 390011,
    http_status: int = 403,
    message_key: str = "demo.error.tenant_suspended",
    maps_from: str = "",
) -> str:
    """拼一条 `[[errcodes]]` 声明（可带 `maps_from`）。

    Args:
        code: 错误码。
        http_status: 传输层状态。
        message_key: 文案键。
        maps_from: `maps_from` 数组文本（如 `[80002]`）。

    Returns:
        str: TOML 片段。
    """
    text = (
        "[[errcodes]]\n"
        f"code = {code}\n"
        'domain = "demo"\n'
        f"http_status = {http_status}\n"
        f'message_key = "{message_key}"\n'
        'severity = "warning"\n'
        'description = "演示"\n'
    )
    if maps_from:
        text += f"maps_from = {maps_from}\n"
    return text


def _write(tmp_path: Path, text: str, name: str = "demo.toml") -> Path:
    """把清单写到临时仓目录。

    Args:
        tmp_path: 临时目录。
        text: 清单文本。
        name: 文件名。

    Returns:
        Path: 清单路径。
    """
    path = tmp_path / "repo" / "deploy" / "registry" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _skip_contract_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """跳过对端契约文件检查（用例只关注映射校验，不铺契约文件）。

    Args:
        monkeypatch: pytest 补丁器。
    """
    monkeypatch.setenv(SKIP_CONTRACT_ENV, "1")


def _inspect(path: Path) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str]]:
    """装载并返回（错误, 告警）。

    Args:
        path: 清单路径。

    Returns:
        tuple[ConcurrentStableList[str], ConcurrentStableList[str]]: （errors, warnings）。
    """
    inspection = inspect_product_manifests(ConcurrentStableList((path,)))
    return inspection.errors, inspection.warnings


def test_valid_mapping_declared(tmp_path: Path) -> None:
    """合法声明：`maps_from` 解析进记录。"""
    path = _write(tmp_path, _manifest(body=_errcode(maps_from="[80002]")))
    errors, _ = _inspect(path)
    assert list(errors) == []
    manifest = inspect_product_manifests(ConcurrentStableList((path,))).manifests[0]
    assert list(manifest.error_codes[0].maps_from) == [80002]


def test_source_must_be_five_digit_platform_code(tmp_path: Path) -> None:
    """M1：源码须为 5 位平台码（6 位产品码即拒）。"""
    path = _write(tmp_path, _manifest(body=_errcode(maps_from="[390001]")))
    errors, _ = _inspect(path)
    assert any("5 位平台码" in item for item in errors)


@pytest.mark.parametrize("source", [89999, 88888])
def test_source_must_be_registered(tmp_path: Path, source: int) -> None:
    """校验一：源码须在平台错误码登记。"""
    path = _write(tmp_path, _manifest(body=_errcode(maps_from=f"[{source}]")))
    errors, _ = _inspect(path)
    assert any("未在平台错误码登记" in item for item in errors)


def test_status_semantics_must_match(tmp_path: Path) -> None:
    """M3：不得改变 HTTP 状态语义（80002 是 403，声明 400 即拒）。"""
    path = _write(tmp_path, _manifest(body=_errcode(http_status=400, maps_from="[80002]")))
    errors, _ = _inspect(path)
    assert any("不得改变状态语义" in item for item in errors)


def test_systemic_failure_source_forbidden(tmp_path: Path) -> None:
    """M4：系统性失败码（10006 / 10007）不得被承接。"""
    for source in (10006, 10007):
        path = _write(tmp_path, _manifest(body=_errcode(http_status=503, maps_from=f"[{source}]")), name="demo.toml")
        errors, _ = _inspect(path)
        assert any("系统性失败码" in item for item in errors), source


def test_duplicate_source_in_same_record(tmp_path: Path) -> None:
    """同一记录重复声明源码即拒。"""
    path = _write(tmp_path, _manifest(body=_errcode(maps_from="[80002, 80002]")))
    errors, _ = _inspect(path)
    assert any("重复声明同一源码" in item for item in errors)


def test_same_source_two_products_rejected(tmp_path: Path) -> None:
    """M5：同一源码被两个产品码承接 → 跨产品撞码。"""
    first = _write(
        tmp_path,
        _manifest(product="demo", body=_errcode(code=390011, maps_from="[80002]")),
        name="demo.toml",
    )
    second = _write(
        tmp_path,
        _manifest(
            product="other",
            segment="38",
            body=_errcode(code=380011, message_key="other.error.tenant_suspended", maps_from="[80002]"),
        ),
        name="other.toml",
    )
    inspection = inspect_product_manifests(ConcurrentStableList((first, second)))
    assert any("错误码映射同源撞码" in item for item in inspection.errors)


def test_same_source_same_target_is_idempotent(tmp_path: Path) -> None:
    """同源同目标（重复装载同一清单）不报撞码。"""
    text = _manifest(body=_errcode(maps_from="[80002]"))
    first = _write(tmp_path, text, name="demo.toml")
    second = _write(tmp_path, text, name="demo-copy.toml")
    inspection = inspect_product_manifests(ConcurrentStableList((first, second)))
    assert not any("同源撞码" in item for item in inspection.errors)


def test_maps_from_type_invalid(tmp_path: Path) -> None:
    """`maps_from` 非整数数组即拒。"""
    path = _write(tmp_path, _manifest(body=_errcode(maps_from='["80002"]')))
    errors, _ = _inspect(path)
    assert any("maps_from" in item for item in errors)


@pytest.mark.parametrize("raw", ["[80002]", "[80001, 80002]"])
def test_multiple_sources_allowed(tmp_path: Path, raw: str) -> None:
    """一条记录可承接多个源码（状态须分别一致）。"""
    path = _write(tmp_path, _manifest(body=_errcode(http_status=403, maps_from=raw)))
    errors, _ = _inspect(path)
    if raw == "[80001, 80002]":
        # 80001 是 404，与 403 不一致 → 拒（状态语义不可折中）
        assert any("不得改变状态语义" in item for item in errors)
    else:
        assert list(errors) == []


def test_maps_from_absent_means_no_mapping(tmp_path: Path) -> None:
    """不声明 `maps_from` ⇒ 空映射（向后兼容）。"""
    path = _write(tmp_path, _manifest(body=_errcode()))
    errors, _ = _inspect(path)
    assert list(errors) == []
    manifest = inspect_product_manifests(ConcurrentStableList((path,))).manifests[0]
    assert list(manifest.error_codes[0].maps_from) == []


def test_maps_from_must_be_array(tmp_path: Path) -> None:
    """`maps_from` 非数组（字符串）即拒。"""
    path = _write(tmp_path, _manifest(body=_errcode(maps_from='"80002"')))
    errors, _ = _inspect(path)
    assert any("maps_from 须为整数数组" in item for item in errors)


def test_maps_from_rejects_bool_element(tmp_path: Path) -> None:
    """元素为布尔即拒（布尔不是合法整数码）。"""
    path = _write(tmp_path, _manifest(body=_errcode(maps_from="[true]")))
    errors, _ = _inspect(path)
    assert any("maps_from 元素须为整数" in item for item in errors)


def test_quota_limit_blank_and_invalid(tmp_path: Path) -> None:
    """配额软限空串按缺省（`None`）；非整数即拒。"""
    blank = (
        "[[data_sources]]\n"
        'data_source_key = "demo_usage"\n'
        'name = "演示用量"\n'
        'kind = "quota"\n'
        'data_source = "demo.demo.tenant_usage"\n'
        'origin = "product"\n'
        'product_key = "demo"\n'
        'path = "/api/v1/demo/tenant-usage"\n'
        'quota_dimensions = ["topic_count"]\n'
        'quota_unit = "count"\n'
        'quota_period = "day"\n'
        'quota_soft_limit = ""\n'
    )
    path = _write(tmp_path, _manifest(body=blank))
    errors, _ = _inspect(path)
    assert list(errors) == []

    explicit = blank.replace('quota_soft_limit = ""', "quota_soft_limit = 80")
    path = _write(tmp_path, _manifest(body=explicit))
    errors, _ = _inspect(path)
    assert list(errors) == []
    manifest = inspect_product_manifests(ConcurrentStableList((path,))).manifests[0]
    assert manifest.data_sources[0].quota_soft_limit == 80

    invalid = blank.replace('quota_soft_limit = ""', 'quota_soft_limit = "many"')
    path = _write(tmp_path, _manifest(body=invalid))
    errors, _ = _inspect(path)
    assert any("quota_soft_limit 须为整数" in item for item in errors)
