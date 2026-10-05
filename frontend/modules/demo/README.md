# 演示模块（frontend/modules/demo）

> `@bms/module-demo`：模块化体系的演示模块（**开发态进菜单，不进生产菜单**），示范八类扩展点贡献与宿主注入上下文的消费方式。

## 定位

- 独立工程、独立构建、独立产物：产物为 `dist/remoteEntry.js` + 页面异步分包，并含**独立预览壳**（`dist-standalone/`，不依赖宿主）。
- 宿主按 `public/modules.json` 条目在运行期加载本容器暴露的 `./module`（模块定义，**默认导出**），经统一装配器倒入扩展点注册表。
- 示范口径：只经注入上下文（`ModuleApi` / 权限码等**只读快照**）访问宿主能力，缺失项自行降级。

## 快速命令

> 在**工作区根（`bms/`）**执行。

```bash
pnpm --filter @bms/module-demo dev               # 独立工程开发服务器
pnpm --filter @bms/module-demo build             # 构建模块产物（dist/）
pnpm --filter @bms/module-demo build:standalone  # 构建独立预览壳
pnpm --filter @bms/module-demo test              # 契约 / 上下文 / 定义用例
pnpm --filter @bms/module-demo lint
pnpm --filter @bms/module-demo budget            # 模块产物体积预算
pnpm --filter @bms/module-demo guard:isolation   # 模块隔离护栏
```

**发布到本地产物服务**（宿主经 `modules.json` 加载）：

```bash
node frontend/scripts/release-module.mjs publish --module demo --force
```

## 目录结构

```text
frontend/modules/demo/
├── src/
│   ├── index.ts        # 模块定义（MF remote 入口：默认导出 defineModule 结果）
│   ├── runtime.ts      # 运行期状态与宿主注入上下文的只读消费
│   ├── standalone.ts   # 独立预览壳装配
│   ├── components/     # 模块内组件
│   ├── views/          # 模块页面
│   └── env.d.ts        # 环境与版本常量声明（构建期注入 __BMS_MODULE_VERSION__）
├── tests/              # module-contract / module-context / module-definition 用例
├── budget.json         # 产物体积预算
└── vite.config.ts      # MF 远端导出配置
```

## 关键约定

- **清单一致性**：`manifest.name` / `version` 须与宿主 `frontend/apps/desktop/public/modules.json` 条目**严格一致**（版本构建期注入）。
- **契约用例必备**：`tests/module-contract.spec.ts` 不可删；契约版本双源（`@bms/core` 常量 ↔ 根 `module-contract.json`）。
- **隔离约定**：模块不直连宿主 store / router、不持久化、不自建 HTTP，一律经注入上下文（护栏 `guard:isolation`）。
- **只 build 不发布无效**：产物服务托管的是 `frontend/releases/**`，同版本重发必须 `--force`。

## 文档导航

- 上层 [frontend 工程说明](../README.md) · 仓库根 [README](../../../README.md)
- 《[架构设计 · 子系统_扩展点与插件化](../../../bms文档/设计/架构设计/10_架构设计_子系统_扩展点与插件化.md)》·《[架构设计 · 子系统_模块注册](../../../bms文档/设计/架构设计/11_架构设计_子系统_模块注册.md)》
- 《[前端开发规范](../../../bms文档/规范/前端开发规范.md)》
