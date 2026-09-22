"""服务启动入口：`python -m bms_platform`（读 `[server]` 配置，单进程；SIGTERM 先摘流再优雅收尾）。"""

from bms_core.core.run import run_service
from bms_platform.main import ApplicationFactory

if __name__ == "__main__":
    run_service(ApplicationFactory)
