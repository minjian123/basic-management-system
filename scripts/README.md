# scripts — 开发期工具链

本目录存放**开发期工具链**（自 `deploy/tools/` 迁入，后统一收纳于 `scripts/tools/`）。以 Python 标准库或 uv 管理依赖为主，Windows / Linux 均可用。

## 工具链清单（`tools/` 子目录）

| 工具 | 用途 |
| --- | --- |
| `tools/wol/` | WOL 电源控制（远程唤醒 / 关机 mjbk） |
| `tools/bg/` | 后台执行器（长命令后台化 + 秒级轮询状态） |
| `tools/defect/` | 缺陷工具链（REPRO 复现包自动上报 / AI 修复 / 一键复现） |
| `tools/backup/` | 开发服务器备份脚本（版本管理源） |
| `tools/gitlab/` | GitLab 流水线盯守（`watch_pipeline.py`） |
| `tools/reorder-design/` | 设计文档节点编号重排 |
| `tools/reorder-stage/` | 阶段目录编号重排（`renumber_stage.py`） |
| `tools/workbuddy/` | WorkBuddy 桌面端补丁脚本 |
| `tools/base-check/` | 基座完整性自检（`check-base.py` 四项：跨层引用 / 措辞 / 清单一致 / 编号引用，CI job `base-integrity`）；`check-backend-base.py` 继承链 / 错误码段位 / 迁移链对账；`check-service-boundaries.py` 服务边界护栏（共享库 / 服务依赖、分层单向、表 / 表前缀跨服务唯一）；`check-links.py` 链接自洽校验**本地手工跑**（不挂 CI，约束过强会逼着文档少写链接） |
| `tools/preflight/` | 本地预检（`check-preflight.py`）：推送前在本地跑 CI 关键门禁（CI 配置 / pytest 选项校验、ruff / pyright、聚合全量 + 工程级范围测试、基座与边界、文档状态），避免「改一点、等整条流水线」的慢循环 |
| `tools/check-docs/` | 项目文档状态一致性核对（`check-status.py`：需求 / 任务 / 计划三处，同挂 `base-integrity`） |
| `tools/governance/` | 治理脚本（`collect_metrics.py` 阶段度量 + 用例统计、`review_stage.py` 阶段末复盘清单；《项目规划说明》§25.3） |
| `tools/observability/` | 可观测部署辅助（`render_alertmanager.py` 从 `deploy/.env` 渲染 Alertmanager 配置；产物不入库） |
| `tools/winrm/` | mjw（Windows）远程控制（WinRM 会话与电源） |
| `tools/vision/` | mjw 识图 MCP（opencode MCP 服务） |

## 职责边界

- `scripts/` 只放开发期工具链，**不放**产品运维脚本（见 `ops/`），**不放**部署产物（见 `deploy/`）。
- 工具链统一收于 `scripts/tools/` 子目录，各工具为独立子目录。
- 凭据统一存 `deploy/.env`（不入库），各工具自动读取，不硬编码密码。

> 各工具的详细用法见其自带 `README.md` 或 docstring，以及 `bms文档/` 下对应的使用说明。
