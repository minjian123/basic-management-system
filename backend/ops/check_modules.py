"""CI 服务目录与产品档案校验：离线清单 / 服务包契约声明 + 接库（迁移与种子后）查重与对账。

用法：

```bash
cd backend
uv run python -m ops.check_modules              # 离线断言 + 接库（URL 读配置解析）
uv run python -m ops.check_modules --offline    # 仅离线断言（无库场景）
```

- **离线**：复用 `ModuleRegistry.validate()` / `ProductRegistry.validate()` 校验清单
  （服务目录四要素唯一 / 格式 / 维度 / 产品归属；产品档案标识唯一 / 格式 / 状态），并比对
  服务工程自报契约版本（`CONTRACT_VERSION`）与清单登记值的主版本；服务工程 ↔ 清单双向核对
  （工程存在但未登记即失败；planned 且无工程目录跳过）。服务包常量经 AST 静态读取，不导入服务包。
- **产品自持清单**（07B `02_01` / `02_05`）：按 `[registry].product_manifests` 装载并做能力 / 种子 /
  错误码三段校验（能力重名 / 业务域 / 归属 / 访问面契约定位 / 版本兼容 / 种子入口 / 错误码段位与撞码
  及契约反向对账），**复用装载期同一校验函数**（不新增并行校验入口）；未配置清单时跳过并打印提示，
  跳过项与降级提示（含「未声明错误码的端点」统计）一律输出（不静默）。
- **接库**（缺省读配置解析，`--url` 显式覆盖）：读平台库 `sys_module` / `sys_product`（未软删行）
  查重与格式校验 + 与清单双向对账，**只读不写**；空库判失败（种子未执行）。`--offline` 强制跳过接库。
- 冲突 / 非法 → 打印明细并退出码 1；通过 → 退出码 0。
"""

import argparse
import ast
import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import get_settings
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
)
from bms_core.registry.products import inspect_product_manifests, load_product_manifest, local_manifest_paths
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
from ops.seed_tenant import resolve_url

RUN_IMAGE = "ci"
"""本脚本导入 `bms_platform.*`（校验职责需实例化平台应用 / 仓储），在 CI 与开发机的全量工作区运行，无镜像边界。"""
_SERVICES_DIR = Path(__file__).resolve().parents[1] / "services"
"""服务工程根（`backend/services`）。"""

_CONTRACT_CONSTANT = "CONTRACT_VERSION"
"""服务包自报契约版本常量名。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="服务目录校验（离线清单 + 服务包声明；缺省接库查重与对账）")
    parser.add_argument("--url", default="", help="平台库连接串（显式覆盖；缺省按配置解析）")
    parser.add_argument("--offline", action="store_true", help="仅离线断言，不接库")
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


def check_manifests() -> tuple[ConcurrentStableList[str], ConcurrentStableList[str]]:
    """装载并校验产品自持清单的能力 / 种子段（**复用装载期同一实现**，不新增并行校验入口）。

    清单与产品代码清单的对账（服务行逐字段同值等）由产品仓自身的 `ops.check_modules` 承担；
    平台侧只校验已装载清单的跨仓契约一致性。

    Returns:
        tuple[ConcurrentStableList[str], ConcurrentStableList[str]]: （错误明细, 跳过 / 降级提示）。
    """
    paths = ConcurrentStableList(get_settings().registry.product_manifests)
    # 07B `02_03`：本仓 `deploy/registry/*.toml`（含平台 `platform.toml`）由装载器**自动发现**，
    # 故「未配置 product_manifests」不再等于「无清单可校验」——实际清单由 `_with_local_manifests` 合并。
    inspection = inspect_product_manifests(paths)
    errors = ConcurrentStableList(inspection.errors)
    # 迁移清单注册完整性（07B `02_03`）：有脚本的清单必须已在 alembic.ini 登记配置段。
    # 与清单校验同源（同一门禁命令），不新增并行校验入口。
    errors.update(validate_series_registry())
    warnings = ConcurrentStableList(inspection.warnings)
    if not paths and not inspection.manifests:
        warnings.add("[清单] 无任何清单可校验（本仓 deploy/registry/ 与 [registry].product_manifests 均为空）")
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


def check_catalog_db(url: str) -> ConcurrentStableList[str]:
    """接库校验：读库查重与格式 + 服务目录 / 产品档案双向对账（空库判失败）。

    Args:
        url: 平台库连接串（迁移 + 种子后）。

    Returns:
        ConcurrentStableList[str]: 冲突 / 非法明细（含库不可读）。
    """
    try:
        records = asyncio.run(_read_catalog(url))
    except Exception as exc:
        return ConcurrentStableList([f"服务目录库不可读（请先执行平台库迁移）：{exc}"])
    if not records:
        return ConcurrentStableList(["库中无登记行（种子未执行？）"])
    errors = ConcurrentStableList(
        validate_catalog(ConcurrentStableList(SERVICE_CATALOG), ConcurrentStableList(records))
    )
    try:
        products = asyncio.run(_read_products(url))
    except Exception as exc:
        errors.add(f"产品档案库不可读（请先执行平台库迁移）：{exc}")
        return errors
    if not products:
        errors.add("产品档案库中无登记行（种子未执行？）")
        return errors
    errors.update(validate_products(ConcurrentStableList(PRODUCT_CATALOG), ConcurrentStableList(products)))
    return errors


def diff_platform_declarations(snapshot: RegistrySnapshot, payload: DeclarationPayload) -> ConcurrentStableList[str]:
    """注册表 ↔ 本仓声明对账（07B `02_06`）：本产品维度逐类比对。

    口径：

    - 只比**本产品**名下的行（`RegistrySnapshot.owner_of`），别的产品行不参与；
    - 已退役的行视为「库里没有」（再声明即恢复，不算缺失）；
    - 内容指纹不同 = 声明漂移（库未随代码更新）；库里多出的行同样报出（声明缺失）。

    Args:
        snapshot: 注册表现状（只读）。
        payload: 本仓声明载荷（`from_manifest(...)`，含平台服务行）。

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
                errors.add(f"{kind}｜{key}：注册表缺该声明（未注册或已退役）")
            elif current != fingerprint:
                errors.add(f"{kind}｜{key}：声明与注册表不一致（库未随代码更新）")
        for key in stored:
            if key not in declared:
                errors.add(f"{kind}｜{key}：注册表多出声明（本仓清单未声明）")
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


