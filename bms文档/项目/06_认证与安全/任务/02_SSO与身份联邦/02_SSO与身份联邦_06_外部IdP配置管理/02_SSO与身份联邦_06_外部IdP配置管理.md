# 06 外部 IdP 配置管理

> 认证与安全 · 02 SSO 与身份联邦 · 子任务 06（需求 02-6）

[文档首页](../../../../../文档首页.md) › [02 SSO 与身份联邦](../02_SSO与身份联邦.md) › 06 外部 IdP 配置管理　|　[← 父任务](../02_SSO与身份联邦.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 06 |
| 父任务 | [02 SSO 与身份联邦](../02_SSO与身份联邦.md) |
| 对应需求 | [02-6](../../../需求/02_需求_SSO与身份联邦.md#r02-6) |
| 工时（重估） | 12h |
| 依赖 | 02_01（SSO 链路）；阶段二 `02-3-11`（配置基座）、限流基座 |
| 负责人 | minjian |
| 状态 | 未开始 |
| 完成日期 | — |

> **前置契约（已交付 · 02_01，2026-09-27）**：`sys_identity_provider` 表 + ORM（`SysIdentityProvider`）+ `identity:tenant` 迁移（0002）+ 读路径（`IdentityProviderRepository.list_enabled` / `get_by_key`）已交付，本任务在其上补 CRUD / 启停 / 排序管理接口；`ProviderRegistry` / `IdentityProviderSpec` / `resolve_secret_ref`（`env:` 已实现、`secret:` 预留抛 `ConfigError`）已交付，连通性测试复用 `ProviderRegistry` 实例化；登录页入口清单 `GET /auth/sso/providers` 已按 `enabled` + `sort` 取数且永不返回 `config`。

## 2. 任务内容 <a id="content"></a>

1. **配置载体**：`sys_identity_provider` 表文件先设计后落库（租户库）——协议类型（OIDC / CAS / 企微 / 钉钉）、`idp_key`、端点与客户端凭据（**密钥字段只存引用 / 加密值，不明文入库**）、状态、排序。
2. **管理接口**：CRUD + 启停 + **连通性测试**（Discovery / 元数据探测或试授权），权限码 `idp:manage`（RBAC 前平台超管口径）；配置变更写操作审计占位。
3. **登录页数据**：为 `GET /auth/sso/providers` 提供按租户 / 按状态的入口清单（凭据字段不出现在任何响应）。
4. **安全口径**：凭据字段永久掩码（经域 04 脱敏基座）；连通性测试限流防滥用；URL 协议 / 白名单校验（《[安全开发规范](../../../../../规范/安全开发规范.md)》SSRF 要求）。
5. **用例**：CRUD / 启停 / 连通性成功与失败 / 凭据掩码 / 限流分支。

## 3. 完成标准 <a id="accept"></a>

租户级 IdP 配置 CRUD / 启停 / 连通性测试可用；凭据字段任何响应不返明文（用例断言）；登录页入口清单按配置正确返回；错误配置给出明确提示；`sys_identity_provider` 表文件 ↔ 登记 ↔ 迁移零漂移。

## 4. 参考文档 <a id="ref"></a>

- [需求 02-6](../../../需求/02_需求_SSO与身份联邦.md#r02-6)
- 《[概要设计 · 身份认证SSO](../../../../../设计/概要设计/26_概要设计_身份认证SSO.md)》
- 《[安全开发规范](../../../../../规范/安全开发规范.md)》、《[数据库开发规范](../../../../../规范/数据库开发规范.md)》

> **前置契约（已交付 · 02_02，2026-09-27）**：JIT 已交付并在 IdP 行 `config` 消费两个新增键——`jit_enabled`（bool，行优先回落全局 `[sso].jit_enabled`）与 `allowed_email_domains`（string 数组，邮箱域名白名单）；02_06 管理面需支持这两键的写入校验（类型 / 取值）与连通性测试覆盖，凭据字段掩码与 SSRF 校验口径不变。

> **前置契约（已交付 · 02_03，2026-09-27）**：CAS 行配置新增平铺键 `cas_server_url`（必填）/ `cas_login_path`（缺省 `/login`）/ `cas_service_validate_path`（缺省 `/p3/serviceValidate`）/ `attribute_map`（对象，属性映射覆盖）；`IdentityProviderRegistry.build` 已支持 `type="cas"` 分派。02_06 管理面需支持这几键的写入校验（`cas_server_url` 必填、`attribute_map` 对象类型）与连通性测试（复用 `serviceValidate`）；CAS 以服务注册校验身份，**不需要客户端密钥**。

> **前置契约（已交付 · 02_04，2026-09-27）**：企微 / 钉钉行配置新增平铺键——企业微信 `corp_id`（必填）/ `agent_id`（必填）/ `secret_ref`（必填，`env:` 引用）/ `mode`（`qr`/`oauth`，缺省 `qr`）/ `login_url` / `oauth_url` / `api_base_url` / `scope` / `login_type`；钉钉 `client_id`（必填）/ `client_secret_ref`（必填）/ `login_url` / `api_base_url` / `scope` / `prompt`；`IdentityProviderRegistry.build` 已支持 `type="wecom"` / `"dingtalk"` 分派，必填缺失 / `mode` 非法抛 `WecomConfigError`（20057）/ `DingtalkConfigError`（20060）。02_06 管理面需支持这几键的写入校验（必填、`mode` 枚举）与连通性测试（企微 `gettoken`、钉钉 `userAccessToken` 探活；密钥字段掩码口径同 OIDC / CAS）。

> 交付物：详细设计、实施记录、测试记录（随任务开工建立，落本目录 `设计/`、`实施/`、`测试/`）。
