"""事件契约快照命令行：导出 / 校验事件契约与订阅（平台默认声明为单一来源）。

用法::

    uv run python -m ops.event_contracts export          # 校验兼容后写入快照
    uv run python -m ops.event_contracts export --print  # 导出并打印
    uv run python -m ops.event_contracts check           # 零漂移 + 兼容校验（CI / 预检用）
    uv run python -m ops.event_contracts check --root .  # 指定仓库根

- 注册表：`register_platform_event_contracts()` 登记平台默认契约（产品 / 服务级契约随实现落地，
  届时在此处补登记入口）；校验与兼容判定在 `bms_core/events/contracts.py`。
- 快照：`deploy/events/contracts.json`（确定性 JSON，缩进 2 / 键排序 / 非 ASCII 直出 + 尾换行；
  同代码 → 同文本，供 Git 比对与零漂移校验）。
- `export` 先做兼容校验（字段只增不删 / 新增可选 / 破坏性升主版本 / 事件类型不删除 /
  主版本升级订阅覆盖），违规不写文件并退出 1；`check` 用于 CI 与本地预检。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from bms_core.core.exceptions import EventContractError
from bms_core.events.contracts import (
    EVENT_SNAPSHOT_PATH,
    EventContract,
    EventContractRegistry,
    EventSubscription,
    check_snapshot_compatibility,
    default_event_contract_registry,
    parse_event_snapshot,
    render_event_snapshot,
    validate_event_registry,
)
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.services.module_registry import known_event_domains

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = _BACKEND_ROOT.parent
"""仓库根（`backend/` 的父目录）。"""


def snapshot_path(root: Path) -> Path:
    """快照文件绝对路径。

    Args:
        root: 仓库根。

    Returns:
        Path: `<root>/deploy/events/contracts.json`。
    """
    return root / EVENT_SNAPSHOT_PATH


def build_registry() -> EventContractRegistry:
    """构建现行事件契约注册表（平台默认声明）。

    Returns:
        EventContractRegistry: 注册表实例。
    """
    registry = default_event_contract_registry()
    register_platform_event_contracts(registry)
    return registry


def load_snapshot(root: Path) -> tuple[tuple[EventContract, ...], tuple[EventSubscription, ...]] | None:
    """读取已提交快照（缺件 None）。

    Args:
        root: 仓库根。

    Returns:
        tuple[tuple[EventContract, ...], tuple[EventSubscription, ...]] | None: （契约清单，订阅清单）。

    Raises:
        EventContractError: 快照结构非法。
    """
    path = snapshot_path(root)
    if not path.is_file():
        return None
    return parse_event_snapshot(json.loads(path.read_text(encoding="utf-8")))


def _registry_errors(registry: EventContractRegistry) -> list[str]:
    """注册表校验明细。

    Args:
        registry: 事件契约注册表。

    Returns:
        list[str]: 违规明细。
    """
    return list(validate_event_registry(registry, domains=known_event_domains()))


def export(root: Path, *, to_stdout: bool = False) -> int:
    """校验兼容后导出快照。

    Args:
        root: 仓库根。
        to_stdout: 是否同时打印快照内容。

    Returns:
        int: 退出码（0 成功；1 有违规）。
    """
    registry = build_registry()
    errors = _registry_errors(registry)
    try:
        previous = load_snapshot(root)
    except (EventContractError, json.JSONDecodeError) as exc:
        errors.append(f"已提交快照不可解析：{EVENT_SNAPSHOT_PATH}（{exc}）")
        previous = None
    if previous is not None:
        errors.extend(check_snapshot_compatibility(previous[0], registry))
    if errors:
        print("事件契约导出失败（兼容校验未通过）：")
        for error in errors:
            print(f"  - {error}")
        return 1
    text = render_event_snapshot(registry)
    path = snapshot_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(
        f"事件契约快照已写入：{EVENT_SNAPSHOT_PATH}"
        f"（契约 {len(registry.contracts())} 条 / 订阅 {len(registry.subscriptions())} 条）"
    )
    if to_stdout:
        print(text)
    return 0


def check(root: Path) -> int:
    """注册表校验 + 兼容校验 + 快照零漂移（CI / 预检门禁）。

    Args:
        root: 仓库根。

    Returns:
        int: 退出码（0 一致；1 不一致）。
    """
    registry = build_registry()
    errors = _registry_errors(registry)
    try:
        previous = load_snapshot(root)
    except (EventContractError, json.JSONDecodeError) as exc:
        errors.append(f"已提交快照不可解析：{EVENT_SNAPSHOT_PATH}（{exc}）")
        previous = None
    if previous is None:
        errors.append(f"事件契约快照缺失：{EVENT_SNAPSHOT_PATH}（请运行 export）")
    else:
        errors.extend(check_snapshot_compatibility(previous[0], registry))
        path = snapshot_path(root)
        if path.read_text(encoding="utf-8") != render_event_snapshot(registry):
            errors.append(f"事件契约快照与现行注册表漂移：{EVENT_SNAPSHOT_PATH}（请运行 export 重导出）")
    if errors:
        print("事件契约校验失败：")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        f"事件契约校验通过：契约 {len(registry.contracts())} 条 / 订阅 {len(registry.subscriptions())} 条，"
        f"快照零漂移（{EVENT_SNAPSHOT_PATH}）"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表（缺省取进程参数）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="事件契约快照（导出 / 校验）")
    subcommands = parser.add_subparsers(dest="command", required=True)
    export_parser = subcommands.add_parser("export", help="校验兼容后写入快照")
    export_parser.add_argument("--print", dest="to_stdout", action="store_true", help="同时打印快照内容")
    export_parser.add_argument("--root", default=str(REPO_ROOT), help="仓库根（默认 backend 的父目录）")
    check_parser = subcommands.add_parser("check", help="零漂移 + 兼容校验")
    check_parser.add_argument("--root", default=str(REPO_ROOT), help="仓库根（默认 backend 的父目录）")
    args = parser.parse_args(argv)
    if args.command == "export":
        return export(Path(args.root), to_stdout=bool(args.to_stdout))
    return check(Path(args.root))


if __name__ == "__main__":
    sys.exit(main())
