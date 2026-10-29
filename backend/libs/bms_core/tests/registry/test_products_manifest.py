"""产品登记清单解析与装载：toml 结构 / 归属 / 缺省降级 / 相对路径基准 / 六类装载校验。

口径（04_05 决策 q2=B）：清单相对路径按**后端工程根**解析（不随工作目录变化）；
格式切换与能力 / 种子段（07B `02_01`）：清单只接受 `.toml`，能力（第五类）与种子（第六类）
同源同通道，装载期完成六类校验并在装配期拒启。

本套用例覆盖解析的全部错误分支、六类校验的每个反例与跳过 / 警示口径；
新增用例的 Kiwi 编号由 07B `05_01` 统一登记后回填（本批不标 `kiwi_id`）。
"""

# pyright: reportUnusedFunction=false
import json
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import bms_core.registry.products as products
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.datasource.registry import data_source_records_view, reset_data_source_records
from bms_core.registry.products import (
    SKIP_CONTRACT_ENV,
    ProductManifest,
    inspect_product_manifests,
    load_product_manifest,
    load_product_manifests,
    register_manifest,
)
from bms_core.services.module_registry import (
    collaboration_catalog_view,
    product_catalog_view,
    product_routes_view,
    reset_collaboration_records,
    reset_product_records,
    reset_product_routes,
    reset_seed_records,
    reset_service_records,
    seed_catalog_view,
    service_catalog_view,
)

_TOML = """\
product_key = "demo"

[[products]]
product_key = "demo"
name = "演示产品"
frontend_package_source = "demo#frontend"
status = "enabled"

[[services]]
module_key = "demo"
service_key = "demo"
name = "演示服务"
table_prefix = "demo_"
business_code = "demo"
errcode_segment = "39"
event_domain = "demo"
service_group = "product"
build_batch = 3
service_version = "0.2.0"
contract_version = "0.2.0"
tenant_base = true
product_key = "demo"
status = "enabled"

[[product_routes]]
product_key = "demo"
domain = "demo"
service_key = "demo"
description = "演示域"

[[data_sources]]
data_source_key = "demo_dept"
name = "部门"
data_source = "demo.demo.dept"
kind = "dict"
origin = "product"
product_key = "demo"
path = "/data-source/dept-tree"
allowlist = ["code", "label"]
cascade = true
strategies = ["select", "region"]
status = "enabled"

[[collaborations]]
name = "demo.org.dept-data"
domain = "org"
kind = "dataset"
path = "/api/v1/demo/data-source/dept-tree"
data_source_key = "demo_dept"
frontend_prefix = "demo"
contract_version = "0.2.0"
default_consumers = ["platform"]

[[seeds]]
name = "demo-admin-codes"
service = "demo"
db_key = "platform_platform"
module = "demo.seeds.permissions"
entry = "seed_admin_codes"
after = []
description = "管理面业务码与权限码"

# 第九类：业务域声明（07B `04_02` 重开——域布局的唯一信息源，不再读 domain_layout.json）
[[domains]]
domain_key = "org"
service_key = "demo"
status = "planned"

[[domains]]
domain_key = "demo"
service_key = "demo"
status = "planned"
"""
"""完整清单（九段齐备；能力 1 条 dataset、种子 1 条、域 2 条）。"""

_CONTRACT_PATHS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("/api/v1/demo/data-source/dept-tree",))
"""默认对端契约中的访问面路径。"""

_DOMAINS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("org", "demo"))
"""默认域布局中的业务域标识。"""


def _write(tmp_path: Path, text: str, name: str = "demo.toml", base: str = "backend") -> Path:
    """把清单内容写到临时目录（`<base>/deploy/registry/`）。

    Args:
        tmp_path: 临时目录。
        text: 清单文本。
        name: 文件名。
        base: 清单所在仓目录名（相对 `tmp_path`）。

    Returns:
        Path: 清单文件路径。
    """
    path = tmp_path / base / "deploy" / "registry" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_contract(
    tmp_path: Path,
    paths: ConcurrentStableFrozenList[str] = _CONTRACT_PATHS,
    *,
    name: str = "demo.json",
    base: str = "backend",
    raw: str | None = None,
) -> Path:
    """写对端契约文件（`<base>/deploy/contracts/<产品>.json`）。

    Args:
        tmp_path: 临时目录。
        paths: 契约 `paths` 键集合。
        name: 契约文件名。
        base: 契约所在仓目录名（相对 `tmp_path`）。
        raw: 直接指定的原始文本（覆盖默认结构，用于非法 JSON 反例）。

    Returns:
        Path: 契约文件路径。
    """
    path = tmp_path / base / "deploy" / "contracts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = raw if raw is not None else json.dumps({"paths": {item: {} for item in paths}})
    path.write_text(text, encoding="utf-8")
    return path


def _write_layout(
    tmp_path: Path, domains: ConcurrentStableFrozenList[str] = _DOMAINS, *, base: str = "backend"
) -> Path:
    """写域布局生成物文件（`<base>/deploy/boundaries/domain_layout.json`）。

    07B `04_02` 重开：域布局改为「清单第九类声明 + 生成物」，装载校验**不再读本文件**。
    本函数保留为「生成物形态」夹具（渲染 / 比对用例用），域声明的真实来源是清单 `[[domains]]`
    （见 `_domains_block()`）。

    Args:
        tmp_path: 临时目录。
        domains: 域标识集合。
        base: 布局所在仓目录名（相对 `tmp_path`）。

    Returns:
        Path: 域布局文件路径。
    """
    path = tmp_path / base / "deploy" / "boundaries" / "domain_layout.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "domains": [{"domain_key": item} for item in domains]}), encoding="utf-8")
    return path


