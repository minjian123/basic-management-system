"""产品帮助包装载 / 卸载 / 校验和 CLI 薄壳（实现已下沉 `help` 业务域；08_03）。

命令：

```bash
cd backend
uv run python -m ops.help_package checksum --package help/package.yaml
uv run python -m ops.help_package load --package help/package.yaml --tenant demo          # 预演
uv run python -m ops.help_package load --package help/package.yaml --tenant demo --apply  # 实跑
uv run python -m ops.help_package unload --product bms --tenant demo --apply
```

口径：`ops/` 属运维通道，本脚本只做入口转发；包解析 / 计划器 / 卸载 / 命令行参数全部归
`bms_platform.domains.help`，避免运维包与业务域两份实现漂移。装载与卸载**默认 dry-run**，
`--apply` 才写库；目标必须显式 `--tenant` 或 `--all-tenants`。
"""

from typing import Any

from bms_platform.domains.help.cli import build_parser, main
from ops._worker import worker_id_lease_sync

RUN_IMAGE = "platform"
"""需访问 platform 服务（租户库 + 平台库锚点），部署态在 platform 容器内运行。"""

__all__ = ["build_parser", "main"]


def __getattr__(name: str) -> Any:
    """把未显式导入的属性转发到帮助域命令行实现（含内部辅助函数，供测试 monkeypatch）。

    Args:
        name: 属性名。

    Returns:
        Any: 帮助域命令行模块中的同名属性。

    Raises:
        AttributeError: 模块无该属性。
    """
    from bms_platform.domains.help import cli as _impl

    return getattr(_impl, name)


if __name__ == "__main__":  # pragma: no cover - 模块直跑入口（部署与用例都走 main()）
    with worker_id_lease_sync():
        raise SystemExit(main())
