"""审计分片结构（`log` 域再导出）：实现已上移基座 `bms_core.audit.shards`（06_02）。

06_02 把分片表结构 / 月份工具 / 规范化记录上移到基座——`log` 域（操作 / 登录日志）与 `audit` 域
（字段级变更审计）共用同一份结构定义；本模块只做再导出，保持 06_01 的调用面与测试导入不变。
"""

from bms_core.audit.shards import (
    DATA_AUDIT_RECORD_FIELDS,
    LOG_TYPE_DATA_AUDIT,
    LOG_TYPE_LOGIN,
    LOG_TYPE_OPERATION,
    LOGIC_TABLES,
    LOGIN_RECORD_FIELDS,
    OPERATION_RECORD_FIELDS,
    build_shard_table,
    canonical_record,
    month_key,
    month_shift,
    parse_month,
    shard_of_id,
    shard_table_name,
)

__all__ = [
    "DATA_AUDIT_RECORD_FIELDS",
    "LOGIC_TABLES",
    "LOGIN_RECORD_FIELDS",
    "LOG_TYPE_DATA_AUDIT",
    "LOG_TYPE_LOGIN",
    "LOG_TYPE_OPERATION",
    "OPERATION_RECORD_FIELDS",
    "build_shard_table",
    "canonical_record",
    "month_key",
    "month_shift",
    "parse_month",
    "shard_of_id",
    "shard_table_name",
]