def _domains_block(domains: ConcurrentStableFrozenList[str] = _DOMAINS) -> str:
    """生成清单的第九类 `[[domains]]` 段（域布局的真实来源）。

    Args:
        domains: 域标识集合。

    Returns:
        str: TOML 片段（每个域一条，承载服务取域标识本身）。
    """
    return "".join(
        f'[[domains]]\ndomain_key = "{item}"\nservice_key = "{item}"\nstatus = "planned"\n' for item in domains
    )


def _default_entry(ctx: object) -> None:
    """默认种子入口（可调用、无副作用）。

    Args:
        ctx: 种子上下文（本用例不消费）。
    """
    del ctx


def _install_seed_package(monkeypatch: pytest.MonkeyPatch, *, entry: object = None) -> None:
    """把 `demo.seeds.permissions` 注入 `sys.modules`（造「提供方包可导入」环境）。

    Args:
        monkeypatch: pytest monkeypatch 夹具（用例结束自动移除注入）。
        entry: 入口对象；缺省为可调用函数。
    """
    top = types.ModuleType("demo")
    seeds = types.ModuleType("demo.seeds")
    module = types.ModuleType("demo.seeds.permissions")
    setattr(module, "seed_admin_codes", _default_entry if entry is None else entry)  # noqa: B010
    monkeypatch.setitem(sys.modules, "demo", top)
    monkeypatch.setitem(sys.modules, "demo.seeds", seeds)
    monkeypatch.setitem(sys.modules, "demo.seeds.permissions", module)


