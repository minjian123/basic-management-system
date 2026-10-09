"""跨服务事务管理器（TM）服务包。

**定位**：纯跨库协调**基础设施**——与租户、与业务无关；账本落平台侧独立基础设施库 `bms_txn`
（`datasource = PLATFORM`、仅 `txn:platform` 一条迁移链、**不建 tenant 链**）。
"""

__version__ = "0.1.0"

CONTRACT_VERSION = "0.1.0"
"""公开契约（OpenAPI）版本（服务自报；启动与 CI 校验主版本兼容，破坏性变更升主版本）。"""

SERVICE_NAME = "txn"
"""服务名（`[app].service` 为空时取本声明；用于日志 `service`、探针响应与按服务配置）。"""

SERVICE_TITLE = "BMS 跨服务事务管理器服务"
"""服务中文名（用于应用 title）。"""
