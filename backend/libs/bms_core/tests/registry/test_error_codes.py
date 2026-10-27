"""第七类记录（产品错误码）：记录 / 合并视图 / 清单解析 / 装载期两档校验（07B `02_05`）。

覆盖：平台码适配（形态与状态映射）、注册幂等与撞码、清单 `[[errcodes]]` 字段级反例、
跨清单（撞平台码 / 跨产品撞码 / 段位跨产品复用 / 同值幂等）、契约反向两档
（已声明强校验 / 未声明只统计）。

新增用例的 Kiwi 编号由 07B `05_01` 统一登记后回填（本批不标 `kiwi_id`）。
"""

# pyright: reportUnusedFunction=false
import inspect as inspect_module
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from bms_core.core import exceptions as exceptions_module
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.error_codes import ERROR_CODE_HTTP_STATUS, ErrorCode
from bms_core.core.exceptions import BizError, CatalogError
from bms_core.datasource.registry import reset_data_source_records
from bms_core.registry import products as products_module
from bms_core.registry.products import (
    CONTRACT_ERROR_CODES_KEY,
    ProductManifest,
    inspect_product_manifests,
    load_product_manifest,
    register_manifest,
)
from bms_core.services.module_registry import (
    PLATFORM_ERROR_CODE_RECORDS,
    ErrorCodeRecord,
    error_code_view,
    register_error_code_records,
    reset_collaboration_records,
    reset_error_code_records,
    reset_product_records,
    reset_product_routes,
    reset_seed_records,
    reset_service_records,
)

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

_ERROR_CODE = """\
[[errcodes]]
code = {code}
domain = "{domain}"
http_status = {http_status}
message_key = "{message_key}"
severity = "{severity}"
description = "{description}"
"""


def _manifest(
    *,
    product: str = "demo",
    segment: str = "39",
    services: bool = True,
    body: str = "",
) -> str:
    """拼一份最小清单（产品档案 + 服务行 + 追加段）。

    Args:
        product: 产品键。
        segment: 服务行段位。
        services: 是否带服务行。
        body: 追加段文本（`[[errcodes]]` 等）。

    Returns:
        str: 清单 TOML 文本。
    """
    text = f'product_key = "{product}"\n\n[[products]]\nproduct_key = "{product}"\nname = "演示产品"\n\n'
    if services:
        text += _SERVICES.format(product=product, segment=segment) + "\n"
    return text + body


def _errcode(
    *,
    code: int = 390001,
    domain: str = "org",
    http_status: int = 404,
    message_key: str = "demo.error.dept_not_found",
    severity: str = "warning",
    description: str = "部门不存在",
) -> str:
    """拼一条 `[[errcodes]]` 声明。

    Args:
        code: 错误码。
        domain: 业务域。
        http_status: 传输层状态。
        message_key: 文案键。
        severity: 严重级别。
        description: 描述。

    Returns:
        str: TOML 片段。
    """
    return _ERROR_CODE.format(
        code=code,
        domain=domain,
        http_status=http_status,
        message_key=message_key,
        severity=severity,
        description=description,
    )