@pytest.fixture(autouse=True)
def _isolate_catalogs(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """每例前后清空六张注入登记表并复位清单基准（进程级全局状态，不污染其他用例）。

    Args:
        monkeypatch: pytest monkeypatch 夹具（复位跳过契约开关）。

    Yields:
        None: 用例运行期。
    """
    monkeypatch.delenv(SKIP_CONTRACT_ENV, raising=False)
    reset_service_records()
    reset_product_records()
    reset_product_routes()
    reset_data_source_records()
    reset_collaboration_records()
    reset_seed_records()
    yield
    reset_service_records()
    reset_product_records()
    reset_product_routes()
    reset_data_source_records()
    reset_collaboration_records()
    reset_seed_records()


def _point_base(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """把清单相对路径基准指向临时后端根。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        tmp_path: 临时目录。

    Returns:
        Path: 临时后端根（`tmp_path/backend`）。
    """
    backend = tmp_path / "backend"
    backend.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(products, "_MANIFEST_BASE", backend)
    return backend


@pytest.mark.kiwi_id(2359)
def test_load_full_manifest(tmp_path: Path) -> None:
    """完整清单：六类记录逐字段解析（含可选字段与缺省值）。

    Args:
        tmp_path: 临时目录。
    """
    manifest = load_product_manifest(_write(tmp_path, _TOML))

    assert isinstance(manifest, ProductManifest)
    assert manifest.product_key == "demo"
    product = manifest.products[0]
    assert (product.product_key, product.name, product.frontend_package_source) == (
        "demo",
        "演示产品",
        "demo#frontend",
    )
    service = manifest.services[0]
    assert service.service_key == "demo"
    assert service.business_code == "demo"
    assert service.errcode_segment == "39"
    assert service.service_version == "0.2.0"
    assert service.build_batch == 3
    assert service.tenant_base is True
    route = manifest.product_routes[0]
    assert (route.domain, route.service_key, route.description) == ("demo", "demo", "演示域")
    data_source = manifest.data_sources[0]
    assert data_source.data_source_key == "demo_dept"
    assert data_source.allowlist == ["code", "label"]
    assert data_source.strategies == ["select", "region"]
    assert data_source.cascade is True
    collaboration = manifest.collaborations[0]
    assert collaboration.name == "demo.org.dept-data"
    assert collaboration.kind == "dataset"
    assert collaboration.data_source_key == "demo_dept"
    assert collaboration.default_consumers == ["platform"]
    assert collaboration.status == "enabled"
    seed = manifest.seeds[0]
    assert (seed.module, seed.entry, seed.description) == (
        "demo.seeds.permissions",
        "seed_admin_codes",
        "管理面业务码与权限码",
    )
    assert seed.after == []


@pytest.mark.kiwi_id(2359)
def test_load_minimal_manifest_defaults(tmp_path: Path) -> None:
    """最简清单：缺省段为空列表，可选字段走缺省值（不静默使用旧值）。

    Args:
        tmp_path: 临时目录。
    """
    text = """\
product_key = "demo"

[[services]]
module_key = "demo"
name = "演示服务"
table_prefix = "demo_"
event_domain = "demo"
service_key = ""
business_code = ""

[[data_sources]]
data_source_key = "demo_dept"
name = "部门"
data_source = "demo.demo.dept"
"""
    manifest = load_product_manifest(_write(tmp_path, text))

    assert manifest.products == []
    assert manifest.product_routes == []
    assert manifest.collaborations == []
    assert manifest.seeds == []
    service = manifest.services[0]
    assert service.service_key is None
    assert service.business_code is None
    assert service.errcode_segment is None
    assert service.service_group == "product"
    assert service.build_batch == 0
    assert service.service_version == "0.1.0"
    assert service.contract_version == "0.1.0"
    assert service.product_key == "demo"
    assert service.status == "enabled"
    assert service.tenant_base is False
    data_source = manifest.data_sources[0]
    assert data_source.kind == "dict"
    assert data_source.origin == "product"
    assert data_source.path is None
    assert data_source.allowlist == []
    assert data_source.cascade is False
    assert data_source.strategies == ["select"]


@pytest.mark.kiwi_id(2359)
def test_load_manifest_rejects_structure_errors(tmp_path: Path) -> None:
    """结构反例：数组段非数组 / 元素非对象 / 必填缺失或空串 一律拒绝。

    Args:
        tmp_path: 临时目录。
    """
    with pytest.raises(CatalogError, match="须为数组"):
        load_product_manifest(_write(tmp_path, 'product_key = "demo"\n[services]\n', name="array.toml"))

    with pytest.raises(CatalogError, match="记录须为对象"):
        load_product_manifest(_write(tmp_path, 'product_key = "demo"\nservices = [1]\n', name="element.toml"))

    missing = """\
product_key = "demo"

[[services]]
module_key = "demo"
name = "演示"
event_domain = "demo"
"""
    with pytest.raises(CatalogError, match="缺少必填字段"):
        load_product_manifest(_write(tmp_path, missing, name="missing.toml"))

    blank = """\
product_key = "demo"

[[services]]
module_key = "demo"
name = ""
table_prefix = "demo_"
event_domain = "demo"
"""
    with pytest.raises(CatalogError, match="缺少必填字段"):
        load_product_manifest(_write(tmp_path, blank, name="blank.toml"))

    with pytest.raises(CatalogError, match="缺少必填字段"):
        load_product_manifest(_write(tmp_path, '[[products]]\nname = "x"\n', name="no_key.toml"))


@pytest.mark.kiwi_id(2359)
def test_load_manifest_rejects_ownership_mismatch(tmp_path: Path) -> None:
    """归属反例：产品档案 / 服务行 / 产品路由 / 数据源 / 能力与文件 `product_key` 不符即拒。

    Args:
        tmp_path: 临时目录。
    """
    cases = (
        ("产品档案归属不符", 'product_key = "demo"\n\n[[products]]\nproduct_key = "other"\nname = "x"\n'),
        (
            "服务行产品归属不符",
            'product_key = "demo"\n\n[[services]]\nmodule_key = "demo"\nname = "x"\n'
            'table_prefix = "demo_"\nevent_domain = "demo"\nproduct_key = "other"\n',
        ),
        (
            "路由归属不符",
            'product_key = "demo"\n\n[[product_routes]]\nproduct_key = "other"\n'
            'domain = "demo"\nservice_key = "demo"\n',
        ),
        (
            "数据源产品归属不符",
            'product_key = "demo"\n\n[[data_sources]]\ndata_source_key = "demo_dept"\nname = "部门"\n'
            'data_source = "demo.demo.dept"\nproduct_key = "other"\n',
        ),
        (
            "能力产品归属不符",
            'product_key = "demo"\n\n[[collaborations]]\nname = "demo.org.x"\ndomain = "org"\n'
            'kind = "codes"\ncontract_version = "0.1.0"\npermission_codes = ["demo:query"]\n'
            'product_key = "other"\n',
        ),
    )
    for index, (message, text) in enumerate(cases):
        with pytest.raises(CatalogError, match=message):
            load_product_manifest(_write(tmp_path, text, name=f"owner-{index}.toml"))


@pytest.mark.kiwi_id(2359)
def test_load_manifest_tenant_base_requires_product_group(tmp_path: Path) -> None:
    """恒开通声明：`tenant_base = true` 的服务行须为 `product` 分组（违规即装载期拒）；非布尔亦拒。

    Args:
        tmp_path: 临时目录。
    """
    foundation = """\
product_key = "demo"

[[services]]
module_key = "demo"
name = "演示服务"
table_prefix = "demo_"
event_domain = "demo"
service_group = "foundation"
tenant_base = true
"""
    with pytest.raises(CatalogError, match="tenant_base 仅适用于 product 分组"):
        load_product_manifest(_write(tmp_path, foundation, name="tenant-foundation.toml"))

    non_bool = """\
product_key = "demo"

[[services]]
module_key = "demo"
name = "演示服务"
table_prefix = "demo_"
event_domain = "demo"
tenant_base = "yes"
"""
    with pytest.raises(CatalogError, match="tenant_base 须为布尔"):
        load_product_manifest(_write(tmp_path, non_bool, name="tenant-type.toml"))


@pytest.mark.kiwi_id(2359)
def test_load_manifest_non_sequence_strings(tmp_path: Path) -> None:
    """`allowlist` / `strategies` 非数组时按空清单处理（数组类策略再回落缺省 `select`）。

    Args:
        tmp_path: 临时目录。
    """
    text = """\
product_key = "demo"

[[data_sources]]
data_source_key = "demo_dept"
name = "部门"
data_source = "demo.demo.dept"
allowlist = "code"
strategies = "select"
"""
    manifest = load_product_manifest(_write(tmp_path, text))

    assert manifest.data_sources[0].allowlist == []
    assert manifest.data_sources[0].strategies == ["select"]


@pytest.mark.kiwi_id(2359)
def test_load_manifest_file_errors(tmp_path: Path) -> None:
    """文件反例：路径不可读 / TOML 非法 / 交付 `.json` 均转 `CatalogError`。

    Args:
        tmp_path: 临时目录。
    """
    with pytest.raises(CatalogError, match="不可读"):
        load_product_manifest(tmp_path / "missing.toml")

    broken = tmp_path / "broken.toml"
    broken.write_text("product_key = ", encoding="utf-8")
    with pytest.raises(CatalogError, match="TOML 非法"):
        load_product_manifest(broken)

    legacy = tmp_path / "legacy.json"
    legacy.write_text('{"product_key": "demo"}', encoding="utf-8")
    with pytest.raises(CatalogError, match="须为 toml"):
        load_product_manifest(legacy)


@pytest.mark.kiwi_id(2359)
def test_register_manifest_feeds_all_views(tmp_path: Path) -> None:
    """装载即注册：六类视图各增一条（服务行 / 产品档案 / 产品路由 / 数据源 / 能力 / 种子）。

    Args:
        tmp_path: 临时目录。
    """
    manifest = load_product_manifest(_write(tmp_path, _TOML))

    register_manifest(manifest)

    assert "demo" in [record.module_key for record in service_catalog_view()]
    assert "demo" in [record.product_key for record in product_catalog_view()]
    assert "demo" in [record.product_key for record in product_routes_view()]
    assert "demo_dept" in [record.data_source_key for record in data_source_records_view()]
    assert "demo.org.dept-data" in [record.name for record in collaboration_catalog_view()]
    assert "demo-admin-codes" in [record.name for record in seed_catalog_view()]


@pytest.mark.kiwi_id(2359)
def test_load_manifests_resolves_relative_path_by_backend_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """相对路径按后端工程根解析（04_05 q2=B）：与工作目录无关；不存在路径静默跳过。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    backend = _point_base(monkeypatch, tmp_path)
    _write(tmp_path, _TOML)
    _write_contract(tmp_path)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    loaded = load_product_manifests(ConcurrentStableList(["deploy/registry/demo.toml", "deploy/registry/none.toml"]))

    assert len(loaded) == 1
    assert loaded[0].product_key == "demo"
    assert "demo" in [record.module_key for record in service_catalog_view()]
    assert load_product_manifests(ConcurrentStableList([tmp_path / "absent.toml"])) == []
    assert (backend / "deploy" / "registry" / "demo.toml").is_file()


def test_inspect_manifest_without_collaborations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """无能力段清单：跳过契约定位与域基准校验，装载成功且无警示（既有四类清单照常工作）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    path = _write(
        tmp_path,
        'product_key = "demo"\n\n[[products]]\nproduct_key = "demo"\nname = "演示产品"\n',
        name="plain.toml",
    )

    inspection = inspect_product_manifests(ConcurrentStableList([path]))

    assert inspection.errors == []
    assert inspection.warnings == []
    assert len(inspection.manifests) == 1


def test_inspect_full_manifest_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """六段齐备 + 契约 + 域布局 + 可导入种子：校验通过、无警示。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    path = _write(tmp_path, _TOML)
    _write_contract(tmp_path)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    inspection = inspect_product_manifests(ConcurrentStableList([path]))

    assert inspection.errors == []
    assert inspection.warnings == []
    assert len(inspection.manifests) == 1
    assert inspection.sources == [path]


def test_inspect_collaboration_duplicate_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """能力重名：跨清单同名异值即拒（同值合并在另例覆盖）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    first = _write(tmp_path, _TOML)
    other = _TOML.replace('product_key = "demo"', 'product_key = "other"').replace(
        "demo.org.dept-data", "demo.org.dept-data"
    )
    other = other.replace("demo_dept", "other_dept").replace("demo-admin-codes", "other-admin-codes")
    second = _write(tmp_path, other, name="other.toml")
    _write_contract(tmp_path)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    errors = inspect_product_manifests(ConcurrentStableList([first, second])).errors

    assert any("能力重名：demo.org.dept-data" in error for error in errors)


def test_inspect_collaboration_same_name_same_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """能力重名但同值：幂等放行（同键同值合并）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    first = _write(tmp_path, _TOML)
    second = _write(tmp_path, _TOML, name="demo-copy.toml")
    _write_contract(tmp_path)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    inspection = inspect_product_manifests(ConcurrentStableList([first, second]))

    assert inspection.errors == []
    assert len(inspection.manifests) == 2


def test_inspect_domain_not_registered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """提供方业务域未声明：清单里无该域即拒（域布局由清单第九类声明）。

    07B `04_02` 重开：域布局从「独立 json 文件」改为「清单 `[[domains]]` 声明」，
    本用例守「声明里没有该域 → 能力被拒」这一核心语义。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = _TOML.replace('[[domains]]\ndomain_key = "org"\nservice_key = "demo"\nstatus = "planned"\n', "")
    path = _write(tmp_path, text)
    _write_contract(tmp_path)
    _install_seed_package(monkeypatch)

    errors = inspect_product_manifests(ConcurrentStableList([path])).errors

    assert any("提供方业务域未登记（org）" in error for error in errors)


def test_inspect_domain_without_service_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """域声明的承载服务未在本清单 `[[services]]` 中 → 拒（防笔误）。

    07B `04_02` 重开新增校验：`service_key` 须为本清单已声明的服务键。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = _TOML.replace('domain_key = "org"\nservice_key = "demo"', 'domain_key = "org"\nservice_key = "ghost"')
    path = _write(tmp_path, text)
    _write_contract(tmp_path)
    _install_seed_package(monkeypatch)

    errors = inspect_product_manifests(ConcurrentStableList([path])).errors

    assert any("承载服务未在本清单" in error and "ghost" in error for error in errors)


def test_inspect_domain_layout_missing_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """清单未声明任何业务域：只做形态校验并输出警示（不静默、不因此拒启）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = _TOML.split("# 第九类")[0]
    path = _write(tmp_path, text)
    _write_contract(tmp_path)
    _install_seed_package(monkeypatch)

    inspection = inspect_product_manifests(ConcurrentStableList([path]))

    assert inspection.errors == []
    assert any("域布局不可用" in warning for warning in inspection.warnings)


def test_inspect_domain_status_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """域状态非法（不在 placement / legacy / planned 内）：解析期即拒。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = _TOML.replace(
        'domain_key = "org"\nservice_key = "demo"\nstatus = "planned"',
        'domain_key = "org"\nservice_key = "demo"\nstatus = "bogus"',
    )
    path = _write(tmp_path, text)
    _write_contract(tmp_path)
    _install_seed_package(monkeypatch)

    errors = inspect_product_manifests(ConcurrentStableList([path])).errors

    assert any("状态非法" in error and "bogus" in error for error in errors)


def test_inspect_domain_paths_required_for_placement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`placement` / `legacy` 域必须声明代码路径（`planned` 可空）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = _TOML.replace('status = "planned"', 'status = "placement"')
    path = _write(tmp_path, text)
    _write_contract(tmp_path)
    _install_seed_package(monkeypatch)

    errors = inspect_product_manifests(ConcurrentStableList([path])).errors

    assert any("须声明代码路径" in error for error in errors)


def test_layout_registry_map_derived_from_manifests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """域映射由**清单第九类**派生（不再读任何文件）；同域取先出现的承载服务。

    07B `04_02` 重开：`_layout_registry_map` 入参从「清单路径」改为「已解析清单」，
    因为域信息随声明到达，平台侧拿不到产品仓的 `domain_layout.json`。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    first = _write(tmp_path, _TOML, name="a.toml")
    second_text = _TOML.replace('domain_key = "org"\nservice_key = "demo"', 'domain_key = "org"\nservice_key = "other"')
    second = _write(tmp_path, second_text, name="b.toml")

    inspection = inspect_product_manifests(ConcurrentStableList([first, second]))

    # 跨清单同域不同承载服务：警示（不静默），且取先出现的
    assert any("业务域跨清单承载服务冲突" in warning for warning in inspection.warnings)
    assert inspection.domain_services["org"] == "demo"


def test_domain_record_rejects_non_string_list(tmp_path: Path) -> None:
    """域字段非字符串数组：解析期拒（`_str_list` 两个分支）。"""
    with pytest.raises(CatalogError, match="须为字符串数组"):
        load_product_manifest(
            _write(tmp_path, _TOML.replace('status = "planned"', 'status = "planned"\npaths = "a"'), name="s1.toml")
        )
    with pytest.raises(CatalogError, match="元素须为字符串"):
        load_product_manifest(
            _write(
                tmp_path,
                _TOML.replace('status = "planned"', 'status = "planned"\npublic_api = [1]'),
                name="s2.toml",
            )
        )


def test_domain_record_rejects_multi_public_api(tmp_path: Path) -> None:
    """`public_api` 超过 1 个：解析期拒（D2 唯一跨域引用面）。"""
    text = _TOML.replace(
        'status = "planned"',
        'status = "planned"\npublic_api = ["a", "b"]',
    )
    with pytest.raises(CatalogError, match="public_api 至多 1 个"):
        load_product_manifest(_write(tmp_path, text, name="pa.toml"))


def test_domain_key_format_rejected(tmp_path: Path) -> None:
    """域标识格式非法：解析期拒（`DomainEntry` 是纯数据类，格式在清单解析处把关）。"""
    text = _TOML.replace('domain_key = "org"', 'domain_key = "Bad-Domain"')
    with pytest.raises(CatalogError, match="标识须匹配"):
        load_product_manifest(_write(tmp_path, text, name="badkey.toml"))


def test_domain_duplicate_within_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """同一清单内业务域重复声明：装载校验拒收。"""
    _point_base(monkeypatch, tmp_path)
    text = _TOML + '\n[[domains]]\ndomain_key = "org"\nservice_key = "demo"\nstatus = "planned"\n'
    path = _write(tmp_path, text)
    _write_contract(tmp_path)
    _install_seed_package(monkeypatch)

    errors = inspect_product_manifests(ConcurrentStableList([path])).errors

    assert any("同一清单内业务域重复声明" in error for error in errors)


def test_domain_without_service_key_errors(tmp_path: Path) -> None:
    """域声明缺承载服务：解析期即拒（`service_key` 是必填，能力寻址第二段无解）。"""
    text = _TOML.replace('domain_key = "org"\nservice_key = "demo"', 'domain_key = "org"')
    with pytest.raises(CatalogError, match="service_key"):
        load_product_manifest(_write(tmp_path, text, name="nosvc.toml"))


def test_inspect_contract_path_normalized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """访问面参数模板归一化：契约与清单占位名不同但路径形态一致 → 通过。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = _TOML.replace(
        'path = "/api/v1/demo/data-source/dept-tree"',
        'path = "/api/v1/demo/depts/{dept_id}"',
    )
    path = _write(tmp_path, text)
    _write_contract(tmp_path, ConcurrentStableFrozenList(("/api/v1/demo/depts/{other_id}",)))
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    assert inspect_product_manifests(ConcurrentStableList([path])).errors == []


def test_inspect_contract_path_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """访问面拼错：归一化后仍不在契约 `paths` 中即拒。

    Args:
        tmp_path: 临时目录.
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    path = _write(tmp_path, _TOML)
    _write_contract(tmp_path, ConcurrentStableFrozenList(("/api/v1/demo/dept-tree",)))
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    errors = inspect_product_manifests(ConcurrentStableList([path])).errors

    assert any("访问面不在对端契约" in error for error in errors)


def test_inspect_contract_version_incompatible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """契约版本不兼容：能力主版本 ≠ 服务行主版本即拒。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = _TOML.replace(
        'contract_version = "0.2.0"\ndefault_consumers', 'contract_version = "1.0.0"\ndefault_consumers'
    )
    path = _write(tmp_path, text)
    _write_contract(tmp_path)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    errors = inspect_product_manifests(ConcurrentStableList([path])).errors

    assert any("契约版本不兼容" in error for error in errors)


def test_inspect_kind_element_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`kind` 与要素不匹配：txn-branch 缺分支要素 / dataset 缺数据源 / codes 缺码集或带路径。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    _write_contract(tmp_path)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)
    cases = (
        (
            "txn-branch 类须声明 branch_id",
            'kind = "txn-branch"\npath = "/api/v1/demo/x"\nbranch_op = "demo.x"\n',
        ),
        (
            "txn-branch 类须声明 branch_op",
            'kind = "txn-branch"\npath = "/api/v1/demo/x"\nbranch_id = "d"\n',
        ),
        (
            "dataset 类须声明 data_source_key",
            'kind = "dataset"\npath = "/api/v1/demo/x"\n',
        ),
        (
            "codes 类须声明 permission_codes",
            'kind = "codes"\n',
        ),
        (
            "codes 类不得声明访问面 path",
            'kind = "codes"\npath = "/api/v1/demo/x"\npermission_codes = ["demo:query"]\n',
        ),
        (
            "须声明访问面 path",
            'kind = "read"\n',
        ),
    )
    for index, (message, body) in enumerate(cases):
        text = (
            'product_key = "demo"\n\n[[collaborations]]\nname = "demo.org.x"\ndomain = "org"\n'
            f'contract_version = "0.2.0"\n{body}'
        )
        with pytest.raises(CatalogError, match=message):
            load_product_manifest(_write(tmp_path, text, name=f"kind-{index}.toml"))


def test_inspect_codes_kind_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`codes` 类正例：无访问面、只有业务码 / 权限码集合，装载校验通过。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = (
        'product_key = "demo"\n\n[[services]]\nmodule_key = "demo"\nname = "演示服务"\n'
        'table_prefix = "demo_"\nevent_domain = "demo"\ncontract_version = "0.2.0"\n\n'
        '[[collaborations]]\nname = "demo.org.admin-codes"\ndomain = "org"\nkind = "codes"\n'
        'contract_version = "0.2.0"\npermission_codes = ["demo:query", "demo:create"]\n'
        'default_consumers = ["platform"]\n'
        '\n[[domains]]\ndomain_key = "org"\nservice_key = "demo"\nstatus = "planned"\n'
    )
    path = _write(tmp_path, text)
    _write_contract(tmp_path, ConcurrentStableFrozenList())

    inspection = inspect_product_manifests(ConcurrentStableList([path]))

    assert inspection.errors == []
    assert inspection.warnings == []


def test_inspect_domain_without_domain_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """域声明缺必填 `domain_key`：解析期即拒（结构级校验，不进装载校验）。

    07B `04_02` 重开：域声明的必填字段由 `_domain_record` 在解析期把关，
    原「文件里条目缺 `domain_key` 则跳过」的宽松口径随文件来源一并退役。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = _TOML.replace('[[domains]]\ndomain_key = "org"\n', "[[domains]]\n")
    path = _write(tmp_path, text)
    _write_contract(tmp_path)
    _install_seed_package(monkeypatch)

    errors = inspect_product_manifests(ConcurrentStableList([path])).errors

    assert any("domain_key" in error for error in errors)


def test_inspect_service_without_service_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """服务行无 `service_key`：默认消费方仍可解析到清单产品键与平台服务键。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = (
        'product_key = "demo"\n\n[[services]]\nmodule_key = "demo"\nname = "演示服务"\n'
        'table_prefix = "demo_"\nevent_domain = "demo"\n\n'
        '[[collaborations]]\nname = "demo.org.admin-codes"\ndomain = "org"\nkind = "codes"\n'
        'contract_version = "0.1.0"\npermission_codes = ["demo:query"]\n'
        'default_consumers = ["platform", "demo"]\n'
    )
    path = _write(tmp_path, text)
    _write_contract(tmp_path, ConcurrentStableFrozenList())
    _write_layout(tmp_path)

    assert inspect_product_manifests(ConcurrentStableList([path])).errors == []


def test_inspect_same_branch_id_same_domain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """同一业务域内多个能力共用分支标识：合法（一个 XA 分支承载多个 op）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    text = (
        'product_key = "demo"\n\n[[services]]\nmodule_key = "demo"\nname = "演示服务"\n'
        'table_prefix = "demo_"\nevent_domain = "demo"\ncontract_version = "0.2.0"\n\n'
        '[[product_routes]]\nproduct_key = "demo"\ndomain = "mdm"\nservice_key = "demo"\n\n'
        '[[collaborations]]\nname = "demo.org.user-posts.assign"\ndomain = "org"\nkind = "txn-branch"\n'
        'path = "/api/v1/demo/internal/user-posts/{user_id}"\nbranch_id = "m"\n'
        'branch_op = "demo.user-posts.assign"\ncontract_version = "0.2.0"\n\n'
        '[[collaborations]]\nname = "demo.org.user-depts.assign"\ndomain = "org"\nkind = "txn-branch"\n'
        'path = "/api/v1/demo/internal/user-depts/{user_id}"\nbranch_id = "m"\n'
        'branch_op = "demo.user-depts.assign"\ncontract_version = "0.2.0"\n'
    )
    path = _write(tmp_path, text)
    _write_contract(
        tmp_path,
        ConcurrentStableFrozenList(
            (
                "/api/v1/demo/internal/user-posts/{user_id}",
                "/api/v1/demo/internal/user-depts/{user_id}",
            )
        ),
    )
    _write_layout(tmp_path)

    assert inspect_product_manifests(ConcurrentStableList([path])).errors == []


def test_inspect_frontend_prefix_underivable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """前端命名空间不可推导：无路由域段 / 路由域段不唯一且未显式声明即拒。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    _write_contract(tmp_path)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)
    base = (
        'product_key = "demo"\n\n[[services]]\nmodule_key = "demo"\nname = "演示服务"\n'
        'table_prefix = "demo_"\nevent_domain = "demo"\ncontract_version = "0.2.0"\n\n'
        '[[collaborations]]\nname = "demo.org.dept-data"\ndomain = "org"\nkind = "dataset"\n'
        'path = "/api/v1/demo/data-source/dept-tree"\ndata_source_key = "demo_dept"\n'
        'contract_version = "0.2.0"\n'
    )

    errors = inspect_product_manifests(ConcurrentStableList([_write(tmp_path, base, name="no-route.toml")])).errors
    assert any("前端命名空间不可推导" in error for error in errors)

    multi = base.replace(
        'contract_version = "0.2.0"\n\n[[collaborations]]',
        'contract_version = "0.2.0"\n\n[[product_routes]]\nproduct_key = "demo"\ndomain = "mdm"\n'
        'service_key = "demo"\n\n[[product_routes]]\nproduct_key = "demo"\ndomain = "org"\n'
        'service_key = "demo"\n\n[[collaborations]]',
    )
    errors = inspect_product_manifests(ConcurrentStableList([_write(tmp_path, multi, name="multi-route.toml")])).errors
    assert any("前端命名空间不可推导" in error for error in errors)


def test_inspect_collaboration_field_errors(tmp_path: Path) -> None:
    """能力字段反例：kind / status / 契约版本非法、`deprecated` 缺替代、`branch_id` 超长。

    Args:
        tmp_path: 临时目录。
    """
    cases = (
        ("kind 非法", 'kind = "unknown"\npath = "/x"\n'),
        ("status 非法", 'kind = "read"\npath = "/x"\nstatus = "draft"\n'),
        ("contract_version 非 semver", 'kind = "read"\npath = "/x"\n', "0.1"),
        ("deprecated 状态须声明 replacement", 'kind = "read"\npath = "/x"\nstatus = "deprecated"\n'),
        (
            "branch_id 超过 16 字符",
            'kind = "txn-branch"\npath = "/x"\nbranch_id = "abcdefghijklmnopq"\nbranch_op = "demo.x"\n',
        ),
    )
    for index, case in enumerate(cases):
        message, body = case[0], case[1]
        version = case[2] if len(case) > 2 else "0.2.0"
        text = (
            'product_key = "demo"\n\n[[collaborations]]\nname = "demo.org.x"\ndomain = "org"\n'
            f'contract_version = "{version}"\n{body}'
        )
        with pytest.raises(CatalogError, match=message):
            load_product_manifest(_write(tmp_path, text, name=f"field-{index}.toml"))


def test_inspect_seed_entry_unresolvable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """种子入口不可解析：子模块不存在 / 入口不存在 / 入口不可调用 三例均拒并定位 `module:entry`。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    _write_contract(tmp_path)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    missing_module = _TOML.replace("demo.seeds.permissions", "demo.seeds.absent")
    errors = inspect_product_manifests(
        ConcurrentStableList([_write(tmp_path, missing_module, name="no-module.toml")])
    ).errors
    assert any("入口不可解析（demo.seeds.absent:seed_admin_codes）" in error for error in errors)

    missing_entry = _TOML.replace('entry = "seed_admin_codes"', 'entry = "absent"')
    errors = inspect_product_manifests(
        ConcurrentStableList([_write(tmp_path, missing_entry, name="no-entry.toml")])
    ).errors
    assert any("入口不可解析（demo.seeds.permissions:absent）" in error for error in errors)

    _install_seed_package(monkeypatch, entry="not-callable")
    errors = inspect_product_manifests(ConcurrentStableList([_write(tmp_path, _TOML, name="not-callable.toml")])).errors
    assert any("入口不可解析（demo.seeds.permissions:seed_admin_codes）" in error for error in errors)


def test_inspect_seed_entry_skipped_without_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """提供方包不可导入：跳过入口校验并输出警示（不静默通过）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    path = _write(tmp_path, _TOML)
    _write_contract(tmp_path)
    _write_layout(tmp_path)

    inspection = inspect_product_manifests(ConcurrentStableList([path]))

    assert inspection.errors == []
    assert any("跳过入口校验（demo 不可导入）" in warning for warning in inspection.warnings)


def test_inspect_contract_missing_and_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """契约文件缺失：缺省拒启；显式跳过变量下跳过并警示。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    path = _write(tmp_path, _TOML)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    errors = inspect_product_manifests(ConcurrentStableList([path])).errors
    assert any("对端契约文件缺失" in error for error in errors)

    monkeypatch.setenv(SKIP_CONTRACT_ENV, "1")
    inspection = inspect_product_manifests(ConcurrentStableList([path]))
    assert inspection.errors == []
    assert any("跳过契约定位" in warning for warning in inspection.warnings)


def test_inspect_contract_fallback_to_backend_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """契约定位回退：清单不在本仓时按后端工程根 `deploy/contracts` 兜底。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    path = _write(tmp_path, _TOML, base="other")
    _write_contract(tmp_path, base=".")
    _write_layout(tmp_path, base="other")
    _install_seed_package(monkeypatch)

    assert inspect_product_manifests(ConcurrentStableList([path])).errors == []


def test_inspect_contract_unreadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """契约 JSON 破损 / `paths` 非对象：逐项报错不静默；读取异常转为清单错误。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    path = _write(tmp_path, _TOML)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    contract = _write_contract(tmp_path, raw="{")
    assert any(
        "对端契约 JSON 非法" in error for error in inspect_product_manifests(ConcurrentStableList([path])).errors
    )

    contract.write_text('{"paths": []}', encoding="utf-8")
    assert any(
        "访问面不在对端契约" in error for error in inspect_product_manifests(ConcurrentStableList([path])).errors
    )


def test_contract_paths_read_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """契约读取异常（`OSError`）：转 `CatalogError` 且信息带路径。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    contract = _write_contract(tmp_path)

    def _boom(self: Path, encoding: str | None = None) -> str:
        """测试替身：读取即抛 OSError。"""
        raise OSError("denied")

    monkeypatch.setattr(Path, "read_text", _boom)
    with pytest.raises(CatalogError, match="对端契约不可读"):
        products._contract_spec(contract)  # pyright: ignore[reportPrivateUsage]


def test_inspect_default_consumers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """默认消费方：未登记标识与前端应用名均拒；已登记服务键放行。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    _write_contract(tmp_path)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    # 03_01 方案 A：未登记的消费方**只告警不拒收**（本地看不到别的产品是常态，
    # 权威校验归注册通道与 04_02 跨仓对账），因此这里断言告警而非错误。
    for index, consumer in enumerate(("nobody", "desktop")):
        text = _TOML.replace('default_consumers = ["platform"]', f'default_consumers = ["{consumer}"]')
        report = inspect_product_manifests(
            ConcurrentStableList([_write(tmp_path, text, name=f"consumer-{index}.toml")])
        )
        assert not any("默认消费方未登记" in error for error in report.errors)
        assert any(f"默认消费方未随本次装载登记（{consumer}" in item for item in report.warnings)


def test_inspect_branch_id_cross_domain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """分支标识跨业务域混用：同一 `branch_id` 只允许同一业务域（同域多能力合法）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    _write_contract(tmp_path, ConcurrentStableFrozenList(("/api/v1/demo/internal/user-posts/{user_id}",)))
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)
    first = _TOML.replace(
        '[[collaborations]]\nname = "demo.org.dept-data"\ndomain = "org"\nkind = "dataset"\n'
        'path = "/api/v1/demo/data-source/dept-tree"\ndata_source_key = "demo_dept"\nfrontend_prefix = "demo"\n'
        'contract_version = "0.2.0"\ndefault_consumers = ["platform"]',
        '[[collaborations]]\nname = "demo.org.user-posts.assign"\ndomain = "org"\nkind = "txn-branch"\n'
        'path = "/api/v1/demo/internal/user-posts/{user_id}"\nbranch_id = "m"\n'
        'branch_op = "demo.user-posts.assign"\ncontract_version = "0.2.0"\ndefault_consumers = ["platform"]',
    )
    second = first.replace('domain = "org"', 'domain = "demo"').replace(
        'name = "demo.org.user-posts.assign"', 'name = "demo.demo.role-posts.assign"'
    )
    errors = inspect_product_manifests(
        ConcurrentStableList(
            [
                _write(tmp_path, first, name="first.toml"),
                _write(tmp_path, second, name="second.toml"),
            ]
        )
    ).errors

    assert any("分支标识跨业务域混用" in error for error in errors)


def test_inspect_type_tightening(tmp_path: Path) -> None:
    """类型收紧：`build_batch` 非整数 / `cascade` 非布尔 / 数组含非字符串 一律拒。

    Args:
        tmp_path: 临时目录。
    """
    with pytest.raises(CatalogError, match="build_batch 须为整数"):
        load_product_manifest(
            _write(
                tmp_path,
                'product_key = "demo"\n\n[[services]]\nmodule_key = "demo"\nname = "x"\n'
                'table_prefix = "demo_"\nevent_domain = "demo"\nbuild_batch = "3"\n',
                name="batch.toml",
            )
        )

    with pytest.raises(CatalogError, match="build_batch 须为整数"):
        load_product_manifest(
            _write(
                tmp_path,
                'product_key = "demo"\n\n[[services]]\nmodule_key = "demo"\nname = "x"\n'
                'table_prefix = "demo_"\nevent_domain = "demo"\nbuild_batch = true\n',
                name="batch-bool.toml",
            )
        )

    with pytest.raises(CatalogError, match="cascade 须为布尔"):
        load_product_manifest(
            _write(
                tmp_path,
                'product_key = "demo"\n\n[[data_sources]]\ndata_source_key = "demo_dept"\nname = "部门"\n'
                'data_source = "demo.demo.dept"\ncascade = "yes"\n',
                name="cascade.toml",
            )
        )

    with pytest.raises(CatalogError, match="permission_codes 须为字符串数组"):
        load_product_manifest(
            _write(
                tmp_path,
                'product_key = "demo"\n\n[[collaborations]]\nname = "demo.org.x"\ndomain = "org"\n'
                'kind = "codes"\ncontract_version = "0.1.0"\npermission_codes = [1]\n',
                name="codes.toml",
            )
        )


def test_inspect_seed_field_errors(tmp_path: Path) -> None:
    """种子字段反例：状态非法 / 必填缺失。

    Args:
        tmp_path: 临时目录。
    """
    with pytest.raises(CatalogError, match="status 非法"):
        load_product_manifest(
            _write(
                tmp_path,
                'product_key = "demo"\n\n[[seeds]]\nname = "demo-admin-codes"\n'
                'module = "demo.seeds.permissions"\nentry = "seed_admin_codes"\nstatus = "draft"\n',
                name="seed-status.toml",
            )
        )

    with pytest.raises(CatalogError, match="缺少必填字段"):
        load_product_manifest(
            _write(tmp_path, 'product_key = "demo"\n\n[[seeds]]\nname = "demo-admin-codes"\n', name="seed-missing.toml")
        )


def test_load_manifests_raises_and_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """装配期装配失败：聚合错误抛 `CatalogError`；警示经日志门面输出。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    path = _write(tmp_path, _TOML)
    _write_contract(tmp_path)
    _write_layout(tmp_path)
    _install_seed_package(monkeypatch)

    records: ConcurrentStableList[str] = ConcurrentStableList()

    class _Recorder:
        """记录 `warning(event, **fields)` 调用的假日志门面。"""

        def warning(self, event: str, **fields: Any) -> None:
            """记录事件与字段。

            Args:
                event: 事件名。
                **fields: 结构化字段。
            """
            records.add(f"{event}:{fields.get('detail')}")

    monkeypatch.setattr(products, "get_logger", lambda _name="bms": _Recorder())
    monkeypatch.setenv(SKIP_CONTRACT_ENV, "1")
    (tmp_path / "backend" / "deploy" / "contracts" / "demo.json").unlink()
    load_product_manifests(ConcurrentStableList([path]))
    assert any(entry.startswith("product_manifest_warning:") for entry in records)

    broken = _write(tmp_path, "product_key = ", name="broken.toml")
    with pytest.raises(CatalogError, match="产品清单装载失败"):
        load_product_manifests(ConcurrentStableList([broken]))


def test_inspect_invalid_manifest_short_circuits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """解析阶段出错即返回：不再做语义校验（错误一次报出，不做逐个试错）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    _point_base(monkeypatch, tmp_path)
    good = _write(tmp_path, _TOML)
    broken = _write(tmp_path, "product_key = ", name="broken.toml")
    _write_contract(tmp_path)
    _install_seed_package(monkeypatch)

    inspection = inspect_product_manifests(ConcurrentStableList([good, broken]))

    assert len(inspection.errors) == 1
    assert "TOML 非法" in inspection.errors[0]
    assert inspection.warnings == []
