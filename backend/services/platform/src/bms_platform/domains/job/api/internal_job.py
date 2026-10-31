"""作业中心服务内部面（平台）：挂载基座通用内部路由，注入平台作业提交器。"""

from __future__ import annotations

from bms_core.jobs.api import build_job_internal_router
from bms_platform.jobs import build_runner

router = build_job_internal_router(runner_factory=build_runner)
