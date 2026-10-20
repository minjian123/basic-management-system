/**
 * 服务契约生成类型：tenant
 *
 * 本文件由 `frontend/packages/api-types/scripts/generate.mjs` 生成，请勿手工修改。
 * 来源：deploy/contracts/tenant.json（服务契约快照，唯一事实源）。
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
    "/api/v1/tenant-registry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Tenant Registry
         * @description 取租户注册快照（按编码 / 域名 / 主键三选一）。
         *
         *     Args:
         *         session: 平台服务库只读会话。
         *         code: 租户编码。
         *         domain: 子域名。
         *         tenant_id: 租户主键雪花 id 字符串。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为注册快照）。
         *
         *     Raises:
         *         ParamError: 未提供或多于一个来源（10001）。
         *         TenantNotFoundError: 未知租户（404 / 80001）。
         *         TenantSuspendedError: 租户已停用（403 / 80002）。
         */
        get: operations["get_tenant_registry_api_v1_tenant_registry_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-registry/active-single": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Single Active Tenant
         * @description 取唯一启用租户注册快照（免登录链路兜底；不返回租户清单）。
         *
         *     恰 1 个启用租户（`status == active` 且未软删）→ 注册快照；0 个 → `80001` / 404；
         *     ≥ 2 个 → `80004` / 409（`MultipleActiveTenantsError`）。
         *
         *     Args:
         *         session: 平台服务库只读会话。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为注册快照）。
         *
         *     Raises:
         *         TenantNotFoundError: 无启用租户（404 / 80001）。
         *         MultipleActiveTenantsError: 多启用租户（409 / 80004）。
         */
        get: operations["get_single_active_tenant_api_v1_tenant_registry_active_single_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant/internal/memberships": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Memberships
         * @description 读某用户可访问目标租户集合（可选含 `disabled` 行，供读路径自愈判据）。
         *
         *     Args:
         *         service: 关系服务。
         *         owner_tenant_id: 归属租户主键。
         *         user_id: 用户主键。
         *         include_disabled: 是否含 `disabled` 行。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为目标集合。
         */
        get: operations["list_memberships_api_v1_tenant_internal_memberships_get"];
        put?: never;
        /**
         * Ensure Membership
         * @description 建立 / 复活关系（幂等）。
         *
         *     Args:
         *         req: 写入请求（归属租户 / 用户 / 目标租户 / 来源）。
         *         service: 关系服务。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为操作后该用户有效目标集合。
         */
        post: operations["ensure_membership_api_v1_tenant_internal_memberships_post"];
        /**
         * Revoke Membership
         * @description 回收关系（置 `disabled`，幂等；省略目标租户则回收该用户全部）。
         *
         *     Args:
         *         service: 关系服务。
         *         owner_tenant_id: 归属租户主键。
         *         user_id: 用户主键。
         *         target_tenant_id: 目标租户主键（省略＝回收全部）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为操作后该用户有效目标集合。
         */
        delete: operations["revoke_membership_api_v1_tenant_internal_memberships_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant/internal/modules/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Module Status
         * @description 取租户模块状态集（模块门禁回源）。
         *
         *     Args:
         *         request: 请求对象。
         *         session: 平台库只读会话。
         *         tenant_id: 租户主键。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为状态集）。
         */
        get: operations["module_status_api_v1_tenant_internal_modules_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant/internal/quotas/check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Check Quota
         * @description 校验配额（不写；超限 82005）。
         *
         *     Args:
         *         req: 校验请求。
         *         session: 平台库只读会话。
         *         request: 请求对象（取配置）。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为校验结果）。
         */
        post: operations["check_quota_api_v1_tenant_internal_quotas_check_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant/internal/quotas/consume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Consume Quota
         * @description 原子占用配额（超限 82005）。
         *
         *     Args:
         *         req: 占用请求。
         *         session: 平台库写会话。
         *         request: 请求对象（取配置）。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为占用结果）。
         */
        post: operations["consume_quota_api_v1_tenant_internal_quotas_consume_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant/internal/quotas/release": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Release Quota
         * @description 释放配额用量（下限 0）。
         *
         *     Args:
         *         req: 释放请求。
         *         session: 平台库写会话。
         *         request: 请求对象（取配置）。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为释放结果）。
         */
        post: operations["release_quota_api_v1_tenant_internal_quotas_release_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Tenants
         * @description 业务租户分页列表（平台租户排除）。
         *
         *     Args:
         *         request: 请求对象。
         *         session: 平台库只读会话。
         *         query: 分页请求。
         *         client: 服务间调用客户端。
         *         cache: 缓存域。
         *         code: 编码模糊筛选。
         *         name: 名称模糊筛选。
         *         status: 状态筛选。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为分页结果）。
         */
        get: operations["list_tenants_api_v1_tenants_get"];
        put?: never;
        /**
         * Create Tenant
         * @description 开通租户（同步全流程；支持幂等键）。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 开通请求。
         *         session: 平台库写会话。
         *         client: 服务间调用客户端。
         *         cache: 缓存域。
         *         auth: 登录态（操作人）。
         *         idempotency: 幂等存储。
         *         idempotency_key: 幂等键请求头。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为开通结果，含初始口令）。
         */
        post: operations["create_tenant_api_v1_tenants_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants/brand": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Tenant Brand
         * @description 取品牌信息（登录前可用；缺省当前租户）。
         *
         *     Args:
         *         service: 租户自助基座。
         *         code: 租户编码（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为品牌信息（`TenantBrandResponse`）。
         */
        get: operations["tenant_brand_api_v1_tenants_brand_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants/mine": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * My Tenants
         * @description 取「我加入的租户」概览（当前租户取自解析链上下文；主体取自登录态）。
         *
         *     Args:
         *         service: 租户自助基座。
         *         tenant: 解析链租户上下文。
         *         auth: 登录态身份（当前租户主键 / 用户主键）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为自助概览（`TenantSelfOverviewResponse`）。
         */
        get: operations["my_tenants_api_v1_tenants_mine_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants/module-options": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Module Options
         * @description 开通向导模块选项（目录全量 + 可勾选标记）。
         *
         *     Args:
         *         request: 请求对象。
         *         client: 服务间调用客户端。
         *         cache: 缓存域。
         *         session: 平台库只读会话。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为选项清单）。
         */
        get: operations["module_options_api_v1_tenants_module_options_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants/switch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Switch Tenant
         * @description 切换到目标租户（越权校验；可按幂等键复用首次结果）。
         *
         *     Args:
         *         service: 租户自助基座。
         *         idempotency: 幂等基座（首次结果复用）。
         *         tenant: 解析链租户上下文（幂等键作用域位）。
         *         auth: 登录态身份（当前租户主键 / 用户主键）。
         *         req: 切换请求。
         *         idempotency_key: 幂等键请求头（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为切换结果（`TenantSwitchResponse`）。
         */
        post: operations["switch_tenant_api_v1_tenants_switch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants/{tenant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Tenant
         * @description 租户详情（含配额与模块清单）。
         *
         *     Args:
         *         request: 请求对象。
         *         tenant_id: 租户主键。
         *         session: 平台库只读会话。
         *         client: 服务间调用客户端。
         *         cache: 缓存域。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为详情）。
         */
        get: operations["get_tenant_api_v1_tenants__tenant_id__get"];
        /**
         * Update Tenant
         * @description 修改租户（名称 / 域名 / 到期时间）。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 修改请求。
         *         tenant_id: 租户主键。
         *         session: 平台库写会话。
         *         client: 服务间调用客户端。
         *         cache: 缓存域。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为更新后的详情）。
         */
        put: operations["update_tenant_api_v1_tenants__tenant_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants/{tenant_id}/activate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Activate Tenant
         * @description 启用租户（事件 + 缓存失效）。
         *
         *     Args:
         *         request: 请求对象。
         *         tenant_id: 租户主键。
         *         session: 平台库写会话。
         *         client: 服务间调用客户端。
         *         cache: 缓存域。
         *         source: 租户源（缓存失效）。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为启用后的详情）。
         */
        post: operations["activate_tenant_api_v1_tenants__tenant_id__activate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants/{tenant_id}/modules": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Modules
         * @description 租户模块清单（三态）。
         *
         *     Args:
         *         request: 请求对象。
         *         tenant_id: 租户主键。
         *         session: 平台库只读会话。
         *         client: 服务间调用客户端。
         *         cache: 缓存域。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为模块项）。
         */
        get: operations["get_modules_api_v1_tenants__tenant_id__modules_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants/{tenant_id}/modules/{module_key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Put Module
         * @description 租户模块开关（目录校验 + 状态切换）。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 开关请求。
         *         tenant_id: 租户主键。
         *         module_key: 模块标识。
         *         session: 平台库写会话。
         *         client: 服务间调用客户端。
         *         cache: 缓存域。
         *         auth: 登录态（操作人）。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为更新后的模块清单）。
         */
        put: operations["put_module_api_v1_tenants__tenant_id__modules__module_key__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants/{tenant_id}/quotas": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Quotas
         * @description 配额与用量。
         *
         *     Args:
         *         request: 请求对象。
         *         tenant_id: 租户主键。
         *         session: 平台库只读会话。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为配额项）。
         */
        get: operations["get_quotas_api_v1_tenants__tenant_id__quotas_get"];
        /**
         * Put Quotas
         * @description 配置配额限额（整组覆盖；未列出的维度保持原值）。
         *
         *     Args:
         *         request: 请求对象。
         *         req: 配额配置请求。
         *         tenant_id: 租户主键。
         *         session: 平台库写会话。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为更新后的配额项）。
         */
        put: operations["put_quotas_api_v1_tenants__tenant_id__quotas_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenants/{tenant_id}/suspend": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Suspend Tenant
         * @description 停用租户（事件 + 引擎回收 + 按租户撤销会话 + 缓存失效）。
         *
         *     Args:
         *         request: 请求对象。
         *         tenant_id: 租户主键。
         *         session: 平台库写会话。
         *         client: 服务间调用客户端。
         *         cache: 缓存域。
         *         source: 租户源（缓存失效）。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为停用后的详情）。
         */
        post: operations["suspend_tenant_api_v1_tenants__tenant_id__suspend_post"];
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
        /**
         * ApiResponse
         * @description 统一响应体：`code=0` 成功，非 0 业务错误码。
         *
         *     - `data` 为业务数据（泛型）；失败时为 `null`；分页载荷复用分页契约基类。
         *     - 雪花 ID 在 JSON 中以字符串输出（`BaseSchema` 统一序列化口径）。
         */
        ApiResponse: {
            /**
             * Code
             * @default 0
             */
            code: number;
            /** Data */
            data?: unknown | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[ModuleStatusResponse] */
        ApiResponse_ModuleStatusResponse_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["ModuleStatusResponse"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[QuotaResult] */
        ApiResponse_QuotaResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["QuotaResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[TenantDetail] */
        ApiResponse_TenantDetail_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["TenantDetail"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[TenantList] */
        ApiResponse_TenantList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["TenantList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[TenantMembershipListResponse] */
        ApiResponse_TenantMembershipListResponse_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["TenantMembershipListResponse"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[TenantModuleItemList] */
        ApiResponse_TenantModuleItemList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["TenantModuleItemList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[TenantModuleOptionList] */
        ApiResponse_TenantModuleOptionList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["TenantModuleOptionList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[TenantProvisionResult] */
        ApiResponse_TenantProvisionResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["TenantProvisionResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[TenantQuotaItemList] */
        ApiResponse_TenantQuotaItemList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["TenantQuotaItemList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * ModuleStatusResponse
         * @description 租户模块状态集（内部契约；模块门禁用）。
         */
        ModuleStatusResponse: {
            /**
             * Disabled
             * @description 已开通但停用的模块标识
             */
            disabled?: string[];
            /**
             * Enabled
             * @description 已开通且启用的模块标识
             */
            enabled?: string[];
            /**
             * Version
             * @description 清单版本号（变更即递增）
             */
            version: number;
        };
        /**
         * QuotaConsumeRequest
         * @description 配额占用 / 校验请求（内部契约）。
         */
        QuotaConsumeRequest: {
            /**
             * Amount
             * @description 占用数量（正数）
             */
            amount: number;
            /**
             * Quota Key
             * @description 配额维度（user_count / storage_bytes / open_calls）
             */
            quota_key: string;
            /**
             * Tenant Id
             * @description 租户主键
             */
            tenant_id: number;
        };
        /**
         * QuotaReleaseRequest
         * @description 配额释放请求（内部契约）。
         */
        QuotaReleaseRequest: {
            /**
             * Amount
             * @description 释放数量（正数）
             */
            amount: number;
            /**
             * Quota Key
             * @description 配额维度
             */
            quota_key: string;
            /**
             * Tenant Id
             * @description 租户主键
             */
            tenant_id: number;
        };
        /**
         * QuotaResult
         * @description 配额操作结果（内部契约）。
         */
        QuotaResult: {
            /**
             * Allowed
             * @description 是否放行（无配额行视为不限制）
             */
            allowed: boolean;
            /**
             * Limit Value
             * @description 限额（无配额行为空）
             */
            limit_value?: number | null;
            /**
             * Used Value
             * @description 操作后的已用量
             */
            used_value: number;
        };
        /**
         * TenantCreateRequest
         * @description 开通租户请求（code / name / domain + 模块勾选清单）。
         */
        TenantCreateRequest: {
            /**
             * Code
             * @description 租户编码（全小写；库名基）
             */
            code: string;
            /**
             * Domain
             * @description 子域名（如 acme.bms.example.com）
             */
            domain?: string | null;
            /**
             * Expire At
             * @description 到期时间（UTC）
             */
            expire_at?: string | null;
            /**
             * Modules
             * @description 开通模块勾选清单（仅可勾选产品模块；基础能力恒开通）
             */
            modules?: string[];
            /**
             * Name
             * @description 租户名称
             */
            name: string;
        };
        /**
         * TenantDetail
         * @description 租户详情（含配额与模块）。
         */
        TenantDetail: {
            /**
             * Code
             * @description 租户编码
             */
            code: string;
            /**
             * Created At
             * Format: date-time
             * @description 创建时间（UTC）
             */
            created_at: string;
            /**
             * Domain
             * @description 子域名
             */
            domain?: string | null;
            /**
             * Expire At
             * @description 到期时间（UTC）
             */
            expire_at?: string | null;
            /**
             * Id
             * @description 租户主键
             */
            id: string;
            /**
             * Modules
             * @description 模块清单（含未开通）
             */
            modules?: components["schemas"]["TenantModuleItem"][];
            /**
             * Name
             * @description 租户名称
             */
            name: string;
            /**
             * Quotas
             * @description 配额与用量
             */
            quotas?: components["schemas"]["TenantQuotaItem"][];
            /**
             * Status
             * @description 状态
             * @enum {string}
             */
            status: "provisioning" | "active" | "suspended";
            /**
             * Updated At
             * Format: date-time
             * @description 更新时间（UTC）
             */
            updated_at: string;
            /**
             * Version
             * @description 乐观锁版本
             */
            version: number;
        };
        /**
         * TenantList
         * @description 租户分页列表。
         */
        TenantList: {
            /** List */
            list: components["schemas"]["TenantListItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /**
         * TenantListItem
         * @description 租户列表项。
         */
        TenantListItem: {
            /**
             * Code
             * @description 租户编码
             */
            code: string;
            /**
             * Created At
             * Format: date-time
             * @description 创建时间（UTC）
             */
            created_at: string;
            /**
             * Domain
             * @description 子域名
             */
            domain?: string | null;
            /**
             * Expire At
             * @description 到期时间（UTC）
             */
            expire_at?: string | null;
            /**
             * Id
             * @description 租户主键
             */
            id: string;
            /**
             * Modules
             * @description 已开通模块标识
             */
            modules?: string[];
            /**
             * Name
             * @description 租户名称
             */
            name: string;
            /**
             * Status
             * @description 状态
             * @enum {string}
             */
            status: "provisioning" | "active" | "suspended";
            /**
             * Version
             * @description 乐观锁版本
             */
            version: number;
        };
        /**
         * TenantMembershipGrantRequest
         * @description 建立 / 复活关系入参（全字段显式；`owner_tenant_id` 为用户归属租户）。
         */
        TenantMembershipGrantRequest: {
            /**
             * Owner Tenant Id
             * @description 归属租户主键（用户建号 / 登录所在租户）
             */
            owner_tenant_id: number;
            /**
             * Source
             * @description 写入来源（super_admin / admin_create / import / sso_jit / …）
             */
            source: string;
            /**
             * Target Tenant Id
             * @description 目标租户主键
             */
            target_tenant_id: number;
            /**
             * User Id
             * @description 用户主键（org 服务 sys_user.id）
             */
            user_id: number;
        };
        /**
         * TenantMembershipListResponse
         * @description 某用户当前有效可访问租户集合（内部端点统一响应）。
         */
        TenantMembershipListResponse: {
            /**
             * Targets
             * @description 有效可访问目标租户（status=active）
             */
            targets?: components["schemas"]["TenantMembershipTarget"][];
        };
        /**
         * TenantMembershipTarget
         * @description 可访问目标租户条目（关系 + 租户元信息）。
         */
        TenantMembershipTarget: {
            /**
             * Code
             * @description 目标租户编码
             */
            code: string;
            /**
             * Domain
             * @description 目标租户子域名
             */
            domain?: string | null;
            /**
             * Name
             * @description 目标租户名称
             */
            name: string;
            /**
             * Source
             * @description 写入来源
             * @default
             */
            source: string;
            /**
             * Status
             * @description 关系状态（active / disabled）
             * @default active
             */
            status: string;
            /**
             * Tenant Id
             * @description 目标租户主键（雪花 id）
             */
            tenant_id: string;
        };
        /**
         * TenantModuleItem
         * @description 租户模块项（目录 + 开通清单合并视图）。
         */
        TenantModuleItem: {
            /**
             * Errcode Segment
             * @description 错误码段
             */
            errcode_segment?: string | null;
            /**
             * Module Key
             * @description 模块标识
             */
            module_key: string;
            /**
             * Name
             * @description 模块名称
             */
            name: string;
            /**
             * Opened At
             * @description 最近开通时间（UTC）
             */
            opened_at?: string | null;
            /**
             * Optional
             * @description 是否可勾选产品模块（基础能力恒开通）
             */
            optional: boolean;
            /**
             * Status
             * @description 状态（enabled / disabled / not_opened）
             * @enum {string}
             */
            status: "enabled" | "disabled" | "not_opened";
            /**
             * Table Prefix
             * @description 表前缀
             */
            table_prefix: string;
        };
        /**
         * TenantModuleItemList
         * @description 租户模块清单（三态）。
         */
        TenantModuleItemList: {
            /**
             * Items
             * @description 模块项
             */
            items?: components["schemas"]["TenantModuleItem"][];
        };
        /**
         * TenantModuleOption
         * @description 开通向导模块选项（目录快照）。
         */
        TenantModuleOption: {
            /**
             * Catalog Status
             * @description 目录状态（enabled / disabled / planned）
             */
            catalog_status: string;
            /**
             * Errcode Segment
             * @description 错误码段
             */
            errcode_segment?: string | null;
            /**
             * Module Key
             * @description 模块标识
             */
            module_key: string;
            /**
             * Name
             * @description 模块名称
             */
            name: string;
            /**
             * Optional
             * @description 是否可勾选（产品模块且目录已启用）
             */
            optional: boolean;
            /**
             * Service Group
             * @description 归属分组（foundation / capability / product）
             */
            service_group: string;
            /**
             * Table Prefix
             * @description 表前缀
             */
            table_prefix: string;
        };
        /**
         * TenantModuleOptionList
         * @description 开通向导模块选项清单。
         */
        TenantModuleOptionList: {
            /**
             * Items
             * @description 模块选项
             */
            items?: components["schemas"]["TenantModuleOption"][];
        };
        /**
         * TenantModuleUpdateRequest
         * @description 租户模块开关请求。
         */
        TenantModuleUpdateRequest: {
            /**
             * Status
             * @description 目标状态（enabled / disabled）
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * TenantProvisionResult
         * @description 开通结果（初始管理员口令仅本次返回）。
         */
        TenantProvisionResult: {
            /**
             * Admin Username
             * @description 初始系统管理员账号
             */
            admin_username: string;
            /**
             * Initial Password
             * @description 初始口令（仅本次返回；首登强制改密）
             */
            initial_password: string;
            /** @description 租户详情 */
            tenant: components["schemas"]["TenantDetail"];
        };
        /**
         * TenantQuotaItem
         * @description 配额项（限额与用量）。
         */
        TenantQuotaItem: {
            /**
             * Limit Value
             * @description 限额
             */
            limit_value: number;
            /**
             * Quota Key
             * @description 配额维度（user_count / storage_bytes / open_calls）
             */
            quota_key: string;
            /**
             * Used Value
             * @description 已用量
             */
            used_value: number;
        };
        /**
         * TenantQuotaItemList
         * @description 租户配额与用量清单。
         */
        TenantQuotaItemList: {
            /**
             * Items
             * @description 配额项
             */
            items?: components["schemas"]["TenantQuotaItem"][];
        };
        /**
         * TenantQuotaUpdateItem
         * @description 配额配置项。
         */
        TenantQuotaUpdateItem: {
            /**
             * Limit Value
             * @description 新限额
             */
            limit_value: number;
            /**
             * Quota Key
             * @description 配额维度（user_count / storage_bytes / open_calls）
             */
            quota_key: string;
        };
        /**
         * TenantQuotaUpdateRequest
         * @description 配额配置请求（整组覆盖；未列出的维度保持原值）。
         */
        TenantQuotaUpdateRequest: {
            /**
             * Items
             * @description 配额项清单
             */
            items: components["schemas"]["TenantQuotaUpdateItem"][];
        };
        /**
         * TenantSwitchRequest
         * @description 切换租户请求：`{code}`。
         */
        TenantSwitchRequest: {
            /**
             * Code
             * @description 目标租户编码
             */
            code: string;
        };
        /**
         * TenantUpdateRequest
         * @description 修改租户请求（名称 / 域名 / 到期时间；`code` 不可改）。
         */
        TenantUpdateRequest: {
            /**
             * Domain
             * @description 子域名
             */
            domain?: string | null;
            /**
             * Expire At
             * @description 到期时间（UTC）
             */
            expire_at?: string | null;
            /**
             * Name
             * @description 租户名称
             */
            name?: string | null;
        };
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
    get_tenant_registry_api_v1_tenant_registry_get: {
        parameters: {
            query?: {
                /** @description 租户编码（与 domain / tenant_id 三选一） */
                code?: string | null;
                /** @description 子域名（与 code / tenant_id 三选一） */
                domain?: string | null;
                /** @description 租户主键雪花 id 字符串（与 code / domain 三选一） */
                tenant_id?: string | null;
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
    get_single_active_tenant_api_v1_tenant_registry_active_single_get: {
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
    list_memberships_api_v1_tenant_internal_memberships_get: {
        parameters: {
            query: {
                /** @description 归属租户主键（用户建号 / 登录所在租户） */
                owner_tenant_id: number;
                /** @description 用户主键（org 服务 sys_user.id） */
                user_id: number;
                /** @description 是否含 disabled 行（缺省只取有效行） */
                include_disabled?: boolean;
            };
            header?: {
                Authorization?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_TenantMembershipListResponse_"];
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
    ensure_membership_api_v1_tenant_internal_memberships_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantMembershipGrantRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_TenantMembershipListResponse_"];
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
    revoke_membership_api_v1_tenant_internal_memberships_delete: {
        parameters: {
            query: {
                /** @description 归属租户主键（用户建号 / 登录所在租户） */
                owner_tenant_id: number;
                /** @description 用户主键（org 服务 sys_user.id） */
                user_id: number;
                /** @description 目标租户主键（省略＝回收该用户全部） */
                target_tenant_id?: number | null;
            };
            header?: {
                Authorization?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_TenantMembershipListResponse_"];
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
    module_status_api_v1_tenant_internal_modules_status_get: {
        parameters: {
            query: {
                /** @description 租户主键 */
                tenant_id: number;
            };
            header?: {
                Authorization?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_ModuleStatusResponse_"];
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
    check_quota_api_v1_tenant_internal_quotas_check_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["QuotaConsumeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_QuotaResult_"];
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
    consume_quota_api_v1_tenant_internal_quotas_consume_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["QuotaConsumeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_QuotaResult_"];
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
    release_quota_api_v1_tenant_internal_quotas_release_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["QuotaReleaseRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_QuotaResult_"];
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
    list_tenants_api_v1_tenants_get: {
        parameters: {
            query?: {
                /** @description 租户编码（模糊） */
                code?: string | null;
                /** @description 租户名称（模糊） */
                name?: string | null;
                /** @description 状态筛选（provisioning/active/suspended） */
                status?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_TenantList_"];
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
    create_tenant_api_v1_tenants_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复开通回放首次结果） */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_TenantProvisionResult_"];
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
    tenant_brand_api_v1_tenants_brand_get: {
        parameters: {
            query?: {
                /** @description 租户编码（缺省当前租户） */
                code?: string | null;
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
    my_tenants_api_v1_tenants_mine_get: {
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
    module_options_api_v1_tenants_module_options_get: {
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
                    "application/json": components["schemas"]["ApiResponse_TenantModuleOptionList_"];
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
    switch_tenant_api_v1_tenants_switch_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复切换复用首次结果） */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantSwitchRequest"];
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
    get_tenant_api_v1_tenants__tenant_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 租户主键 */
                tenant_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_TenantDetail_"];
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
    update_tenant_api_v1_tenants__tenant_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 租户主键 */
                tenant_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_TenantDetail_"];
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
    activate_tenant_api_v1_tenants__tenant_id__activate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 租户主键 */
                tenant_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_TenantDetail_"];
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
    get_modules_api_v1_tenants__tenant_id__modules_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 租户主键 */
                tenant_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_TenantModuleItemList_"];
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
    put_module_api_v1_tenants__tenant_id__modules__module_key__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 租户主键 */
                tenant_id: number;
                /** @description 模块标识 */
                module_key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantModuleUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_TenantModuleItemList_"];
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
    get_quotas_api_v1_tenants__tenant_id__quotas_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 租户主键 */
                tenant_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_TenantQuotaItemList_"];
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
    put_quotas_api_v1_tenants__tenant_id__quotas_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 租户主键 */
                tenant_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantQuotaUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_TenantQuotaItemList_"];
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
    suspend_tenant_api_v1_tenants__tenant_id__suspend_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 租户主键 */
                tenant_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_TenantDetail_"];
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
