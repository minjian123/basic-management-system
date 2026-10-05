# 具名插槽样例（frontend/modules/slot-sample）

> `@bms/module-slot-sample`：**无路由**的运行时模块样例——只向宿主页具名插槽注册区域项。

## 定位

- 与 `sample` 的差异：本模块**不声明路由**（无页面、不进菜单），只向宿主页具名插槽 `sys.user.detail.tabs` 注册**区域项**，示范平台内插件经插槽挂接的形态。
- 数据与写操作归**后端契约**（platform 服务 `/api/v1/user-extensions`，权限码 `sys:user-extension:query` / `sys:user-extension:update`），模块只渲染并**经宿主注入的 `api` 能力**调用。
- 独立工程、独立构建、独立产物（`dist/remoteEntry.js` + 区域件异步分包 + `module.meta.json`）。

## 快速命令

> 在**工作区根（`bms/`）**执行。

```bash
pnpm --filter @bms/module-slot-sample dev
pnpm --filter @bms/module-slot-sample build             # 构建模块产物（dist/）
pnpm --filter @bms/module-slot-sample build:standalone  # 构建独立预览壳
pnpm --filter @bms/module-slot-sample test
pnpm --filter @bms/module-slot-sample lint
pnpm --filter @bms/module-slot-sample budget
pnpm --filter @bms/module-slot-sample guard:isolation
```

**发布到本地产物服务**：

```bash
node frontend/scripts/release-module.mjs publish --module slot-sample --force
```

## 目录结构

```text
frontend/modules/slot-sample/
├── src/
│   ├── index.ts        # 模块定义（只注册区域项，无 routes）
│   ├── runtime.ts      # 运行期状态与宿主注入上下文的只读消费
│   ├── standalone.ts   # 独立预览壳装配
│   ├── services/       # 经注入 api 能力调用后端契约
│   ├── composables/    # 模块组合式逻辑
│   ├── components/     # 区域件
│   ├── i18n/           # 模块文案（zh-CN / en-US）
│   └── env.d.ts        # 环境与版本常量声明
├── tests/              # module-contract / module-context / module-definition 用例
├── budget.json         # 产物体积预算
└── vite.config.ts      # MF 远端导出配置
```

## 关键约定

- **插槽标识**：`sys.user.detail.tabs`（格式 `{域}.{页面}.{区域}`，注册期校验 ≥ 2 段）；宿主页「用户详情」声明该挂接点。
- **区域项形态**：`inline`（一行高窄容器，只放紧凑件）/ `tabs` 两形态；越界的整页不得注册进区域。
- **权限对齐**：区域项 `perm` 引用后端同一权限码（`sys:user-extension:update` 等），前后端同源。
- **清单一致性**：`manifest.name` / `version` 须与宿主 `public/modules.json` 条目严格一致（版本构建期注入）。
- **只 build 不发布无效**：产物服务托管 `frontend/releases/**`，同版本重发必须 `--force`。

## 文档导航

- 上层 [frontend 工程说明](../README.md) · 仓库根 [README](../../../README.md)
- 《[架构设计 · 子系统_扩展点与插件化](../../../bms文档/设计/架构设计/10_架构设计_子系统_扩展点与插件化.md)》·《[架构设计 · 子系统_模块注册](../../../bms文档/设计/架构设计/11_架构设计_子系统_模块注册.md)》
- 《[前端开发规范](../../../bms文档/规范/前端开发规范.md)》·《[前端基类清单](../../../bms文档/前端基类清单.md)》
