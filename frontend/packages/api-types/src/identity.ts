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
        ApiResponse_LoginResult_: unknown;
        ApiResponse_NoneType_: unknown;
        ApiResponse_RefreshResult_: unknown;
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
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
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
             * Tenant
             * @description 租户编码（可选；携带则以之为准）
             */
            tenant?: string | null;
        };
        LoginResult: unknown;
        RefreshResult: unknown;
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
