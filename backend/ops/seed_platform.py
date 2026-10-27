"""种子统一编排入口（07B `02_03`）：平台 + 产品同构声明，一个 XA 全局事务内串行执行。

命令：

```bash
cd backend
uv run python -m ops.seed_platform --dry-run                # 只预检（不开事务）
uv run python -m ops.seed_platform --tenant demo            # 执行全部种子
uv run python -m ops.seed_platform --only seed-menu         # 只跑指定种子
uv run python -m ops.seed_platform --json                   # 机器可读报告
```

**口径**：本脚本是**薄客户端**——实现与参数解析在 `bms_core.tenant.seed.cli`，执行在
platform 服务进程内（XA 分支需要应用装配提供的引擎注册表与分支处理器）。
既有单步命令（`seed_menu` / `seed_module` 等）保留为「内部单步（排障用）」。

退出码：0 成功 / 1 数据冲突 / 2 执行失败（已整体回滚）/ 3 前置错误 / 64 参数错误。
"""

from bms_core.tenant.seed.cli import main

RUN_IMAGE = "platform"
"""需访问 platform 服务（编排端点），部署态在 platform 容器内运行。"""

if __name__ == "__main__":
    raise SystemExit(main())
