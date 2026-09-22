"""服务启动入口：`python -m bms_tenant`（读 `[server]` 配置，SIGTERM 先摘流再优雅收尾）。"""

from bms_core.core.run import run_service
from bms_tenant.main import ApplicationFactory

if __name__ == "__main__":
    run_service(ApplicationFactory)