def _write(tmp_path: Path, text: str, name: str = "demo.toml") -> Path:
    """把清单写到临时仓目录（`<tmp>/repo/deploy/registry/`）。

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


def _write_contract(
    tmp_path: Path,
    *,
    product: str = "demo",
    declared: ConcurrentStableDict[str, ConcurrentStableList[int]] | None = None,
    paths: ConcurrentStableList[str] | None = None,
    raw: str | None = None,
) -> Path:
    """写对端公开契约（`<tmp>/repo/deploy/contracts/<产品>.json`）。

    Args:
        tmp_path: 临时目录。
        product: 产品键（契约文件名）。
        declared: `路径 → x-error-codes` 声明。
        paths: 未声明错误码的路径集合（缺省 `None` 时不写任何路径）。
        raw: 直接指定原始文本（非法声明反例）。

    Returns:
        Path: 契约路径。
    """
    path = tmp_path / "repo" / "deploy" / "contracts" / f"{product}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
        return path
    operations: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    empty_operation: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for item in paths or ConcurrentStableList():
        methods: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        methods.set("get", empty_operation)
        operations.set(item, methods)
    for item, codes in (declared or ConcurrentStableDict[str, ConcurrentStableList[int]]()).items():
        extension: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        extension.set(CONTRACT_ERROR_CODES_KEY, codes)
        operation: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        operation.set("get", extension)
        operations.set(item, operation)
    path.write_text(json.dumps({"paths": _plain(operations)}), encoding="utf-8")
    return path


def _plain(value: object) -> object:
    """把并发集合递归转成可 JSON 序列化的原生结构（写契约夹具用）。

    Args:
        value: 待转换值。

    Returns:
        object: 原生 dict / 原值。
    """
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {str(key): _plain(item) for key, item in mapping.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        sequence = cast("Sequence[object]", value)
        return [_plain(item) for item in sequence]
    return value


def _declared(path: str, *codes: int) -> ConcurrentStableDict[str, ConcurrentStableList[int]]:
    """构造契约侧错误码声明（`路径 → 码清单`）。

    Args:
        path: 契约路径（带前导 `/`）。
        *codes: 声明的错误码（可重复，用于验证去重）。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableList[int]]: 声明映射。
    """
    return ConcurrentStableDict({path: ConcurrentStableList(codes)})


def _record(**overrides: object) -> ErrorCodeRecord:
    """构造一条产品错误码记录（缺省为合法 demo 码）。

    Args:
        **overrides: 字段覆盖。

    Returns:
        ErrorCodeRecord: 记录。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "code": 390001,
            "domain": "org",
            "http_status": 404,
            "message_key": "demo.error.dept_not_found",
            "severity": "warning",
            "description": "部门不存在",
            "product_key": "demo",
            "segment": "39",
        }
    )
    for key, value in overrides.items():
        payload.set(key, value)
    return ErrorCodeRecord(**payload)  # pyright: ignore[reportArgumentType]


def _global_errors(records: ConcurrentStableList[ErrorCodeRecord]) -> ConcurrentStableList[str]:
    """用给定记录走跨清单校验（绕过解析期约束，单测判定分支）。

    Args:
        records: 错误码记录。

    Returns:
        ConcurrentStableList[str]: 校验错误。
    """
    manifests = ConcurrentStableList(
        (ProductManifest(product_key="demo", error_codes=ConcurrentStableFrozenList(records)),)
    )
    sources = ConcurrentStableList((Path("demo.toml"),))
    return products_module._validate_error_codes(manifests, sources)  # pyright: ignore[reportPrivateUsage]


@pytest.fixture(autouse=True)
def _isolate_records() -> Iterator[None]:
    """每例前后清空注入登记表（进程级全局状态，不污染其他用例）。

    Yields:
        None: 用例运行期。
    """

    def _reset() -> None:
        reset_service_records()
        reset_product_records()
        reset_product_routes()
        reset_data_source_records()
        reset_collaboration_records()
        reset_seed_records()
        reset_error_code_records()

    _reset()
    yield
    _reset()


def test_platform_records_cover_enum_and_shape() -> None:
    """平台码适配：与枚举同量同序；5 位、首位 1~9；文案键 `error.{code}`、提供方 `platform`。"""
    members = list(ErrorCode)
    assert len(PLATFORM_ERROR_CODE_RECORDS) == len(members)
    assert list(PLATFORM_ERROR_CODE_RECORDS) == [int(member) for member in members]
    for code, record in PLATFORM_ERROR_CODE_RECORDS.items():
        assert isinstance(record, ErrorCodeRecord)
        assert len(str(code)) == 5 and str(code)[0] in "123456789"
        assert record.segment == str(code)[0]
        assert record.domain == record.product_key == "platform"
        assert record.message_key == f"error.{code}"
        assert str(record.severity) == "error"
        assert record.description == ErrorCode(code).name


