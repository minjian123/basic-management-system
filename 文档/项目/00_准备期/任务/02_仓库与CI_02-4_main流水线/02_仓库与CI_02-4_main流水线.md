# 02-4 main 流水线

> 准备期 · 02 仓库与CI · 子任务 02-4

[文档首页](../../../../文档首页.md) › [02 仓库与CI](../02_仓库与CI.md) › 02-4 main 流水线　|　[← 父任务](../02_仓库与CI.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 02-4 |
| 父任务 | [02 仓库与CI](../02_仓库与CI.md) |
| 对应需求 | [02-4](../../需求/02_需求_仓库与CI.md#r02-4) |
| 工时（重估） | 11h |
| 依赖 | 02-3、阶段一骨架 |
| 负责人 | minjian |
| 状态 | 进行中 |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. Playwright E2E（服务容器起后端（SQLite）与前端产物）
2. MySQL/PostgreSQL/达梦 DM8 三库方言集成测试：job 连 mjbk 常驻三库，建 `bms_test` 前缀测试库 → Alembic 迁移 → 集成测试 → 删库清理
3. 构建 `bms-backend`、`bms-frontend` 镜像并推 GitLab Registry（5050）
4. 容器镜像安全扫描：GitLab Container Scanning（Trivy 引擎）扫描 Registry 镜像，CVSS ≥ 9 高危漏洞阻断发版
5. `swagger.json` 契约快照导出归档
6. 测试报告：Allure 报告归档（CI artifact），测试结果经官方插件导入 Kiwi TCMS 用例库

## 3. 完成标准 <a id="accept"></a>

main 流水线端到端通过；契约快照与 Allure 报告已归档；高危漏洞（CVSS ≥ 9）时流水线阻断。

> 口径说明（2026-08-22）：镜像扫描 job 为规划新增项（《项目规划说明》16 节安全专项，GitLab 内置模板增量小、不加工时）；模板镜像需外网拉取——mjbk 外网不可达时预缓存或与 02-6 一并暂缓，不阻塞其余 job。

## 4. 参考文档 <a id="ref"></a>

- 《开发部署规划》第 7 节、《测试规范》

## 5. 实施记录（2026-08-22 框架就绪，端到端验证待阶段一代码）<a id="impl"></a>

| 项 | 结果 |
| --- | --- |
| Registry 启用 | gitlab.rb 配 `registry_external_url 'http://192.168.0.107:5050'` + reconfigure；mjbk daemon.json 加 `insecure-registries`（需重启 docker，容器自动拉起） |
| Registry 链路实测 | docker login（root PAT）→ push `bms/bms/smoke:ci-test` → pull 往返通过 ✅ |
| main job 骨架 | E2E、三库集成 ×3（mysql/postgres/dm8）、镜像构建推 Registry ×2、Trivy 高危阻断、swagger 快照、Allure——全部以 exists 守卫落地（`backend/pyproject.toml` 等出现即激活） |
| 空载流水线验证 | pipeline #23 success：gate-smoke 绿，业务 job 按设计跳过 ✅ |

待办（随阶段一骨架）：

- E2E / 三库集成 / 镜像构建 / 扫描的真实数据验证
- 三库 `bms_test` 测试库与对应 CI 变量（BMS_TEST_DB_*）建立
- Kiwi TCMS 结果导入 job 随用例登记补入

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-21 · 更新：2026-08-22（框架就绪记录）
