/**
 * 服务契约生成类型：txn
 *
 * 本文件由 `frontend/packages/api-types/scripts/generate.mjs` 生成，请勿手工修改。
 * 来源：deploy/contracts/txn.json（服务契约快照，唯一事实源）。
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
    "/api/v1/txn/global": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Begin Global Txn
         * @description 开启全局事务并分配各分支 `xid`。
         *
         *     Args:
         *         req: 开启请求（分支声明清单 + 可选超时）。
         *         uow: 请求级工作单元。
         *         token: 服务身份（`caller_service` 来源）。
         *         request: 请求对象（取分支驱动）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为全局事务视图。
         */
        post: operations["begin_global_txn_api_v1_txn_global_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/txn/global/{global_txn_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Global Txn
         * @description 查询全局事务状态。
         *
         *     Args:
         *         global_txn_id: 全局事务标识。
         *         uow: 请求级工作单元。
         *         token: 服务身份（占位）。
         *         request: 请求对象（取分支驱动）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为全局事务视图。
         */
        get: operations["get_global_txn_api_v1_txn_global__global_txn_id__get"];
        put?: never;
        post?: never;
        /**
         * Rollback Global Txn
         * @description 请求回滚（决定点之前有效；之后由 TM 幂等吸收）。
         *
         *     Args:
         *         global_txn_id: 全局事务标识。
         *         uow: 请求级工作单元。
         *         token: 服务身份（占位）。
         *         request: 请求对象（取分支驱动）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为全局事务视图。
         */
        delete: operations["rollback_global_txn_api_v1_txn_global__global_txn_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/txn/global/{global_txn_id}/commit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Commit Global Txn
         * @description 请求提交（TM 核验全部分支 `prepared` 后落决定点并逐分支提交）。
         *
         *     Args:
         *         global_txn_id: 全局事务标识。
         *         uow: 请求级工作单元。
         *         token: 服务身份（占位：TM 不校验发起方一致性，由服务身份通道保证）。
         *         request: 请求对象（取分支驱动）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为全局事务视图。
         */
        post: operations["commit_global_txn_api_v1_txn_global__global_txn_id__commit_post"];
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
        /** ApiResponse[GlobalTxnView] */
        ApiResponse_GlobalTxnView_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["GlobalTxnView"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /**
         * BeginGlobalTxnRequest
         * @description 开启全局事务请求（`caller_service` 取自服务身份，不由请求体声明）。
         */
        BeginGlobalTxnRequest: {
            /**
             * Branches
             * @description 分支声明清单（非空）
             */
            branches?: components["schemas"]["BranchSpecRequest"][];
            /**
             * Timeout Seconds
             * @description 全局提交截止（秒）；缺省取 `[transaction_manager].deadline_seconds`
             */
            timeout_seconds?: number | null;
        };
        /**
         * BranchSpecRequest
         * @description 分支声明（调用方给出；TM 只作寻址）。
         */
        BranchSpecRequest: {
            /**
             * Branch Id
             * @description 分支标识（同一全局事务内唯一；同时作为 XA `bqual`）
             */
            branch_id: string;
            /**
             * Db Key
             * @description **不透明库键**（平台 / 租户 / 归档库均可）
             */
            db_key: string;
            /**
             * Service
             * @description 参与方服务键（分支执行端点的服务身份）
             */
            service: string;
        };
        /**
         * BranchView
         * @description 分支视图（含 `xid` 与驱动痕迹）。
         */
        BranchView: {
            /**
             * Branch Id
             * @description 分支标识
             */
            branch_id: string;
            /**
             * Db Key
             * @description 不透明库键
             */
            db_key: string;
            /**
             * Last Error
             * @description 最近一次驱动失败原因
             */
            last_error?: string | null;
            /**
             * Retry Count
             * @description TM 驱动重试次数
             */
            retry_count: number;
            /**
             * Service
             * @description 参与方服务键
             */
            service: string;
            /**
             * State
             * @description 分支状态（active / prepared / committed / rolled_back / rejected）
             */
            state: string;
            /**
             * Xid
             * @description XA 事务标识（由 TM 生成）
             */
            xid: string;
        };
        /**
         * GlobalTxnView
         * @description 全局事务视图（`begin` / `commit` / `rollback` / `status` 统一返回）。
         */
        GlobalTxnView: {
            /**
             * Branches
             * @description 分支清单
             */
            branches?: components["schemas"]["BranchView"][];
            /**
             * Caller Service
             * @description 发起方服务键
             */
            caller_service: string;
            /**
             * Deadline At
             * @description 提交决定截止时间（UTC）
             */
            deadline_at?: string | null;
            /**
             * Decided At
             * @description 提交决定点时间（UTC；非空即已过决定点）
             */
            decided_at?: string | null;
            /**
             * Global Txn Id
             * @description 全局事务标识（同时作为 XA `gtrid`）
             */
            global_txn_id: string;
            /**
             * State
             * @description 全局事务状态（TXN_*）
             */
            state: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
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
    begin_global_txn_api_v1_txn_global_post: {
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
                "application/json": components["schemas"]["BeginGlobalTxnRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_GlobalTxnView_"];
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
    get_global_txn_api_v1_txn_global__global_txn_id__get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
            };
            path: {
                global_txn_id: string;
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
                    "application/json": components["schemas"]["ApiResponse_GlobalTxnView_"];
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
    rollback_global_txn_api_v1_txn_global__global_txn_id__delete: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
            };
            path: {
                global_txn_id: string;
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
                    "application/json": components["schemas"]["ApiResponse_GlobalTxnView_"];
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
    commit_global_txn_api_v1_txn_global__global_txn_id__commit_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
            };
            path: {
                global_txn_id: string;
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
                    "application/json": components["schemas"]["ApiResponse_GlobalTxnView_"];
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
