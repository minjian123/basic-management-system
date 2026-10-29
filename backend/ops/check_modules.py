"""CI 服务目录与声明校验（三档）：离线 / 接库 / 跨仓。

用法：

```bash
cd backend
uv run python -m ops.check_modules                 # 离线断言 + 接库（URL 读配置解析）
uv run python -m ops.check_modules --offline       # 仅离线断言（无库场景）
uv run python -m ops.check_modules --cross-repo    # 跨仓档：L1 契约定位 + L2 注册表对账（一次性临时库）
```

- **离线**：复用 `ModuleRegistry.validate()` / `ProductRegistry.validate()` 校验清单（服务目录四要素唯一 /
  格式 / 维度 / 产品归属；产品档案标识唯一 / 格式 / 状态），并比对服务工程自报契约版本
  （`CONTRACT_VERSION`）与清单登记值的主版本；服务工程 ↔ 清单双向核对（工程存在但未登记即失败；
  planned 且无工程目录跳过）。服务包常量经 AST 静态读取，不导入服务包。
- **清单**（07B `04_02`，`[registry].product_manifests` 已退役）：取源固定为**本仓**
  `deploy/registry/*.toml` 自动发现 + `--manifest` 显式追加（排障 / CI 指外部目录）；装载校验
  复用装载期同一实现（`inspect_product_manifests`），覆盖能力 / 种子 / 错误码 / 使用声明四段，
  未配置清单时提示「无清单可校验」（不静默）。
- **接库**（缺省读配置解析，`--url` 显式覆盖）：读平台库 `sys_module` / `sys_product`（未软删行）
  查重与格式校验 + 与**声明**双向对账（07B `04_02` 口径：平台自身行以常量为基准、产品行以各自
  声明为基准），**只读不写**；`--offline` 强制跳过接库。
- **跨仓档**（`--cross-repo`，07B `04_02`）：
  - **L1 跨仓文件校验**：本仓清单 + 各产品仓清单一次装载（`inspect_product_manifests`），校验
    「声明 ↔ 产品自己的契约」（访问面定位 / 主版本 / 错误码段位与反向 / 种子入口 / 使用声明）；
  - **L2 注册表一致性**：在 `tempfile` 生成的一次性 SQLite 上建表（26 表，与启动期同一
    `apply_unit_schema`）、平台自注册 → 各产品注册（按 `product_key` 升序）、再做「声明 ↔ 注册表」
    与「平台常量行 ↔ 库」双向对账；用完即删（`--keep-tmp` 保留便于复现）；
  - 产品仓取源：`--product-root`（可重复）或缺省扫描**同级克隆**（`<工作区>/<repo>/deploy/registry`）；
    一个都取不到即失败（`--allow-missing` 才允许跳过并警示）。
- 冲突 / 非法 → 打印明细并退出码 1；参数或环境错误 → 退出码 2；通过 → 退出码 0。
"""

import argparse
import ast
import asyncio
import shutil
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.exceptions import CatalogError
from bms_core.core.version import contract_major
from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_core.db.migration import validate_series_registry
from bms_core.registry.declarations import (
    DECLARATION_KINDS,
    DeclarationPayload,
    RegistrySnapshot,
    content_hash_of,
    declaration_key,
    from_manifest,
    validate_seed_tables,
)
from bms_core.registry.products import (
    inspect_product_manifests,
    load_product_manifest,
    local_manifest_paths,
    register_domain_services,
)
from bms_core.services.module_registry import (
    PRODUCT_CATALOG,
    SERVICE_CATALOG,
    ModuleRecord,
    ModuleRegistry,
    ProductRecord,
    ProductRegistry,
    validate_catalog,
    validate_products,
)
from bms_platform.domains.platform_registry.repositories.declaration_repository import DeclarationRepository
from bms_platform.domains.platform_registry.repositories.module_repository import ModuleRepository
from bms_platform.domains.platform_registry.repositories.product_repository import ProductRepository
from bms_platform.domains.platform_registry.services.declaration_registry import DeclarationRegistryService
from ops.seed_tenant import resolve_url

