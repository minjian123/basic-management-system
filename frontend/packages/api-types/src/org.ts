/**
 * 服务契约生成类型：org
 *
 * 本文件由 `frontend/packages/api-types/scripts/generate.mjs` 生成，请勿手工修改。
 * 来源：deploy/contracts/org.json（服务契约快照，唯一事实源）。
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
    "/api/v1/org/dept-tree": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Org Dept Tree
         * @description 取部门树（一次性返回、不分页）。
         *
         *     Args:
         *         service: 组织查询契约。
         *         status: 状态过滤。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为部门树根节点序列。
         */
        get: operations["get_org_dept_tree_api_v1_org_dept_tree_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/internal/account-locks/scan-inactive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Scan Inactive
         * @description 扫描并锁定长期未登录账号（幂等；含从未登录账号）。
         *
         *     Args:
         *         req: 扫描请求（空体）。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数（读 `account.inactive_lock_days`）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为扫描概要（`InactiveScanResult`）。
         */
        post: operations["scan_inactive_api_v1_org_internal_account_locks_scan_inactive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/internal/credentials/login-state": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Apply Login State
         * @description 写回登录态（成功清零并记录登录时间；失败累计并锁定）。
         *
         *     Args:
         *         req: 登录态写回请求。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希实现（未使用，保持服务构造一致）。
         *         policy: 密码策略（未使用，保持服务构造一致）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为登录态结果（`LoginStateResult`）。
         */
        post: operations["apply_login_state_api_v1_org_internal_credentials_login_state_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/internal/credentials/update-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Update Password
         * @description 更新账号密码（策略闸门：复杂度 + 历史重复；写新哈希 + 变更时间 + 历史）。
         *
         *     Args:
         *         req: 密码更新请求。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希实现。
         *         policy: 密码策略（复杂度 / 历史）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新结果（`UpdatePasswordResult`）。
         */
        post: operations["update_password_api_v1_org_internal_credentials_update_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/internal/credentials/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Verify Credential
         * @description 校验账号口令（命中且参数过期时同请求内重哈希回写）。
         *
         *     Args:
         *         req: 凭据校验请求（账号 + 口令）。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希实现。
         *         policy: 密码策略（判定是否超有效期置强制改密）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为校验结果（`CredentialVerifyResult`）。
         */
        post: operations["verify_credential_api_v1_org_internal_credentials_verify_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/internal/users/create": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create User
         * @description 统一建号入口（用户名空闲即建；撞名 `created=false`，由调用侧换后缀重试）。
         *
         *     建号成功后经关系数据源维护「用户↔归属租户」可达关系（失败不阻断建号）。
         *
         *     Args:
         *         req: 建号请求（账号 / 昵称 / 语言时区 / 来源）。
         *         uow: 请求级工作单元。
         *         tenant: 解析链租户上下文（归属租户）。
         *         membership: 关系数据源（服务间调用；本服务为远端实现）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为建号结果（`UserCreateResult`）。
         */
        post: operations["create_user_api_v1_org_internal_users_create_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/internal/users/profile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * User Profile
         * @description 按主键取用户概要（不存在 `found=false`，由调用侧判定错误语义）。
         *
         *     Args:
         *         req: 概要查询请求（用户主键）。
         *         uow: 请求级工作单元。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为概要结果（`UserProfileResult`）。
         */
        post: operations["user_profile_api_v1_org_internal_users_profile_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/internal/users/reset-target": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reset Target
         * @description 按标识（账号 / 手机 / 邮箱）解析找回密码投递目标（不存在 / 不可送达由调用侧统一防枚举处理）。
         *
         *     Args:
         *         req: 重置目标查询请求（标识）。
         *         uow: 请求级工作单元。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为解析结果（`UserResetTargetResult`）。
         */
        post: operations["reset_target_api_v1_org_internal_users_reset_target_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/locks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Locks
         * @description 锁定记录列表（筛选 + 分页）。
         *
         *     Args:
         *         query: 分页与排序参数。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数。
         *         user_id: 用户主键（精确）。
         *         lock_type: 锁定类型（精确）。
         *         active: 是否生效中。
         *         locked_from: 锁定时间下界（UTC）。
         *         locked_to: 锁定时间上界（UTC）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页锁定记录列表。
         */
        get: operations["list_locks_api_v1_org_locks_get"];
        put?: never;
        /**
         * Lock Account
         * @description 手动锁定账号（`manual` 型；已生效锁幂等返回既有）。
         *
         *     Args:
         *         req: 手动锁定请求（用户主键 + 原因）。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数。
         *         audit: 审计捕获（占位）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为锁定记录行。
         */
        post: operations["lock_account_api_v1_org_locks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/locks/{lock_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Lock
         * @description 锁定记录详情（含已解锁）。
         *
         *     Args:
         *         lock_id: 锁定记录主键。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为锁定记录行。
         */
        get: operations["get_lock_api_v1_org_locks__lock_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/locks/{lock_id}/unlock": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Unlock Account
         * @description 手动解锁（清账号锁定状态 + 回填解锁信息 + 留痕）。
         *
         *     Args:
         *         lock_id: 锁定记录主键。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数。
         *         audit: 审计捕获（占位）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为解锁后的锁定记录行。
         */
        put: operations["unlock_account_api_v1_org_locks__lock_id__unlock_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/posts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Org Posts
         * @description 查询组织岗位（关键字 / 部门 / 含子级 / 状态 / 分页）。
         *
         *     Args:
         *         service: 组织查询契约。
         *         keyword: 关键字。
         *         dept_id: 归属部门 ID。
         *         include_children: 部门过滤是否含下级。
         *         status: 状态过滤。
         *         page: 页码。
         *         size: 每页条数。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页岗位。
         */
        get: operations["list_org_posts_api_v1_org_posts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/resolve-names": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Resolve Org Names
         * @description 按 id 批量回显名称（避免 N+1）。
         *
         *     Args:
         *         service: 组织回显契约。
         *         id_in: 逗号分隔的 id 列表。
         *         target: 目标类型。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为回显项序列。
         */
        get: operations["resolve_org_names_api_v1_org_resolve_names_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Org Users
         * @description 查询组织用户（关键字 / 部门 / 含子级 / 状态 / 分页）。
         *
         *     Args:
         *         service: 组织查询契约。
         *         keyword: 关键字。
         *         dept_id: 归属部门 ID。
         *         include_children: 部门过滤是否含下级。
         *         status: 状态过滤。
         *         page: 页码。
         *         size: 每页条数。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页用户。
         */
        get: operations["list_org_users_api_v1_org_users_get"];
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
        /** ApiResponse[BasePageResponse[LockItem]] */
        ApiResponse_BasePageResponse_LockItem__: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BasePageResponse_LockItem_"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[CredentialVerifyResult] */
        ApiResponse_CredentialVerifyResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["CredentialVerifyResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[InactiveScanResult] */
        ApiResponse_InactiveScanResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["InactiveScanResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[LockItem] */
        ApiResponse_LockItem_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["LockItem"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[LoginStateResult] */
        ApiResponse_LoginStateResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["LoginStateResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UpdatePasswordResult] */
        ApiResponse_UpdatePasswordResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UpdatePasswordResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UserCreateResult] */
        ApiResponse_UserCreateResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserCreateResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UserProfileResult] */
        ApiResponse_UserProfileResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserProfileResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UserResetTargetResult] */
        ApiResponse_UserResetTargetResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserResetTargetResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** BasePageResponse[LockItem] */
        BasePageResponse_LockItem_: {
            /** List */
            list: components["schemas"]["LockItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /**
         * CredentialUserSummary
         * @description 登录成功所需的最小用户概要。
         */
        CredentialUserSummary: {
            /**
             * Id
             * @description 用户 ID
             */
            id: string;
            /**
             * Locale
             * @description 语言偏好
             */
            locale?: string | null;
            /**
             * Name
             * @description 昵称 / 显示名
             */
            name: string;
            /**
             * Pwd Changed At
             * @description 密码最近变更时间（UTC）
             */
            pwd_changed_at?: string | null;
            /**
             * Timezone
             * @description 时区偏好
             */
            timezone?: string | null;
            /**
             * Username
             * @description 登录账号
             */
            username: string;
        };
        /**
         * CredentialVerifyRequest
         * @description 凭据校验请求（账号 + 密码明文；租户经服务 JWT `tenant` claim 解析）。
         */
        CredentialVerifyRequest: {
            /**
             * Account
             * @description 登录账号
             */
            account: string;
            /**
             * Password
             * @description 口令明文
             */
            password: string;
        };
        /**
         * CredentialVerifyResult
         * @description 凭据校验结果（登录侧统一映射为认证错误码，不直出内部差异）。
         */
        CredentialVerifyResult: {
            /**
             * Found
             * @description 账号是否存在
             */
            found: boolean;
            /**
             * Locked
             * @description 账号是否处于锁定期
             */
            locked: boolean;
            /**
             * Pwd Reset Required
             * @description 是否需强制改密（密码超有效期）
             * @default false
             */
            pwd_reset_required: boolean;
            /**
             * Rehashed
             * @description 是否本次按当前参数重算了哈希
             * @default false
             */
            rehashed: boolean;
            /**
             * Status
             * @description 账号状态（enabled/disabled）
             */
            status: string;
            /** @description 用户概要（命中时） */
            user?: components["schemas"]["CredentialUserSummary"] | null;
            /**
             * Valid
             * @description 口令是否匹配
             */
            valid: boolean;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * InactiveScanRequest
         * @description 不活跃账号扫描请求（空体；租户经服务 JWT `tenant` claim 解析）。
         */
        InactiveScanRequest: Record<string, never>;
        /**
         * InactiveScanResult
         * @description 不活跃账号扫描结果。
         */
        InactiveScanResult: {
            /**
             * Locked
             * @description 本次锁定账号数
             */
            locked: number;
            /**
             * Scanned
             * @description 扫描候选账号数
             */
            scanned: number;
        };
        /**
         * LockItem
         * @description 锁定记录行契约（列表 / 详情 / 手动锁定 / 解锁统一）。
         */
        LockItem: {
            /**
             * Expire At
             * @description 锁定到期时间（UTC；NULL=需手动解锁）
             */
            expire_at?: string | null;
            /**
             * Id
             * @description 锁定记录主键
             */
            id: string;
            /**
             * Lock Type
             * @description 锁定类型（fail_limit/inactive/manual）
             */
            lock_type: string;
            /**
             * Locked At
             * Format: date-time
             * @description 锁定时间（UTC）
             */
            locked_at: string;
            /**
             * Locked By
             * @description 锁定操作人（系统触发为 NULL）
             */
            locked_by?: number | null;
            /**
             * Reason
             * @description 锁定原因
             */
            reason?: string | null;
            /**
             * Unlock At
             * @description 解锁时间（UTC；NULL=未解锁）
             */
            unlock_at?: string | null;
            /**
             * Unlock By
             * @description 解锁操作人（自动解锁为 NULL）
             */
            unlock_by?: number | null;
            /**
             * Unlock Mode
             * @description 解锁方式（manual/auto；NULL=未解锁）
             */
            unlock_mode?: string | null;
            /**
             * User Id
             * @description 用户主键
             */
            user_id: string;
        };
        /**
         * LoginStateRequest
         * @description 登录态写回请求（成功清零 / 失败计数与锁定）。
         */
        LoginStateRequest: {
            /**
             * Account
             * @description 登录账号
             */
            account: string;
            /**
             * Failed Count
             * @description 失败计数（失败时由登录侧传入）
             */
            failed_count?: number | null;
            /**
             * Lock Seconds
             * @description 锁定时长（秒；>0 且失败时写 locked_until）
             */
            lock_seconds?: number | null;
            /**
             * Success
             * @description 本次登录是否成功
             */
            success: boolean;
        };
        /**
         * LoginStateResult
         * @description 登录态写回结果。
         */
        LoginStateResult: {
            /**
             * Failed Count
             * @description 当前失败计数
             */
            failed_count: number;
            /**
             * Last Login At
             * @description 最近登录时间（UTC）
             */
            last_login_at?: string | null;
            /**
             * Locked Until
             * @description 锁定到期时间（UTC）
             */
            locked_until?: string | null;
        };
        /**
         * ManualLockRequest
         * @description 手动锁定请求（写 `manual` 型；租户经登录态解析）。
         */
        ManualLockRequest: {
            /**
             * Reason
             * @description 锁定原因
             * @default
             */
            reason: string;
            /**
             * User Id
             * @description 用户主键
             */
            user_id: number;
        };
        /**
         * UpdatePasswordRequest
         * @description 密码更新请求（改密 / 找回密码 / 重哈希回写）。
         */
        UpdatePasswordRequest: {
            /**
             * Account
             * @description 登录账号
             */
            account: string;
            /**
             * Keep History
             * @description 保留历史密码条数（缺省取策略 history_count）
             */
            keep_history?: number | null;
            /**
             * New Password
             * @description 新口令明文
             */
            new_password: string;
        };
        /**
         * UpdatePasswordResult
         * @description 密码更新结果（策略闸门：复杂度 30005 / 历史重复 30006 由调用侧映射）。
         */
        UpdatePasswordResult: {
            /**
             * Reason
             * @description 未更新原因（空=成功；not_found / policy_violation / history_reused）
             * @default
             */
            reason: string;
            /**
             * Updated
             * @description 是否更新成功
             */
            updated: boolean;
            /**
             * Violations
             * @description 复杂度违规原因码清单（reason=policy_violation 时）
             */
            violations?: string[];
        };
        /**
         * UserCreateRequest
         * @description 建号请求（账号 / 昵称 / 语言时区 / 来源；租户经服务 JWT `tenant` claim 解析）。
         */
        UserCreateRequest: {
            /**
             * Locale
             * @description 语言偏好（可空）
             */
            locale?: string | null;
            /**
             * Name
             * @description 昵称 / 显示名
             */
            name: string;
            /**
             * Source
             * @description 建号来源（缺省 sso_jit；其余建号路径显式传 admin_create / import / self_register / super_admin）
             * @default sso_jit
             */
            source: string;
            /**
             * Timezone
             * @description 时区偏好（可空）
             */
            timezone?: string | null;
            /**
             * Username
             * @description 登录账号（调用侧已清洗）
             */
            username: string;
        };
        /**
         * UserCreateResult
         * @description JIT 建号结果（撞名 `created=false` + `reason=username_conflict`，由调用侧换后缀重试）。
         */
        UserCreateResult: {
            /**
             * Created
             * @description 是否建号成功
             */
            created: boolean;
            /**
             * Reason
             * @description 未建号原因（username_conflict）
             */
            reason?: string | null;
            /** @description 新建用户概要（created=true 时返回） */
            user?: components["schemas"]["UserProfileUser"] | null;
        };
        /**
         * UserProfileRequest
         * @description 用户概要查询请求（按主键；租户经服务 JWT `tenant` claim 解析）。
         */
        UserProfileRequest: {
            /**
             * User Id
             * @description 用户主键
             */
            user_id: number;
        };
        /**
         * UserProfileResult
         * @description 用户概要查询结果（不存在时 `found=false`，由调用侧判定错误语义）。
         */
        UserProfileResult: {
            /**
             * Found
             * @description 用户是否存在
             */
            found: boolean;
            /** @description 用户概要（found=true 时返回） */
            user?: components["schemas"]["UserProfileUser"] | null;
        };
        /**
         * UserProfileUser
         * @description 用户概要（SSO 回调定位用户后取展示信息与状态）。
         */
        UserProfileUser: {
            /**
             * Id
             * @description 用户 ID
             */
            id: string;
            /**
             * Locale
             * @description 语言偏好
             */
            locale?: string | null;
            /**
             * Name
             * @description 昵称 / 显示名
             */
            name: string;
            /**
             * Pwd Reset Required
             * @description 是否需强制改密（密码超有效期）
             * @default false
             */
            pwd_reset_required: boolean;
            /**
             * Status
             * @description 账号状态（enabled / disabled）
             */
            status: string;
            /**
             * Timezone
             * @description 时区偏好
             */
            timezone?: string | null;
            /**
             * Username
             * @description 登录账号
             */
            username: string;
        };
        /**
         * UserResetTargetRequest
         * @description 找回密码重置目标查询请求（账号 / 手机 / 邮箱；租户经服务 JWT `tenant` claim 解析）。
         */
        UserResetTargetRequest: {
            /**
             * Identifier
             * @description 账号 / 手机号 / 邮箱
             */
            identifier: string;
        };
        /**
         * UserResetTargetResult
         * @description 重置目标解析结果（通道与目标供 identity 侧通知投递；不可送达以 `deliverable=false` 表达）。
         */
        UserResetTargetResult: {
            /**
             * Account
             * @description 登录账号（found=true 时返回）
             * @default
             */
            account: string;
            /**
             * Channel
             * @description 投递通道（email / sms；无可用通道为空串）
             * @default
             */
            channel: string;
            /**
             * Deliverable
             * @description 是否可送达（启用且有可用通道）
             * @default false
             */
            deliverable: boolean;
            /**
             * Found
             * @description 账号是否存在（未软删）
             * @default false
             */
            found: boolean;
            /**
             * Target
             * @description 投递目标（原始邮箱 / 手机号；内部契约，不对外回显）
             * @default
             */
            target: string;
            /**
             * User Id
             * @description 用户主键（found=true 时返回）
             */
            user_id?: string | null;
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
    get_org_dept_tree_api_v1_org_dept_tree_get: {
        parameters: {
            query?: {
                /** @description 状态过滤（enabled / disabled） */
                status?: string | null;
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
    scan_inactive_api_v1_org_internal_account_locks_scan_inactive_post: {
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
                "application/json": components["schemas"]["InactiveScanRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_InactiveScanResult_"];
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
    apply_login_state_api_v1_org_internal_credentials_login_state_post: {
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
                "application/json": components["schemas"]["LoginStateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_LoginStateResult_"];
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
    update_password_api_v1_org_internal_credentials_update_password_post: {
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
                "application/json": components["schemas"]["UpdatePasswordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UpdatePasswordResult_"];
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
    verify_credential_api_v1_org_internal_credentials_verify_post: {
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
                "application/json": components["schemas"]["CredentialVerifyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_CredentialVerifyResult_"];
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
    create_user_api_v1_org_internal_users_create_post: {
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
                "application/json": components["schemas"]["UserCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserCreateResult_"];
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
    user_profile_api_v1_org_internal_users_profile_post: {
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
                "application/json": components["schemas"]["UserProfileRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserProfileResult_"];
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
    reset_target_api_v1_org_internal_users_reset_target_post: {
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
                "application/json": components["schemas"]["UserResetTargetRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserResetTargetResult_"];
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
    list_locks_api_v1_org_locks_get: {
        parameters: {
            query?: {
                /** @description 用户主键（精确） */
                user_id?: number | null;
                /** @description 锁定类型（fail_limit/inactive/manual） */
                lock_type?: string | null;
                /** @description 是否生效中（未解锁且未到期；缺省=全部） */
                active?: boolean | null;
                /** @description 锁定时间下界（UTC，闭区间） */
                locked_from?: string | null;
                /** @description 锁定时间上界（UTC，闭区间） */
                locked_to?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_LockItem__"];
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
    lock_account_api_v1_org_locks_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ManualLockRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_LockItem_"];
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
    get_lock_api_v1_org_locks__lock_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                lock_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_LockItem_"];
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
    unlock_account_api_v1_org_locks__lock_id__unlock_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                lock_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_LockItem_"];
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
    list_org_posts_api_v1_org_posts_get: {
        parameters: {
            query?: {
                /** @description 关键字（岗位编码 / 名称） */
                keyword?: string | null;
                /** @description 归属部门 ID */
                dept_id?: number | null;
                /** @description 部门过滤是否含下级 */
                include_children?: boolean;
                /** @description 状态过滤（enabled / disabled） */
                status?: string | null;
                /** @description 页码（从 1 起） */
                page?: number;
                /** @description 每页条数 */
                size?: number;
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
    resolve_org_names_api_v1_org_resolve_names_get: {
        parameters: {
            query: {
                /** @description 对象 ID 列表（逗号分隔，如 1,2,3） */
                id_in: string;
                /** @description 目标类型（user / post / dept） */
                target?: string;
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
    list_org_users_api_v1_org_users_get: {
        parameters: {
            query?: {
                /** @description 关键字（用户名 / 昵称 / 手机号） */
                keyword?: string | null;
                /** @description 归属部门 ID */
                dept_id?: number | null;
                /** @description 部门过滤是否含下级 */
                include_children?: boolean;
                /** @description 状态过滤（enabled / disabled） */
                status?: string | null;
                /** @description 页码（从 1 起） */
                page?: number;
                /** @description 每页条数 */
                size?: number;
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
