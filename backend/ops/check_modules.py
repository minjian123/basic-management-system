"""CI 服务目录清单校验：复用注册服务的唯一性与格式校验规则。

用法：

```bash
uv run python ops/check_modules.py
```

冲突 / 非法 → 打印明细并退出码 1；通过 → 退出码 0。
"""

import sys
from collections.abc import Sequence

from bms_core.services.module_registry import SERVICE_CATALOG, ModuleRegistry


def main(argv: Sequence[str] | None = None) -> int:
    """校验服务目录清单。

    Args:
        argv: 命令行参数（本阶段未使用，预留）。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    del argv
    errors = ModuleRegistry().validate()
    if errors:
        for error in errors:
            print(f"[服务目录] {error}")
        return 1
    print(f"[服务目录] 校验通过（{len(SERVICE_CATALOG)} 项）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
