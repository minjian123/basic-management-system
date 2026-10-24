"""数据所有权越界判定纯函数（静态校验与运行时守卫同源；06_03 起按表级归属判定，07C 03_01 起支持域维度）。

- `OwnershipViolation`：一条越界（访问方服务 / 访问方域 / 表 / 前缀 / 归属服务 / 归属域 / 操作）。
- `assess_table`：单表越界判定——基础设施表（每服务自有）与**不归域表**放行；未登记表名放行
  （无归属可判，声明场景由静态校验拦截）；归属为当前服务 / 当前域放行；命中只读例外放行；其余越界。
- `assess_statement`：SQL 语句越界判定（经 `sql.analyze` 提取表引用后逐表判定）。

口径：**无共享前缀概念**——`sys_` 表按表级归属判定；读侧例外仅放行 `read` 操作。
**域维度优先**：传入 `domain` 时按「表归属域 == 当前域」判定（合并部署下边界不消失），
不传时保持服务维判定（既有调用面零改动）。
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from bms_core.boundary.directory import OWNER_EVERY_SERVICE, table_domain, table_owner, table_prefix_of
from bms_core.boundary.exceptions import OwnershipException, exception_allows
from bms_core.boundary.sql import analyze
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseOwnershipContract

__all__ = ["OwnershipViolation", "assess_statement", "assess_table"]


@dataclass(frozen=True)
class OwnershipViolation(BaseOwnershipContract):
    """一条数据所有权越界。"""

    PREFIX_FIELD: ClassVar[str] = "prefix"

    service: str
    """当前服务标识（访问方；域维度判定时填当前域承载服务，可为空串）。"""

    table: str
    """被访问表名。"""

    prefix: str
    """表前缀。"""

    owner: str
    """表归属（他服务标识）。"""

    operation: str
    """操作归类（read / write / ddl / schema / unknown）。"""

    domain: str = ""
    """当前业务域标识（访问方；服务维判定时为空串）。"""

    owner_domain: str = ""
    """表归属业务域标识（不归域 / 未登记时为空串）。"""


def assess_table(
    table: str,
    *,
    service: str,
    operation: str,
    exceptions: Iterable[OwnershipException] = (),
    domain: str = "",
) -> OwnershipViolation | None:
    """单表越界判定（按表级归属；传入 `domain` 时改按归属域判定）。

    Args:
        table: 被访问表名。
        service: 当前服务标识。
        operation: 操作归类（read / write / ddl / schema / unknown）。
        exceptions: 例外登记条目。
        domain: 当前业务域标识（空串 = 服务维判定）。

    Returns:
        OwnershipViolation | None: 越界返回违规项；放行返回 None。
    """
    if domain:
        return _assess_by_domain(table, domain=domain, service=service, operation=operation, exceptions=exceptions)
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
        owner_domain=table_domain(table) or "",
    )


def _assess_by_domain(
    table: str,
    *,
    domain: str,
    service: str,
    operation: str,
    exceptions: Iterable[OwnershipException],
) -> OwnershipViolation | None:
    """按归属域判定越界（同域放行、跨域拒绝；不归域 / 未登记表放行）。

    Args:
        table: 被访问表名。
        domain: 当前业务域标识。
        service: 当前服务标识（仅用于例外匹配与文案）。
        operation: 操作归类。
        exceptions: 例外登记条目。

    Returns:
        OwnershipViolation | None: 越界返回违规项；放行返回 None。
    """
    owner_domain = table_domain(table)
    if owner_domain is None or owner_domain == "" or owner_domain == domain:
        return None
    if exception_allows(exceptions, service=service, table=table, operation=operation, domain=domain):
        return None
    return OwnershipViolation(
        service=service,
        table=table,
        prefix=table_prefix_of(table),
        owner=table_owner(table) or "",
        operation=operation,
        domain=domain,
        owner_domain=owner_domain,
    )


def assess_statement(
    statement: str,
    *,
    service: str,
    exceptions: Iterable[OwnershipException] = (),
    domain: str = "",
) -> ConcurrentStableList[OwnershipViolation]:
    """SQL 语句越界判定。

    Args:
        statement: SQL 语句。
        service: 当前服务标识。
        exceptions: 例外登记条目。
        domain: 当前业务域标识（空串 = 服务维判定）。

    Returns:
        tuple[OwnershipViolation, ...]: 越界项（无越界返回空元组）。
    """
    violations: ConcurrentStableList[OwnershipViolation] = ConcurrentStableList()
    for ref in analyze(statement):
        violation = assess_table(
            ref.table, service=service, operation=ref.operation, exceptions=exceptions, domain=domain
        )
        if violation is not None:
            violations.add(violation)
    return ConcurrentStableList(violations)
