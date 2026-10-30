"""发布对账端口（07C `04_01`）：域内只依赖协议，实现由装配面 / 运维入口注入。

为什么需要端口：

- **结构 revision 不在本库**：每域一张版本记录表（`alembic_version_{domain}`），落在该域所属清单的库里；
  领域服务只持平台库会话，读别的库要连接串与方言（`ops` 侧才有），故以协议注入；
- **契约破坏性变更结论不在本进程**：真正判定要跑 oasdiff（`ops.contract_gate`，需 docker 与对外二进制），
  发布流程只**消费结论**（结论可来自 CI 报告文件），不内联外部命令；
- 协议放域根（`ports.py`），实现放装配面与运维入口，域内实现不反向 import 装配层（`03_04` 已确立该形态）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from bms_core.core.concurrent import ConcurrentStableList

__all__ = ["ContractBreachReader", "ReleaseRevisionPort"]


class ReleaseRevisionPort(Protocol):
    """结构 revision 读面：域标识 → 该域版本记录表当前 revision。"""

    async def current(self, domain_key: str) -> str | None:
        """读取某域的结构 revision。

        Args:
            domain_key: 业务域标识。

        Returns:
            str | None: 当前 revision；该域尚未初始化结构（无记录表 / 无记录）返回 None。
        """
        ...


ContractBreachReader = Callable[[str], Awaitable[ConcurrentStableList[str]]]
"""契约破坏性变更读面：服务标识 → 破坏性变更摘要。

返回非空即「该服务本次含破坏性变更」，发布流程据此拒绝（除非显式放行）；
空清单表示要么兼容、要么尚无基线（调用方在 `detail` 里注明来源）。
"""
