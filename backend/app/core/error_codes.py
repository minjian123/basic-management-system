"""core 层错误码基座：平台错误码与段位常量（统一登记点）。

段位（《架构设计 · 接口与集成》「错误码分段」节，一经发布稳定不变）：

- `1xxxx` 通用（参数校验 / 资源不存在 / 冲突 / 系统内部）
- `2xxxx` 认证、`3xxxx` 用户与组织、`4xxxx` 系统配置、`5xxxx` 文件、
  `6xxxx` 工作流、`7xxxx` 通知 / 任务、`8xxxx` 开放 / 租户 / SSO、`9xxxx` 报表 / 审计
- 业务模块扩展段 `10xxxx` 起（模块注册制，段号见 `sys_module.errcode_segment`），
  由产品仓库各自定义错误码（不得占用平台段）。

新增平台错误码只改本文件；模块错误码按段位在各自域登记。
"""

from enum import IntEnum


class ErrorSegment(IntEnum):
    """错误码段位（万位段号）。"""

    GENERAL = 1
    AUTH = 2
    USER_ORG = 3
    CONFIG = 4
    FILE = 5
    WORKFLOW = 6
    NOTIFY_TASK = 7
    OPEN_TENANT = 8
    REPORT_AUDIT = 9


class ErrorCode(IntEnum):
    """平台错误码（骨架；段内序号递增，禁止复用已发布码）。"""

    INTERNAL = 10000
    PARAM = 10001
    NOT_FOUND = 10002
    CONFLICT = 10003
    CONCURRENT_CONFLICT = 10004
    AUTH = 20001
    PERMISSION = 30001
