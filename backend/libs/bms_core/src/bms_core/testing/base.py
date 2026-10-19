"""测试基类总根（13_04）：统一断言 / 日志 / 输出方法 + 模板方法钩子。

分层口径（《测试规范》「测试公共基座」节）：

    BaseTestCase（本文件）
    ├── DbTestCase     事务与数据库扩展点
    ├── ApiTestCase    HTTP 客户端扩展点
    └── ServiceTestCase 服务应用扩展点
        └── 具体测试类（可继续派生；测试类扩展的新方法可被同类测试继承）

红线：**子类只覆写 `prepare` / `assert_invariants` / `cleanup`**，不得覆写
`setup_method` / `teardown_method`（否则绕过基类统一逻辑）；基类不持有连接 / 会话，资源一律由夹具提供。
"""

from pathlib import Path
from typing import Any

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.testing.assertions import assert_error
from bms_core.testing.logs import assert_logged, log_events
from bms_core.testing.output import CliResult, assert_output, run_cli, stdout_text


class BaseTestCase:
    """测试总基类：方法别名 + 模板方法钩子（无状态、不持有资源）。"""

    def prepare(self) -> None:
        """用例前置（子类覆写；基类空实现）。"""

    def assert_invariants(self) -> None:
        """用例后置不变量（子类覆写；失败即红）。"""

    def cleanup(self) -> None:
        """用例自定义清理（子类覆写；基类空实现）。"""

    def setup_method(self) -> None:
        """pytest 前置：统一调用 `prepare`（子类不得覆写）。"""
        self.prepare()

    def teardown_method(self) -> None:
        """pytest 后置：先断言不变量、再清理（子类不得覆写）。"""
        try:
            self.assert_invariants()
        finally:
            self.cleanup()

    def assert_error(
        self,
        target: Any,
        *,
        code: int | None = None,
        status: int | None = None,
        message: str | None = None,
    ) -> None:
        """断言错误对象（异常 / 响应 / JSON 字典三形态）。

        Args:
            target: 异常实例 / 响应对象 / 已解析字典。
            code: 期望业务错误码。
            status: 期望 HTTP 状态码。
            message: 期望消息片段。
        """
        assert_error(target, code=code, status=status, message=message)

    def log_events(self, source: Any) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """解析日志事件（capsys / caplog / 文本）。

        Args:
            source: `capsys` / `caplog` / 文本。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 事件列表。
        """
        return log_events(source)

    def assert_logged(self, source: Any, *, event: str, level: str | None = None, **fields: object) -> None:
        """断言存在匹配的日志事件。

        Args:
            source: `capsys` / `caplog` / 文本。
            event: 事件名。
            level: 级别。
            **fields: 字段子集。
        """
        assert_logged(source, event=event, level=level, **fields)

    def stdout_text(self, capsys: Any) -> str:
        """读取标准输出（调用后缓冲清空）。

        Args:
            capsys: pytest `capsys` 夹具。

        Returns:
            str: 标准输出。
        """
        return stdout_text(capsys)

    def assert_output(self, capsys: Any, *, contains: str = "", not_contains: str = "") -> None:
        """断言捕获输出包含 / 不包含片段。

        Args:
            capsys: pytest `capsys` 夹具。
            contains: 必须包含的片段。
            not_contains: 不得包含的片段。
        """
        assert_output(capsys, contains=contains, not_contains=not_contains)

    def run_cli(self, *args: str, cwd: Path | None = None) -> CliResult:
        """执行 CLI 并返回结果。

        Args:
            *args: 解释器参数（如 `-m ops.check_modules`）。
            cwd: 工作目录。

        Returns:
            CliResult: 退出码与输出。
        """
        return run_cli(*args, cwd=cwd)
