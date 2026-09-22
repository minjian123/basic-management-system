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
    RATE_LIMIT = 10005
    DATABASE_UNAVAILABLE = 10006
    SEARCH_UNAVAILABLE = 10101
    SEARCH_TIMEOUT = 10102
    SEARCH_DEGRADED = 10103
    SEARCH_INDEX_NOT_READY = 10104
    SEARCH_REBUILD_RUNNING = 10105
    SEARCH_FILE_NOT_SEARCHABLE = 10106
    SEARCH_TIME_RANGE_EXCEEDED = 10107
    AUTH = 20001
    CAPTCHA_VERIFY_FAILED = 20101
    CAPTCHA_EXPIRED = 20102
    CAPTCHA_TOO_FREQUENT = 20103
    PERMISSION = 30001
    ORG_SOURCE_UNAVAILABLE = 30101
    ORG_TARGET_UNSUPPORTED = 30102
    ORG_DEPT_NOT_FOUND = 30103
    CONFIG = 40001
    PLUGIN = 40002
    DICT_SOURCE_UNAVAILABLE = 40101
    DICT_TYPE_NOT_FOUND = 40102
    DICT_LOCALE_UNSUPPORTED = 40103
    PRINT_TEMPLATE_NOT_FOUND = 50201
    PRINT_ARTIFACT_NOT_FOUND = 50202
    PRINT_BATCH_LIMIT_EXCEEDED = 50203
    TENANT_NOT_FOUND = 80001
    TENANT_SUSPENDED = 80002
