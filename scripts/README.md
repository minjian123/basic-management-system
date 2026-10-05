# scripts — 开发期工具链

> 开发期工具链（统一收于 `scripts/tools/`）：本机开发与依赖外置、基座与边界护栏、文档校验、推送前预检、治理统计与远程运维。

## 定位与边界

- 只放**开发期工具链**；产品运维脚本见 `ops/`（后端开发期运维脚本在 `backend/ops/`），部署产物见 `deploy/`。
- 工具以 Python 标准库或 uv 管理依赖为主，Windows / Linux 均可用。
- 凭据统一存 `deploy/.env`（不入库），各工具自动读取，不硬编码密码。

## 工具清单（`tools/` 子目录）

| 工具 | 用途 |
| --- | --- |
| `tools/dev/` | **本机裸跑全套**（`本地全套.sh`：四服务起停 / seed / status / logs / unlock）与宿主端口清理 |
| `tools/deps/` | 依赖外置维护（`外置依赖.sh` / `还原依赖.sh` / `重装依赖.sh`） |
| `tools/preflight/` | 推送前本地预检（`check-preflight.py`；`--fast` 秒级只跑 CI 配置 / 静态 / 基座与边界） |
| `tools/base-check/` | 基座与边界护栏：`check-base.py`、`check-backend-base.py`、`check-service-boundaries.py`、`check-bare-collections.py`、`check-docs-scope.py`、`check-coverage-threshold.py`、`check-prototype-review.py`、`check-env-example.py`、`check-links.py`（链接自洽，**本地手工跑**，不挂 CI） |
| `tools/check-docs/` | 项目文档状态一致性核对（`check-status.py`：需求 / 任务 / 计划三处，同挂 `base-integrity`） |
| `tools/governance/` | 治理脚本（`collect_metrics.py` 阶段度量 + 用例统计、`review_stage.py` 阶段末复盘清单、`boundary_metrics.py` 越界 / 跨库 / 例外计数） |
| `tools/deploy/` | 服务编排与发布部署（`release.py`：bootstrap / deploy / rollback，在部署机执行） |
| `tools/docker/` | 本地镜像拉取辅助（`拉取镜像.sh` + `镜像清单.txt`） |
| `tools/observability/` | 可观测部署辅助（`render_alertmanager.py` 从 `deploy/.env` 渲染配置；产物不入库） |
| `tools/wol/` | 开发服务器电源控制（远程唤醒 / 睡眠 / 关机 mjbk；关机为破坏性操作） |
| `tools/winrm/` | Windows（mjw）远程控制（WinRM 会话与电源） |
| `tools/vision/` | mjw 识图 MCP（opencode MCP 服务） |
| `tools/bg/` | 后台执行器（长命令后台化 + 秒级轮询状态） |
| `tools/defect/` | 缺陷工具链（REPRO 复现包自动上报 / AI 修复 / 一键复现） |
| `tools/backup/` | 开发服务器备份脚本（版本管理源） |
| `tools/gitlab/` | GitLab 流水线盯守（`watch_pipeline.py`） |
| `tools/reorder-design/` | 设计文档节点编号重排 |
| `tools/reorder-stage/` | 阶段目录编号重排（`renumber_stage.py`） |
| `tools/workbuddy/` | WorkBuddy 桌面端补丁脚本 |

## 常用命令

> 在**仓库根（`bms/`）**执行。

```bash
bash scripts/tools/dev/本地全套.sh up                        # 本机四服务起栈（首次后跑 seed）
python3 scripts/tools/preflight/check-preflight.py --fast     # 推送前预检
python3 scripts/tools/base-check/check-links.py               # 链接自洽（本地手工）
bash scripts/tools/deps/外置依赖.sh                           # 依赖外置态复位
```

## 文档导航

- 仓库根 [README](../README.md)
- 《[AI 开发规范](../bms文档/规范/AI开发规范.md)》·《[测试规范](../bms文档/规范/测试规范.md)》·《[部署发布规范](../bms文档/规范/部署发布规范.md)》
- 《[开发机部署使用说明总览](../bms文档/资料/开发机/开发机部署使用说明总览.md)》·《[开发服务器部署使用说明总览](../bms文档/资料/开发服务器/linux/开发服务器部署使用说明总览.md)》

> 各工具详细用法见其自带 `README.md` 或 docstring，以及 `bms文档/` 下对应的使用说明。
