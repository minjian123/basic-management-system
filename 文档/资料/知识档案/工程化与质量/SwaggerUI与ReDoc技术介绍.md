# Swagger UI 与 ReDoc 技术介绍

> OpenAPI 文档渲染器 · BMS 接口联调与验收依据

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [工程化与质量](../技术栈知识档案总览.md#eng) › Swagger UI 与 ReDoc 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Swagger UI** 与 **ReDoc** 都是把 OpenAPI（原称 Swagger）schema
渲染成网页文档的前端工具，两者定位互补：
Swagger UI 偏"用"——可以填参数、发请求、看响应，是调试台；
ReDoc 偏"读"——单栏排版、只读不执行，适合通读接口全貌。
BMS 中两者都由 FastAPI 自动生成并内置，零额外成本。

- **定位**：BMS 接口文档渲染器——FastAPI 自动生成 OpenAPI schema，内置两个文档界面，作为接口联调与验收依据。
- **版本**：Swagger UI 5.x 系列、ReDoc 2.x 系列（均由 FastAPI 依赖链引入，随 FastAPI 锁定）。
- **许可**：Swagger UI 为 Apache-2.0，ReDoc 为 MIT，均为 OSI 认证开源。
- **运行方式**：纯前端静态页面，读一个 JSON（openapi.json）即可渲染，无需独立服务。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| OpenAPI（OAS） | 接口描述的开放标准（原 Swagger 规范）：用 JSON/YAML 完整描述路径、参数、请求/响应模型、认证方式，机器可读、人可读 |
| OpenAPI schema（openapi.json） | 按标准产出的接口契约文件：FastAPI 从路由与 Pydantic 模型自动推导生成，是文档与契约的唯一数据源 |
| Swagger UI | 交互式文档：每个接口可展开填参数、点 "Try it out" 直接发真实请求并查看响应，适合联调与验收演示 |
| ReDoc | 只读文档：左侧接口树 + 右侧详情的单栏布局，排版克制、无执行能力，适合系统性通读与对外交付 |
| FastAPI 自动生成 | 框架启动即产出 schema：类型注解 + Pydantic 模型 → 参数与响应结构，无需手写文档（见《[FastAPI 技术介绍](../后端核心/FastAPI技术介绍.md)》） |
| 三个内置端点 | `/docs`（Swagger UI）、`/redoc`（ReDoc）、`/openapi.json`（原始 schema），FastAPI 开箱即用 |
| 契约快照（swagger.json） | CI 从 `/openapi.json` 导出的版本化快照：随 main 流水线归档分发，作为前后端与外部系统的对接基线 |
| tags（分组） | 接口按模块打标签分组，文档里按组折叠，BMS 按功能模块组织路由即自动成组 |
| securitySchemes（认证声明） | 在 schema 中声明 Bearer JWT 等认证方式，文档页可直接填 Token 调试受保护接口 |
| summary / description | 接口与字段的中文摘要描述：FastAPI 的 `summary`、`description` 参数与 Pydantic 的 `description` 直接进文档 |
| 静态渲染 | 两个渲染器都是纯前端：拿到 openapi.json 就能渲染，可内嵌、可离线打包，不依赖文档后端 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- FastAPI 自动生成 OpenAPI schema 并内置两个文档界面：`/docs`（Swagger UI）与 `/redoc`（ReDoc），开发联调零成本（见《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节"API 文档：Swagger UI / ReDoc"）。
- **接口联调依据**：前端、移动端与外部系统对接时，以 Swagger UI 的 "Try it out" 实际发请求验证行为，以 ReDoc 通读接口全貌与字段语义（见《[项目规划说明](../../../规划/项目规划说明.md#sel-eng)》3.3 节）。
- **验收依据**：UAT 与阶段验收时，接口行为以文档声明为准，文档与实现不一致即缺陷。
- **契约快照**：main 流水线导出 `swagger.json` 契约快照归档分发；生产环境关闭 Swagger/ReDoc 在线文档，对外只发快照（见《[项目规划说明](../../../规划/项目规划说明.md#api)》8 节"API 设计规范"）。
- 本地开发入口：`http://localhost:8000/docs`（见《[开发部署规划](../../../规划/开发部署规划.md)》5.3 节）。

导出契约快照（本地起服务后执行）：

```bash
# Linux / macOS
curl -o swagger.json http://localhost:8000/openapi.json

# Windows PowerShell
Invoke-WebRequest -Uri http://localhost:8000/openapi.json -OutFile swagger.json
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Swagger UI（选中，交互）** | 可填参发请求、看真实响应，调试效率高；界面偏"工具感"，通读略累<br>缺点：功能多、体积大 | 联调、验收演示、外部对接首选 |
| **ReDoc（选中，通读）** | 单栏只读、排版清爽，适合系统性阅读与对外交付<br>缺点：不能发请求 | 通读接口全貌、写文档引用首选 |
| Redocly（商业文档平台） | docs-as-code、主题定制强<br>缺点：商业授权、需独立构建链，BMS 无此需求 | 不引入 |
| Stoplight Elements | 可交互、可定制<br>缺点：社区与资料少，与 FastAPI 无内置集成 | 不引入 |
| 手写 Markdown 接口文档 | 自由度高<br>缺点：与实现必然漂移，维护成本最高 | 禁止：一切以自动生成的 schema 为准 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **生产环境必须关闭**：`docs_url=None, redoc_url=None` 关掉在线文档，避免泄露接口结构与内部字段；对外契约只发 CI 导出的快照（《[项目规划说明](../../../规划/项目规划说明.md#api)》8 节已明确）。
- **文档不是契约的唯一事实源**：在线文档随部署环境走，跨团队对接以 main 流水线的 `swagger.json` 快照为基线，避免"你环境和我环境文档不一样"。
- **接口多了渲染变慢**：BMS 接口量大时 `/docs` 首次加载会慢，属正常现象；用 tags 分组折叠缓解，不要为此拆服务。
- **中文描述要写全**：`summary`、`description`、Pydantic 字段 `description` 用中文写清楚，验收时读文档的人（含外部对接方）全靠它。
- **内部字段别暴露**：调试用字段、废弃字段用 `deprecated` 标注或从响应模型剔除，文档即对外承诺。
- **"Try it out" 会动真实数据**：写接口（POST/PUT/DELETE）在 test 环境调试前确认环境隔离，避免污染联调数据。
- **版本漂移**：FastAPI 升级可能改变 schema 细节（字段顺序、默认值表达），契约快照比对纳入升级验证。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| OpenAPI Initiative 官网 | https://www.openapis.org/ | OpenAPI 标准官方组织 |
| OpenAPI 3.1 规范 | https://spec.openapis.org/oas/3.1 | 规范正文，schema 字段语义以此为准 |
| Swagger UI 官方页 | https://swagger.io/tools/swagger-ui/ | 官方介绍与下载 |
| Swagger UI GitHub | https://github.com/swagger-api/swagger-ui | 源码、issue 与配置项参考 |
| ReDoc GitHub | https://github.com/Redocly/redoc | 源码与主题定制文档 |
| Swagger Editor | https://editor.swagger.io/ | 在线手写/校验 OpenAPI 文档（学习用） |
| FastAPI OpenAPI 文档 | https://fastapi.tiangolo.com/zh/openapi/ | FastAPI 如何生成与定制 OpenAPI schema |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节 | 工程化与质量技术栈（API 文档：Swagger UI / ReDoc 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-eng)》3.3 节 | 选型说明：FastAPI 自动生成，接口联调与验收依据 |
| 《[项目规划说明](../../../规划/项目规划说明.md#api)》8 节 | API 设计规范：生产关闭在线文档、契约快照分发 |
| 《[开发部署规划](../../../规划/开发部署规划.md)》5.3 节 | 本地接口调试入口 `http://localhost:8000/docs` |
| 《[FastAPI 技术介绍](../后端核心/FastAPI技术介绍.md)》 | OpenAPI schema 的产出方与三个内置端点 |
| 《[API 接口规范](../../../规范/API接口规范.md)》 | 统一响应、错误码约定，与文档声明保持一致 |
| 《[TypeScript 技术介绍](../前端/TypeScript技术介绍.md)》 | 前端类型与契约快照（swagger.json）的对应关系 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19