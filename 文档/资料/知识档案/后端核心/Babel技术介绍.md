# Babel 技术介绍

> Python 国际化库 · BMS 开发期消息提取

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › Babel 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Babel** 是 Python 生态里做**国际化（i18n）与本地化（l10n）**的标准库，
提供一整套工具：管理 gettext 消息目录、从代码里提取可翻译字符串、按语言环境格式化日期与数字。
它由 Pallets 组织维护（与 Flask、Jinja2 同门），Django、Pylint 等大量项目都依赖它。

> 注意别和前端那个 **JavaScript Babel**（JS 转译器，babeljs.io）搞混——
> 本项目的 Babel 是 **Python 库**，装的是 `pip install Babel`，两者毫无关系。

- **定位**：BMS 后端国际化的**开发期辅助工具**——提取消息 key 入库，运行时文案走数据库，Babel 不参与运行时翻译。
- **版本**：2.17.0（2.x 系列，持续迭代）。
- **许可**：BSD-3-Clause，OSI 认证开源。
- **语言**：纯 Python，无 C 扩展依赖。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| gettext | 一套跨语言的国际化标准：代码里写「原始文案」（msgid），各语言提供「翻译」（msgstr），运行时按语言取对应文案 |
| msgid / msgstr | gettext 的一对核心字段：msgid 是原文（本项目用英文原文或消息 key），msgstr 是某语言下的译文 |
| .po 文件（Portable Object） | 人类可读的翻译目录，逐条记录 msgid 与每个语言的 msgstr，是翻译协作的载体 |
| .mo 文件（Machine Object） | .po 编译后的二进制格式，程序运行时加载它做翻译查找，体积小、查得快 |
| Locale（语言环境） | 描述「语言 + 地区」的代码，如 `zh_CN`、`en_US`，决定用哪套文案与格式 |
| Babel extract（提取） | 扫描 Python 源码，把 `_()`、`ngettext()` 等调用里的字符串抽出来生成 .pot 模板，是「开发期提取消息 key」的核心动作 |
| CLDR 数据 | 通用语言数据仓库：Babel 内嵌了它的日期、数字、时区、国家名等本地化数据，供 `format_date`、`format_number` 使用 |
| 复数形式（plural） | 不同语言复数规则不同（中文无复数、英语有、俄语更复杂），gettext 用 `ngettext` 处理，Babel 提供各语言的复数公式 |
| 消息 key | 本项目约定：msgid 不直接写中文句子，而用语义化 key（如 `user.form.username`），便于入库管理与多语言对齐 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

BMS 的国际化走「**文案入库、运行时下发**」路线：固定文案统一存 `sys_i18n_message`，
页面在线维护、运行时经接口下发（Redis 缓存），新增语言免发版。
Babel 在这条链路里只承担**开发期**的辅助工作，不参与运行时翻译。

