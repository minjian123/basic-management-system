"""认证与身份服务包。"""

__version__ = "0.1.0"

CONTRACT_VERSION = "0.1.0"
"""公开契约（OpenAPI）版本（服务自报；启动与 CI 校验主版本兼容，破坏性变更升主版本）。"""

SERVICE_NAME = "identity"
"""服务名（`[app].service` 为空时取本声明；用于日志 `service`、探针响应与按服务配置）。"""

SERVICE_TITLE = "BMS 认证与身份服务"
"""服务中文名（用于应用 title）。"""
