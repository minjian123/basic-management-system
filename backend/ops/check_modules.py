"""CI 服务目录校验：离线清单 / 服务包契约声明 + 可选接库（迁移与种子后）查重与对账。

用法：

```bash
cd backend
uv run python -m ops.check_modules
uv run python -m ops.check_modules --url sqlite+aiosqlite:///./bms_ci_catalog.db
```

- **离线**：复用 `ModuleRegistry.validate()` 校验清单（四要素唯一 / 格式 / 维度），并比对
  服务工程自报契约版本（`CONTRACT_VERSION`）与清单登记值的主版本；服务工程 ↔ 清单双向核对
  （工程存在但未登记即失败；planned 且无工程目录跳过）。服务包常量经 AST 静态读取，不导入服务包。
- **接库**（`--url`）：读平台库 `sys_module`（未软删行）查重与格式校验 + 与清单双向对账，
  **只读不写**；空库判失败（种子未执行）。
- 冲突 / 非法 → 打印明细并退出码 1；通过 → 退出码 0。
"""

import argparse
import ast
import asyncio
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.version import contract_major
from bms_core.repositories.module_repository import ModuleRepository
from bms_core.services.module_registry import (
    SERVICE_CATALOG,
    ModuleRecord,
    ModuleRegistry,
    validate_catalog,
)

_SERVICES_DIR = Path(__file__).resolve().parents[1] / "services"
"""服务工程根（`backend/services`）。"""

_CONTRACT_CONSTANT = "CONTRACT_VERSION"
"""服务包自报契约版本常量名。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="服务目录校验（离线清单 + 服务包声明；--url 接库查重与对账）")
    parser.add_argument("--url", default="", help="平台库连接串（给定后追加接库校验；迁移 + 种子后执行）")
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


def resolve_service_contracts(services_dir: Path = _SERVICES_DIR) -> dict[str, str | None]:
    """扫描服务工程读各自报契约版本。

    Args:
        services_dir: 服务工程根。

    Returns:
        dict[str, str | None]: {服务名: 自报契约版本}；已声明但非字符串字面量为 None。
    """
    declarations: dict[str, str | None] = {}
    for entry in sorted(services_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        init_path = entry / "src" / f"bms_{entry.name}" / "__init__.py"
        if init_path.is_file():
            declarations[entry.name] = _extract_contract_version(init_path)
    return declarations


def check_service_declarations(
    catalog: Sequence[ModuleRecord],
    declarations: Mapping[str, str | None],
) -> list[str]:
    """服务工程声明 ↔ 清单双向核对（工程未登记 / 未声明常量 / 主版本不符）。

    Args:
        catalog: 服务目录清单。
        declarations: 服务工程自报契约版本映射。

    Returns:
        list[str]: 冲突 / 非法明细。
    """
    errors: list[str] = []
    expected = {module.service_key for module in catalog if module.service_key}
    for name in sorted(declarations):
        if name not in expected:
            errors.append(f"服务工程未登记：{name}")
    for module in catalog:
        if module.service_key is None or module.service_key not in declarations:
            continue
        declared = declarations[module.service_key]
        if declared is None:
            errors.append(f"{module.service_key}：服务包未声明 CONTRACT_VERSION")
            continue
        declared_major = contract_major(declared)
        if declared_major is None:
            errors.append(f"{module.service_key}：服务包契约版本非 semver（{declared}）")
            continue
        if declared_major != contract_major(module.contract_version):
            errors.append(
                f"{module.service_key}：服务包契约版本与清单主版本不符"
                f"（服务包 {declared}，清单 {module.contract_version}）"
            )
    return errors


def check_offline(services_dir: Path = _SERVICES_DIR) -> list[str]:
    """离线校验：清单自校验 + 服务包声明比对。

    Args:
        services_dir: 服务工程根。

    Returns:
        list[str]: 冲突 / 非法明细。
    """
    errors = ModuleRegistry().validate()
    errors.extend(check_service_declarations(SERVICE_CATALOG, resolve_service_contracts(services_dir)))
    return errors


async def _read_catalog(url: str) -> list[ModuleRecord]:
    """只读读取平台库服务目录（未软删行）。

    Args:
        url: 平台库连接串。

    Returns:
        list[ModuleRecord]: 登记记录列表。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = await ModuleRepository(session).list_catalog()
    finally:
        await engine.dispose()
    return [ModuleRecord.from_row(row) for row in rows]


def check_catalog_db(url: str) -> list[str]:
    """接库校验：读库查重与格式 + 与清单双向对账（空库判失败）。

    Args:
        url: 平台库连接串（迁移 + 种子后）。

    Returns:
        list[str]: 冲突 / 非法明细（含库不可读）。
    """
    try:
        records = asyncio.run(_read_catalog(url))
    except Exception as exc:
        return [f"服务目录库不可读（请先执行平台库迁移）：{exc}"]
    if not records:
        return ["库中无登记行（种子未执行？）"]
    return validate_catalog(SERVICE_CATALOG, records)


def main(argv: Sequence[str] | None = None) -> int:
    """入口：离线校验（默认）+ 可选接库校验。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    args = build_parser().parse_args(argv)
    errors = check_offline()
    if args.url:
        errors.extend(check_catalog_db(args.url))
    if errors:
        for error in errors:
            print(f"[服务目录] {error}")
        print(f"[服务目录] 校验失败（{len(errors)} 项）")
        return 1
    scope = f"清单 {len(SERVICE_CATALOG)} 项 + 服务包声明"
    if args.url:
        scope += " + 接库对账"
    print(f"[服务目录] 校验通过（{scope}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
