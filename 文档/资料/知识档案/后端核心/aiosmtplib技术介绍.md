# aiosmtplib 技术介绍

> 异步 SMTP 邮件客户端 · BMS 邮件通知发送通道

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › aiosmtplib 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**aiosmtplib** 是一个异步 SMTP（简单邮件传输）客户端库，专门用于在 asyncio 环境里发送邮件。
它把标准库 `smtplib` 的同步逻辑改写成 `async/await` 形式，
让邮件发送不阻塞事件循环，可以和其他异步 I/O（数据库、HTTP）并发进行。

- **定位**：BMS 邮件通知的发送通道，负责把渲染好的邮件真正投递出去（审批提醒、告警、找回密码链接）。
- **版本**：5.x 系列（截至 2026 年最新 5.1.x），要求 Python 3.10+，本项目用 3.14+。
- **许可**：MIT，OSI 认证开源。
- **依赖**：零第三方依赖（zero-deps），只依赖 Python 标准库，安装轻量、无版本冲突风险。
- **作者**：Cole Maclean。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| SMTP 协议 | 简单邮件传输协议：客户端与邮件服务器之间的标准通信协议，负责把一封邮件从发件方投递到收件方服务器 |
| `aiosmtplib.send()` | 核心发送函数：传入一封 `EmailMessage` 和服务器地址，一次性异步发送，最常用入口 |
| `aiosmtplib.Client` | SMTP 客户端类：可复用同一条连接连续发多封，支持 STARTTLS/SSL 与认证，适合批量发送 |
| `EmailMessage` | 标准库 `email.message.EmailMessage`：构造邮件对象，设置发件人、收件人、主题、正文与附件 |
| STARTTLS | 在明文连接上协商升级为加密连接，通常走 587 端口；比纯明文安全，比全程 SSL 灵活 |
| SSL/TLS | 全程加密连接，通常走 465 端口；连接建立即加密 |
| SMTP AUTH（认证） | 服务器要求用户名密码登录（`username`/`password` 参数），绝大多数企业邮箱都要求 |
| 附件 | 通过 `EmailMessage.add_attachment()` 添加文件，自动处理 MIME 编码 |
| 超时控制 | `timeout` 参数控制连接与读写超时，避免邮件服务器无响应时长时间挂起 |
| 零依赖 | 不引入任何第三方包，只依赖标准库，降低依赖冲突与供应链风险 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

aiosmtplib 在 BMS 里只干一件事：**把渲染好的邮件发出去**。
邮件长什么样由 Jinja2 模板决定（见《[Jinja2 技术介绍](Jinja2技术介绍.md)》），
aiosmtplib 负责通过 SMTP 协议投递。