RUN_IMAGE = "ci"
"""本脚本导入 `bms_platform.*`（校验职责需实例化平台应用 / 仓储），在 CI 与开发机的全量工作区运行，无镜像边界。"""
_SERVICES_DIR = Path(__file__).resolve().parents[1] / "services"
"""服务工程根（`backend/services`）。"""
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
"""后端工程根（`backend/`）：清单相对路径与显式路径的解析基准。"""
_REPO_ROOT = _BACKEND_ROOT.parent
"""仓库根：同级克隆发现以它的父目录（工作区根）为基准。"""
_CONTRACT_CONSTANT = "CONTRACT_VERSION"
"""服务包自报契约版本常量名。"""
_REGISTRY_RELATIVE = Path("deploy") / "registry"
"""声明目录（相对仓根；本仓与产品仓同一口径）。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="服务目录 / 声明校验（离线 + 接库 + 跨仓三档）")
    parser.add_argument("--url", default="", help="平台库连接串（显式覆盖；缺省按配置解析）")
    parser.add_argument("--offline", action="store_true", help="仅离线断言，不接库")
    parser.add_argument(
        "--manifest",
        action="append",
        default=[],
        metavar="PATH",
        help="追加声明清单（可重复；相对路径锚 backend/；本仓 deploy/registry/ 恒自动发现）",
    )
    parser.add_argument(
        "--cross-repo",
        action="store_true",
        help="跨仓档：L1 跨仓契约校验 + L2 注册表一致性（一次性临时库）",
    )
    parser.add_argument(
        "--product-root",
        action="append",
        default=[],
        metavar="PATH",
        help="产品仓根或 deploy/registry 目录（可重复；缺省扫描同级克隆）",
    )
    parser.add_argument("--ephemeral", action="store_true", help="用一次性临时库跑注册与对账（与 --url 互斥）")
    parser.add_argument("--keep-tmp", action="store_true", help="保留一次性临时库目录并打印路径（复现用）")
    parser.add_argument("--allow-missing", action="store_true", help="取不到产品仓时跳过并警示（缺省取不到即失败）")
    return parser


def _extract_contract_version(init_path: Path) -> str | None:
    """AST 静态提取服务包 `__init__.py` 的 `CONTRACT_VERSION` 字符串字面量。

    Args:
        init_path: 服务包 `__init__.py` 路径。

    Returns:
        str | None: 常量值；未声明或非字符串字面量返回 None。
    """
    module = ast.parse(init_path.read_text(encoding="utf-8"))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == _CONTRACT_CONSTANT for target in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
        return None
    return None


def resolve_service_contracts(services_dir: Path = _SERVICES_DIR) -> ConcurrentStableDict[str, str | None]:
    """扫描服务工程读各自报契约版本。

    Args:
        services_dir: 服务工程根。

    Returns:
        ConcurrentStableDict[str, str | None]: {服务名: 自报契约版本}；已声明但非字符串字面量为 None。
    """
    declarations: ConcurrentStableDict[str, str | None] = ConcurrentStableDict()
    for entry in sorted(services_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        init_path = entry / "src" / f"bms_{entry.name}" / "__init__.py"
        if init_path.is_file():
            declarations.set(entry.name, _extract_contract_version(init_path))
    return declarations


def check_service_declarations(
    catalog: ConcurrentStableList[ModuleRecord],
    declarations: ConcurrentStableDict[str, str | None],
) -> ConcurrentStableList[str]:
    """服务工程声明 ↔ 清单双向核对（工程未登记 / 未声明常量 / 主版本不符）。

    Args:
        catalog: 服务目录清单。
        declarations: 服务工程自报契约版本映射。

    Returns:
        ConcurrentStableList[str]: 冲突 / 非法明细。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    expected = {module.service_key for module in catalog if module.service_key}
    for name in sorted(declarations):
        if name not in expected:
            errors.add(f"服务工程未登记：{name}")
    for module in catalog:
        if module.service_key is None or module.service_key not in declarations:
            continue
        declared = declarations[module.service_key]
        if declared is None:
            errors.add(f"{module.service_key}：服务包未声明 CONTRACT_VERSION")
            continue
        declared_major = contract_major(declared)
        if declared_major is None:
            errors.add(f"{module.service_key}：服务包契约版本非 semver（{declared}）")
            continue
        if declared_major != contract_major(module.contract_version):
            errors.add(
                f"{module.service_key}：服务包契约版本与清单主版本不符"
                f"（服务包 {declared}，清单 {module.contract_version}）"
            )
    return errors


def check_offline(services_dir: Path = _SERVICES_DIR) -> ConcurrentStableList[str]:
    """离线校验：服务目录 / 产品档案清单自校验 + 服务包声明比对。

    Args:
        services_dir: 服务工程根。

    Returns:
        ConcurrentStableList[str]: 冲突 / 非法明细。
    """
    errors = ConcurrentStableList(ModuleRegistry().validate())
    errors.update(ProductRegistry().validate())
    errors.update(
        check_service_declarations(ConcurrentStableList(SERVICE_CATALOG), resolve_service_contracts(services_dir))
    )
    return errors


