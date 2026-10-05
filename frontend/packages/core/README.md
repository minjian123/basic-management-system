# 前端核心基座（frontend/packages/core）

> `@bms/core`：框架无关的前端核心基座（纯 TypeScript），承载分层基类族、能力域、机制与契约。

## 定位

- 前端「**固定三段**」体系的定义侧：`BaseComponent`（组件根）→ 能力基类 → 组件基类 → 具体件；本包只定义基类 / 能力 / 契约，**具体 UI 实现见 `@bms/ui-ep`**。
- 承载：基类族（`base/`）、能力域基类族（`capabilities/`）、契约（`contracts/`）、领域（`domain/`）、机制（`mechanisms/`）、扩展点注册表与统一装配（`registries/`）、模块契约（`module/`）。
- 经 `@bms/core/testing` 向各包与运行时模块提供**契约用例工厂**与护栏工具。

## 快速命令

> 在**工作区根（`bms/`）**执行。

```bash
pnpm --filter @bms/core typecheck
pnpm --filter @bms/core lint
pnpm --filter @bms/core test
pnpm run core:check          # 上方三项聚合（根脚本）
```

## 目录结构

```text
frontend/packages/core/
├── src/
│   ├── index.ts        # 包根出口（基类 / 能力具名导出；改基类须同步此处）
│   ├── base/           # 基类族（组件根 / 能力基类 / 组件基类等）
│   ├── capabilities/   # 能力域基类族
│   ├── contracts/      # 契约定义与契约集合口径
│   ├── domain/         # 领域模型与错误码解析等
│   ├── mechanisms/     # 机制（注册 / 装配 / 生命周期等）
│   ├── module/         # 模块契约（版本常量与类型，与根 module-contract.json 双源一致）
│   └── registries/     # 扩展点注册表与统一装配 assemble
└── testing/            # @bms/core/testing：契约用例工厂与护栏工具（各包 / 模块复用）
```

## 关键约定

- **基类改动同步三处**：基类清单登记 + `extends` 链 + `src/index.ts` 具名导出；漏一处即 `guard-base-registry` 六道护栏红。
- **能力即继承链上的层**：链外不得挂接；新增能力基类须另登记 `CAPABILITY_MANIFEST`。
- **模块契约版本双源**：本包契约常量与根 `module-contract.json` 必须一致（护栏用例断言）；版本递增后须重建并重发布全部模块。
- **严格依赖树**：本包是「源码直出」包，只允许依赖自身声明过的包；不得反向依赖宿主或模块。

## 文档导航

- 上层 [frontend 工程说明](../README.md) · 仓库根 [README](../../../README.md)
- 《[前端基类清单](../../../bms文档/前端基类清单.md)》（基类权威登记）·《[前端开发规范](../../../bms文档/规范/前端开发规范.md)》
- 《[架构设计 · 前端组件体系](../../../bms文档/设计/架构设计/05_架构设计_前端组件体系.md)》·《[架构设计 · 子系统_扩展点与插件化](../../../bms文档/设计/架构设计/10_架构设计_子系统_扩展点与插件化.md)》