def test_platform_http_status_matches_exception_classes() -> None:
    """平台码状态映射 ↔ 异常类实测一致（同码多形态时取其一，如 20012 的 200 / 401 两态）。"""
    statuses: ConcurrentStableDict[int, ConcurrentStableSet[int]] = ConcurrentStableDict()
    for _, member in inspect_module.getmembers(exceptions_module, lambda item: isinstance(item, type)):
        if not isinstance(member, type) or not issubclass(member, BizError) or member is BizError:
            continue
        factory = cast("Callable[[], BizError]", member)
        try:
            error = factory()
        except TypeError:
            continue
        bucket = statuses.get(error.code)
        if bucket is None:
            bucket = ConcurrentStableSet[int]()
            statuses.set(error.code, bucket)
        bucket.add(error.http_status)
    assert len(statuses) > 50
    for code, allowed in statuses.items():
        assert ERROR_CODE_HTTP_STATUS.get(ErrorCode(code), 200) in allowed


def test_register_same_value_is_idempotent_and_conflict_rejected() -> None:
    """注册纪律：同码同值幂等、同码异值即拒（与其余五类记录同构）。"""
    record = _record()
    register_error_code_records(ConcurrentStableList((record,)))
    register_error_code_records(ConcurrentStableList((record,)))
    assert error_code_view()[390001] == record
    with pytest.raises(CatalogError, match="同码异值"):
        register_error_code_records(ConcurrentStableList((_record(http_status=200),)))


def test_error_code_view_merges_platform_and_product() -> None:
    """合并视图：平台码在前 + 产品码在后，逐码一条。"""
    record = _record(code=390051, segment="39")
    register_error_code_records(ConcurrentStableList((record,)))
    view = error_code_view()
    assert len(view) == len(PLATFORM_ERROR_CODE_RECORDS) + 1
    assert list(view)[-1] == 390051
    assert view[390051] == record


def test_error_code_view_rejects_platform_collision() -> None:
    """防御分支：产品码与平台码撞码时视图构建即拒。"""
    platform_code = int(ErrorCode.NOT_FOUND)
    register_error_code_records(ConcurrentStableList((_record(code=platform_code, segment=str(platform_code)[:2]),)))
    with pytest.raises(CatalogError, match="撞码"):
        error_code_view()


def test_load_error_code_fields(tmp_path: Path) -> None:
    """合法声明：字段逐项解析，`product_key` / `segment` 装载期注入。"""
    manifest = load_product_manifest(_write(tmp_path, _manifest(body=_errcode())))
    record = manifest.error_codes[0]
    assert (record.code, record.domain, record.http_status) == (390001, "org", 404)
    assert record.message_key == "demo.error.dept_not_found"
    assert (record.severity, record.description, record.status) == ("warning", "部门不存在", "enabled")
    assert (record.product_key, record.segment) == ("demo", "39")


@pytest.mark.parametrize(
    ("block", "match"),
    [
        ('[[errcodes]]\ncode = "390001"\n', "code 须为整数"),
        (_errcode(code=39001), "6 位"),
        (_errcode(domain="Org"), "domain 形态非法"),
        (_errcode().replace("http_status = 404", 'http_status = "404"'), "http_status 须为整数"),
        (_errcode(http_status=99), "http_status 越界"),
        (_errcode(http_status=600), "http_status 越界"),
        (_errcode(message_key="other.error.dept_not_found"), "message_key"),
        (_errcode(message_key="demo.error.Dept"), "message_key"),
        (_errcode(severity="fatal"), "severity 非法"),
        (_errcode() + 'status = "planned"\n', "status 非法"),
        (_errcode(code=380001), "段位不符"),
        (_errcode() + "\n" + _errcode(), "重复声明"),
    ],
)
def test_error_code_structure_errors(tmp_path: Path, block: str, match: str) -> None:
    """字段级反例：逐项拒绝并给出可定位信息。"""
    with pytest.raises(CatalogError, match=match):
        load_product_manifest(_write(tmp_path, _manifest(body=block)))


def test_error_code_disabled_status_preserved(tmp_path: Path) -> None:
    """`status = "disabled"`：声明保留（码位不复用），记录状态为 disabled。"""
    manifest = load_product_manifest(_write(tmp_path, _manifest(body=_errcode() + 'status = "disabled"\n')))
    assert manifest.error_codes[0].status == "disabled"


