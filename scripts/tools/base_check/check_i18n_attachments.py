#!/usr/bin/env python3
"""i18n 附表登记护栏：模型层每张 `*_i18n` 表都必须在台账内，且台账行在文档中可查。

台账的机器可读事实源是 `bms_core/i18n/attachments.py::I18N_ATTACHMENTS`，人类可读视图是
《数据库设计 · 国际化管理》「i18n 附表登记」节。本脚本断言三者一致（防止后续任务新增附表漏登记、
或台账与文档漂移）：

1. 模型层（`bms_core/models/**`）声明的 `*_i18n` 表集合 ⊆ 台账表集合；
2. 台账中 `status="landed"` 的表都在模型层存在；
3. 台账中 `status="pending"` 的表不在模型层（建表后须改状态）；
4. 台账每张表名都出现在《数据库设计 · 国际化管理》正文（文档台账未同步即失败）。

用法::

    python3 scripts/tools/base_check/check_i18n_attachments.py [仓库根] [--files-from -]

退出码：0 通过 / 1 存在问题 / 2 运行环境异常。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_DOC_RELATIVE = Path("bms文档/设计/数据库设计/30_数据库设计_国际化管理.md")
_MODELS_RELATIVE = Path("backend/libs/bms_core/src/bms_core/models")
_SRC_RELATIVE = Path("backend/libs/bms_core/src")

_IGNORED_ARGS = ("--files-from",)


def _pop_args(argv: list[str]) -> tuple[Path, list[str]]:  # bare-collections:allow（argv 为 sys.argv 切片）
    """解析参数（位置参数为仓库根；`--files-from` 兼容预检增量传参，本脚本为全局一致性检查，忽略其值）。

    Args:
        argv: 命令行参数（不含脚本名）。

    Returns:
        tuple[Path, list[str]]: (仓库根, 告警信息)。
    """
    notes: list[str] = []  # bare-collections:allow（脚本内告警收集）
    root: Path | None = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in _IGNORED_ARGS:
            index += 2
            continue
        if arg.startswith("-"):
            index += 1
            continue
        root = Path(arg)
        index += 1
    if root is None:
        root = Path.cwd()
    return root.resolve(), notes


def _iter_model_tables(models_root: Path) -> set[str]:  # bare-collections:allow（脚本内临时集合）
    """扫描模型层源码里的 `__tablename__` 字面量。

    Args:
        models_root: 模型根目录。

    Returns:
        set[str]: 模型层声明的表名集合。
    """
    tables: set[str] = set()  # bare-collections:allow（脚本内临时集合）
    for path in models_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, ast.Assign) or len(item.targets) != 1:
                    continue
                target = item.targets[0]
                if not isinstance(target, ast.Name) or target.id != "__tablename__":
                    continue
                if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                    tables.add(item.value.value)
    return tables


def _load_attachments(src_root: Path) -> dict[str, tuple[str, str]]:  # bare-collections:allow（脚本内台账快照）
    """从台账模块取「表名 → (状态, 归口)」。

    Args:
        src_root: `bms_core/src` 目录。

    Returns:
        dict[str, tuple[str, str]]: 台账条目。

    Raises:
        RuntimeError: 台账模块不可导入。
    """
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    try:
        from bms_core.i18n.attachments import I18N_ATTACHMENTS
    except Exception as exc:  # pragma: no cover - 环境异常（缺依赖）时给出可读报错
        raise RuntimeError(f"无法导入台账模块 bms_core.i18n.attachments：{exc}") from exc
    return {table: (item.status, item.owner_task) for table, item in I18N_ATTACHMENTS.items()}


def main(argv: list[str] | None = None) -> int:  # bare-collections:allow（argv 为 sys.argv 切片）
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码。
    """
    root, notes = _pop_args(list(sys.argv[1:] if argv is None else argv))
    models_root = root / _MODELS_RELATIVE
    src_root = root / _SRC_RELATIVE
    doc_path = root / _DOC_RELATIVE
    if not models_root.is_dir():
        print(f"[i18n-attachments] 模型目录不存在：{models_root}")
        return 2
    try:
        attachments = _load_attachments(src_root)
    except RuntimeError as exc:
        print(f"[i18n-attachments] {exc}")
        return 2

    problems: list[str] = []  # bare-collections:allow（脚本内问题收集）
    model_tables = _iter_model_tables(models_root)
    model_i18n = {name for name in model_tables if name.endswith("_i18n")}

    unregistered = sorted(model_i18n - set(attachments))
    for table in unregistered:
        problems.append(f"模型层 i18n 附表未登记台账：{table}（在 attachments.py 补一行）")

    landed = {table for table, (status, _owner) in attachments.items() if status == "landed"}
    missing_models = sorted(landed - model_tables)
    for table in missing_models:
        problems.append(f"台账登记为已落库但模型层无此表：{table}")

    pending = {table for table, (status, _owner) in attachments.items() if status == "pending"}
    landed_by_mistake = sorted(pending & model_tables)
    for table in landed_by_mistake:
        problems.append(f"附表已建表但台账仍标 pending：{table}（建表后改 status=landed）")

    doc_text = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else ""
    if not doc_text:
        problems.append(f"台账文档不存在或为空：{doc_path}")
    else:
        for table in sorted(attachments):
            if table not in doc_text:
                problems.append(f"台账文档缺登记行：{table}（{_DOC_RELATIVE.as_posix()}）")

    for note in notes:
        print(f"[i18n-attachments] {note}")
    if problems:
        print(f"[i18n-attachments] 失败 {len(problems)} 项：")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        f"[i18n-attachments] 通过：台账 {len(attachments)} 行（已落库 {len(landed)} / 待落地 {len(pending)}），"
        f"模型层 i18n 表 {len(model_i18n)} 张"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