def manifest_paths(extra: Iterable[str] = ()) -> ConcurrentStableList[Path]:
    """本次校验的清单路径：本仓自动发现（平台在前）+ `--manifest` 追加（去重保序）。

    Args:
        extra: 命令行追加的路径（相对路径锚 `backend/`）。

    Returns:
        ConcurrentStableList[Path]: 清单绝对路径。
    """
    paths: ConcurrentStableList[Path] = ConcurrentStableList(local_manifest_paths())
    seen = {path.resolve() for path in paths}
    for raw in extra:
        candidate = Path(raw)
        resolved = (candidate if candidate.is_absolute() else (_BACKEND_ROOT / candidate)).resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        paths.add(resolved)
    return paths


def check_manifests(extra: Iterable[str] = ()) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str]]:
    """装载并校验声明清单的能力 / 种子 / 错误码 / 使用声明段（复用装载期同一实现）。

    07B `04_02`：取源从「`[registry].product_manifests`」改为「本仓自动发现 + `--manifest`」——
    此前配置恒为空导致本仓 `platform.toml` 的四段校验在 CI 上**空跑**（只被 `gateway_config check`
    顺带覆盖）；现在平台自身声明也走这条门禁。

    Args:
        extra: 命令行追加的清单路径。

    Returns:
        tuple[ConcurrentStableList[str], ConcurrentStableList[str]]: （错误明细, 跳过 / 降级提示）。
    """
    paths = manifest_paths(extra)
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    warnings: ConcurrentStableList[str] = ConcurrentStableList()
    if not paths:
        warnings.add("[清单] 无任何清单可校验（本仓 deploy/registry/ 为空，且未给 --manifest）")
        return errors, warnings
    inspection = inspect_product_manifests(paths)
    errors.update(inspection.errors)
    errors.update(validate_series_registry())
    # 平台自身种子的 `[seeds.tables]` 表名存在性（07B `04_02`）：与注册期同一实现，装载期即暴露
    for manifest in inspection.manifests:
        if manifest.product_key == PLATFORM_SERVICE_KEY:
            errors.update(validate_seed_tables(_with_platform_services(from_manifest(manifest))))
    warnings.update(inspection.warnings)
    return errors, warnings


async def _read_catalog(url: str) -> ConcurrentStableList[ModuleRecord]:
    """只读读取平台库服务目录（未软删行）。

    Args:
        url: 平台库连接串。

    Returns:
        ConcurrentStableList[ModuleRecord]: 登记记录列表。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = await ModuleRepository(session).list_catalog()
    finally:
        await engine.dispose()
    return ConcurrentStableList(ModuleRecord.from_row(row) for row in rows)


async def _read_products(url: str) -> ConcurrentStableList[ProductRecord]:
    """只读读取平台库产品档案（未软删行）。

    Args:
        url: 平台库连接串。

    Returns:
        ConcurrentStableList[ProductRecord]: 产品档案记录列表。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = await ProductRepository(session).list_products()
    finally:
        await engine.dispose()
    return ConcurrentStableList(ProductRecord.from_row(row) for row in rows)


def declared_products(payloads: ConcurrentStableList[DeclarationPayload]) -> ConcurrentStableList[ProductRecord]:
    """本次声明的产品档案（按 `product_key` 去重保序）。

    Args:
        payloads: 各声明方的载荷（平台在前）。

    Returns:
        ConcurrentStableList[ProductRecord]: 产品档案记录。
    """
    merged: ConcurrentStableDict[str, ProductRecord] = ConcurrentStableDict()
    for payload in payloads:
        for record in payload.products:
            if record.product_key not in merged:
                merged.set(record.product_key, record)
    return ConcurrentStableList(merged.values())


