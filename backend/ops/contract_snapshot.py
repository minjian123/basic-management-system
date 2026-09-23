"""公开契约快照命令行：导出 / 校验各服务的 OpenAPI 公开契约（服务目录为单一来源）。

用法::

    uv run python -m ops.contract_snapshot export          # 导出（覆盖写入 deploy/contracts/）
    uv run python -m ops.contract_snapshot export --print  # 导出并打印
    uv run python -m ops.contract_snapshot check           # 零漂移校验（CI / 预检用）
    uv run python -m ops.contract_snapshot check --root .  # 指定仓库根

快照生成走**内存构建**：动态导入各启用服务 `ApplicationFactory`，`create(None)` 构造应用后取
`app.openapi()`（不启 lifespan、不连库）；渲染与校验逻辑在 `bms_core/services/service_contract.py`。
共享库不得依赖服务包，故服务侧构建逻辑落本 CLI。

确定性：同代码 → 同文本（缩进 2 / 键排序 / 非 ASCII 直出），供 Git 比对与零漂移校验（同 04_01 网关配置）。
"""

from __future__ import annotations

import argparse
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from bms_core.services.module_registry import ModuleRecord
from bms_core.services.service_contract import (
    CONTRACTS_DIR,
    contract_file_name,
    enabled_service_records,
    render_contract_json,
    validate_contract,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = _BACKEND_ROOT.parent
"""仓库根（`backend/` 的父目录）。"""


def contracts_dir(root: Path) -> Path:
    """快照目录绝对路径。

    Args:
        root: 仓库根。

    Returns:
        Path: `<root>/deploy/contracts`。
    """
    return root / CONTRACTS_DIR


def snapshot_path(root: Path, service_key: str) -> Path:
    """单个服务的快照文件路径。

    Args:
        root: 仓库根。
        service_key: 服务标识。

    Returns:
        Path: `<root>/deploy/contracts/<service_key>.json`。
    """
    return contracts_dir(root) / contract_file_name(service_key)


def build_openapi(service_key: str) -> dict[str, Any]:
    """内存构建服务应用并取公开契约（OpenAPI）。

    Args:
        service_key: 服务标识（包名 `bms_<service_key>`）。

    Returns:
        dict[str, Any]: OpenAPI 映射。

    Raises:
        RuntimeError: 服务包 / 应用工厂缺失或应用构建失败。
    """
    try:
        module = import_module(f"bms_{service_key}.main")
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"服务包缺失：bms_{service_key}.main（{exc}）") from exc
    factory_cls = getattr(module, "ApplicationFactory", None)
    if factory_cls is None:
        raise RuntimeError(f"服务缺少 ApplicationFactory：bms_{service_key}.main")
    try:
        app = factory_cls().create(None)
        return cast("dict[str, Any]", app.openapi())
    except Exception as exc:
        raise RuntimeError(f"服务应用构建失败：{service_key}（{exc!r}）") from exc


def _validate(record: ModuleRecord, openapi: dict[str, Any]) -> list[str]:
    """校验单个服务快照（结构 + 契约版本）。

    Args:
        record: 服务登记行。
        openapi: 公开契约映射。

    Returns:
        list[str]: 违规明细；空列表表示通过。
    """
    return validate_contract(cast("str", record.service_key), openapi, record)


def export(root: Path, *, to_stdout: bool = False) -> int:
    """导出各启用服务公开契约快照。

    Args:
        root: 仓库根。
        to_stdout: 是否同时打印生成内容。

    Returns:
        int: 退出码（0 成功）。
    """
    target_dir = contracts_dir(root)
    target_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for record in enabled_service_records():
        service_key = cast("str", record.service_key)
        openapi = build_openapi(service_key)
        errors = _validate(record, openapi)
        if errors:
            failures.extend(errors)
            continue
        text = render_contract_json(openapi)
        path = snapshot_path(root, service_key)
        path.write_text(text, encoding="utf-8")
        if to_stdout:
            print(text, end="")
        else:
            print(f"[contract_snapshot] 已生成 {path}")
    if failures:
        for message in failures:
            print(f"  - {message}", file=sys.stderr)
        return 1
    return 0


def check(root: Path) -> int:
    """校验仓库内快照与各服务公开契约零漂移、契约版本一致、无缺件 / 无多余件。

    Args:
        root: 仓库根。

    Returns:
        int: 退出码（0 一致；1 缺件 / 多余件 / 漂移 / 契约版本不符）。
    """
    records = {cast("str", record.service_key): record for record in enabled_service_records()}
    expected = {contract_file_name(service_key) for service_key in records}
    directory = contracts_dir(root)
    actual = {path.name for path in directory.glob("*.json")} if directory.is_dir() else set()
    problems: list[str] = [f"缺快照文件：{name}" for name in sorted(expected - actual)]
    problems.extend(f"多余快照文件：{name}" for name in sorted(actual - expected))
    for service_key, record in records.items():
        path = snapshot_path(root, service_key)
        if not path.is_file():
            continue
        openapi = build_openapi(service_key)
        errors = _validate(record, openapi)
        if errors:
            problems.extend(errors)
            continue
        if path.read_text(encoding="utf-8") != render_contract_json(openapi):
            problems.append(f"{service_key}：快照与当前公开契约漂移（重新运行 export）")
    if problems:
        print(f"[contract_snapshot] 不通过：{len(problems)} 项", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"[contract_snapshot] 通过：{len(records)} 个启用服务快照与公开契约一致")
    return 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="导出 / 校验各服务公开契约（OpenAPI）快照")
    parser.add_argument("command", choices=("export", "check"), help="export 导出；check 零漂移校验")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="仓库根（缺省自动定位）")
    parser.add_argument("--print", dest="to_stdout", action="store_true", help="export 时打印生成内容")
    args = parser.parse_args(argv)
    if args.command == "export":
        return export(args.root, to_stdout=args.to_stdout)
    return check(args.root)


if __name__ == "__main__":
    raise SystemExit(main())
