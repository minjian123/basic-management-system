<div align="center">

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-2F5B7C?logo=sqlalchemy&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3.5+-42B883?logo=vue.js&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-7-B47159?logo=vite&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)
![Element Plus](https://img.shields.io/badge/Element_Plus-2.x-364FD1?logo=element&logoColor=white)
![Vant](https://img.shields.io/badge/Vant-4.x-3C8DDE?logo=apacheflink&logoColor=white)
![bpmn-js](https://img.shields.io/badge/bpmn--js-17+-2C7A79)
![Redis](https://img.shields.io/badge/Redis-8+-DC382D?logo=redis&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.4+-4479A1?logo=mysql&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-316192?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-27+-2496ED?logo=docker&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker_Compose-2.33+-2496ED?logo=docker&logoColor=white)
![GitLab](https://img.shields.io/badge/GitLab-18+-FC6A21?logo=gitlab&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

## 简介

基础管理系统（BMS）是一个面向企业级场景的后端管理系统，支持分布式、集群部署；多租户 SaaS 架构（租户独立库），支持 SSO 单点登录，内置报表 BI 与移动端 H5。

后端基于 FastAPI + SQLAlchemy，前端基于 Vue 3 + Vite（PC 管理端 + 移动端 H5 双工程），通过知识图谱（graphify）辅助代码理解与架构分析。

## 文档

> 全部文档位于 `文档/` 目录，入口为《[文档首页](文档/文档首页.md)》（全量导航）。正文以 Markdown 为载体，线框图/可交互原型保留 `.html` 资产。

## 目录结构

```text
bms/
├── README.md                 # 本文件
├── LICENSE                   # MIT 许可
├── AGENTS.md                 # AI 协作约定
├── ops/                      # 产品运维脚本（种子数据、备份恢复、租户库迁移，后续阶段填充）
├── deploy/                   # 部署配置
│   ├── .env.example          # 凭据模板
│   ├── compose/              # Docker Compose（base / gitlab / kiwi）
│   └── setup/                # 环境安装脚本
├── scripts/                  # 开发期工具链
│   └── tools/                # backup 备份、bg 后台执行器、defect 缺陷工具、gitlab 流水线、graphify 本地化、reorder-design 设计整理、wol 电源控制
└── 文档/                     # 项目文档
    ├── 文档首页.md            # 全量导航
    ├── 规划/                  # 3篇：项目规划说明、总体项目规划、开发部署规划
    ├── 规范/                  # 19篇：文档、命名、前后端、数据库、API、安全、测试、日志、评审、国际化、Git、部署发布、原型审查、项目管理、需求/计划/任务文档、英文简称
    ├── 设计/
    │   ├── 架构设计/          # 31篇：总纲 1 + 专题 10 + 子系统设计 20
    │   ├── 概要设计/          # 38篇：总纲 1 + 功能模块 37
    │   ├── 布局设计/          # 16篇（html 资产）
    │   ├── 原型设计/          # 63篇可交互原型（html 资产）
    │   └── 组件设计/          # 1篇：字典字段组件
    ├── 资料/
    │   ├── 开发服务器/        # 12篇：各服务部署使用说明（含排障记录）
    │   ├── 开发机/            # 2篇：开发机部署说明
    │   ├── 工具/              # 5篇：Ubuntu 安装、GitLab 迁移、电源控制、后台执行器等
    │   ├── AI/                # 3篇：graphify、llamacpp、deepseek_harness 部署说明
    │   └── 知识档案/          # 73篇：72项技术介绍 + 总览（后端 34 / 前端 20 / 工程化 8 / 部署运维 8 / AI 2）
    ├── 用户文档/              # 本地资源（机器凭据等，已 gitignore）
    └── 资源/                  # 文档共享样式与 mermaid 资产
```

> 凭据统一存 `deploy/.env`（已 gitignore，模板见 `deploy/.env.example`）。

## 使用指南

| 目的 | 文档 |
| --- | --- |
| 快速上手（技术栈、功能范围、开发计划） | [规划/项目规划说明](文档/规划/项目规划说明.md) |
| 开发环境部署方案（分工、服务清单、端口与磁盘规划） | [规划/开发部署规划](文档/规划/开发部署规划.md) |
| 全量文档导航 | [文档首页](文档/文档首页.md) |
| 文档格式与检查清单 | [规范/文档生成规范](文档/规范/文档生成规范.md) |
| 命名约定（代码 / 数据库 / API / 基础设施） | [规范/命名规范](文档/规范/命名规范.md) |
| 原型审查 | [规范/原型审查规范](文档/规范/原型审查规范.md) |
| 开发服务器环境部署 | [资料/开发服务器/开发服务器部署使用说明总览](文档/资料/开发服务器/开发服务器部署使用说明总览.md) |
| 技术栈知识档案（选型背景） | [资料/知识档案/技术栈知识档案总览](文档/资料/知识档案/技术栈知识档案总览.md) |
| 架构设计入口 | [设计/架构设计/01_总览](文档/设计/架构设计/01_架构设计_总览.md) |
