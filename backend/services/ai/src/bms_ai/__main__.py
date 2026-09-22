"""服务启动入口：`python -m bms_ai`（读 `[server]` 配置，SIGTERM 先摘流再优雅收尾）。"""

from bms_ai.main import ApplicationFactory
from bms_core.core.run import run_service

if __name__ == "__main__":
    run_service(ApplicationFactory)