def test_error_codes_require_contract(tmp_path: Path) -> None:
    """声明了错误码但契约缺失：拒启（契约反向对账无基准，不得静默跳过）。"""
    path = _write(tmp_path, _manifest(body=_errcode()))
    inspection = inspect_product_manifests(ConcurrentStableList((path,)))
    assert any("对端契约文件缺失" in error for error in inspection.errors)


def test_contract_reverse_dedupes_repeated_codes(tmp_path: Path) -> None:
    """契约同一端点重复列同一码：去重后仍视为已声明（不误报未登记）。"""
    path = _write(tmp_path, _manifest(body=_errcode()))
    _write_contract(tmp_path, declared=_declared("/api/v1/demo/depts", 390001, 390001))
    inspection = inspect_product_manifests(ConcurrentStableList((path,)))
    assert inspection.errors == []


def test_error_codes_require_service_segment(tmp_path: Path) -> None:
    """有 `[[errcodes]]` 但服务行无段位：拒启（段位不可判定）。"""
    with pytest.raises(CatalogError, match="errcode_segment"):
        load_product_manifest(_write(tmp_path, _manifest(services=False, body=_errcode())))


def test_error_codes_require_single_segment(tmp_path: Path) -> None:
    """服务行存在多个不同段位：拒启（无法确定错误码归属段）。"""
    second_service = (
        _SERVICES.format(product="demo", segment="38")
        .replace('module_key = "demo"', 'module_key = "demo2"')
        .replace('service_key = "demo"', 'service_key = "demo2"')
    )
    with pytest.raises(CatalogError, match="段位须唯一"):
        load_product_manifest(_write(tmp_path, _manifest(body=second_service + _errcode())))


def test_inspect_accepts_valid_error_codes(tmp_path: Path) -> None:
    """装载校验通过：契约已声明该码且归属本清单，无错误、无「未声明」提示。"""
    path = _write(tmp_path, _manifest(body=_errcode()))
    _write_contract(tmp_path, declared=_declared("/api/v1/demo/depts", 390001))
    inspection = inspect_product_manifests(ConcurrentStableList((path,)))
    assert inspection.errors == []
    assert all("未声明" not in warning for warning in inspection.warnings)


def test_global_check_rejects_platform_collision() -> None:
    """全局唯一：与平台码撞码即拒（解析期 6 位约束之外的独立判定）。"""
    platform_code = int(ErrorCode.NOT_FOUND)
    errors = _global_errors(ConcurrentStableList((_record(code=platform_code, segment=str(platform_code)[:2]),)))
    assert any("撞码" in error for error in errors)


def test_global_check_allows_same_value_and_rejects_conflict() -> None:
    """跨清单：同码同值放行（幂等）、同码异值拒。"""
    record = _record()
    manifests = ConcurrentStableList(
        (
            ProductManifest(product_key="demo", error_codes=ConcurrentStableFrozenList((record,))),
            ProductManifest(product_key="demo", error_codes=ConcurrentStableFrozenList((record,))),
        )
    )
    sources = ConcurrentStableList((Path("demo.toml"), Path("demo-copy.toml")))
    assert products_module._validate_error_codes(manifests, sources) == []  # pyright: ignore[reportPrivateUsage]
    conflicting = ConcurrentStableList(
        (
            ProductManifest(product_key="demo", error_codes=ConcurrentStableFrozenList((record,))),
            ProductManifest(
                product_key="other",
                error_codes=ConcurrentStableFrozenList((_record(product_key="other"),)),
            ),
        )
    )
    errors = products_module._validate_error_codes(  # pyright: ignore[reportPrivateUsage]
        conflicting, ConcurrentStableList((Path("demo.toml"), Path("other.toml")))
    )
    assert any("撞码" in error for error in errors)