async def _check_catalog_db(
    url: str,
    payloads: ConcurrentStableList[DeclarationPayload],
    warnings: ConcurrentStableList[str],
) -> ConcurrentStableList[str]:
    """接库校验：读库查重与格式 + 与**声明**双向对账（07B `04_02` 口径）。

    基准（`02_06` 注册表权威化后的修正）：

    - **平台自身行**（`product_key` 为空）：以常量 `SERVICE_CATALOG` 为基准双向对账；
    - **产品行 / 产品档案**：以各自清单声明为基准（产品自己声明自己，不在常量里）；
    - 常量登记了、但无任何清单声明的产品档案（如计划产品 `biz` / `cw`）：**警示**不判红。

    Args:
        url: 平台库连接串（迁移 + 注册后）。
        payloads: 本次声明（平台 + 产品）。
        warnings: 警示收集器。

    Returns:
        ConcurrentStableList[str]: 冲突 / 非法明细（含库不可读）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    try:
        records = await _read_catalog(url)
    except Exception as exc:
        return ConcurrentStableList([f"服务目录库不可读（请先执行平台库迁移）：{exc}"])
    expected_platform = ConcurrentStableList(record for record in SERVICE_CATALOG if not record.product_key)
    actual_platform = ConcurrentStableList(record for record in records if not record.product_key)
    if not actual_platform:
        errors.add("库中无平台自身服务行（注册未执行？）")
    else:
        # 路由映射属声明方所有：常量维度的目录对账跳过（路由由 `diff_platform_declarations` 按声明比）
        errors.update(
            validate_catalog(
                expected_platform,
                actual_platform,
                products=ConcurrentStableList(PRODUCT_CATALOG),
                routes=ConcurrentStableList(),
            )
        )
    try:
        products = await _read_products(url)
    except Exception as exc:
        errors.add(f"产品档案库不可读（请先执行平台库迁移）：{exc}")
        return errors
    declared = declared_products(payloads)
    declared_keys = {record.product_key for record in declared}
    for record in PRODUCT_CATALOG:
        if record.product_key not in declared_keys:
            warnings.add(
                f"[产品] 常量登记的产品 {record.product_key} 无任何清单声明"
                "（07B `04_02`：产品档案以声明为权威；该产品尚未自持声明，暂不判缺）"
            )
    if not declared:
        warnings.add("[产品] 本次无任何产品声明：跳过产品档案对账")
        return errors
    errors.update(validate_products(declared, products))
    return errors


def check_catalog_db(
    url: str,
    payloads: ConcurrentStableList[DeclarationPayload],
    warnings: ConcurrentStableList[str],
) -> ConcurrentStableList[str]:
    """接库校验的同步壳（注册表档在事件循环内用 `_check_catalog_db`）。

    Args:
        url: 平台库连接串。
        payloads: 本次声明。
        warnings: 警示收集器。

    Returns:
        ConcurrentStableList[str]: 冲突 / 非法明细。
    """
    return asyncio.run(_check_catalog_db(url, payloads, warnings))


def diff_platform_declarations(snapshot: RegistrySnapshot, payload: DeclarationPayload) -> ConcurrentStableList[str]:
    """注册表 ↔ 声明对账（07B `02_06`）：按声明方作用域逐类比对。

    口径：

    - 只比**本声明方**名下的行（`RegistrySnapshot.owner_of`），别的产品行不参与；
    - 已退役的行视为「库里没有」（再声明即恢复，不算缺失）；
    - 内容指纹不同 = 声明漂移（库未随代码更新）；库里多出的行同样报出（声明缺失）。

    Args:
        snapshot: 注册表现状（只读）。
        payload: 本声明方载荷。

    Returns:
        ConcurrentStableList[str]: 差异明细（空表示一致）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    for kind in DECLARATION_KINDS:
        declared: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for record in payload.of(kind):
            declared.set(declaration_key(kind, record), content_hash_of(kind, record))
        stored: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for record in snapshot.of(kind):
            key = declaration_key(kind, record)
            if snapshot.owner_of(kind, key) != payload.product_key or snapshot.is_retired(kind, key):
                continue
            stored.set(key, content_hash_of(kind, record))
        for key, fingerprint in declared.items():
            current = stored.get(key)
            if current is None:
                errors.add(f"{payload.product_key}｜{kind}｜{key}：注册表缺该声明（未注册或已退役）")
            elif current != fingerprint:
                errors.add(f"{payload.product_key}｜{kind}｜{key}：声明与注册表不一致（库未随代码更新）")
        for key in stored:
            if key not in declared:
                errors.add(f"{payload.product_key}｜{kind}｜{key}：注册表多出声明（本次声明未包含）")
    return errors


