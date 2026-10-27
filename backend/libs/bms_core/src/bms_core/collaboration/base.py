"""跨产品协同能力寻址模型（07B `02_02`）：能力 → 访问面的**冻结返回模型**。

- `CapabilityMode`：第二段解析的部署模式（`remote` / `colocated` / `local`）。
- `CapabilityTarget`：第二段解析结果（部署单元 / 服务标识 / 基址 / 库键）。
- `CapabilityEndpoint`：第一段（能力记录）+ 第二段（目标）合成的取用结果，消费方唯一返回模型。

口径：

- 能力声明权威在产品仓自持清单，本模块只承载**返回模型**（不新增第二份登记）；
- 取用入口唯一（`resolve_capability`，见 `resolver.py`），消费方不得按名自查视图或自拼路径；
- 模型一律为 `BaseValueObject`（`@dataclass(frozen=True)`），消费方只读。
"""

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import StrEnum

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseValueObject

__all__ = [
    "WRITE_KINDS",
    "CapabilityEndpoint",
    "CapabilityMode",
    "CapabilityTarget",
]

WRITE_KINDS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("write", "txn-branch"))
"""写 / 强一致路径的能力类别（`fail-closed` 档；不得声明降级）。"""


class CapabilityMode(StrEnum):
    """第二段解析的部署模式（判定口径归 07C `02_02`）。"""

    REMOTE = "remote"
    """跨部署单元调用（本任务默认实现的恒取值）。"""

    COLOCATED = "colocated"
    """同承载集合、不同进程（阶段 A 的目标形态）。"""

    LOCAL = "local"
    """与本实例同进程（进程内直调；传输实现归 07C）。"""


@dataclass(frozen=True)
class CapabilityTarget(BaseValueObject):
    """第二段解析结果：能力落在**哪个部署单元 / 服务 / 基址 / 库**。

    过渡默认实现（本任务）恒为 `mode=remote`、`unit_key` 取业务域、`db_keys` 为空集；
    07C `02_02` 落地时替换解析实现，字段与消费方代码不变。
    """

    mode: str
    """部署模式（取值见 `CapabilityMode`）。"""

    unit_key: str
    """部署单元标识（过渡默认取业务域）。"""

    service_key: str
    """承载服务标识（服务间调用的目标 `service`）。"""

    base_url: str
    """基址（按既有模板从 `service_key` 派生，不含访问面路径）。"""

    db_keys: ConcurrentStableFrozenList[str] = dataclass_field(
        default_factory=lambda: ConcurrentStableFrozenList[str]()
    )
    """关联库键（空集表示**未由拓扑解析**，消费方沿用既有按服务键派生）。"""


@dataclass(frozen=True)
class CapabilityEndpoint(BaseValueObject):
    """能力取用结果：第一段（能力记录）+ 第二段（解析目标）。

    `codes` 类能力无访问面（`path is None`），消费方不得据此发起调用。
    """

    name: str
    """能力名（回显，便于日志与错误定位）。"""

    domain: str
    """提供方业务域标识（不是服务标识）。"""

    kind: str
    """访问面类别（`read` / `write` / `txn-branch` / `dataset` / `codes`）。"""

    contract_version: str
    """提供方契约版本。"""

    target: CapabilityTarget
    """第二段解析结果。"""

    path: str | None = None
    """访问面路径模板（可含 `{param}` 占位；`codes` 类为 None）。"""

    branch_op: str | None = None
    """事务分支动作名（`txn-branch` 类）。"""

    branch_id: str | None = None
    """事务参与者稳定短标识（`txn-branch` 类；不随版本漂移）。"""

    data_source_key: str | None = None
    """数据源登记键（`dataset` 类）。"""

    permission_codes: ConcurrentStableFrozenList[str] = dataclass_field(
        default_factory=lambda: ConcurrentStableFrozenList[str]()
    )
    """业务码 / 权限码集合（`codes` 类）。"""

    product_key: str | None = None
    """对外暴露的产品命名空间段。"""

    frontend_prefix: str | None = None
    """前端命名空间域段（装载期已补齐，非 `codes` 类恒有值）。"""

    @property
    def is_write_path(self) -> bool:
        """是否写 / 强一致路径（`kind ∈ {write, txn-branch}`）。

        Returns:
            bool: 写路径为 True（该档失败即整体失败，不得声明降级）。
        """
        return self.kind in WRITE_KINDS

    def access_url(self) -> str:
        """访问面地址（`target.base_url` + `path`）。

        Returns:
            str: 访问面地址（不含查询串；路径参数由消费方按模板填充）。

        Raises:
            ParamError: 能力无访问面（`codes` 类），不得发起调用。
        """
        if self.path is None:
            raise ParamError(f"能力无访问面（kind={self.kind}）：{self.name}")
        return f"{self.target.base_url.rstrip('/')}{self.path}"
