"""错误码手册导出命令行（07B `02_05` 第七类记录）。

用法::

    uv run python -m ops.export_errcodes export                    # 打印 Markdown 表
    uv run python -m ops.export_errcodes export --format json      # 打印 JSON
    uv run python -m ops.export_errcodes export --out tmp/errcodes.md
    uv run python -m ops.export_errcodes check tmp/errcodes.md     # 比对导出文件与当前视图

- **数据来源**：与装配期同源——按 `[registry].product_manifests` 装载产品清单后取
  `error_code_view()`（平台 `ErrorCode` 枚举 + 产品 `[[errcodes]]` 声明）；未配置清单时只含平台码并提示。
- **确定性**：按 `code` 升序、固定列序；同视图同文本（供 Git 比对与 `check` 零漂移校验）。
- **产物去向**：缺省打印 stdout；`--out` 落文件（建议工作区 `tmp/`，不写仓库树）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.registry.products import load_product_manifests
from bms_core.services.module_registry import ErrorCodeRecord, error_code_view

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core`（不导入任何服务包），任意服务镜像均可运行。"""

COLUMNS: ConcurrentStableList[str] = ConcurrentStableList(
    ("code", "segment", "domain", "provider", "http_status", "message_key", "severity", "description", "status")
)
"""导出列（固定顺序；`md` 表头按此渲染，`json` 键按此排序）。"""

STATUS_TEXT: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "enabled": "启用",
        "disabled": "已停用（码位保留不复用）",
    }
)
"""状态展示口径（`disabled` 仍参与渲染，仅手册标注）。"""


def build_records() -> ConcurrentStableList[ErrorCodeRecord]:
    """装载清单并取合并视图记录（按 `code` 升序）。

    Returns:
        ConcurrentStableList[ErrorCodeRecord]: 错误码记录。
    """
    paths = ConcurrentStableList(get_settings().registry.product_manifests)
    if paths:
        load_product_manifests(paths)
    else:
        print("[export_errcodes] 未配置 [registry].product_manifests：仅导出平台码", file=sys.stderr)
    return ConcurrentStableList(sorted(error_code_view().values(), key=lambda record: record.code))


def record_row(record: ErrorCodeRecord) -> ConcurrentStableDict[str, object]:
    """把记录规整为导出行（键序同 `COLUMNS`）。

    Args:
        record: 错误码记录。

    Returns:
        ConcurrentStableDict[str, object]: 导出行。
    """
    return ConcurrentStableDict(
        {
            "code": record.code,
            "segment": record.segment,
            "domain": record.domain,
            "provider": record.product_key,
            "http_status": record.http_status,
            "message_key": record.message_key,
            "severity": str(record.severity),
            "description": record.description,
            "status": STATUS_TEXT[str(record.status)],
        }
    )


def render_markdown(records: ConcurrentStableList[ErrorCodeRecord]) -> str:
    """渲染 Markdown 错误码表（确定性）。

    Args:
        records: 错误码记录（调用方已排序）。

    Returns:
        str: Markdown 文本（末行带换行）。
    """
    lines: ConcurrentStableList[str] = ConcurrentStableList(
        (
            "| 错误码 | 段 | 业务域 | 提供方 | HTTP | 文案键 | 级别 | 描述 | 状态 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        )
    )
    for record in records:
        row = record_row(record)
        lines.add(
            f"| `{row['code']}` | {row['segment']} | {row['domain']} | {row['provider']} | {row['http_status']}"
            f" | `{row['message_key']}` | {row['severity']} | {row['description']} | {row['status']} |"
        )
    return "\n".join(lines) + "\n"


def render_json(records: ConcurrentStableList[ErrorCodeRecord]) -> str:
    """渲染 JSON 错误码表（键排序、确定性）。

    Args:
        records: 错误码记录（调用方已排序）。

    Returns:
        str: JSON 文本（末行带换行）。
    """
    payload = [dict(record_row(record)) for record in records]
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render(records: ConcurrentStableList[ErrorCodeRecord], fmt: str) -> str:
    """按格式渲染导出内容。

    Args:
        records: 错误码记录。
        fmt: `md` / `json`。

    Returns:
        str: 渲染文本。
    """
    return render_json(records) if fmt == "json" else render_markdown(records)


def _build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="错误码手册导出（合并视图 → md / json）")
    parser.add_argument("command", choices=("export", "check"), help="export 导出；check 比对导出文件")
    parser.add_argument("path", nargs="?", type=Path, help="check 时必填：待比对文件路径")
    parser.add_argument("--format", choices=("md", "json"), default="md", help="导出格式（缺省 md）")
    parser.add_argument("--out", type=Path, default=None, help="export 落文件路径（缺省打印 stdout）")
    return parser


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 成功 / 1 不一致或参数非法）。
    """
    args = _build_parser().parse_args(None if argv is None else list(argv))
    text = render(build_records(), cast("str", args.format))
    if args.command == "export":
        out = cast("Path | None", args.out)
        if out is None:
            print(text, end="")
            return 0
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"[export_errcodes] 已写出 {out}")
        return 0
    path = cast("Path | None", args.path)
    if path is None or not path.is_file():
        print(f"[export_errcodes] check 须给出存在的文件路径（现 {path}）", file=sys.stderr)
        return 1
    existing = path.read_text(encoding="utf-8")
    same = json.loads(existing) == json.loads(text) if str(args.format) == "json" else existing == text
    if not same:
        print(f"[export_errcodes] 不一致：{path}（重新导出后再比对）", file=sys.stderr)
        return 1
    print(f"[export_errcodes] 一致：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