async def _read_registry(url: str) -> RegistrySnapshot:
    """只读读取注册表现状（八类表）。

    Args:
        url: 平台库连接串。

    Returns:
        RegistrySnapshot: 注册表快照。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await DeclarationRepository(session).load_snapshot()
    finally:
        await engine.dispose()


async def _check_registry_db(
    url: str, payloads: ConcurrentStableList[DeclarationPayload], warnings: ConcurrentStableList[str]
) -> ConcurrentStableList[str]:
    """接库对账：注册表 ↔ 各声明方声明（平台 + 产品逐方比对）。

    Args:
        url: 平台库连接串（迁移 + 注册后）。
        payloads: 各声明方载荷。
        warnings: 警示收集器。

    Returns:
        ConcurrentStableList[str]: 差异明细（含库不可读 / 未建表提示）。
    """
    try:
        snapshot = await _read_registry(url)
    except Exception as exc:
        text = str(exc).lower()
        if "no such table" in text or "does not exist" in text or "invalid object name" in text:
            # 尚未建注册表（老库 / 迁移未跑）：跳过对账并明示，不把「还没迁移」当成「声明漂移」
            warnings.add("[注册表] 未建表：跳过注册表对账（请先执行迁移与注册）")
            return ConcurrentStableList()
        return ConcurrentStableList([f"注册表库不可读（请先执行迁移与注册）：{exc}"])
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    for payload in payloads:
        errors.update(diff_platform_declarations(snapshot, payload))
    return errors


def check_registry_db(
    url: str, payloads: ConcurrentStableList[DeclarationPayload], warnings: ConcurrentStableList[str]
) -> ConcurrentStableList[str]:
    """注册表对账的同步壳（注册表档在事件循环内用 `_check_registry_db`）。

    Args:
        url: 平台库连接串。
        payloads: 各声明方载荷。
        warnings: 警示收集器。

    Returns:
        ConcurrentStableList[str]: 差异明细。
    """
    return asyncio.run(_check_registry_db(url, payloads, warnings))


def platform_payload() -> DeclarationPayload:
    """取本仓平台声明载荷（平台自身清单 + `product_key` 为空的平台自身服务行）。

    07B `04_02`：只并 `product_key` 为空的行——与 `declaration_bootstrap`（`02_06` 修正 #3）同口径。
    此前并入整个 `SERVICE_CATALOG` 会让计划产品行（`biz` / `cw` 名下）按 `product_key` 落库后被
    判为「不是平台的行」，对账恒报 6 项缺失。

    Returns:
        DeclarationPayload: 注册载荷。

    Raises:
        CatalogError: 本仓平台清单缺失。
    """
    for path in local_manifest_paths():
        if path.name == f"{PLATFORM_SERVICE_KEY}.toml":
            return _with_platform_services(from_manifest(load_product_manifest(path)))
    raise CatalogError(f"本仓平台清单缺失：deploy/registry/{PLATFORM_SERVICE_KEY}.toml")


def _with_platform_services(payload: DeclarationPayload) -> DeclarationPayload:
    """把 `SERVICE_CATALOG` 中 `product_key` 为空的平台自身服务行并进载荷（同键去重）。

    Args:
        payload: 平台清单载荷。

    Returns:
        DeclarationPayload: 合并后的载荷。
    """
    services: ConcurrentStableList[ModuleRecord] = ConcurrentStableList(
        record for record in SERVICE_CATALOG if not record.product_key
    )
    known = {record.module_key for record in services}
    for record in payload.services:
        if record.module_key not in known:
            services.add(record)
            known.add(record.module_key)
    return DeclarationPayload(
        product_key=payload.product_key,
        service_key=payload.service_key,
        contract_version=payload.contract_version,
        products=payload.products,
        services=ConcurrentStableFrozenList(services),
        product_routes=payload.product_routes,
        data_sources=payload.data_sources,
        collaborations=payload.collaborations,
        seeds=payload.seeds,
        errcodes=payload.errcodes,
        usages=payload.usages,
    )


def _has_platform(payloads: ConcurrentStableList[DeclarationPayload]) -> bool:
    """载荷里是否含平台声明（对账基准是否就绪）。

    Args:
        payloads: 各声明方载荷。

    Returns:
        bool: 含平台声明 True。
    """
    return any(payload.product_key == PLATFORM_SERVICE_KEY for payload in payloads)


def payloads_of(paths: Iterable[Path]) -> ConcurrentStableList[DeclarationPayload]:
    """把清单路径转成注册载荷（平台在前，产品按 `product_key` 升序）。

    Args:
        paths: 清单路径序列。

    Returns:
        ConcurrentStableList[DeclarationPayload]: 注册载荷（与清单一一对应）。
    """
    inspection = inspect_product_manifests(paths)
    platform: ConcurrentStableList[DeclarationPayload] = ConcurrentStableList()
    products: ConcurrentStableDict[str, DeclarationPayload] = ConcurrentStableDict()
    for manifest in inspection.manifests:
        if manifest.product_key == PLATFORM_SERVICE_KEY:
            platform.add(_with_platform_services(from_manifest(manifest)))
            continue
        if manifest.product_key not in products:
            products.set(manifest.product_key, from_manifest(manifest))
    payloads: ConcurrentStableList[DeclarationPayload] = ConcurrentStableList(platform)
    for key in sorted(products):
        record = products.get(key)
        if record is not None:
            payloads.add(record)
    return payloads


def _is_registry_dir(path: Path) -> bool:
    """是否声明目录（含 `*.toml` 的 `deploy/registry`）。

    Args:
        path: 待判定目录。

    Returns:
        bool: 是声明目录 True。
    """
    return path.is_dir() and any(path.glob("*.toml"))


def _expand_root(path: Path) -> ConcurrentStableList[Path]:
    """把一条路径规整为产品仓根清单（支持三种形态）。

    - 产品仓根（含 `deploy/registry/*.toml`）→ 自身；
    - 声明目录（`…/deploy/registry`）→ 其仓根；
    - **克隆容器目录**（CI 的 `../product`：下级各仓）→ 逐个子目录按前两条展开。

    Args:
        path: 候选路径。

    Returns:
        ConcurrentStableList[Path]: 产品仓根（可能为空）。
    """
    roots: ConcurrentStableList[Path] = ConcurrentStableList()
    if _is_registry_dir(path / _REGISTRY_RELATIVE):
        roots.add(path)
        return roots
    if path.name == _REGISTRY_RELATIVE.name and _is_registry_dir(path):
        roots.add(path.parent.parent)
        return roots
    if path.is_dir():
        for entry in sorted(path.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if _is_registry_dir(entry / _REGISTRY_RELATIVE):
                roots.add(entry)
    return roots


def _sibling_product_roots() -> ConcurrentStableList[Path]:
    """扫描同级克隆（工作区根下除本仓外、含 `deploy/registry/*.toml` 的目录）。

    Returns:
        ConcurrentStableList[Path]: 产品仓根（按目录名排序）。
    """
    roots: ConcurrentStableList[Path] = ConcurrentStableList()
    workspace = _REPO_ROOT.parent
    if not workspace.is_dir():
        return roots
    for entry in sorted(workspace.iterdir()):
        if not entry.is_dir() or entry.resolve() == _REPO_ROOT.resolve() or entry.name.startswith("."):
            continue
        for root in _expand_root(entry):
            roots.add(root)
    return roots


def resolve_product_roots(explicit: Iterable[str]) -> ConcurrentStableList[Path]:
    """解析产品仓根：显式优先（仓根 / 声明目录 / 克隆容器目录），缺省扫描同级克隆。

    Args:
        explicit: `--product-root` 给的路径。

    Returns:
        ConcurrentStableList[Path]: 产品仓根（去重保序）。
    """
    if not explicit:
        return _sibling_product_roots()
    roots: ConcurrentStableList[Path] = ConcurrentStableList()
    seen: ConcurrentStableSet[Path] = ConcurrentStableSet()
    for raw in explicit:
        path = Path(raw)
        if not path.is_absolute():
            path = (_REPO_ROOT / path).resolve()
        for root in _expand_root(path):
            if root in seen:
                continue
            seen.add(root)
            roots.add(root)
    return roots


def product_manifest_paths(roots: Iterable[Path]) -> ConcurrentStableList[Path]:
    """取各产品仓的声明清单（`deploy/registry/*.toml`；平台清单不收）。

    Args:
        roots: 产品仓根（或直接给 `deploy/registry` 目录）。

    Returns:
        ConcurrentStableList[Path]: 产品清单路径（按仓名 + 文件名排序）。
    """
    paths: ConcurrentStableList[Path] = ConcurrentStableList()
    for root in roots:
        registry = root if root.name == _REGISTRY_RELATIVE.name and root.is_dir() else root / _REGISTRY_RELATIVE
        if not registry.is_dir():
            continue
        for path in sorted(registry.glob("*.toml")):
            if path.name == f"{PLATFORM_SERVICE_KEY}.toml":
                continue
            paths.add(path)
    return paths


async def _apply_schema(url: str) -> None:
    """在一次性库上按平台单元建表（与启动期 / `ops.init_schema` 同一入口）。

    Args:
        url: 一次性库连接串。
    """
    from bms_core.db.bootstrap import apply_unit_schema
    from bms_core.db.migration import DATASOURCE_PLATFORM

    await apply_unit_schema(PLATFORM_SERVICE_KEY, DATASOURCE_PLATFORM, url, target="跨仓临时库")


async def _register_payloads(
    url: str, payloads: ConcurrentStableList[DeclarationPayload]
) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str]]:
    """按顺序注册各声明方（平台在前），返回（错误, 逐方摘要）。

    Args:
        url: 一次性库连接串。
        payloads: 注册载荷（平台在前）。

    Returns:
        tuple[ConcurrentStableList[str], ConcurrentStableList[str]]: （错误明细, 摘要行）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for payload in payloads:
            async with factory() as session:
                try:
                    report = await DeclarationRegistryService(session).register(payload)
                    await session.commit()
                except CatalogError as exc:
                    await session.rollback()
                    errors.add(str(exc))
                    continue
            created = sum(report.created.values())
            unchanged = sum(report.unchanged.values())
            lines.add(f"{payload.product_key}：新增 {created} / 未变 {unchanged}")
            for warning in report.warnings:
                lines.add(f"  · {warning}")
    finally:
        await engine.dispose()
    return errors, lines


