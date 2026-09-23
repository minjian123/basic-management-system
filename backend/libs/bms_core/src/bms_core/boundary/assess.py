"""数据所有权越界判定纯函数（静态校验与运行时守卫同源；06_03 起按表级归属判定）。

- `OwnershipViolation`：一条越界（服务 / 表 / 前缀 / 归属 / 操作）。
- `assess_table`：单表越界判定——基础设施表（每服务自有）放行；未登记表名放行
  （无归属可判，声明场景由静态校验拦截）；归属为当前服务放行；命中只读例外放行；其余越界。
- `assess_statement`：SQL 语句越界判定（经 `sql.analyze` 提取表引用后逐表判定）。

口径：**无共享前缀概念**——`sys_` 表按表级归属判定；读侧例外仅放行 `read` 操作。
"""

from collections.abc import Iterable
from dataclasses import dataclass

from bms_core.boundary.directory import OWNER_EVERY_SERVICE, table_owner, table_prefix_of
from bms_core.boundary.exceptions import OwnershipException, exception_allows
from bms_core.boundary.sql import analyze
from bms_core.core.base import BaseObject

__all__ = ["OwnershipViolation", "assess_statement", "assess_table"]


@dataclass(frozen=True)
class OwnershipViolation(BaseObject):
    """一条数据所有权越界。"""

    service: str
    """当前服务标识（访问方）。"""

    table: str
    """被访问表名。"""

    prefix: str
    """表前缀。"""

    owner: str
    """表归属（他服务标识）。"""

    operation: str
    """操作归类（read / write / ddl / schema / unknown）。"""


def assess_table(
    table: str,
    *,
    service: str,
    operation: str,
    exceptions: Iterable[OwnershipException] = (),
) -> OwnershipViolation | None:
    """单表越界判定（按表级归属）。

    Args:
        table: 被访问表名。
        service: 当前服务标识。
        operation: 操作归类（read / write / ddl / schema / unknown）。
        exceptions: 例外登记条目。

    Returns:
        OwnershipViolation | None: 越界返回违规项；放行返回 None。
    """
    owner = table_owner(table)
    if owner is None or owner in (OWNER_EVERY_SERVICE, service):
        return None
    if exception_allows(exceptions, service=service, table=table, operation=operation):
        return None
    return OwnershipViolation(
        service=service,
        table=table,
        prefix=table_prefix_of(table),
        owner=owner,
        operation=operation,
    )


def assess_statement(
    statement: str,
    *,
    service: str,
    exceptions: Iterable[OwnershipException] = (),
) -> tuple[OwnershipViolation, ...]:
    """SQL 语句越界判定。

    Args:
        statement: SQL 语句。
        service: 当前服务标识。
        exceptions: 例外登记条目。

    Returns:
        tuple[OwnershipViolation, ...]: 越界项（无越界返回空元组）。
    """
    violations: list[OwnershipViolation] = []
    for ref in analyze(statement):
        violation = assess_table(ref.table, service=service, operation=ref.operation, exceptions=exceptions)
        if violation is not None:
            violations.append(violation)
    return tuple(violations)
