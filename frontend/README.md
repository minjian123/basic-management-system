# 前端工程（frontend）

> BMS 前端单仓多包（pnpm workspace）：`packages/` 基座 + `apps/` 宿主 + `modules/` 运行时模块。

## 定位

- **基座（`packages/`）**：与宿主无关的能力底座——框架无关核心 `@bms/core`、Vue 绑定 `@bms/vue`、PC 实现插件 `@bms/ui-ep`、契约类型 `@bms/api-types`。
- **宿主（`apps/`）**：装配基座并渲染最终界面的应用；当前为 PC 管理端 `apps/desktop`（移动端 H5 随阶段十七交付）。
- **运行时模块（`modules/`）**：以 Module Federation 在运行时装载的业务模块（样例 `demo` / `sample` / `slot-sample`），平台与产品插件均按此形态接入。

workspace 收敛与单一锁文件都在**仓库根（`bms/`）**：`pnpm-workspace.yaml` 收敛 `frontend/{packages,apps,modules}/*`，锁文件为根 `pnpm-lock.yaml`。依赖**不进仓库树**——node_modules 外置到本地依赖仓，原位为符号链接（见下「依赖外置」）。

## 快速命令

> 以下均在**工作区根（`bms/`）**执行。

```bash
# 依赖外置维护：安装前必须先还原，装完恢复外置态
bash scripts/tools/deps/还原依赖.sh
pnpm install --frozen-lockfile
bash scripts/tools/deps/外置依赖.sh

# 基座四包聚合门禁（core / api-types / vue / ui-ep：typecheck + lint + test）
pnpm run check
pnpm run lint

# 宿主与模块不在根 check 内，需按包单独跑
pnpm --filter @bms/desktop dev            # PC 宿主开发服务器（端口 5173）
pnpm --filter @bms/desktop test           # 宿主用例（含 guard-* 护栏）
pnpm --filter @bms/module-demo build      # 运行时模块构建

# 契约类型生成（后端 OpenAPI → 前端类型）
pnpm run api-types:gen
```

## 目录结构

```text
frontend/
├── packages/                # 基座多包（源码头，宿主经 vite alias / tsconfig paths 消费）
│   ├── core/                # @bms/core：框架无关核心（基类 / 机制 / 领域 / 契约 / 注册表 / 模块契约）
│   ├── vue/                 # @bms/vue：Vue 绑定插件（组合式投影）
│   ├── ui-ep/               # @bms/ui-ep：PC 实现插件（Element Plus 组件族）
│   └── api-types/           # @bms/api-types：后端契约生成类型（9 个服务）
├── apps/
│   └── desktop/             # @bms/desktop：PC 管理端宿主（Vue 3 + Vite）
├── modules/                 # 运行时模块（Module Federation 远端）
│   ├── demo/                # @bms/module-demo：演示模块（含独立预览壳）
│   ├── sample/              # @bms/module-sample：能力样例模块
│   └── slot-sample/         # @bms/module-slot-sample：具名插槽样例（只注册区域项，无路由）
├── scripts/                 # 模块产物发布 / 托管与模块治理校验（release-module / serve-module-releases / check-module-*）
├── releases/                # 模块产物归档（不入库；仅 release-log.{json,md} 入库）
├── module-contract.json     # 模块契约版本单一来源（当前 v2）
└── shared-dependencies.json # 模块共享依赖清单（MF shared 口径：vue / vue-router / pinia 单例共享）
```

## 关键约定

- **依赖外置**：`pnpm install` 前必须先跑 `还原依赖.sh`（安装器见符号链接会误判跳过），装完用 `外置依赖.sh` 恢复外置态。
- **严格依赖树**：import 了哪个包就在该工程 `package.json` 声明哪个包；唯一安装入口 `pnpm install --frozen-lockfile`（与 CI 同口径）。
- **基类改动同步三处**：基类清单登记 + `extends` 链 + 包 `src/index.ts` 具名导出，否则 `guard-base-registry` 护栏红。
- **模块契约版本双源一致**：根 `module-contract.json` 与 `@bms/core` 契约常量须一致；声明增改属不向后兼容变更→升版本并重建重发布所有模块。
- **模块产物生效链路**：`pnpm --filter @bms/module-<x> build` → `node frontend/scripts/release-module.mjs publish --module <x> --force`（**只 build 不发布 ⇒ 产物服务仍发旧产物**；同版本重发必须 `--force`）。
- **UI 复用强制**：业务侧（宿主 + `modules/*`）模板内不得出现裸原生交互元素（`<input>` / `<button>` / `<select>` / `<textarea>`），一律经 `@bms/ui-ep` 组件族或 Element Plus 基础件。
- **界面改动须过原型对照门禁**：依据取 `bms文档/设计/原型设计/`（页面任务）或《组件设计》（件族任务）。

## 文档导航

- 仓库根 [README](../README.md)
- 《[前端开发规范](../bms文档/规范/前端开发规范.md)》·《[前端基类清单](../bms文档/前端基类清单.md)》
- 《[架构设计 · 前端组件体系](../bms文档/设计/架构设计/05_架构设计_前端组件体系.md)》·《[架构设计 · 前端架构](../bms文档/设计/架构设计/08_架构设计_前端架构.md)》
- 《[组件设计总览](../bms文档/设计/组件设计/01_组件设计_总览.md)》·《[原型设计总览](../bms文档/设计/原型设计/01_原型设计_总览.html)》·《[布局设计总览](../bms文档/设计/布局设计/01_布局设计_总览.html)》
- 《[开发机部署使用说明总览](../bms文档/资料/开发机/开发机部署使用说明总览.md)》
