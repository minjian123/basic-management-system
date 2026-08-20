# pyright 技术介绍

> Python 静态类型检查器 · 微软出品 · BMS 类型安全防线

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [工程化与质量](../技术栈知识档案总览.md#eng) › pyright 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**pyright** 是微软出品的 Python 静态类型检查器，
与 TypeScript 编译器同源技术（同样用 TypeScript 编写），
在不运行代码的前提下分析类型错误：参数传错类型、访问不存在的属性、
空值未判断等"运行时才炸"的问题在写代码时就被标红。

- **定位**：BMS 后端严格类型检查工具，配合 Pydantic v2 模型实现类型安全。
- **版本**：快速迭代；VS Code 侧以 Pylance 扩展方式随编辑器分发。
- **许可**：MIT，OSI 认证开源。
- **语言**：TypeScript 实现，作为 npm 包与独立命令行两种形式分发。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 静态类型检查（type check） | 不运行程序、只按源码与类型标注分析：函数实参类型、返回值使用、属性访问是否合法 |
| 类型注解 | PEP 484 语法：`def get_user(user_id: int) -> User:` 把类型写进签名，供检查器与 IDE 使用 |
| 严格度模式 | pyright 提供 basic / standard / strict 三档严格度，strict 要求全部代码显式标注类型、禁隐式 Any |
| Pylance | VS Code 官方 Python 扩展内置 pyright 服务：编辑时实时检查、悬停看类型、自动补全类型提示 |
| pyproject.toml 配置 | `[tool.pyright]` 段集中配置：严格度模式、include/exclude 扫描范围、typeCheckingMode |
| 类型推断 | 没有注解的表达式也能推断类型，配合注解逐步收紧全项目类型覆盖率 |
| Stub 文件（.pyi） | 为无类型标注的第三方库补充"类型说明书"，BMS 为关键依赖缺失类型时可自行补 stub |
| 泛型与协议 | TypeVar / Protocol 等高级标注：描述"任意类型但保持一致"与"鸭子类型"约束 |
| 与 Pydantic 配合 | Pydantic 模型即类型声明：请求/响应模型写错字段名或类型，IDE 与 CI 立即报错 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 作为《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节指定的类型检查工具，采用严格类型检查（strict 模式）作为工程约束（选型依据见《[项目规划说明](../../../规划/项目规划说明.md#sel-eng)》3.3 节）。
- VS Code 原生支持：装 Pylance 即内置 pyright，保存即检查，问题在编辑器里即时标红，无需等 CI。
- 与 Pydantic v2 模型配合：schemas 层的字段声明、FastAPI 接口签名全部有类型，类型错误在 IDE 即时发现（见《[Pydantic 技术介绍](../后端核心/Pydantic技术介绍.md)》）。
- CI 执行：

```bash
uv run pyright              # 全项目类型检查，错误即非零退出
```

- 类型安全贯通前后端：后端 Pydantic schema 与前端 TypeScript 类型经 openapi-typescript 同源生成（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节），pyright 守后端这一侧。
- 与《[ruff](ruff技术介绍.md)》分工：ruff 管风格、pyright 管类型；SQLAlchemy 模型、依赖注入等复杂泛型处按类型标注推进。

## 4. 选型对比 <a id="compare"></a>

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| **pyright（选中）** | TS 实现快、VS Code 原生（Pylance）、strict 模式严格、配置轻 | 新工具，个别第三方库类型支持需补 stub | 与 VS Code 生态、类型安全目标完全契合 |
| mypy | 生态最老、插件多、文档全 | 慢、strict 配置繁琐、与 Pylance 双轨维护 | 性能与上手成本劣势，不采用 |
| pyre（Meta） | 性能好、增量检查 | 安装重、文档少、社区小 | 不适合本项目体量，不采用 |
| pytype（Google） | 推断能力强、自动补标注 | 更新慢、与 Pydantic v2 兼容一般 | 维护活跃度不足，不采用 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **strict 模式约束大**：要求全量显式标注、禁隐式 Any，历史代码/第三方调用会先报一批错，按"先 core 后外围"逐步收敛，不要一次性开全量。
- **Pydantic v2 泛型**：模型、TypeAdapter 等泛型写法有时需 `TypeAlias` 或显式标注辅助，报错先查官方 typing 兼容说明，不要随手 Any 绕过。
- **SQLAlchemy 声明式模型**：Mapped / relationship 动态属性可能误报，用 `mapped_column` 泛型标注或局部配置解决，禁止用 `# type: ignore` 批量豁免。
- **第三方库无类型**：无 stub 的库在 strict 下会报隐式 Any，需要时补 .pyi 或配置局部放宽，并在配置里注明原因。
- **Pylance 与 CLI 一致性**：编辑器实时检查用的也是 pyright，配置只有一份（pyproject.toml），避免"编辑器绿、CI 红"靠版本锁统一。
- **运行时与类型脱节**：类型检查通过不等于运行时正确（动态构造、反射、DB 返回仍可能偏离），类型只是防线之一，测试不能省。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| pyright 官方文档 | https://microsoft.github.io/pyright/ | 功能说明、strict 模式、配置参考 |
| pyright GitHub 仓库 | https://github.com/microsoft/pyright | 源码、issue、FAQ（与 Pylance 的关系） |
| Pylance（VS Code 扩展） | https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance | VS Code 原生接入入口，装这个即内置 pyright |
| Python typing 官方文档 | https://docs.python.org/3/library/typing.html | 类型标注语法标准参考 |
| typing 指南 | https://typing.readthedocs.io/ | 社区维护的类型标注最佳实践 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节 | 技术栈：类型检查 = pyright |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-eng)》3.3 节 | 选型说明：严格类型检查、Pylance 即时反馈 |
| 《[Pydantic 技术介绍](../后端核心/Pydantic技术介绍.md)》 | 请求/响应模型即类型声明，与 pyright 强配合 |
| 《[SQLAlchemy 技术介绍](../后端核心/SQLAlchemy技术介绍.md)》 | ORM 模型的类型标注实践 |
| 《[ruff 技术介绍](ruff技术介绍.md)》 | 风格检查与 pyright 分工配合 |
| 《[uv 技术介绍](uv技术介绍.md)》 | 统一以 `uv run pyright` 执行，配置共用 pyproject.toml |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19