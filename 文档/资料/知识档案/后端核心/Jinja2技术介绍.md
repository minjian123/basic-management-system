# Jinja2 技术介绍

> Python 模板引擎 · BMS 邮件/通知模板与简单页面输出

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › Jinja2 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Jinja2** 是 Python 生态最主流的模板引擎，由 Pallets 项目维护（Flask 的模板引擎即它）。
它把「模板文本 + 运行时变量」渲染成最终内容，语法简洁、表达力强，
内置**自动转义（防 XSS）**与**沙箱模式**，特别适合渲染用户可编辑的模板。

- **定位**：BMS 的服务端模板渲染——邮件/通知模板（在线编辑）、简单 HTML 页面输出（导出预览）。
- **版本**：3.1.x 系列（截至 2026 年最新 3.1.x，3.2.0 开发中），要求 Python 3.10+，本项目用 3.14+。
- **许可**：BSD-3-Clause，OSI 认证开源，商用无限制。
- **依赖**：依赖 `MarkupSafe`（安全转义）。
- **维护**：Pallets 项目（Flask、Jinja、Click 等作者团队）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| 模板（Template） | 含变量、表达式、标签的文本，渲染时填入数据得到最终内容 |
| 变量 `{{ var }}` | 输出上下文里的值，如 `{{ user.name }}` |
| 表达式 `{{ ... }}` | 可写运算与属性访问，如 `{{ 1 + 1 }}`、`{{ items|length }}` |
| 标签 `{% ... %}` | 控制结构：`{% if %}`、`{% for %}`、`{% set %}` 等 |
| 过滤器 `\|` | 对值做转换：`\| upper`、`\| safe`、`\| date`、自定义过滤器等 |
| 自动转义（Autoescape） | 默认把输出值做 HTML 转义，防 XSS；BMS 渲染 HTML 类模板时务必开启 |
| 沙箱（Sandbox） | `SandboxedEnvironment`：限制模板能访问的属性/方法，防止用户模板执行危险代码 |
| 模板继承 `{% extends %}` | 子模板继承父模板的公共结构，只覆写差异块，减少重复 |
| 宏 `{% macro %}` | 定义可复用的模板片段，类似模板里的函数 |
| 上下文（Context） | 渲染时传入的变量字典，模板里 `{{ }}` 取的就是它 |
| 语法校验 | `env.parse()` 编译模板，可在保存前检查语法错误，BMS 邮件模板保存前用它校验 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

Jinja2 在 BMS 里负责**服务端模板渲染**，把「模板 + 数据」变成最终的邮件正文、通知文案或简单 HTML 页面。
注意边界：BMS 页面主体仍是前后端分离（Vue 3），Jinja2 只用于邮件/通知这类「服务端生成内容」和少量简单 HTML 输出。

- **邮件/通知模板**：模板入库 `sys_mail_template`，页面在线编辑；保存前做**语法校验**（`env.parse()`）与**沙箱渲染测试**（用样例数据试渲染，确认不报错、不越权）（见《[项目规划说明](../../../规划/项目规划说明.html#sel-backend)》3.1 节、5 节「邮件通知」）。
- **多语言内容**：邮件主题/内容的多语言走 `sys_mail_template_i18n` 附表，运行时按收件人 `locale` 渲染（见《[项目规划说明](../../../规划/项目规划说明.html#dbrule)》11.1 节、《[国际化规范](../../../规范/国际化规范.html)》）。
- **简单 HTML 页面输出**：如导出预览、打印视图等轻量 HTML，由 Jinja2 渲染，不引入前端构建。
- **与邮件发送衔接**：渲染出的正文交给 aiosmtplib 发送（见《[aiosmtplib 技术介绍](aiosmtplib技术介绍.md)》）。

典型渲染代码（沙箱 + 自动转义）：

```python
from jinja2.sandbox import SandboxedEnvironment

env = SandboxedEnvironment(autoescape=True)

# 保存前语法校验：模板有语法错误会抛 TemplateSyntaxError
env.parse("尊敬的 {{ user.name }}：\n您有一条新的审批待办，请及时处理。")

# 渲染邮件正文
template = env.from_string("尊敬的 {{ user.name }}：\n您有一条新的审批待办，请及时处理。")
body = template.render(user={"name": "张三"})
# -> "尊敬的 张三：\n您有一条新的审批待办，请及时处理。"
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Jinja2（选中）** | 最成熟、沙箱 + 自动转义、Pallets 维护、生态大 | 契合邮件模板安全渲染需求，首选 |
| Mako | 性能好；但语法偏「代码式」、沙箱能力弱、社区较小 | 安全沙箱不如 Jinja2，用户在线编辑场景风险高 |
| Django Template | 安全、简单；但**绑定 Django 框架**，BMS 用 FastAPI 不引入 Django | 框架耦合，不契合 |
| 字符串拼接 / f-string | 最简单；但**无转义、无沙箱**，用户模板易致 XSS 与代码注入 | 不安全，不适合用户可编辑模板 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **用户模板必须沙箱**：邮件模板由页面在线编辑，属于「用户可控内容」，渲染必须用 `SandboxedEnvironment`，防止模板里夹带危险代码执行。
- **自动转义别关**：渲染 HTML 类内容时保持 `autoescape=True` 防 XSS；确需输出原始 HTML 的片段才用 `| safe`，且只用于可信内容。
- **保存前做语法校验**：用 `env.parse()` 检查模板语法，失败给出明确错误位置，避免「存了个坏模板、发送时才报错」。
- **沙箱渲染测试**：保存后用样例数据试渲染一次，确认不抛异常、变量齐全、不越权访问属性。
- **多语言走 i18n 附表**：主题/内容多语言存 `sys_mail_template_i18n`，按收件人 `locale` 取，别在模板里硬编码语言。
- **别拿它渲染主页面**：BMS 页面主体是前后端分离（Vue 3），Jinja2 只用于邮件/通知与少量简单 HTML 输出，别用它做 SPA 页面。
- **依赖 MarkupSafe**：需安装 `MarkupSafe`，注意其版本与 Python 3.14 的兼容。
- **模板缓存**：频繁渲染的模板可编译缓存（`env.cache`），避免每次重新解析，提升性能。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Jinja2 官方文档 | https://jinja.palletsprojects.com/ | 权威文档，含模板设计、过滤器、沙箱 |
| Jinja2 GitHub | https://github.com/pallets/jinja | 源码、issue 与 changelog |
| PyPI 包页 | https://pypi.org/project/Jinja2/ | 版本、依赖与安装信息 |
| Jinja2 沙箱文档 | https://jinja.palletsprojects.com/en/stable/sandboxed/ | `SandboxedEnvironment` 用法与安全边界 |
| MarkupSafe | https://github.com/pallets/markupsafe | 安全转义底层库 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-backend)》3.1 节 | 选型说明：Jinja2 条目（邮件模板入库、在线编辑、沙箱） |
| 《[项目规划说明](../../../规划/项目规划说明.html#modules)》5 节 | 功能模块：邮件通知（模板入库、语法校验、i18n） |
| 《[项目规划说明](../../../规划/项目规划说明.html#tables)》6 节 | 核心数据表：`sys_mail_template`、`sys_mail_template_i18n` |
| 《[aiosmtplib 技术介绍](aiosmtplib技术介绍.md)》 | 渲染后的邮件正文发送 |
| 《[国际化规范](../../../规范/国际化规范.html)》 | 多语言内容（i18n 附表）约定 |
| 《[安全开发规范](../../../规范/安全开发规范.html)》 | XSS 防护与模板沙箱安全 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19