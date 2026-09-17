# 框架无关核心重构 · S6 实施记录（desktop 旧层收口）

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · 收尾批次（S6）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | `02_07` 收尾批次 **S6 desktop 旧层收口**（按 S4c 同口径，2026-09-17 追加） |
| 对应设计 | [S4 详细设计](../设计/01_详细设计_S4_ui-vant插件与移动端收口.md)（同口径沿用；S6 增量：`dynamic-routes` 下沉） |
| 实施日期 | 2026-09-17 |
| 实施人 | minjian |
| 环境 | Linux 开发机（mjpc）；Node v24.20.0；npm workspaces（core / vue / ui-ep / ui-vant）+ 宿主（apps/desktop / apps/mobile） |
| 实测工时 | ≈2h |
| 结论 | S6 完成：`apps/desktop` 旧基座 / 片段层删除并全量切 `@bms/*`；`dynamic-routes`（菜单→路由构建）下沉 `@bms/core` + `@bms/vue` 新投影 `useDynamicRoutes`；`02_07` 全链含收尾完成 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 能力下沉 | `packages/core/src/capabilities/dynamic-routes.ts`：扩展 `buildRoutes`（前缀推导 / `public` 过滤 / 白名单 / 元信息 / 递归子级）、反应式 `routes`、`register`（按名去重 + adapter 通知）、`unregister` / `hasRoute` / `reset`（行为自旧片段逐条保持） |
| Vue 投影 | `packages/vue/src/bindings/useDynamicRoutes.ts`（接口面与旧片段同构：`routes` / `registered` / `buildRoutes` / `register` / `unregister` / `hasRoute` / `reset`）；测试 2 条 |
| 宿主切流 | `apps/desktop`：新增 `adapters/host-base.ts`（宿主根系 sink）；`layouts/BasicLayout.vue` 的 `usePersistedState` 切 `@bms/vue`；`router/menuRoutes.ts` 切 `useDynamicRoutes`（`MenuNode` / `RouteRecord` 类型自 `@bms/core`；只保留 Vue 注册适配）；`stores/{base,permission}.ts`、`api/{base,error,http,request}.ts` 切 `@bms/core` / `@bms/vue`（与移动端同口径，含 `filterRoutes` host 侧实现） |
| 旧层删除 | `apps/desktop/src/base/`（12 文件）、`src/components/`（31 片段 + `fragments.ts` / `index.ts` + 4 域包装件 `BaseInput` / `BaseDisplay` / `BaseTree` / `BaseEditor` 及域内组合式）；旧 spec **19 个**（`base-*` 14 / `guard-*` 4 / `format-registry` 1）+ `tests/helpers/guard/` |
| 用例改造 | `base.spec` / `http.spec` / `request.spec` 改宿主 sink（`@/adapters/host-base`）；其余宿主用例（permission / directive-perm / layout / menu / tabs / modal 等）保持不变 |
| 文档回写 | 《前端基类清单》§9 / §10 全表重写（核心 / 绑定 / 契约工厂 / 插件 / 令牌 / 宿主四层现状）；《前端开发规范》§3 旧层措辞清理；审计 §9（S6 重跑）；计划 / 任务（S6 行与状态）；bms `README.md` 目录树 updated |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `apps/desktop`：`npm run lint` / `vue-tsc -b` | 零告警 / 通过 |
| `apps/desktop`：`npm run test` | **14 文件 / 77 用例**全绿（旧层用例 157 条随旧 spec 下线） |
| `apps/desktop`：`npm run build` + `npm run budget` | 通过：合计 **208.9 KB**（预算 240 KB）/ 最大单文件 **110.2 KB**（预算 120 KB） |
| bms 根：`npm run check` | core **11 / 65**（新增 dynamic-routes 6 条）+ vue **4 / 13**（新增投影 2 条）+ ui-ep 12 / 78 + ui-vant 11 / 64 全绿 |
| 文档校验 | `check-base` / `check-links` / `check-status` 通过 |

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | 旧片段 `dynamic-routes` 的 `buildRoutes` / 登记链在 core 侧不存在（core 仅有 adapter 注册骨架） | 经确认「下沉 core + vue 投影」：扩展 `BaseDynamicRoutes`（纯逻辑 + 反应式 routes）并新增 `useDynamicRoutes`；`RouteRecordLike`（adapter 契约）保持原样，新增 `RouteRecord`（含 `meta` / `children`），既有调用兼容 |
| 2 | `MenuNode` / `RouteRecord` 类型经 `@bms/vue` 导入不存在 | 类型自 `@bms/core` 导入（契约在 core），绑定仅提供组合式（口径与「useXxx 只在 packages/vue」一致） |
| 3 | desktop 的 `stores/permission` 依赖旧片段 `AccessFilterableNode` 与 `filterRoutes` | 与移动端同口径：类型本地声明、`filterRoutes` host 侧实现（保 Kiwi 720 第 ⑮ 条覆盖）；`permVersion` 由 store 自持 |
| 4 | 旧 `BaseFrontend` 全局 sink 在核心不存在 | 新增 `apps/desktop/src/adapters/host-base.ts`（与移动端同口径；宿主日志 / 上报出口统一，测试可注入） |

## 5. 偏差与遗留 <a id="deviation"></a>

| # | 项 | 归口 / 去向 |
| --- | --- | --- |
| 1 | 4 域包装件（`BaseInput` / `BaseDisplay` / `BaseTree` / `BaseEditor`）与域基类组合式随旧层删除 | 域 05+（回补波）按新体系在 core + `@bms/vue` + 插件重建（原实现作为参考，历史经 git 追溯） |
| 2 | 设计令牌仍由各宿主 `src/styles/tokens.scss` 自持 | 令牌下沉 `@bms/vue/styles` 随品牌化任务评估（清单已登记） |
| 3 | Kiwi 平台侧旧件用例置 `DISABLED` | 随本轮执行（apps 侧 724 ~ 737 / 740 ~ 741；清单见 `test/test文档/用例/Kiwi用例台账.md` §2.1） |
| 4 | 移动端缺口清单批次（反馈件 4 件）与包级 ESLint | 本轮后续（域 03 嵌套子任务 / 工程化批次） |

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写
