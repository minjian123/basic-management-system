# PC 实现插件（frontend/packages/ui-ep）

> `@bms/ui-ep`：基于 Element Plus 的前端实现插件，按族组织组件并提供基类投影 composables。

## 定位

- 承载前端「具体件」实现：把 `@bms/core` 的组件基类落成 Element Plus 之上的实际组件；族划分与《[组件设计](../../../bms文档/设计/组件设计/01_组件设计_总览.md)》目录一致（基础组件类 / 布局 / 容器 / 基础控件 / 字段 / 展示 / 交互 / 基础类）。
- 对外提供组件 + 基类投影 composables + 注入点 + 单一落点 utils。
- **件复用唯一来源**：业务侧（宿主 + `modules/*`）模板内不得自绘原生交互元素，缺件时先补进本包并在《组件设计》登记。

## 快速命令

> 在**工作区根（`bms/`）**执行。

```bash
pnpm --filter @bms/ui-ep typecheck    # vue-tsc
pnpm --filter @bms/ui-ep lint
pnpm --filter @bms/ui-ep test
pnpm run ui-ep:check                  # 上方三项聚合（根脚本）
```

## 目录结构

```text
frontend/packages/ui-ep/
├── src/
│   ├── index.ts        # 包根出口（组件与 composables 具名导出）
│   ├── components/     # 按族组织的组件实现
│   ├── composables/    # 基类投影 composables
│   ├── icons/          # 图标资源与渲染
│   ├── assets/         # 样式与静态资源
│   └── utils/          # 单一落点工具
└── tests/              # 组件族用例（含契约用例）
```

## 关键约定

- **件族原型依据**：《[组件设计](../../../bms文档/设计/组件设计/01_组件设计_总览.md)》目录下的 `*.html` 为件族的原型依据（页面任务用《[原型设计](../../../bms文档/设计/原型设计/01_原型设计_总览.html)》，门禁两者都认）。
- **样式入件**：件样式一律写在组件 `<style scoped>` 内并只用设计令牌（`tokens.scss`），不硬编码色值 / 间距。
- **组件根出口**：新增件必须进 `src/index.ts` 根出口，否则宿主与模块消费不到。
- **受控口径**：件同时受宿主 props 与内核双通道时须实现 `applySnapshot()`，写入统一经壳 `slot.setValue` 进域。
- **EP 折叠态**：`el-menu` 折叠态隐藏 `.el-menu-item > span` / `.el-sub-menu__title > span`，侧栏图标须包在非 `span` 元素内或置于标题 `span` 之外。

## 文档导航

- 上层 [frontend 工程说明](../README.md) · 仓库根 [README](../../../README.md)
- 《[组件设计总览](../../../bms文档/设计/组件设计/01_组件设计_总览.md)》·《[布局设计 · 设计令牌](../../../bms文档/设计/布局设计/02_布局设计_设计令牌.html)》
- 《[前端开发规范](../../../bms文档/规范/前端开发规范.md)》·《[前端基类清单](../../../bms文档/前端基类清单.md)》·《[原型审查规范](../../../bms文档/规范/原型审查规范.md)》