def check_registry_db(url: str) -> ConcurrentStableList[str]:
    """接库对账：注册表 ↔ 本仓声明（平台自身维度）。

    Args:
        url: 平台库连接串（迁移 + 注册后）。

    Returns:
        ConcurrentStableList[str]: 差异明细（含库不可读 / 清单缺失）。
    """
    try:
        payload = _platform_payload()
    except CatalogError as exc:
        return ConcurrentStableList([f"本仓声明不可读：{exc}"])
    try:
        snapshot = asyncio.run(_read_registry(url))
    except Exception as exc:
        text = str(exc).lower()
        if "no such table" in text or "does not exist" in text or "invalid object name" in text:
            # 尚未建注册表（老库 / 迁移未跑）：跳过对账并明示，不把「还没迁移」当成「声明漂移」
            print("[注册表] 未建表：跳过注册表对账（请先执行迁移与注册）")
            return ConcurrentStableList()
        return ConcurrentStableList([f"注册表库不可读（请先执行迁移与注册）：{exc}"])
    return diff_platform_declarations(snapshot, payload)


def _platform_payload() -> DeclarationPayload:
    """取本仓平台声明载荷（平台自身清单 + `SERVICE_CATALOG` 服务行）。

    Returns:
        DeclarationPayload: 注册载荷。

    Raises:
        CatalogError: 本仓平台清单缺失。
    """
    for path in local_manifest_paths():
        if path.name == f"{PLATFORM_SERVICE_KEY}.toml":
            manifest = load_product_manifest(path)
            payload = from_manifest(manifest)
            services: ConcurrentStableList[ModuleRecord] = ConcurrentStableList(SERVICE_CATALOG)
            known = {record.module_key for record in services}
            for record in payload.services:
                if record.module_key not in known:
                    services.add(record)
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
    raise CatalogError(f"本仓平台清单缺失：deploy/registry/{PLATFORM_SERVICE_KEY}.toml")


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口：离线校验（默认）+ 可选接库校验。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    args = build_parser().parse_args(argv)
    errors = check_offline()
    manifest_errors, manifest_warnings = check_manifests()
    errors.update(manifest_errors)
    url = "" if args.offline else (args.url or resolve_url(service=PLATFORM_SERVICE_KEY))
    if url:
        errors.update(check_catalog_db(url))
        # 注册表 ↔ 本仓声明对账（07B `02_06`）：声明漂移在 CI 暴露，而不是等到启动期
        errors.update(check_registry_db(url))
    for warning in manifest_warnings:
        print(warning)
    if errors:
        for error in errors:
            print(f"[服务目录] {error}")
        print(f"[服务目录] 校验失败（{len(errors)} 项）")
        return 1
    scope = f"清单 {len(SERVICE_CATALOG)} 项 + 产品档案 {len(PRODUCT_CATALOG)} 项 + 服务包声明 + 产品清单能力 / 种子段"
    if url:
        scope += " + 接库对账"
    print(f"[服务目录] 校验通过（{scope}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(ConcurrentStableList(sys.argv[1:])))
