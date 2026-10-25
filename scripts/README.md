# scripts — 开发期工具链

> 开发期工具链（统一收于 `scripts/tools/`）：本机开发与依赖外置、基座与边界护栏、文档校验、推送前预检、治理统计与远程运维。

## 定位与边界

- 只放**开发期工具链**；产品运维脚本见 `ops/`（后端开发期运维脚本在 `backend/ops/`），部署产物见 `deploy/`。
- 工具以 Python 标准库或 uv 管理依赖为主，Windows / Linux 均可用；少数工具的**可选**第三方依赖列在其目录 `requirements.txt`（如 `tools/preflight/` 的 pyyaml，缺失时对应检查降级跳过），按需装到本机 `python3`；可执行入口统一「**Python 单一实现 + 薄包装**」——逻辑只在同名 `.py`（如 `本地全套.py`），Linux `.sh` / Windows `.bat` 仅转调同目录 `.py`；被拷到目标机执行的脚本（`backup/`、`wol/`、`llamacpp/`）须**包装与 `.py` 成对拷贝**。
- 凭据统一存 `deploy/.env`（不入库），各工具自动读取，不硬编码密码。

## 工具清单（`tools/` 子目录）

| 工具 | 用途 |
| --- | --- |
| `tools/dev/` | **本机裸跑全套**（`本地全套`：三服务起停 / seed / status / logs / unlock）、宿主端口清理（`清理宿主端口`）与 5002 模块产物服务守护（`确保模块产物服务`）——Python 单一实现，Linux `.sh` / Windows `.bat` 薄包装 |
| `tools/deps/` | 依赖外置维护（`外置依赖` / `还原依赖` / `重装依赖`：Python 单一实现，Linux `.sh` / Windows `.bat` 瘦包装） |
| `tools/preflight/` | 推送前本地预检（`check_preflight.py`；`--fast` 秒级只跑 CI 配置 / 静态 / 基座与边界；可选依赖 pyyaml 见同目录 `requirements.txt`） |
| `tools/base_check/` | 基座与边界护栏：`check_base.py`、`check_backend_base.py`、`check_service_boundaries.py`、`check_bare_collections.py`、`check_docs_scope.py`、`check_prototype_review.py`、`check_env_example.py`、`check_links.py`（链接自洽，**本地手工跑**，不挂 CI） |
| `tools/check_docs/` | 项目文档状态一致性核对（`check_status.py`：需求 / 任务 / 计划三处，同挂 `base-integrity`） |
| `tools/governance/` | 治理脚本（`collect_metrics.py` 阶段度量 + 用例统计、`review_stage.py` 阶段末复盘清单、`boundary_metrics.py` 越界 / 跨库 / 例外计数） |
| `tools/deploy/` | 服务编排与发布部署（`release.py`：bootstrap / deploy / rollback，在部署机执行） |
| `tools/docker/` | 本地镜像拉取辅助（`拉取镜像` + `镜像清单.txt`：Python 单一实现，Linux `.sh` / Windows `.bat` 薄包装） |
| `tools/observability/` | 可观测部署辅助（`render_alertmanager.py` 从 `deploy/.env` 渲染配置；产物不入库） |
| `tools/wol/` | 开发服务器电源控制（远程唤醒 / 睡眠 / 关机 mjbk，睡眠含 RTC 定时唤醒；关机为破坏性操作；Python 单一实现 + `.sh` 薄包装） |
| `tools/winrm/` | Windows（mjw）远程控制（WinRM 会话与电源） |
| `tools/bg/` | 后台执行器（长命令后台化 + 秒级轮询状态） |
| `tools/defect/` | 缺陷工具链（REPRO 复现包自动上报 / AI 修复 / 一键复现） |
| `tools/backup/` | 开发服务器备份脚本（版本管理源；`backup_daily` Python 单一实现 + `.sh` 薄包装，部署须两文件成对） |
| `tools/gitlab/` | GitLab 流水线盯守（`watch_pipeline.py`） |
| `tools/reorder_design/` | 设计文档节点编号重排 |
| `tools/reorder_stage/` | 阶段目录编号重排（`renumber_stage.py`） |
| `tools/workbuddy/` | WorkBuddy 桌面端补丁脚本 |
| `tools/ide/` | IDE 工作区状态修复（`fix_scm_state.py`：源代码管理面板看不到仓库，VS Code / CodeBuddy 通用） |
| `tools/opencode/` | opencode Web 手机扫码访问（`配对二维码`：出一次性配对链接与二维码 PNG，手机无 App 时用浏览器扫码直连；Python 单一实现 + 双平台薄包装；可选依赖 segno 见同目录 `requirements.txt`） |

## 常用命令

> 在**仓库根（`bms/`）**执行。

```bash
python3 scripts/tools/dev/本地全套.py up                        # 本机三服务起栈（首次后跑 seed；org 随组织主数据归 mdm，已不在平台服务清单）
python3 scripts/tools/preflight/check_preflight.py --fast     # 推送前预检
python3 scripts/tools/base_check/check_links.py               # 链接自洽（本地手工）
python3 scripts/tools/deps/外置依赖.py                         # 依赖外置态复位（Windows：scripts\tools\deps\外置依赖.bat）
```

## 文档导航

- 仓库根 [README](../README.md)
- 《[AI 开发规范](../bms文档/规范/AI开发规范.md)》·《[测试规范](../bms文档/规范/测试规范.md)》·《[部署发布规范](../bms文档/规范/部署发布规范.md)》
- 《[开发机部署使用说明总览（Linux）](../bms文档/资料/开发机/linux/开发机部署使用说明总览.md)》·《[开发机部署使用说明总览（Windows）](../bms文档/资料/开发机/windows/开发机部署使用说明总览.md)》·《[开发服务器部署使用说明总览](../bms文档/资料/开发服务器/linux/开发服务器部署使用说明总览.md)》

> 各工具详细用法见其自带 `README.md` 或 docstring，以及 `bms文档/` 下对应的使用说明。