async def _run_registry_checks(
    payloads: ConcurrentStableList[DeclarationPayload], *, url: str, keep_tmp: bool
) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str], ConcurrentStableList[str]]:
    """L2：建一次性库 → 注册 → 双向对账。

    Args:
        payloads: 注册载荷（平台在前）。
        url: 一次性库连接串。
        keep_tmp: 是否保留临时目录。

    Returns:
        tuple[ConcurrentStableList[str], ConcurrentStableList[str], ConcurrentStableList[str]]:
            （错误, 警示, 摘要行）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    warnings: ConcurrentStableList[str] = ConcurrentStableList()
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    try:
        await _apply_schema(url)
    except Exception as exc:
        errors.add(f"一次性库建表失败（{type(exc).__name__}: {exc}）")
        return errors, warnings, lines
    register_errors, register_lines = await _register_payloads(url, payloads)
    errors.update(register_errors)
    lines.update(register_lines)
    if register_errors:
        return errors, warnings, lines
    errors.update(await _check_catalog_db(url, payloads, warnings))
    errors.update(await _check_registry_db(url, payloads, warnings))
    return errors, warnings, lines


def run_cross_repo(
    *, product_roots: Iterable[str], manifests: Iterable[str], allow_missing: bool, keep_tmp: bool
) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str], ConcurrentStableList[str]]:
    """跨仓档：L1 跨仓契约校验 + L2 注册表一致性。

    Args:
        product_roots: `--product-root`（可为空 → 扫描同级克隆）。
        manifests: `--manifest` 追加清单（L1 一并装载）。
        allow_missing: 取不到产品仓时是否允许跳过。
        keep_tmp: 是否保留一次性临时库。

    Returns:
        tuple[ConcurrentStableList[str], ConcurrentStableList[str], ConcurrentStableList[str]]:
            （错误, 警示, 摘要行）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    warnings: ConcurrentStableList[str] = ConcurrentStableList()
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    roots = resolve_product_roots(product_roots)
    product_paths = product_manifest_paths(roots)
    if not product_paths:
        message = (
            "未取到任何产品仓声明（同级克隆缺失且未给 --product-root）："
            "跨仓契约校验无法进行（如需临时放行加 --allow-missing）"
        )
        if allow_missing:
            warnings.add(f"[跨仓] {message}（已显式跳过）")
            return errors, warnings, lines
        errors.add(message)
        return errors, warnings, lines
    for root in roots:
        lines.add(f"[跨仓] 产品仓：{root}")
    # L1：本仓清单 + 产品清单一次装载（跨清单一致性依赖「一次装载」）
    l1_paths = ConcurrentStableList(manifest_paths(manifests))
    known = {path.resolve() for path in l1_paths}
    for path in product_paths:
        if path.resolve() not in known:
            known.add(path.resolve())
            l1_paths.add(path)
    inspection = inspect_product_manifests(l1_paths)
    errors.update(inspection.errors)
    warnings.update(inspection.warnings)
    lines.add(
        f"[跨仓] L1 装载校验：{len(inspection.manifests)} 份清单"
        f"（{', '.join(manifest.product_key for manifest in inspection.manifests)}）"
        f" → {len(inspection.errors)} 错误 / {len(inspection.warnings)} 警示"
    )
    if inspection.errors:
        return errors, warnings, lines
    # 域布局（能力寻址第二段的校验基准）先登记，注册期校验要用
    register_domain_services(inspection.domain_services)
    payloads = payloads_of(l1_paths)
    if not _has_platform(payloads):
        errors.add(f"本仓平台声明缺失：deploy/registry/{PLATFORM_SERVICE_KEY}.toml（跨仓对账无基准）")
        return errors, warnings, lines
    tmp_dir = Path(tempfile.mkdtemp(prefix="bms-cross-repo-"))
    url = f"sqlite+aiosqlite:///{(tmp_dir / 'registry.db').as_posix()}"
    try:
        l2_errors, l2_warnings, l2_lines = asyncio.run(_run_registry_checks(payloads, url=url, keep_tmp=keep_tmp))
    finally:
        if keep_tmp:
            print(f"[跨仓] 临时库保留：{tmp_dir}")
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    errors.update(l2_errors)
    warnings.update(l2_warnings)
    lines.update(l2_lines)
    lines.add(f"[跨仓] L2 注册表：{len(payloads)} 个声明方 → {len(l2_errors)} 差异")
    return errors, warnings, lines