- **开发期提取消息 key**：用 Babel 的 extract 机制扫描后端源码，把 `_()` 调用里的可翻译字符串抽成 .pot 模板，再整理入库 `sys_i18n_message`（见《[项目规划说明](../../../规划/项目规划说明.md#sel-backend)》3.1 节「消息文案入库 + Babel」）。
- **Accept-Language 驱动**：接口层按请求头 `Accept-Language`（或租户/用户 locale）选择文案语言，Babel 提供 `Locale.parse`、`format_date` 等辅助解析与格式化（见《[项目规划说明](../../../规划/项目规划说明.md#sel-backend)》2.1 节「后端国际化」）。
- **数据文案走 i18n 附表**：菜单名、字典 label、邮件模板等业务展示文案不入 Babel 消息目录，而走 `{主表}_i18n` 附表按 locale 存储（见《[项目规划说明](../../../规划/项目规划说明.md#dbrule)》11.1 节「多语言」）。
- **错误码文案分离**：后端只返回错误码 `code`，文案由前端按 `error.xxxxx` key 映射，Babel 负责开发期把这些 key 提取对齐（见《[国际化规范](../../../规范/国际化规范.md#error)》5 节）。
- **日期/数字本地化**：导出、报表、通知里的日期与数字用 Babel 的 CLDR 数据按 locale 格式化，不硬编码格式串。

> 边界提醒：Babel 只做「开发期提取 + 语言数据辅助」，**不做运行时翻译引擎**。
> 运行时文案查找走 `sys_i18n_message` 数据库 + Redis 缓存，前端走 vue-i18n 拉取语言包，
> 两者与 Babel 是「同一套 key、不同载体」的关系。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Babel（选中）** | Python 标准 i18n 库、gettext 生态成熟、CLDR 语言数据全、Pallets 维护稳定；纯 Python 无编译依赖 | 与 Django/Flask 生态通用，提取 + 格式化一体，首选 |
| gettext 命令行工具 | 功能全、跨语言；但需系统安装 GNU gettext 二进制，Windows/容器里折腾，纯 Python 项目不便 | Babel 已把常用 gettext 能力用 Python 实现，免去二进制依赖 |
| 自研 i18n 字典 | 简单场景够用；但无提取工具、无复数/格式化支持、多语言对齐靠手工，规模一上来就乱 | BMS 文案量大且要页面维护，自研成本与风险高 |
| django.utils.translation | 功能强；但绑定 Django 框架，本项目用 FastAPI，引入 Django 不划算 | 框架不匹配，不采用 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **别和 JS Babel 混**：后端 `pip install Babel`（Python i18n）与前端 `npm i @babel/core`（JS 转译）是两码事，依赖清单里别写串。
- **msgid 用 key 不用中文句子**：本项目约定 msgid 用语义化 key（`模块.页面.字段`），不把中文句子当 msgid，否则多语言对齐与入库维护会失控。
- **提取不等于翻译**：Babel extract 只产出 .pot 模板（空 msgstr），真正翻译仍要人工/机器填充，别以为跑了提取就有译文。
- **运行时不靠 Babel 翻译**：BMS 运行时文案走 `sys_i18n_message` 数据库，Babel 只在开发期提取与格式化时出现，别在请求路径里加载 .mo 文件。
- **复数与占位符**：动态文案用 `{var}` 插值、复数用 `ngettext`，不要字符串拼接，保证各语言语序正确（见《[国际化规范](../../../规范/国际化规范.md#format)》7 节）。
- **新增文案补双语言**：新增 key 必须同时补中英文，CI 检查 key 对齐（缺失即失败），避免某语言漏译。
- **locale 代码规范**：统一 `zh_CN`、`en_US` 这类「语言_地区」写法，别混用 `zh`、`cn`，否则语言包匹配不上。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Babel 官方文档 | https://babel.pocoo.org/ | 权威文档：用户指南 + API 参考，Pallets 维护 |
| Babel GitHub | https://github.com/python-babel/babel | 源码、issue 与 release notes |
| Babel @ PyPI | https://pypi.org/project/Babel/ | 安装包与版本历史 |
| Working with Message Catalogs | https://babel.pocoo.org/en/latest/messages.html | 消息目录（.po/.mo）提取与编译详解 |
| Locale Data（CLDR） | https://babel.pocoo.org/en/latest/api.html | 日期/数字/时区本地化 API |
| 《[国际化规范](../../../规范/国际化规范.md)》 | 项目内文档 | BMS 的 key 约定、语言包与文案规则 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-backend)》2.1 / 3.1 节 | 后端国际化选型：消息文案入库 + Babel 开发期提取 |
| 《[项目规划说明](../../../规划/项目规划说明.md#dbrule)》11.1 节 | 数据规范：多语言 i18n 附表约定 |
| 《[国际化规范](../../../规范/国际化规范.md)》 | i18n key 命名、语言包、错误码文案映射 |
| 《[国际化管理（概要设计）](?../../../设计/概要设计/30_概要设计_国际化管理.md》 | 语言清单、语言包维护、用户时区偏好设计 |
| 《[Jinja2 技术介绍](Jinja2技术介绍.md)》 | 邮件/通知模板渲染，多语言内容走 i18n 附表 |
| 《[vue-i18n 技术介绍](../前端/vue-i18n技术介绍.md)》 | 前端语言包运行时拉取，与后端同一套 key |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19