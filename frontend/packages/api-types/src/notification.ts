/**
 * 服务契约生成类型：notification
 *
 * 本文件由 `frontend/packages/api-types/scripts/generate.mjs` 生成，请勿手工修改。
 * 来源：deploy/contracts/notification.json（服务契约快照，唯一事实源）。
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
    "/api/v1/notifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Notifications
         * @description 列当前用户通知（筛选 + 分页）。
         *
         *     Args:
         *         center: 通知中心。
         *         filter: 筛选契约。
         *         page: 分页契约。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页通知。
         */
        get: operations["list_notifications_api_v1_notifications_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Mark Notifications Read
         * @description 按 id 批量标记已读（返回操作后未读总数供前端校准角标）。
         *
         *     Args:
         *         center: 通知中心。
         *         req: 批量已读请求。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{count}`（操作后未读总数）。
         */
        post: operations["mark_notifications_read_api_v1_notifications_read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/read-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Mark All Notifications Read
         * @description 全部标记已读（返回操作后未读总数，恒 0）。
         *
         *     Args:
         *         center: 通知中心。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{count}`。
         */
        post: operations["mark_all_notifications_read_api_v1_notifications_read_all_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/unread-count": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Unread Count
         * @description 当前未读总数（服务端唯一口径）。
         *
         *     Args:
         *         center: 通知中心。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{count}`。
         */
        get: operations["get_unread_count_api_v1_notifications_unread_count_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/{notification_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Notification Detail
         * @description 取通知详情（查看即已读）。
         *
         *     Args:
         *         center: 通知中心。
         *         notification_id: 通知 ID。
         *         mark_read: 命中是否标记已读。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为通知或 null。
         */
        get: operations["get_notification_detail_api_v1_notifications__notification_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Notification
         * @description 删除单条通知。
         *
         *     Args:
         *         center: 通知中心。
         *         notification_id: 通知 ID。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为是否删除到既有通知。
         */
        delete: operations["delete_notification_api_v1_notifications__notification_id__delete"];
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
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * NotificationReadRequest
         * @description 批量已读请求：待标记已读的通知 ID 列表。
         */
        NotificationReadRequest: {
            /**
             * Ids
             * @description 通知 ID 列表
             */
            ids?: number[];
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
    list_notifications_api_v1_notifications_get: {
        parameters: {
            query?: {
                /** @description 关键字（跨字段模糊，命中列由后端定义） */
                keyword?: string | null;
                /** @description 筛选条件 JSON（FilterSpec 数组） */
                filters?: string | null;
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
    mark_notifications_read_api_v1_notifications_read_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NotificationReadRequest"];
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
    mark_all_notifications_read_api_v1_notifications_read_all_post: {
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
    get_unread_count_api_v1_notifications_unread_count_get: {
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
    get_notification_detail_api_v1_notifications__notification_id__get: {
        parameters: {
            query?: {
                /** @description 命中是否标记已读（默认 true，查看即已读） */
                mark_read?: boolean;
            };
            header?: never;
            path: {
                notification_id: number;
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
    delete_notification_api_v1_notifications__notification_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                notification_id: number;
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
