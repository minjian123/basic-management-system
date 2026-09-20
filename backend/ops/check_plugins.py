"""CI 插件装配离线校验：复用装配清单与注册表语义（provider 引用 / 重名 / 契约版本）。

用法：

```bash
uv run python -m ops.check_plugins
```

校验失败（非法 provider / 重名 / 版本格式等）→ 打印明细并退出码 1；通过 → 退出码 0。
离线校验（不连依赖服务、不进入应用生命周期）；以应用工厂提供离线 app / resources 供
依赖注入型工厂登记（如 `health_check_registry:local`）；工厂实现的版本兼容由装配运行时校验。
"""

import sys
from collections.abc import Sequence
from typing import cast

from app.core.assembly import PLUGIN_WIRINGS, register_platform_plugins
from app.core.config import PluginSelection, Settings
from app.core.exceptions import PluginError
from app.core.plugin import NULL_PLUGIN_NAME, build_plugin_registry
from app.core.resources import ResourceManager
from app.main import ApplicationFactory


def main(argv: Sequence[str] | None = None) -> int:
    """校验各能力 provider 引用（存在性 / 重名 / 版本格式）。

    Args:
        argv: 命令行参数（本阶段未使用，预留）。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    del argv
    app = ApplicationFactory().create(None)
    settings = cast("Settings", app.state.settings)
    resources = cast("ResourceManager", app.state.resources)
    try:
        register_platform_plugins(settings, app, resources)
        snapshot = build_plugin_registry()
    except PluginError as exc:
        print(f"[插件装配] {exc}")
        return 1
    errors: list[str] = []
    for wiring in PLUGIN_WIRINGS:
        selection = getattr(settings, wiring.settings_section, None)
        provider = selection.provider if isinstance(selection, PluginSelection) else ""
        name = provider or NULL_PLUGIN_NAME
        bucket = snapshot.get(wiring.plugin_key)
        if not bucket or name not in bucket:
            registered = "、".join(sorted(bucket)) if bucket else "无"
            errors.append(f"{wiring.plugin_key} 未注册实现：{name}（已注册：{registered}）")
    if errors:
        for error in errors:
            print(f"[插件装配] {error}")
        return 1
    print(f"[插件装配] 校验通过（{len(PLUGIN_WIRINGS)} 项）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
