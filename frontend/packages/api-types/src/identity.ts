/**
 * 服务契约生成类型：identity
 *
 * 本文件由 `frontend/packages/api-types/scripts/generate.mjs` 生成，请勿手工修改。
 * 来源：deploy/contracts/identity.json（服务契约快照，唯一事实源）。
 * 重新生成：pnpm run api-types:gen
 */
export interface paths {
    "/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Root
         * @description 应用信息。
         *
         *     Returns:
         *         ApiResponse: {code, message, data:{name, version}}。
         */
        get: operations["root__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/.well-known/jwks.json": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Jwks
         * @description 取公开 JWKS 文档（服务令牌 + 用户令牌公钥合并）。
         *
         *     Args:
         *         request: 请求对象（取应用装配的服务 / 用户令牌签发者）。
         *
         *     Returns:
         *         dict[str, object]: 标准 JWKS 文档（只含公钥）。
         *
         *     Raises:
         *         HTTPException: 两域 kid 冲突 / 文档非法（503，fail-closed）。
         */
        get: operations["get_jwks__well_known_jwks_json_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/forgot-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Forgot Password
         * @description 发起找回：验证码 / 限流 / 重置目标解析 → 生成令牌并占位发送（恒 `{sent: true}`）。
         *
         *     Args:
         *         request: 请求对象（取应用配置与引擎注册表）。
         *         req: 发起找回请求（标识 / 验证码 / 租户）。
         *         captcha: 验证码基座。
         *         limiter: 限流基座。
         *         client: 服务间调用客户端。
         *         state_store: 流程状态存储。
         *         notifier: 通知基座。
         *         security: 会话安全原语。
         *         store: 会话标记存储。
         *         publisher: 实时推送器。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为发起结果（`PasswordForgotResult`）。
         */
        post: operations["forgot_password_api_v1_auth_forgot_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/introspect": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Introspect
         * @description 网关认证子请求：公开路径放行；受保护路径校验用户 JWT 并换发网关服务 JWT。
         *
         *     Args:
         *         request: 请求对象（取应用配置）。
         *         verifier: 统一校验器（按 `aud=api` 校验用户 JWT）。
         *         issuer: 服务 JWT 签发者（换发网关服务 JWT）。
         *         authorization: 客户端 `Authorization` 头（网关经 `request_headers` 转发）。
         *         forwarded_uri: 原始请求 URI（网关 `forward-auth` 添加的 `X-Forwarded-Uri`）。
         *
         *     Returns:
         *         Response: 200（公开路径 / 校验通过，含身份头与网关服务 JWT）或 401 / 503。
         */
        get: operations["introspect_api_v1_auth_introspect_get"];
        put?: never;
        /**
         * Introspect
         * @description 网关认证子请求：公开路径放行；受保护路径校验用户 JWT 并换发网关服务 JWT。
         *
         *     Args:
         *         request: 请求对象（取应用配置）。
         *         verifier: 统一校验器（按 `aud=api` 校验用户 JWT）。
         *         issuer: 服务 JWT 签发者（换发网关服务 JWT）。
         *         authorization: 客户端 `Authorization` 头（网关经 `request_headers` 转发）。
         *         forwarded_uri: 原始请求 URI（网关 `forward-auth` 添加的 `X-Forwarded-Uri`）。
         *
         *     Returns:
         *         Response: 200（公开路径 / 校验通过，含身份头与网关服务 JWT）或 401 / 503。
         */
        post: operations["introspect_api_v1_auth_introspect_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Login
         * @description 本地账号密码登录：验证码 / 限流 / org 凭据校验 → 签发双 token 并建会话。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 登录请求。
         *         response: 响应对象（下发 refresh cookie）。
         *         issuer: 用户双 token 签发者。
         *         security: 会话安全原语。
         *         store: 会话标记存储。
         *         captcha: 验证码基座。
         *         limiter: 限流基座。
         *         client: 服务间调用客户端。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为登录结果（`LoginResult`）。
         */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Logout
         * @description 登出（幂等）：refresh 入黑名单 + 会话撤销 + 删标记；清 cookie。
         *
         *     Args:
         *         request: 请求对象（读 refresh cookie）。
         *         response: 响应对象（清 refresh cookie）。
         *         issuer: 用户双 token 签发者。
         *         security: 会话安全原语。
         *         store: 会话标记存储。
         *         captcha: 验证码基座（未使用，保持服务构造一致）。
         *         limiter: 限流基座（未使用）。
         *         client: 服务间调用客户端（未使用）。
         *         tenant_ctx: 请求上下文租户。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为 null）。
         */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Refresh
         * @description 静默刷新：校验 refresh 并轮换签发新双 token（同会话 id）。
         *
         *     Args:
         *         request: 请求对象（读 refresh cookie）。
         *         response: 响应对象（重设 refresh cookie）。
         *         issuer: 用户双 token 签发者。
         *         security: 会话安全原语。
         *         store: 会话标记存储。
         *         captcha: 验证码基座（未使用，保持服务构造一致）。
         *         limiter: 限流基座（未使用）。
         *         client: 服务间调用客户端（未使用）。
         *         tenant_ctx: 请求上下文租户。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为刷新结果（`RefreshResult`）。
         *
         *     Raises:
         *         AuthError: 缺少 refresh cookie / 租户上下文（20001/401）。
         */
        post: operations["refresh_api_v1_auth_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/reset-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reset Password
         * @description 提交重置：一次性消费令牌 → 改密（强制过策略）→ 该账号全部会话失效。
         *
         *     Args:
         *         request: 请求对象（取应用配置与引擎注册表）。
         *         req: 提交重置请求（令牌 / 新口令 / 租户）。
         *         captcha: 验证码基座（未使用，保持服务构造一致）。
         *         limiter: 限流基座（未使用）。
         *         client: 服务间调用客户端。
         *         state_store: 流程状态存储（一次性消费令牌）。
         *         notifier: 通知基座（未使用）。
         *         security: 会话安全原语。
         *         store: 会话标记存储。
         *         publisher: 实时推送器。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为重置结果（`PasswordResetResult`）。
         */
        post: operations["reset_password_api_v1_auth_reset_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/sso/providers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Providers
         * @description 可用 IdP 入口清单（仅 `enabled`；无启用 IdP 返回空列表）。
         *
         *     Args:
         *         request: 请求对象。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *         state_store: 流程状态存储（保持服务构造一致）。
         *         limiter: 限流基座（保持服务构造一致）。
         *         lock: 分布式锁（保持服务构造一致）。
         *         outbox_store: 事务性发件箱（保持服务构造一致）。
         *         client: 服务间调用客户端（保持服务构造一致）。
         *         tenant_code: 租户编码（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `SsoProviderList`。
         */
        get: operations["providers_api_v1_auth_sso_providers_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/sso/{idp_key}/authorize": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Authorize
         * @description 生成流程状态并 `302` 到外部授权端点。
         *
         *     Args:
         *         request: 请求对象。
         *         idp_key: 租户内 IdP 标识（路由参数）。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *         state_store: 流程状态存储。
         *         limiter: 限流基座。
         *         lock: 分布式锁（保持服务构造一致）。
         *         outbox_store: 事务性发件箱（保持服务构造一致）。
         *         client: 服务间调用客户端。
         *         tenant_code: 租户编码（可选）。
         *
         *     Returns:
         *         Response: `302` 跳转外部授权端点。
         *
         *     Raises:
         *         SsoProviderNotFoundError: IdP 不存在或已停用（20051/404）。
         *         SsoProviderUnavailableError: IdP 配置缺失 / 发现失败（20053/503）。
         *         RateLimitError: 限流命中（10005/429）。
         */
        get: operations["authorize_api_v1_auth_sso__idp_key__authorize_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/sso/{idp_key}/authorize-url": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Authorize Url
         * @description 取外部授权 URL（JSON 形态；供前端渲染二维码 / 初始化平台内嵌登录组件）。
         *
         *     Args:
         *         request: 请求对象。
         *         idp_key: 租户内 IdP 标识（路由参数）。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *         state_store: 流程状态存储。
         *         limiter: 限流基座。
         *         lock: 分布式锁（保持服务构造一致）。
         *         outbox_store: 事务性发件箱（保持服务构造一致）。
         *         client: 服务间调用客户端。
         *         tenant_code: 租户编码（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `SsoAuthorizeInfo`（授权 URL / 流程状态 / 有效期）。
         *
         *     Raises:
         *         SsoProviderNotFoundError: IdP 不存在或已停用（20051/404）。
         *         SsoProviderUnavailableError: IdP 配置缺失 / 发现失败（20053/503）。
         *         EnterpriseIdpError: 企微 / 钉钉专用失败（20057~20062）。
         *         RateLimitError: 限流命中（10005/429）。
         */
        get: operations["authorize_url_api_v1_auth_sso__idp_key__authorize_url_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/sso/{idp_key}/callback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Callback
         * @description 回调闭环：`state` 一次性消费 → 换码 / 票据校验 → 映射（未命中 JIT 建号）→ 签发会话 → `302` 前端。
         *
         *     Args:
         *         request: 请求对象。
         *         idp_key: 回调路径中的 IdP 标识。
         *         tenant_ctx: 请求上下文租户（有则与 `state` 记录交叉校验）。
         *         tenant_source: 租户源（按 `state` 记录租户定位库键）。
         *         state_store: 流程状态存储。
         *         limiter: 限流基座。
         *         lock: 分布式锁（JIT 临界区）。
         *         outbox_store: 事务性发件箱（JIT 事件）。
         *         client: 服务间调用客户端。
         *         issuer: 用户双 token 签发者。
         *         security: 会话安全原语。
         *         store: 会话标记存储。
         *         publisher: 实时推送器。
         *         state: IdP 回传流程状态。
         *         code: IdP 回传授权码（OIDC）。
         *         ticket: IdP 回传服务票据（CAS；与 `code` 归一）。
         *         error: IdP 回传错误。
         *
         *     Returns:
         *         Response: 成功 `302 {success_redirect}?tenant_code=…` + refresh cookie（未配置回退 200 JSON）；
         *         失败 `302 {failure_redirect}?error=&message=`（未配置抛 `BizError`）。
         */
        get: operations["callback_api_v1_auth_sso__idp_key__callback_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/captcha/challenges": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Challenge
         * @description 生成验证码挑战（图形 / 滑块）。
         *
         *     Args:
         *         captcha: 验证码基座。
         *         req: 出题请求。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为挑战（`CaptchaChallengeResponse`）。
         */
        post: operations["create_challenge_api_v1_captcha_challenges_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/captcha/scenes/{scene}/policy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Scene Policy
         * @description 取场景策略（是否强制 / 连续失败阈值 / 有效期 / 重发冷却）。
         *
         *     Args:
         *         captcha: 验证码基座。
         *         scene: 使用场景。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为场景策略（`CaptchaPolicyResponse`）。
         */
        get: operations["get_scene_policy_api_v1_captcha_scenes__scene__policy_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/captcha/sms": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send Sms Code
         * @description 发送短信验证码（占位不真发；目标手机号脱敏后回显）。
         *
         *     Args:
         *         captcha: 验证码基座。
         *         req: 短信发送请求。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为挑战（`CaptchaChallengeResponse`，`target` 为脱敏手机号）。
         */
        post: operations["send_sms_code_api_v1_captcha_sms_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/captcha/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Verify Captcha
         * @description 校验验证码凭证（失败以业务错误码 20101 表达）。
         *
         *     Args:
         *         captcha: 验证码基座。
         *         req: 凭证校验请求。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为校验结果（`CaptchaVerifyResponse`）。
         */
        post: operations["verify_captcha_api_v1_captcha_verify_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/idp/providers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Providers
         * @description IdP 配置分页列表（可筛选 status / type / name）。
         *
         *     Args:
         *         request: 请求对象。
         *         tenant_ctx: 请求上下文租户。
         *         audit: 审计捕获占位。
         *         limiter: 限流基座。
         *         query: 分页请求。
         *         status: 状态过滤（可选）。
         *         type: 协议类型过滤（可选）。
         *         name: 名称模糊过滤（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页 IdP 项。
         */
        get: operations["list_providers_api_v1_idp_providers_get"];
        put?: never;
        /**
         * Create Provider
         * @description 新建 IdP 配置。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 新建请求。
         *         tenant_ctx: 请求上下文租户。
         *         auth: 登录态身份（操作者）。
         *         audit: 审计捕获占位。
         *         limiter: 限流基座（保持服务构造一致）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为新建项（config 脱敏）。
         */
        post: operations["create_provider_api_v1_idp_providers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/idp/providers/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Test Draft Provider
         * @description 草稿连通性测试（不落库）。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 草稿测试请求。
         *         tenant_ctx: 请求上下文租户。
         *         auth: 登录态身份（操作者）。
         *         audit: 审计捕获占位（保持服务构造一致）。
         *         limiter: 限流基座。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为测试结果（可达）。
         *
         *     Raises:
         *         IdpConfigInvalidError: 配置非法（20064/400）。
         *         IdpTestFailedError: 不可达 / 不可探测（20066/502）。
         *         RateLimitError: 限流命中（10005/429）。
         */
        post: operations["test_draft_provider_api_v1_idp_providers_test_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/idp/providers/{provider_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Provider
         * @description IdP 配置详情。
         *
         *     Args:
         *         request: 请求对象。
         *         provider_id: 主键。
         *         tenant_ctx: 请求上下文租户。
         *         audit: 审计捕获占位。
         *         limiter: 限流基座。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为详情项（config 脱敏）。
         */
        get: operations["get_provider_api_v1_idp_providers__provider_id__get"];
        /**
         * Update Provider
         * @description 修改 IdP 配置（`type` / `idp_key` 不可改）。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 修改请求。
         *         provider_id: 主键。
         *         tenant_ctx: 请求上下文租户。
         *         auth: 登录态身份（操作者）。
         *         audit: 审计捕获占位。
         *         limiter: 限流基座。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后项（config 脱敏）。
         */
        put: operations["update_provider_api_v1_idp_providers__provider_id__put"];
        post?: never;
        /**
         * Delete Provider
         * @description 软删除 IdP 配置。
         *
         *     Args:
         *         request: 请求对象。
         *         provider_id: 主键。
         *         tenant_ctx: 请求上下文租户。
         *         auth: 登录态身份（操作者）。
         *         audit: 审计捕获占位。
         *         limiter: 限流基座。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为空对象。
         */
        delete: operations["delete_provider_api_v1_idp_providers__provider_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/idp/providers/{provider_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Set Provider Status
         * @description 启停 IdP 配置。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 启停请求。
         *         provider_id: 主键。
         *         tenant_ctx: 请求上下文租户。
         *         auth: 登录态身份（操作者）。
         *         audit: 审计捕获占位。
         *         limiter: 限流基座。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后项。
         */
        post: operations["set_provider_status_api_v1_idp_providers__provider_id__status_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/idp/providers/{provider_id}/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Test Saved Provider
         * @description 已保存行连通性测试。
         *
         *     Args:
         *         request: 请求对象。
         *         provider_id: 主键。
         *         tenant_ctx: 请求上下文租户。
         *         auth: 登录态身份（操作者）。
         *         audit: 审计捕获占位。
         *         limiter: 限流基座。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为测试结果（可达）。
         *
         *     Raises:
         *         IdpNotFoundError: 不存在（20063/404）。
         *         IdpConfigInvalidError: 存量配置非法（20064/400）。
         *         IdpTestFailedError: 不可达 / 不可探测（20066/502）。
         *         RateLimitError: 限流命中（10005/429）。
         */
        get: operations["test_saved_provider_api_v1_idp_providers__provider_id__test_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/oidc/.well-known/openid-configuration": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Openid Configuration
         * @description OIDC Discovery 文档（标准 JSON，无统一响应包体）。
         *
         *     Args:
         *         request: 请求对象。
         *         provider: OIDC Provider。
         *         state_store: 流程状态存储（保持服务构造一致）。
         *         client: 服务间调用客户端（保持服务构造一致）。
         *         hasher: 口令哈希（保持服务构造一致）。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *         tenant_code: 租户编码（可选）。
         *
         *     Returns:
         *         JSONResponse: Discovery 文档。
         */
        get: operations["openid_configuration_api_v1_oidc__well_known_openid_configuration_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/oidc/authorize": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Authorize
         * @description 授权端点：校验客户端并签发一次性授权码，`302` 回跳 `redirect_uri`。
         *
         *     Args:
         *         request: 请求对象。
         *         provider: OIDC Provider。
         *         state_store: 流程状态存储（授权码一次性）。
         *         client: 服务间调用客户端（保持服务构造一致）。
         *         hasher: 口令哈希（保持服务构造一致）。
         *         auth: 可选登录态。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *         response_type: 响应类型（须为 `code`）。
         *         client_id: 客户端标识。
         *         redirect_uri: 回跳地址。
         *         scope: 申请 scope。
         *         state: 透传状态。
         *         nonce: 透传 nonce。
         *         code_challenge: PKCE 挑战。
         *         code_challenge_method: PKCE 方法。
         *         tenant_code: 租户编码（可选）。
         *
         *     Returns:
         *         Response: `302` 回跳地址。
         *
         *     Raises:
         *         OidcAccessDeniedError: 未登录且未配登录页（80106/401）。
         *         OidcInvalidRequestError: 客户端未知 / `redirect_uri` 不可信（80101/400）。
         */
        get: operations["authorize_api_v1_oidc_authorize_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/oidc/jwks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Jwks
         * @description IdP 公开 JWKS（标准 JSON，无统一响应包体）。
         *
         *     Args:
         *         request: 请求对象。
         *         provider: OIDC Provider。
         *         state_store: 流程状态存储（保持服务构造一致）。
         *         client: 服务间调用客户端（保持服务构造一致）。
         *         hasher: 口令哈希（保持服务构造一致）。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *         tenant_code: 租户编码（可选）。
         *
         *     Returns:
         *         JSONResponse: JWKS 文档。
         */
        get: operations["jwks_api_v1_oidc_jwks_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/oidc/token": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Token
         * @description 令牌端点：客户端认证 + 授权码换 ID Token / access token（标准 OAuth2 JSON）。
         *
         *     Args:
         *         request: 请求对象。
         *         provider: OIDC Provider。
         *         state_store: 流程状态存储（授权码一次性消费）。
         *         client: 服务间调用客户端（org 用户概要）。
         *         hasher: 口令哈希（客户端密钥比对）。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *         tenant_code: 租户编码（可选）。
         *
         *     Returns:
         *         Response: 标准令牌 JSON 或标准错误 JSON。
         */
        post: operations["token_api_v1_oidc_token_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/oidc/userinfo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Userinfo
         * @description 用户信息端点：Bearer access token → 标准 userinfo JSON。
         *
         *     Args:
         *         request: 请求对象。
         *         provider: OIDC Provider。
         *         state_store: 流程状态存储（保持服务构造一致）。
         *         client: 服务间调用客户端（org 用户概要）。
         *         hasher: 口令哈希（保持服务构造一致）。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *         tenant_code: 租户编码（可选）。
         *
         *     Returns:
         *         Response: 标准 userinfo JSON 或 401。
         */
        get: operations["userinfo_api_v1_oidc_userinfo_get"];
        put?: never;
        /**
         * Userinfo
         * @description 用户信息端点：Bearer access token → 标准 userinfo JSON。
         *
         *     Args:
         *         request: 请求对象。
         *         provider: OIDC Provider。
         *         state_store: 流程状态存储（保持服务构造一致）。
         *         client: 服务间调用客户端（org 用户概要）。
         *         hasher: 口令哈希（保持服务构造一致）。
         *         tenant_ctx: 请求上下文租户。
         *         tenant_source: 租户源。
         *         tenant_code: 租户编码（可选）。
         *
         *     Returns:
         *         Response: 标准 userinfo JSON 或 401。
         */
        post: operations["userinfo_api_v1_oidc_userinfo_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/open/clients": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Clients
         * @description 客户端分页列表（可选 status / name 筛选）。
         *
         *     Args:
         *         request: 请求对象。
         *         tenant_ctx: 请求上下文租户。
         *         hasher: 口令哈希实现。
         *         audit: 审计捕获占位。
         *         query: 分页请求。
         *         status: 状态过滤（可选）。
         *         name: 名称模糊过滤（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页客户端。
         */
        get: operations["list_clients_api_v1_open_clients_get"];
        put?: never;
        /**
         * Create Client
         * @description 注册客户端（返回 `client_id` 与明文 secret 一次）。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 注册请求。
         *         tenant_ctx: 请求上下文租户。
         *         hasher: 口令哈希实现。
         *         audit: 审计捕获占位。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为凭据（`ClientCreated`）。
         */
        post: operations["create_client_api_v1_open_clients_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/open/clients/{client_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Client
         * @description 客户端详情。
         *
         *     Args:
         *         request: 请求对象。
         *         client_id: 客户端主键。
         *         tenant_ctx: 请求上下文租户。
         *         hasher: 口令哈希实现。
         *         audit: 审计捕获占位。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为客户端项。
         */
        get: operations["get_client_api_v1_open_clients__client_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/open/clients/{client_id}/reset-secret": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reset Client Secret
         * @description 重置客户端密钥（新明文仅本次返回）。
         *
         *     Args:
         *         request: 请求对象。
         *         client_id: 客户端主键。
         *         tenant_ctx: 请求上下文租户。
         *         hasher: 口令哈希实现。
         *         audit: 审计捕获占位。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为新凭据（`ClientSecretReset`）。
         */
        post: operations["reset_client_secret_api_v1_open_clients__client_id__reset_secret_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/open/clients/{client_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Set Client Status
         * @description 启停客户端。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 启停请求。
         *         client_id: 客户端主键。
         *         tenant_ctx: 请求上下文租户。
         *         hasher: 口令哈希实现。
         *         audit: 审计捕获占位。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后的客户端项。
         */
        post: operations["set_client_status_api_v1_open_clients__client_id__status_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Sessions
         * @description 在线会话列表（仅未撤销未过期；筛选 + 分页）。
         *
         *     Args:
         *         request: 请求对象（取引擎注册表与会话工厂）。
         *         query: 分页与排序参数。
         *         security: 会话安全原语。
         *         store: 会话标记存储。
         *         publisher: 实时推送器。
         *         tenant_ctx: 请求上下文租户。
         *         user_id: 用户 ID（精确）。
         *         device: 设备标识（模糊）。
         *         ip: 登录 IP（模糊）。
         *         login_from: 登录时间下界（UTC）。
         *         login_to: 登录时间上界（UTC）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页会话列表。
         */
        get: operations["list_sessions_api_v1_sessions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Session
         * @description 会话详情（含已撤销会话，供 revoked 状态查询）。
         *
         *     Args:
         *         request: 请求对象。
         *         session_id: 会话 id。
         *         security: 会话安全原语。
         *         store: 会话标记存储。
         *         publisher: 实时推送器。
         *         tenant_ctx: 请求上下文租户。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为会话行。
         */
        get: operations["get_session_api_v1_sessions__session_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sessions/{session_id}/kick": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Kick Session
         * @description 强制踢出会话（即时生效：删标记 + 吊销 refresh + `revoked_at` 落库 + 广播占位）。
         *
         *     Args:
         *         request: 请求对象。
         *         session_id: 会话 id。
         *         security: 会话安全原语。
         *         store: 会话标记存储。
         *         publisher: 实时推送器。
         *         tenant_ctx: 请求上下文租户。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为踢出结果（会话 id / 撤销时间 / 原因）。
         */
        post: operations["kick_session_api_v1_sessions__session_id__kick_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/{user_id}/identities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Identities
         * @description 按本地用户反查 SSO 身份绑定（平台库只读；无绑定返回空列表）。
         *
         *     Args:
         *         request: 请求对象（取引擎注册表与会话工厂）。
         *         user_id: 本地用户 ID（路由参数）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为绑定清单（`SsoIdentityList`）。
         */
        get: operations["list_identities_api_v1_users__user_id__identities_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/healthz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Healthz
         * @description 存活检查端点。
         *
         *     Args:
         *         request: 当前请求（取服务身份）。
         *
         *     Returns:
         *         dict: 服务状态与身份，固定返回 {"status": "ok", "service": 名, "version": 版}。
         */
        get: operations["healthz_healthz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/readyz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Readyz
         * @description 就绪检查端点（启动完成态 + 停机摘流 + 注册表聚合）。
         *
         *     Args:
         *         request: 当前请求（取应用启动完成态 / 停机摘流标记 / 服务身份）。
         *         registry: 健康检查项注册表（依赖注入）。
         *
         *     Returns:
         *         JSONResponse: 全部就绪 200；未就绪、启动未完成或停机中 503。
         */
        get: operations["readyz_readyz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        ApiResponse: unknown;
        ApiResponse_BasePageResponse_ClientItem__: unknown;
        ApiResponse_BasePageResponse_IdpProviderItem__: unknown;
        ApiResponse_BasePageResponse_SessionItem__: unknown;
        ApiResponse_ClientCreated_: unknown;
        ApiResponse_ClientItem_: unknown;
        ApiResponse_ClientSecretReset_: unknown;
        ApiResponse_IdpProviderItem_: unknown;
        ApiResponse_IdpProviderTestResult_: unknown;
        ApiResponse_KickResult_: unknown;
        ApiResponse_LoginResult_: unknown;
        ApiResponse_NoneType_: unknown;
        ApiResponse_PasswordForgotResult_: unknown;
        ApiResponse_PasswordResetResult_: unknown;
        ApiResponse_RefreshResult_: unknown;
        ApiResponse_SessionItem_: unknown;
        ApiResponse_SsoAuthorizeInfo_: unknown;
        ApiResponse_SsoIdentityList_: unknown;
        ApiResponse_SsoProviderList_: unknown;
        ApiResponse_dict_str__object__: unknown;
        BasePageResponse_ClientItem_: unknown;
        BasePageResponse_IdpProviderItem_: unknown;
        BasePageResponse_SessionItem_: unknown;
        /**
         * CaptchaChallengeRequest
         * @description 验证码出题请求。
         */
        CaptchaChallengeRequest: {
            /**
             * @description 挑战类型（image / slider）
             * @default image
             */
            kind: components["schemas"]["CaptchaKind"];
            /**
             * Scene
             * @description 使用场景（取值见 CAPTCHA_SCENES）
             * @default login
             */
            scene: string;
        };
        /**
         * CaptchaInput
         * @description 登录验证码凭证（图形 / 滑块 / 短信；与验证码基座 `CaptchaCredential` 字段对应）。
         */
        CaptchaInput: {
            /**
             * Captcha Id
             * @description 挑战编号
             * @default
             */
            captcha_id: string;
            /**
             * Code
             * @description 校验码（图形 / 短信）
             * @default
             */
            code: string;
            /**
             * Kind
             * @description 验证码形态（image / slider / sms）
             * @default image
             */
            kind: string;
            /**
             * Trace
             * @description 滑块轨迹点（x / y / 相对起点毫秒）
             */
            trace?: [
                number,
                number,
                number
            ][];
        };
        /**
         * CaptchaKind
         * @description 挑战类型（与前端验证码字段形态取值同源）。
         * @enum {string}
         */
        CaptchaKind: "image" | "slider" | "sms";
        /**
         * CaptchaSmsRequest
         * @description 短信验证码发送请求。
         */
        CaptchaSmsRequest: {
            /**
             * Phone
             * @description 目标手机号（格式校验随真实实现）
             */
            phone: string;
            /**
             * Scene
             * @description 使用场景（取值见 CAPTCHA_SCENES）
             * @default login
             */
            scene: string;
        };
        /**
         * CaptchaVerifyRequest
         * @description 验证码凭证校验请求。
         */
        CaptchaVerifyRequest: {
            /**
             * Captcha Id
             * @description 挑战编号
             */
            captcha_id: string;
            /**
             * Code
             * @description 用户输入的校验码（图形 / 短信）
             * @default
             */
            code: string;
            /**
             * @description 挑战类型（决定取校验码还是轨迹）
             * @default image
             */
            kind: components["schemas"]["CaptchaKind"];
            /**
             * Scene
             * @description 使用场景（取值见 CAPTCHA_SCENES）
             * @default login
             */
            scene: string;
            /**
             * Trace
             * @description 滑块轨迹点序列（每点为 x / y / 相对起点毫秒）
             */
            trace?: [
                number,
                number,
                number
            ][];
        };
        /**
         * ClientCreateRequest
         * @description 客户端注册请求。
         */
        ClientCreateRequest: {
            /**
             * Grant Types
             * @description 授权类型（client_credentials/authorization_code）
             */
            grant_types?: string[];
            /**
             * Ip Whitelist
             * @description 来源 IP / CIDR 白名单（开放接口阶段十用）
             */
            ip_whitelist?: string[];
            /**
             * Name
             * @description 应用名称
             */
            name: string;
            /**
             * Public
             * @description 是否公共客户端（不生成 secret；授权码流程强制 PKCE）
             * @default false
             */
            public: boolean;
            /**
             * Redirect Uris
             * @description 回调地址白名单（精确匹配）
             */
            redirect_uris?: string[];
            /**
             * Scopes
             * @description 允许申请的 scope 集合
             */
            scopes?: string[];
        };
        ClientCreated: unknown;
        ClientItem: unknown;
        ClientSecretReset: unknown;
        /**
         * ClientStatusRequest
         * @description 客户端启停请求。
         */
        ClientStatusRequest: {
            /**
             * Status
             * @description 目标状态（enabled/disabled）
             */
            status: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * IdpProviderCreateRequest
         * @description 新建 IdP 配置请求。
         */
        IdpProviderCreateRequest: {
            /**
             * Config
             * @description 协议配置对象
             */
            config?: {
                [key: string]: unknown;
            };
            /**
             * Icon
             * @description 图标（可空）
             * @default
             */
            icon: string;
            /**
             * Idp Key
             * @description 租户内标识 slug
             */
            idp_key: string;
            /**
             * Name
             * @description 显示名
             */
            name: string;
            /**
             * Sort
             * @description 登录页排序
             * @default 0
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled，缺省 enabled）
             * @default enabled
             */
            status: string;
            /**
             * Type
             * @description 协议类型（oidc / cas / wecom / dingtalk）
             */
            type: string;
        };
        IdpProviderItem: unknown;
        /**
         * IdpProviderStatusRequest
         * @description 启停请求。
         */
        IdpProviderStatusRequest: {
            /**
             * Status
             * @description 目标状态（enabled/disabled）
             */
            status: string;
        };
        /**
         * IdpProviderTestRequest
         * @description 草稿连通性测试请求（不落库）。
         */
        IdpProviderTestRequest: {
            /**
             * Config
             * @description 协议配置对象
             */
            config?: {
                [key: string]: unknown;
            };
            /**
             * Idp Key
             * @description 租户内标识（派生回调地址用；可占位）
             * @default draft
             */
            idp_key: string;
            /**
             * Type
             * @description 协议类型
             */
            type: string;
        };
        IdpProviderTestResult: unknown;
        /**
         * IdpProviderUpdateRequest
         * @description 修改 IdP 配置请求（局部更新；`type` / `idp_key` 不可改）。
         */
        IdpProviderUpdateRequest: {
            /**
             * Config
             * @description 协议配置对象（全量替换）
             */
            config?: {
                [key: string]: unknown;
            } | null;
            /**
             * Icon
             * @description 图标
             */
            icon?: string | null;
            /**
             * Name
             * @description 显示名
             */
            name?: string | null;
            /**
             * Sort
             * @description 登录页排序
             */
            sort?: number | null;
        };
        KickResult: unknown;
        /**
         * LoginRequest
         * @description 本地登录请求。
         */
        LoginRequest: {
            /**
             * Account
             * @description 登录账号
             */
            account: string;
            /** @description 验证码凭证（策略强制或已出题时携带） */
            captcha?: components["schemas"]["CaptchaInput"] | null;
            /**
             * Password
             * @description 口令明文
             */
            password: string;
            /**
             * Tenant Code
             * @description 租户编码（可选；携带则以之为准）
             */
            tenant_code?: string | null;
        };
        LoginResult: unknown;
        /**
         * PasswordForgotRequest
         * @description 发起找回请求（账号 / 手机 / 邮箱取通道；验证码按场景策略必带）。
         */
        PasswordForgotRequest: {
            /** @description 验证码凭证（场景 reset_password；策略强制时必带） */
            captcha?: components["schemas"]["CaptchaInput"] | null;
            /**
             * Identifier
             * @description 账号 / 手机号 / 邮箱
             */
            identifier: string;
            /**
             * Tenant Code
             * @description 租户编码（可选；携带则以之为准）
             */
            tenant_code?: string | null;
        };
        PasswordForgotResult: unknown;
        /**
         * PasswordResetRequest
         * @description 提交重置请求（重置令牌 + 新口令；策略判定在 org 侧）。
         */
        PasswordResetRequest: {
            /**
             * New Password
             * @description 新口令明文
             */
            new_password: string;
            /**
             * Tenant Code
             * @description 租户编码（可选；携带则以之为准）
             */
            tenant_code?: string | null;
            /**
             * Token
             * @description 重置令牌（通知下发；单次有效）
             */
            token: string;
        };
        PasswordResetResult: unknown;
        RefreshResult: unknown;
        SessionItem: unknown;
        SsoAuthorizeInfo: unknown;
        SsoIdentityItem: unknown;
        SsoIdentityList: unknown;
        SsoProviderItem: unknown;
        SsoProviderList: unknown;
        UserSummary: unknown;
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    root__get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    get_jwks__well_known_jwks_json_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    forgot_password_api_v1_auth_forgot_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordForgotRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_PasswordForgotResult_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    introspect_api_v1_auth_introspect_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-Forwarded-Uri"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    introspect_api_v1_auth_introspect_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-Forwarded-Uri"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_LoginResult_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
                };
            };
        };
    };
    refresh_api_v1_auth_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_RefreshResult_"];
                };
            };
        };
    };
    reset_password_api_v1_auth_reset_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordResetRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_PasswordResetResult_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    providers_api_v1_auth_sso_providers_get: {
        parameters: {
            query?: {
                /** @description 租户编码（上下文缺省时的回落） */
                tenant_code?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_SsoProviderList_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    authorize_api_v1_auth_sso__idp_key__authorize_get: {
        parameters: {
            query?: {
                /** @description 租户编码（上下文缺省时的回落） */
                tenant_code?: string | null;
            };
            header?: never;
            path: {
                idp_key: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    authorize_url_api_v1_auth_sso__idp_key__authorize_url_get: {
        parameters: {
            query?: {
                /** @description 租户编码（上下文缺省时的回落） */
                tenant_code?: string | null;
            };
            header?: never;
            path: {
                idp_key: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_SsoAuthorizeInfo_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    callback_api_v1_auth_sso__idp_key__callback_get: {
        parameters: {
            query?: {
                /** @description IdP 回传流程状态 */
                state?: string | null;
                /** @description IdP 回传授权码（OIDC） */
                code?: string | null;
                /** @description IdP 回传服务票据（CAS） */
                ticket?: string | null;
                /** @description IdP 回传错误（如 access_denied） */
                error?: string | null;
            };
            header?: never;
            path: {
                idp_key: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_challenge_api_v1_captcha_challenges_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaptchaChallengeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    get_scene_policy_api_v1_captcha_scenes__scene__policy_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 使用场景（取值见 CAPTCHA_SCENES） */
                scene: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    send_sms_code_api_v1_captcha_sms_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaptchaSmsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    verify_captcha_api_v1_captcha_verify_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaptchaVerifyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    list_providers_api_v1_idp_providers_get: {
        parameters: {
            query?: {
                status?: string | null;
                type?: string | null;
                name?: string | null;
                /** @description 页码（从 1 起） */
                page?: number;
                /** @description 每页条数（默认 20，上限 200） */
                size?: number;
                /** @description 排序字段，逗号分隔多值（如 status,created_at） */
                order_by?: string | null;
                /** @description 排序方向数组，与 order_by 位置一一对应 */
                order?: string[] | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_IdpProviderItem__"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    create_provider_api_v1_idp_providers_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IdpProviderCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_IdpProviderItem_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    test_draft_provider_api_v1_idp_providers_test_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IdpProviderTestRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_IdpProviderTestResult_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    get_provider_api_v1_idp_providers__provider_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description IdP 配置主键 */
                provider_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_IdpProviderItem_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    update_provider_api_v1_idp_providers__provider_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description IdP 配置主键 */
                provider_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IdpProviderUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_IdpProviderItem_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    delete_provider_api_v1_idp_providers__provider_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description IdP 配置主键 */
                provider_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_dict_str__object__"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    set_provider_status_api_v1_idp_providers__provider_id__status_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description IdP 配置主键 */
                provider_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IdpProviderStatusRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_IdpProviderItem_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    test_saved_provider_api_v1_idp_providers__provider_id__test_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description IdP 配置主键 */
                provider_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_IdpProviderTestResult_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    openid_configuration_api_v1_oidc__well_known_openid_configuration_get: {
        parameters: {
            query?: {
                /** @description 租户编码（上下文缺省时的回落） */
                tenant_code?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    authorize_api_v1_oidc_authorize_get: {
        parameters: {
            query?: {
                response_type?: string | null;
                client_id?: string | null;
                redirect_uri?: string | null;
                scope?: string | null;
                state?: string | null;
                nonce?: string | null;
                code_challenge?: string | null;
                code_challenge_method?: string | null;
                /** @description 租户编码（上下文缺省时的回落） */
                tenant_code?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    jwks_api_v1_oidc_jwks_get: {
        parameters: {
            query?: {
                /** @description 租户编码（上下文缺省时的回落） */
                tenant_code?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    token_api_v1_oidc_token_post: {
        parameters: {
            query?: {
                /** @description 租户编码（上下文缺省时的回落） */
                tenant_code?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    userinfo_api_v1_oidc_userinfo_get: {
        parameters: {
            query?: {
                /** @description 租户编码（上下文缺省时的回落） */
                tenant_code?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    userinfo_api_v1_oidc_userinfo_post: {
        parameters: {
            query?: {
                /** @description 租户编码（上下文缺省时的回落） */
                tenant_code?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_clients_api_v1_open_clients_get: {
        parameters: {
            query?: {
                status?: string | null;
                name?: string | null;
                /** @description 页码（从 1 起） */
                page?: number;
                /** @description 每页条数（默认 20，上限 200） */
                size?: number;
                /** @description 排序字段，逗号分隔多值（如 status,created_at） */
                order_by?: string | null;
                /** @description 排序方向数组，与 order_by 位置一一对应 */
                order?: string[] | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_ClientItem__"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    create_client_api_v1_open_clients_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClientCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_ClientCreated_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    get_client_api_v1_open_clients__client_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 客户端主键 */
                client_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_ClientItem_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    reset_client_secret_api_v1_open_clients__client_id__reset_secret_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 客户端主键 */
                client_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_ClientSecretReset_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    set_client_status_api_v1_open_clients__client_id__status_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 客户端主键 */
                client_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClientStatusRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_ClientItem_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    list_sessions_api_v1_sessions_get: {
        parameters: {
            query?: {
                /** @description 用户 ID（精确） */
                user_id?: number | null;
                /** @description 设备标识（模糊） */
                device?: string | null;
                /** @description 登录 IP（模糊） */
                ip?: string | null;
                /** @description 登录时间下界（UTC，闭区间） */
                login_from?: string | null;
                /** @description 登录时间上界（UTC，闭区间） */
                login_to?: string | null;
                /** @description 页码（从 1 起） */
                page?: number;
                /** @description 每页条数（默认 20，上限 200） */
                size?: number;
                /** @description 排序字段，逗号分隔多值（如 status,created_at） */
                order_by?: string | null;
                /** @description 排序方向数组，与 order_by 位置一一对应 */
                order?: string[] | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_SessionItem__"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    get_session_api_v1_sessions__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_SessionItem_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    kick_session_api_v1_sessions__session_id__kick_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_KickResult_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    list_identities_api_v1_users__user_id__identities_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 本地用户 ID */
                user_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_SsoIdentityList_"];
                };
            };
            /** @description 未认证 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 无权限 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 资源不存在 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description 限流 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
            /** @description 服务异常 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse"];
                };
            };
        };
    };
    healthz_healthz_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    readyz_readyz_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
}