def run_ephemeral(
    *, manifests: Iterable[str], keep_tmp: bool
) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str], ConcurrentStableList[str]]:
    """一次性库档（`--ephemeral`，无产品仓）：本仓清单 → 注册 → 对账。

    Args:
        manifests: `--manifest` 追加清单。
        keep_tmp: 是否保留一次性临时库。

    Returns:
        tuple[ConcurrentStableList[str], ConcurrentStableList[str], ConcurrentStableList[str]]:
            （错误, 警示, 摘要行）。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    warnings: ConcurrentStableList[str] = ConcurrentStableList()
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    paths = manifest_paths(manifests)
    inspection = inspect_product_manifests(paths)
    errors.update(inspection.errors)
    warnings.update(inspection.warnings)
    if inspection.errors:
        return errors, warnings, lines
    register_domain_services(inspection.domain_services)
    payloads = payloads_of(paths)
    if not _has_platform(payloads):
        errors.add(f"本仓平台声明缺失：deploy/registry/{PLATFORM_SERVICE_KEY}.toml（注册对账无基准）")
        return errors, warnings, lines
    tmp_dir = Path(tempfile.mkdtemp(prefix="bms-registry-"))
    url = f"sqlite+aiosqlite:///{(tmp_dir / 'registry.db').as_posix()}"
    try:
        l2_errors, l2_warnings, l2_lines = asyncio.run(_run_registry_checks(payloads, url=url, keep_tmp=keep_tmp))
    finally:
        if keep_tmp:
            print(f"[注册表] 临时库保留：{tmp_dir}")
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    errors.update(l2_errors)
    warnings.update(l2_warnings)
    lines.update(l2_lines)
    return errors, warnings, lines


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口：离线校验（默认）+ 可选接库 / 跨仓校验。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（0 通过 / 1 失败 / 2 参数或环境错误）。
    """
    args = build_parser().parse_args(argv)
    if args.ephemeral and args.url:
        print("[服务目录] --ephemeral 与 --url 互斥（一次性库不连既有库）", file=sys.stderr)
        return 2
    if (args.cross_repo or args.product_root) and args.url:
        print("[服务目录] 跨仓档固定使用一次性临时库，不接受 --url", file=sys.stderr)
        return 2
    if (args.cross_repo or args.product_root) and args.offline:
        print("[服务目录] --cross-repo 与 --offline 互斥（跨仓档需要建临时库）", file=sys.stderr)
        return 2
    errors = check_offline()
    manifest_errors, warnings = check_manifests(args.manifest)
    errors.update(manifest_errors)
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    cross = args.cross_repo or bool(args.product_root)
    if cross:
        con_errors, con_warnings, con_lines = run_cross_repo(
            product_roots=args.product_root,
            manifests=args.manifest,
            allow_missing=args.allow_missing,
            keep_tmp=args.keep_tmp,
        )
        errors.update(con_errors)
        warnings.update(con_warnings)
        lines.update(con_lines)
    elif args.ephemeral:
        ep_errors, ep_warnings, ep_lines = run_ephemeral(manifests=args.manifest, keep_tmp=args.keep_tmp)
        errors.update(ep_errors)
        warnings.update(ep_warnings)
        lines.update(ep_lines)
    else:
        url = "" if args.offline else (args.url or resolve_url(service=PLATFORM_SERVICE_KEY))
        if url:
            payloads = payloads_of(manifest_paths(args.manifest))
            if not _has_platform(payloads):
                errors.add(f"本仓声明不可读：deploy/registry/{PLATFORM_SERVICE_KEY}.toml 缺失（接库对账无基准）")
            else:
                errors.update(check_catalog_db(url, payloads, warnings))
                # 注册表 ↔ 声明对账（07B `02_06`）：声明漂移在 CI 暴露，而不是等到启动期
                errors.update(check_registry_db(url, payloads, warnings))
    for line in lines:
        print(line)
    for warning in warnings:
        print(warning)
    if errors:
        for error in errors:
            print(f"[服务目录] {error}")
        print(f"[服务目录] 校验失败（{len(errors)} 项）")
        return 1
    scope = f"清单 {len(SERVICE_CATALOG)} 项 + 产品档案 {len(PRODUCT_CATALOG)} 项 + 服务包声明 + 声明清单"
    if cross or args.ephemeral:
        scope += " + 跨仓契约 + 注册表对账"
    elif args.url or not args.offline:
        scope += " + 接库对账"
    print(f"[服务目录] 校验通过（{scope}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(ConcurrentStableList(sys.argv[1:])))
