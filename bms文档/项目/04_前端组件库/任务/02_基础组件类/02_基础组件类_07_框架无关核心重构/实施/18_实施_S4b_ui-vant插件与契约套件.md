# 框架无关核心重构 · S4b 实施记录（ui-vant 插件与契约套件）

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · S4 阶段（S4b）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | S4 `ui-vant` 插件与移动端收口 · **S4b `ui-vant` 插件 + 契约套件 + CI / 镜像** |
| 对应设计 | [S4 详细设计](../设计/01_详细设计_S4_ui-vant插件与移动端收口.md)（决策确认版） |
| 实施日期 | 2026-09-17 |
| 实施人 | minjian |
| 环境 | Linux 开发机（mjpc）；Node v24.20.0；npm workspaces（core / vue / ui-ep / ui-vant） |
| 实测工时 | ≈3h |
| 结论 | S4b 完成：`packages/ui-vant` 建立并迁入 9 件（8 容器件 + `PermButton`）+ 注入实现；组件契约工厂与 Vue 挂载适配就位，**ui-ep 与 ui-vant 跑同一套断言全绿**；CI `core-check` 切 workspace 根依赖、镜像扩展（含 vant）与 `build-base.sh` 哈希输入更新 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 包骨架 | `packages/ui-vant/`：`package.json`（deps `@bms/core` / `@bms/vue` / `vant@^4.10.2`；peer `vue` / `vue-i18n` / `vue-router`）/ `tsconfig.json` / `vitest.config.ts`（jsdom + vant inline）/ `env.d.ts`（Vant 按需样式声明） |
| 组件迁入（9 件） | 8 容器件 + `PermButton`：import 源切 `@bms/vue` / `@bms/core`；`PermButton` 判定切本插件 `checkPerm`（原 `@/utils/perm` 宿主依赖去除）；类名钩子 / props / emits / 暴露方法契约不变 |
| 注入实现 | `confirm.ts`：Vant `showConfirmDialog` 默认实现（`danger` 映射危险色）+ core 共享工厂实例；`permission.ts`：core `createPermissionGate` 实例（未注入 = 无权限） |
| 契约套件 | core `testing/components.ts`：`describeContainerComponentsContract` / `describePermButtonContract`（结构不变量 + 关键交互）；`@bms/vue/testing` 新增子路径导出：`createContractKit` 挂载适配（结构接口，core 不引入 Vue 类型） |
| 用例 | 迁入 mobile 9 个容器 spec（Kiwi 742 ~ 750 等，import 源改包内）+ 两插件同跑契约套件（确认 / 权限 / 组件） |
| 工程 | 根 `check` 增 `ui-vant:check`；workspace 根 `npm install` 更新锁文件并落 `vant`（4.10.2，根 node_modules）+ `@bms/ui-vant` 链接 |
| CI / 镜像 | `Dockerfile.frontend` 增 workspace 根 `npm ci`（`/opt/ci/workspace`，含 vant）；`build-base.sh` 哈希输入加根 `package-lock.json`、镜像上下文补根清单与各包清单；`core-check` 改为复制 workspace 根依赖 + 源码 symlink 防旧镜像 |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run check`（core + vue + ui-ep + ui-vant） | 全绿：core **10 / 60** + vue **2 / 6** + ui-ep **12 / 78**（含契约套件）+ ui-vant **11 / 64**（含契约套件）；合计 **35 文件 / 208 用例** |
| `npm run -w @bms/ui-vant typecheck` | 通过（vue-tsc） |
| `apps/desktop`：`npm run lint` + `npm run test` | lint 零告警；**33 文件 / 234 用例**全绿（ui-ep 改造对 PC 宿主无回归） |
| 契约一致性 | `ui-ep` 与 `ui-vant` 对同一套契约（确认 / 权限 / 8 容器件 + 权限按钮）断言全绿 |

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | mobile spec 的测试基座依赖宿主 `@/i18n` 与 pinia | ui-vant 测试助手自建 i18n（容器件文案最小集），不依赖宿主与 pinia（包自足） |
| 2 | mobile 工程 `vue-tsc` 不检查 tests；迁入包后（tsconfig 含 tests）`wrapper.vm.resetMeasurement` 类型报错 | 按包口径显式结构类型断言（与 ui-ep 测试同风格） |
| 3 | `VirtualList` 的 `scroll` 事件经 rAF 合并，提交后一帧才 emit | 契约挂载适配提供 `flushRender()`（等帧 + 渲染），`stubMetrics` 内置等帧 |
| 4 | 契约组件挂载需要 i18n 插件（`FullscreenContainer` / `LoadingContainer` 取词） | `createContractKit` 增 `global` 选项（插件注入 i18n），契约核心不绑插件 |
| 5 | `@bms/vue` 无 DOM 类型面（`lib: ES2022`），挂载适配用 `requestAnimationFrame` 类型缺失 | 经 `globalThis` 结构访问（保持包无 DOM 依赖） |
| 6 | `emitted('click')` 空事件语义（undefined vs 空数组） | 适配统一返回空数组；契约断言 `toHaveLength(0)` |
| 7 | 组件契约首版在 `LoadingContainer` / `SectionContainer` 的类名与事件口径与两实现对齐 | 契约以两实现共同不变量为准（根钩子 / 状态钩子 / 事件语义）；细粒度行为留在各自 spec |

## 5. 偏差与遗留 <a id="deviation"></a>

| # | 项 | 归口 / 去向 |
| --- | --- | --- |
| 1 | 包级 ESLint 未覆盖（`ui-vant` 与 `ui-ep` 一致，仅 `vue-tsc` + Vitest 门禁） | 如需包级 lint，另立工程化批次（沿用 `apps/*` 口径） |
| 2 | 镜像首次重建（含 workspace 根 `npm ci`）耗时增加 | 随 CI 首跑观察；如超时再评估分层缓存 |
| 3 | 契约套件覆盖面为「结构不变量 + 关键交互」（约 9 组） | 后续新增组件时按同模板补契约；细粒度行为保留在两插件 spec |
| 4 | mobile 旧件（9 件 + 31 片段 + 旧基座 + 38 spec）未删；宿主未切流 | S4c（实施记录 19） |
| 5 | Kiwi 台账 mobile 侧对账与平台置 `DISABLED` 清单 | S4c |

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写
