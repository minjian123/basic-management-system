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

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.services.module_registry import ModuleRecord
from bms_core.services.service_contract import (
    CONTRACTS_DIR,
    contract_file_name,
    enabled_service_records,
    render_contract_json,
    validate_contract,
)

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""
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


def build_app(service_key: str) -> Any:
    """内存构建服务应用（不启 lifespan、不连库）。

    Args:
        service_key: 服务标识（包名 `bms_<service_key>`）。

    Returns:
        Any: 服务应用对象（`ApplicationFactory().create(None)` 产物）。

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
        return factory_cls().create(None)
    except Exception as exc:
        raise RuntimeError(f"服务应用构建失败：{service_key}（{exc!r}）") from exc


def build_openapi(service_key: str) -> ConcurrentStableDict[str, Any]:
    """内存构建服务应用并取公开契约（OpenAPI）。

    Args:
        service_key: 服务标识（包名 `bms_<service_key>`）。

    Returns:
        ConcurrentStableDict[str, Any]: OpenAPI 映射。

    Raises:
        RuntimeError: 服务包 / 应用工厂缺失或应用构建失败。
    """
    app = build_app(service_key)
    return ConcurrentStableDict(cast("dict[str, Any]", app.openapi()))


def _validate(record: ModuleRecord, openapi: ConcurrentStableDict[str, Any]) -> ConcurrentStableList[str]:
    """校验单个服务快照（结构 + 契约版本）。

    Args:
        record: 服务登记行。
        openapi: 公开契约映射。

    Returns:
        ConcurrentStableList[str]: 违规明细；空列表表示通过。
    """
    return ConcurrentStableList(
        validate_contract(cast("str", record.service_key), ConcurrentStableDict(openapi), record)
    )


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
    failures: ConcurrentStableList[str] = ConcurrentStableList()
    for record in enabled_service_records():
        service_key = cast("str", record.service_key)
        openapi = build_openapi(service_key)
        errors = _validate(record, openapi)
        if errors:
            failures.update(errors)
            continue
        text = render_contract_json(ConcurrentStableDict(openapi))
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


def affected_services(listed: ConcurrentStableList[str]) -> ConcurrentStableList[str] | None:
    """从改动文件推导受影响服务。

    粒度是服务（要构建服务应用取公开契约）：`backend/services/<key>/` 命中即该服务；碰
    `backend/libs/`（基座影响所有服务的路由与 schema）退化为全量，返回 None。

    Args:
        listed: 改动文件清单（仓根相对）。

    Returns:
        ConcurrentStableList[str] | None: 受影响服务（None 表示全量）；空列表表示本次改动不涉及。
    """
    picked: ConcurrentStableList[str] = ConcurrentStableList()
    for rel in listed:
        if rel.startswith("backend/libs/"):
            return None
        parts = rel.split("/")
        if len(parts) < 3 or parts[0] != "backend" or parts[1] != "services":
            continue
        key = parts[2]
        if key not in picked:
            picked.add(key)
    return picked


def read_changed(path: str) -> ConcurrentStableList[str]:
    """读取改动文件清单。

    Args:
        path: 清单路径；`-` 表示从标准输入读取（门禁直接传参，不落临时清单）。

    Returns:
        ConcurrentStableList[str]: 相对路径清单（空行与注释略过）。

    Raises:
        OSError: 清单不可读。
    """
    listed: ConcurrentStableList[str] = ConcurrentStableList()
    content = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    for line in content.splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            listed.add(text)
    return listed


def check(root: Path, *, files_from: str = "") -> int:
    """校验仓库内快照与各服务公开契约零漂移、契约版本一致、无缺件 / 无多余件。

    Args:
        root: 仓库根。
        files_from: 改动文件清单（增量只比对受影响服务的快照；空串全量）。

    Returns:
        int: 退出码（0 一致 / 本次不涉及；1 缺件 / 多余件 / 漂移 / 契约版本不符；2 清单不可读）。
    """
    records = {cast("str", record.service_key): record for record in enabled_service_records()}
    if files_from:
        try:
            listed = read_changed(files_from)
        except OSError as exc:
            print(f"[contract_snapshot] 改动清单不可读：{exc}", file=sys.stderr)
            return 2
        affected = affected_services(listed)
        if affected is None:
            print("[contract_snapshot] 增量模式：改动触及基座，按全量校验")
        else:
            records = {key: record for key, record in records.items() if key in affected}
            print(f"[contract_snapshot] 增量模式：只比对受影响服务 {len(records)} 个")
            if not records:
                print("[contract_snapshot] 通过：本次改动不涉及服务公开契约")
                return 0
    expected = {contract_file_name(service_key) for service_key in records}
    directory = contracts_dir(root)
    actual: ConcurrentStableSet[str] = ConcurrentStableSet()
    if directory.is_dir():
        actual.update(path.name for path in directory.glob("*.json"))
    problems: ConcurrentStableList[str] = ConcurrentStableList(
        f"缺快照文件：{name}" for name in sorted(expected - actual)
    )
    if not files_from:
        problems.update(f"多余快照文件：{name}" for name in sorted(actual - expected))
    for service_key, record in records.items():
        path = snapshot_path(root, service_key)
        if not path.is_file():
            continue
        openapi = build_openapi(service_key)
        errors = _validate(record, openapi)
        if errors:
            problems.update(errors)
            continue
        if path.read_text(encoding="utf-8") != render_contract_json(ConcurrentStableDict(openapi)):
            problems.add(f"{service_key}：快照与当前公开契约漂移（重新运行 export）")
    if problems:
        print(f"[contract_snapshot] 不通过：{len(problems)} 项", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"[contract_snapshot] 通过：{len(records)} 个启用服务快照与公开契约一致")
    return 0


def main(argv: ConcurrentStableList[str] | None = None) -> int:
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
    parser.add_argument(
        "--files-from",
        default="",
        help="改动文件清单（增量只比对受影响服务的快照；基座改动仍全量）",
    )
    args = parser.parse_args(argv)
    if args.command == "export":
        return export(args.root, to_stdout=args.to_stdout)
    return check(args.root, files_from=str(args.files_from))


if __name__ == "__main__":
    raise SystemExit(main())
