# BMS 移动端 H5（frontend-mobile）

> Vue 3 + Vite + TypeScript 移动端工程（阶段一最小可运行占位，05 细化为完整工程）

## 项目简介

BMS 平台移动端 H5：Vue 3 + Vite + TypeScript（后续按阶段引入 Vant 4、移动端骨架与视口适配）。阶段一先交付最小占位页，完整工程由 05 细化。

## 快速启动

前置：Node 22（nvm 管理）。

```bash
cd frontend-mobile
npm ci
npm run dev
# 验证：访问 http://127.0.0.1:5174 看到占位页
```

## 目录结构

```text
frontend-mobile/
├── .nvmrc            # 固定 Node 22
├── package.json
├── package-lock.json # 依赖锁定（必须提交）
├── vite.config.ts    # 固定开发端口 5174
├── tsconfig.json     # 及 tsconfig.app.json / tsconfig.node.json（模板）
├── index.html
├── README.md         # 本文件
├── public/
│   └── favicon.svg
└── src/
    ├── main.ts
    ├── App.vue       # 占位页面
    └── vite-env.d.ts
```

## 文档导航

- 仓库根 [README](../README.md)
- 《[前端开发规范](../bms文档/规范/前端开发规范.md)》（05 起遵循）
- 《[架构设计 · 前端架构](../bms文档/设计/架构设计/28_架构设计_前端架构.md)》移动端节
