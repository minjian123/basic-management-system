"""BMS 平台地基服务包：应用入口 / 接口层 / 平台业务模块。

服务镜像与流水线落点：运行镜像 `backend/Dockerfile`（构建 `--build-arg SERVICE=platform`），
按服务构建 / 发布 / 扫描见服务子流水线模板 `deploy/ci/templates/backend-service.yml`（09_01）。
"""

__version__ = "0.1.0"

CONTRACT_VERSION = "0.3.0"
"""公开契约（OpenAPI）版本（服务自报；启动与 CI 校验主版本兼容，破坏性变更升主版本）。

**2026-10-07（02_03 角色管理）**：`sys_form` 去 `menu_id` 改经 `sys_menu_form` 多对多，
`FormItem.menu_id` → `menu_ids`、`MyMenuNode.form` → `forms`、`FormCreateRequest` 改 `menu_ids`
均属**破坏性变更**（只加不删口径违约），故升 `0.1.0` → `0.2.0`（详设 N8）。

**2026-10-21（02_14 字典字段绑定 ID）**：`GET /dicts/{data_source_key}` 的 `values`（条目 `value`
子集）改为 `ids`（条目 **整数 id** 子集），字典字段类型 `select` / `multi_select` 更名
`option` / `option_multi`——属**破坏性变更**，0.x 阶段以次版本表达，故升 `0.2.0` → `0.3.0`。
"""

SERVICE_NAME = "platform"
"""服务名（`[app].service` 为空时取本声明；用于日志 `service`、探针响应与按服务配置）。"""

SERVICE_TITLE = "BMS 基础管理系统"
"""服务中文名（用于应用 title）。"""
