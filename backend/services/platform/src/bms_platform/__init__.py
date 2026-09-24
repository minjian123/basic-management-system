"""BMS 平台地基服务包：应用入口 / 接口层 / 平台业务模块。

服务镜像与流水线落点：运行镜像 `backend/Dockerfile`（构建 `--build-arg SERVICE=platform`），
按服务构建 / 发布 / 扫描见服务子流水线模板 `deploy/ci/templates/backend-service.yml`（09_01）。
"""

__version__ = "0.1.0"

CONTRACT_VERSION = "0.1.0"
"""公开契约（OpenAPI）版本（服务自报；启动与 CI 校验主版本兼容，破坏性变更升主版本）。"""

SERVICE_NAME = "platform"
"""服务名（`[app].service` 为空时取本声明；用于日志 `service`、探针响应与按服务配置）。"""

SERVICE_TITLE = "BMS 基础管理系统"
"""服务中文名（用于应用 title）。"""

# 09_03 契约冒烟链路验证（临时改动，验证后回退）