def test_inspect_rejects_cross_product_conflict(tmp_path: Path) -> None:
    """跨产品撞码（同码异义）：拒启，信息含两侧提供方。"""
    demo = _write(tmp_path, _manifest(body=_errcode()), name="demo.toml")
    other = _write(
        tmp_path,
        _manifest(
            product="other",
            segment="39",
            body=_errcode(message_key="other.error.dept_not_found"),
        ),
        name="other.toml",
    )
    _write_contract(tmp_path, declared=_declared("/api/v1/demo/depts", 390001))
    _write_contract(tmp_path, product="other", declared=_declared("/api/v1/demo/depts", 390001))
    inspection = inspect_product_manifests(ConcurrentStableList((demo, other)))
    assert any("撞码" in error for error in inspection.errors)


def test_inspect_rejects_segment_reuse(tmp_path: Path) -> None:
    """段位跨产品复用：拒启。"""
    demo = _write(tmp_path, _manifest(body=_errcode(code=390001)), name="demo.toml")
    other = _write(
        tmp_path,
        _manifest(
            product="other",
            segment="39",
            body=_errcode(code=390002, message_key="other.error.dept_not_found"),
        ),
        name="other.toml",
    )
    _write_contract(tmp_path, declared=_declared("/api/v1/demo/depts", 390001))
    _write_contract(tmp_path, product="other", declared=_declared("/api/v1/demo/depts", 390002))
    inspection = inspect_product_manifests(ConcurrentStableList((demo, other)))
    assert any("段位跨产品复用" in error for error in inspection.errors)


def test_inspect_allows_duplicate_same_value_manifest(tmp_path: Path) -> None:
    """同一产品清单重复装载且定义相同：放行（幂等重载）。"""
    text = _manifest(body=_errcode())
    first = _write(tmp_path, text, name="demo.toml")
    second = _write(tmp_path, text, name="demo-copy.toml")
    _write_contract(tmp_path, declared=_declared("/api/v1/demo/depts", 390001))
    inspection = inspect_product_manifests(ConcurrentStableList((first, second)))
    assert inspection.errors == []


def test_contract_reverse_rejects_unregistered_code(tmp_path: Path) -> None:
    """契约反向（已声明强校验）：契约列了未登记的码即拒启。"""
    path = _write(tmp_path, _manifest(body=_errcode()))
    _write_contract(tmp_path, declared=_declared("/api/v1/demo/depts", 390001, 390099))
    inspection = inspect_product_manifests(ConcurrentStableList((path,)))
    assert any("契约声明的码未登记" in error and "390099" in error for error in inspection.errors)


def test_contract_reverse_warns_undeclared_endpoints(tmp_path: Path) -> None:
    """契约反向（未声明档）：未声明错误码的端点只统计，不阻断。"""
    path = _write(tmp_path, _manifest(body=_errcode()))
    _write_contract(tmp_path, paths=ConcurrentStableList(("/api/v1/demo/depts", "/api/v1/demo/posts")))
    inspection = inspect_product_manifests(ConcurrentStableList((path,)))
    assert inspection.errors == []
    assert any("2 个端点未声明" in warning for warning in inspection.warnings)


def test_contract_reverse_rejects_malformed_declaration(tmp_path: Path) -> None:
    """契约声明形态非法（非整数数组 / 元素非整数）：拒启并定位到方法与路径。"""
    path = _write(tmp_path, _manifest(body=_errcode()))
    _write_contract(
        tmp_path,
        raw=json.dumps({"paths": {"/api/v1/demo/depts": {"get": {CONTRACT_ERROR_CODES_KEY: "390001"}}}}),
    )
    inspection = inspect_product_manifests(ConcurrentStableList((path,)))
    assert any("错误码声明非法" in error for error in inspection.errors)
    _write_contract(
        tmp_path,
        raw=json.dumps({"paths": {"/api/v1/demo/depts": {"get": {CONTRACT_ERROR_CODES_KEY: ["390001"]}}}}),
    )
    inspection = inspect_product_manifests(ConcurrentStableList((path,)))
    assert any("元素须为整数" in error for error in inspection.errors)


def test_register_manifest_registers_error_codes(tmp_path: Path) -> None:
    """注册入口：清单装载后错误码进入合并视图。"""
    manifest = load_product_manifest(_write(tmp_path, _manifest(body=_errcode())))
    register_manifest(manifest)
    assert error_code_view()[390001].product_key == "demo"
