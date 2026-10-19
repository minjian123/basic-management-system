"""测试公共基座（13_04）：统一事务 / 日志 / 输出 / 报错断言与可派生测试基类。

入口：

- 基类：`BaseTestCase` / `DbTestCase` / `ApiTestCase` / `ServiceTestCase`；
- 断言：`assert_error` / `assert_no_error`；
- 日志：`log_events` / `assert_logged`；
- 输出：`stdout_text` / `stderr_text` / `assert_output` / `CliResult` / `run_cli` / `assert_exit`；
- 事务：`rollback_session`（回滚夹具内核）；
- 夹具：经 `pytest -p bms_core.testing.plugin` 全局注册（`conftest` 无需再写 `pytest_plugins`）。

产品仓（mdm / biz）可直接 `from bms_core.testing import ...` 复用，不再复制第二套。
"""

from bms_core.testing.api import ApiTestCase
from bms_core.testing.assertions import assert_error, assert_no_error
from bms_core.testing.base import BaseTestCase
from bms_core.testing.db import DbTestCase
from bms_core.testing.logs import assert_logged, log_events
from bms_core.testing.output import (
    CliResult,
    assert_exit,
    assert_output,
    run_cli,
    stderr_text,
    stdout_text,
)
from bms_core.testing.service import ServiceTestCase
from bms_core.testing.transaction import rollback_session

__all__ = (
    "ApiTestCase",
    "BaseTestCase",
    "CliResult",
    "DbTestCase",
    "ServiceTestCase",
    "assert_error",
    "assert_exit",
    "assert_logged",
    "assert_no_error",
    "assert_output",
    "log_events",
    "rollback_session",
    "run_cli",
    "stderr_text",
    "stdout_text",
)
