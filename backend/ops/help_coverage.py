"""帮助覆盖率台账命令行薄壳（08_04）。

命令：

```bash
cd backend
uv run python -m ops.help_coverage                                    # 告警档（有缺口也退出 0）
uv run python -m ops.help_coverage --format markdown --output ../tmp/help-coverage.md
uv run python -m ops.help_coverage --strict                           # 强档（发布验收 / 阶段收口）
uv run python -m ops.help_coverage --baseline ../tmp/help-coverage-上次.json
```

口径：`ops/` 属运维通道，本脚本只做入口转发；参数解析、平台库读取、豁免 / 基线与渲染全部在
`bms_core.help.coverage_cli`，判定引擎在 `bms_core.help.coverage`。台账只读平台库元数据，不读写租户库。
"""

from typing import Any

from bms_core.help.coverage_cli import build_parser, main
from ops._worker import worker_id_lease_sync

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""

__all__ = ["build_parser", "main"]


def __getattr__(name: str) -> Any:
    """把未显式导入的属性转发到基座命令行实现（供测试 monkeypatch）。

    Args:
        name: 属性名。

    Returns:
        Any: 基座命令行模块中的同名属性。

    Raises:
        AttributeError: 模块无该属性。
    """
    from bms_core.help import coverage_cli as _impl

    return getattr(_impl, name)


if __name__ == "__main__":  # pragma: no cover - 模块直跑入口（部署与用例都走 main()）
    with worker_id_lease_sync():
        raise SystemExit(main())