- **审批提醒**：流程走到某审批节点时，给审批人发提醒邮件（配合 SpiffWorkflow 流程引擎，见《[SpiffWorkflow 技术介绍](SpiffWorkflow技术介绍.md)》）。
- **告警邮件**：系统监控告警、任务执行失败等场景的对外通知。
- **找回密码**：自助找回密码时发送含短时效 token 的重置链接（见《[项目规划说明](../../../规划/项目规划说明.html#security)》12 节）。
- **模板在线编辑**：邮件模板入库 `sys_mail_template`，页面在线编辑，保存前做语法校验与沙箱渲染测试；多语言主题/内容存 `sys_mail_template_i18n` 附表（见《[项目规划说明](../../../规划/项目规划说明.html#tables)》6 节）。
- **发送记录**：每封邮件的收件人、主题、模板、状态、错误信息落 `sys_mail_log`，便于排查与审计。
- **异步契合**：接口 `async def` 内直接 `await` 发送，不阻塞事件循环，与 FastAPI 异步栈一致（见《[FastAPI 技术介绍](FastAPI技术介绍.md)》）。

典型用法（渲染 + 发送）：

```python
import aiosmtplib
from email.message import EmailMessage

message = EmailMessage()
message["From"] = "noreply@bms.example.com"
message["To"] = "user@example.com"
message["Subject"] = "审批提醒"
message.set_content("您有一条新的审批待办，请及时处理。")

await aiosmtplib.send(
    message,
    hostname="smtp.example.com",
    port=587,
    start_tls=True,
    username="noreply@bms.example.com",
    password="***",
    timeout=10,
)
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **aiosmtplib（选中）** | 异步、零依赖、与 FastAPI 异步栈天然契合；功能聚焦（只做发送） | 契合本项目异步栈与轻量需求，首选 |
| smtplib（标准库） | 零依赖、无需安装；但**同步阻塞**，在 async 接口中会卡住整个事件循环 | 仅在纯同步脚本中可用，不适合 BMS 异步栈 |
| aiosmtpd | 注意：它是 SMTP **服务器**（接收邮件），不是客户端，方向相反 | 不适用，名字相近易混淆 |
| 第三方邮件服务 SDK（SendGrid/Mailgun 等） | 免维护 SMTP、送达率高；但依赖外部服务、增加成本与网络耦合 | 本项目走自建/企业 SMTP，不引入外部服务 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **别用同步 smtplib**：在 `async def` 接口里调用同步 `smtplib` 会阻塞事件循环，拖垮整个进程，必须用 aiosmtplib。
- **批量发送复用连接**：一次发多封时用 `aiosmtplib.Client` 复用同一条连接，避免每封都重新握手、认证，显著降低开销。
- **端口与加密方式要配对**：587 配 `start_tls=True`，465 配 `use_tls=True`（全程 SSL），配错会握手失败。
- **认证参数别漏**：企业邮箱普遍要求 SMTP AUTH，`username`/`password` 缺失会 535 认证失败；密码走 Secret 管理，不落库不入镜像。
- **设置超时**：`timeout` 参数必设，避免邮件服务器无响应时协程长时间挂起、占满连接池。
- **发送失败要落记录**：捕获异常后写 `sys_mail_log`（状态 + 错误信息），告警类邮件可加重试；不要静默吞掉异常。
- **中文正文编码**：用 `EmailMessage.set_content()` / `add_alternative()` 设置正文，库会自动处理 MIME 编码，避免手写 `Content-Type` 导致乱码。
- **功能边界**：aiosmtplib 只负责「发送」，不含模板渲染、队列、重试策略——模板走 Jinja2，重试与记录由 BMS 业务层实现。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| aiosmtplib 官方文档 | https://aiosmtplib.readthedocs.io/ | 权威文档，含 API 参考与示例 |
| aiosmtplib GitHub | https://github.com/cole/aiosmtplib | 源码、issue 讨论与 changelog |
| PyPI 包页 | https://pypi.org/project/aiosmtplib/ | 版本、依赖与安装信息 |
| Python email 标准库 | https://docs.python.org/zh-cn/3/library/email.html | `EmailMessage` 构造邮件的官方文档（中文版） |
| SMTP 协议 RFC 5321 | https://datatracker.ietf.org/doc/html/rfc5321 | SMTP 协议规范，理解握手与错误码 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html#modules)》5 节 | 功能模块：邮件通知（模板入库、SMTP 发送、发送记录） |
| 《[项目规划说明](../../../规划/项目规划说明.html#tables)》6 节 | 核心数据表：`sys_mail_template`、`sys_mail_log` |
| 《[项目规划说明](../../../规划/项目规划说明.html#security)》12 节 | 认证与安全：找回密码邮件通道 |
| 《[Jinja2 技术介绍](Jinja2技术介绍.md)》 | 邮件/通知模板渲染与沙箱测试 |
| 《[FastAPI 技术介绍](FastAPI技术介绍.md)》 | 异步栈背景，接口内 await 发送 |
| 《[Redis 技术介绍](Redis技术介绍.md)》 | 邮件频控/限流的共享计数后端 |
| 《[日志规范](../../../规范/日志规范.html)》 | 发送记录与错误日志的落库约定 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19