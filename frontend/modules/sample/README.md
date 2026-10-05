# 模块样例（frontend/modules/sample）

> `@bms/module-sample`：**首个真实形态**的运行时模块样例（查询筛选 + 列表 + 详情 / 表单）。

## 定位

- 独立工程、独立构建、独立产物（`dist/remoteEntry.js` + 页面异步分包），宿主按 `public/modules.json` 在运行期加载。
- 与演示模块 `demo` 的差异：形态更接近真实业务模块（含服务层、领域模型、i18n、组合式逻辑），是后续业务模块的**工程样板**。
- 只经宿主注入上下文（`ModuleApi` / 权限码只读快照）访问能力；不直连宿主 store / router、不持久化、不自建 HTTP。

## 快速命令

> 在**工作区根（`bms/`）**执行。

```bash
pnpm --filter @bms/module-sample dev
pnpm --filter @bms/module-sample build             # 构建模块产物（dist/）
pnpm --filter @bms/module-sample build:standalone  # 构建独立预览壳
pnpm --filter @bms/module-sample test
pnpm --filter @bms/module-sample lint
pnpm --filter @bms/module-sample budget            # 模块产物体积预算
pnpm --filter @bms/module-sample guard:isolation   # 模块隔离护栏
```

**发布到本地产物服务**：

```bash
node frontend/scripts/release-module.mjs publish --module sample --force
```

## 目录结构

```text
frontend/modules/sample/
├── src/
│   ├── index.ts        # 模块定义（MF remote 入口：默认导出 defineModule 结果）
│   ├── runtime.ts      # 运行期状态与宿主注入上下文的只读消费
│   ├── standalone.ts   # 独立预览壳装配
│   ├── domain.ts       # 模块领域模型
│   ├── services/       # 模块服务（经注入的 api 能力调用后端契约）
│   ├── composables/    # 模块组合式逻辑
│   ├── components/     # 模块内组件
│   ├── views/          # 模块页面
│   ├── i18n/           # 模块文案（zh-CN / en-US）
│   └── env.d.ts        # 环境与版本常量声明
├── tests/              # module-contract / module-context / module-definition 用例
├── budget.json         # 产物体积预算
└── vite.config.ts      # MF 远端导出配置
```

## 关键约定

- **清单一致性**：`manifest.name` / `version` 须与宿主 `frontend/apps/desktop/public/modules.json` 条目严格一致（版本构建期注入）。
- **契约用例必备**：`tests/module-contract.spec.ts` 不可删；契约版本双源一致。
- **体积预算**：`budget.json` 为模块产物成本基线（当前 gzip 上限 660 KB，调整须有实测依据）。
- **UI 复用**：模板内不得出现裸原生交互元素，走 `@bms/ui-ep` 组件族或 Element Plus 基础件。
- **只 build 不发布无效**：产物服务托管 `frontend/releases/**`，同版本重发必须 `--force`。

## 文档导航

- 上层 [frontend 工程说明](../README.md) · 仓库根 [README](../../../README.md)
- 《[架构设计 · 子系统_扩展点与插件化](../../../bms文档/设计/架构设计/10_架构设计_子系统_扩展点与插件化.md)》·《[架构设计 · 子系统_模块注册](../../../bms文档/设计/架构设计/11_架构设计_子系统_模块注册.md)》
- 《[前端开发规范](../../../bms文档/规范/前端开发规范.md)》·《[组件设计总览](../../../bms文档/设计/组件设计/01_组件设计_总览.md)》
