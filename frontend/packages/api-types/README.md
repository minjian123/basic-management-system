# 契约类型包（frontend/packages/api-types）

> `@bms/api-types`：由后端 OpenAPI 契约生成的前端类型（9 个服务各一份）。

## 定位

- 消费后端契约快照生成前端类型，供宿主与模块共享同一套接口类型（`BaseApi` / 请求层与业务代码引用）。
- **生成物不手改**：`src/*.ts` 由 `scripts/generate.mjs` 产出；后端端点变更后重生成，`preflight --fast` 会核对零漂移。

## 快速命令

> 在**工作区根（`bms/`）**执行。

```bash
pnpm run api-types:gen          # 生成（后端契约 → src/*.ts）
pnpm run api-types:gen:check    # 零漂移校验（CI / 预检同口径）
pnpm run api-types:check        # typecheck + lint + test 聚合
```

## 目录结构

```text
frontend/packages/api-types/
├── src/
│   ├── index.ts       # 包根出口
│   ├── platform.ts    # 平台服务契约类型
│   ├── identity.ts    # 认证与身份
│   ├── tenant.ts      # 租户与配置
│   ├── org.ts         # 组织主数据
│   ├── file.ts        # 文件
│   ├── notification.ts# 通知
│   ├── search.ts      # 检索
│   ├── ai.ts          # AI
│   └── report.ts      # 报表打印
├── scripts/           # generate.mjs（契约快照 → 类型）
└── tests/             # 生成物一致性用例
```

## 关键约定

- **单一来源**：类型源自后端契约快照（`deploy/contracts/<service>.json`，由 `ops.contract_snapshot export` 生成）；前端不维护手写接口类型。
- **后端改端点后必须重生成**：`pnpm run api-types:gen`，否则 `api-types` 漂移检查失败。
- **生成物与源码同库提交**：`src/*.ts` 入库，评审看差异而非全量。

## 文档导航

- 上层 [frontend 工程说明](../README.md) · 仓库根 [README](../../../README.md)
- 《[API 接口规范](../../../bms文档/规范/API接口规范.md)》·《[前端开发规范](../../../bms文档/规范/前端开发规范.md)》
- 《[架构设计 · 接口与集成](../../../bms文档/设计/架构设计/09_架构设计_接口与集成.md)》
