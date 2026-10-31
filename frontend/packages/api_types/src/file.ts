/**
 * 服务契约生成类型：file
 *
 * 本文件由 `frontend/packages/api_types/scripts/generate.mjs` 生成，请勿手工修改。
 * 来源：deploy/contracts/file.json（服务契约快照，唯一事实源）。
 * 重新生成：pnpm run api_types:gen
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
    "/api/v1/files": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Files
         * @description 文件列表（名称 / 类型 / 上传人 / 状态 / 时间范围筛选 + 分页）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         page: 分页参数。
         *         name: 名称关键字。
         *         mime_type: 内容类型前缀。
         *         uploader_id: 上传人。
         *         status: 状态。
         *         created_from: 创建时间下限。
         *         created_to: 创建时间上限。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页结果。
         */
        get: operations["list_files_api_v1_files_get"];
        put?: never;
        /**
         * Upload File
         * @description 整包上传（≤ `file.upload.max_size`；类型白名单 + 大小 + 配额校验）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         file: 上传文件。
         *         name: 覆盖文件名（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `UploadResult`。
         */
        post: operations["upload_file_api_v1_files_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/dedup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Dedup
         * @description 秒传登记（同租户命中既有对象即建行；未命中 data 为 null）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         request: 秒传请求。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `DedupResult` 或 null。
         */
        post: operations["dedup_api_v1_files_dedup_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/internal/cleanup-orphans": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cleanup Orphans
         * @description 孤儿回收（服务间内部端点；由内置任务 `cleanup_orphan_parts` 触发）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         limit: 单批上限。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `CleanupResult`。
         */
        post: operations["cleanup_orphans_api_v1_files_internal_cleanup_orphans_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/multipart": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Initiate Multipart
         * @description 分片上传初始化（返回会话标识 / 分片大小 / 分片总数 / 过期时间；可按幂等键复用）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         idempotency: 幂等存储。
         *         request: 初始化请求。
         *         idempotency_key: 幂等键（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `MultipartInitiateResult`。
         */
        post: operations["initiate_multipart_api_v1_files_multipart_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/multipart/{upload_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Multipart Status
         * @description 断点续传状态（已上传 / 缺失分片序号）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         upload_id: 会话标识。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `MultipartStatusResult`。
         */
        get: operations["multipart_status_api_v1_files_multipart__upload_id__get"];
        put?: never;
        post?: never;
        /**
         * Abort Multipart
         * @description 取消上传会话（清分片对象与分片行，状态置 failed）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         upload_id: 会话标识。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["abort_multipart_api_v1_files_multipart__upload_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/multipart/{upload_id}/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Complete Multipart
         * @description 合并分片为最终对象（幂等：已完成的重复调用回既有结果）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         upload_id: 会话标识。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `MultipartCompleteResult`。
         */
        post: operations["complete_multipart_api_v1_files_multipart__upload_id__complete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/multipart/{upload_id}/parts/{part_no}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Upload Part
         * @description 上传单个分片（服务端复算 SHA256 与请求头比对；同片重传为覆盖写）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         upload_id: 会话标识。
         *         part_no: 分片序号。
         *         part_sha256: 分片 SHA256（请求头）。
         *         data: 分片内容。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `MultipartPartResult`。
         */
        put: operations["upload_part_api_v1_files_multipart__upload_id__parts__part_no__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{file_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete File
         * @description 删除文件（软删元数据；对象保留、配额不释放，物理清理归 13_01）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         file_id: 文件主键。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["delete_file_api_v1_files__file_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{file_id}/download-url": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download Url
         * @description 取限时预签名下载地址（后端不代理文件流；过期即不可下载）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         file_id: 文件主键。
         *         expires_in: 期望有效期（秒）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `PresignResult`。
         */
        get: operations["download_url_api_v1_files__file_id__download_url_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{file_id}/preview-url": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Preview Url
         * @description 取限时预签名预览地址（仅图片 / PDF 直开）。
         *
         *     Args:
         *         uow: 工作单元。
         *         storage: 对象存储。
         *         multipart: 分片上传。
         *         config: 系统参数。
         *         client: 服务调用客户端。
         *         outbox: 发件箱。
         *         audit: 审计捕获器。
         *         metrics: 指标。
         *         file_id: 文件主键。
         *         expires_in: 期望有效期（秒）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `PresignResult`。
         */
        get: operations["preview_url_api_v1_files__file_id__preview_url_get"];
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
        /** Body_upload_file_api_v1_files_post */
        Body_upload_file_api_v1_files_post: {
            /**
             * File
             * @description 文件内容（表单字段 file）
             */
            file: string;
        };
        /** Body_upload_part_api_v1_files_multipart__upload_id__parts__part_no__put */
        Body_upload_part_api_v1_files_multipart__upload_id__parts__part_no__put: {
            /**
             * Data
             * @description 分片内容（表单字段 data）
             */
            data: string;
        };
        /**
         * DedupRequest
         * @description 秒传登记请求。
         */
        DedupRequest: {
            /**
             * Mime
             * @description 声明的内容类型（仅供预检）
             */
            mime?: string | null;
            /**
             * Name
             * @description 原始文件名（含扩展名）
             */
            name: string;
            /**
             * Sha256
             * @description 整文件 SHA256
             */
            sha256: string;
            /**
             * Size
             * @description 文件字节数
             */
            size: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * MultipartInitiateRequest
         * @description 分片初始化请求。
         */
        MultipartInitiateRequest: {
            /**
             * Mime
             * @description 声明的内容类型（仅供预检，不作真值）
             */
            mime?: string | null;
            /**
             * Name
             * @description 原始文件名（含扩展名）
             */
            name: string;
            /**
             * Sha256
             * @description 整文件 SHA256（64 位小写十六进制）
             */
            sha256: string;
            /**
             * Size
             * @description 文件字节数（须大于 0）
             */
            size: number;
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
    list_files_api_v1_files_get: {
        parameters: {
            query?: {
                /** @description 文件名关键字（模糊匹配） */
                name?: string | null;
                /** @description 内容类型前缀（如 image/） */
                mime_type?: string | null;
                /** @description 上传人 */
                uploader_id?: number | null;
                /** @description 状态（uploading/completed/failed/orphan） */
                status?: string | null;
                /** @description 创建时间下限（含） */
                created_from?: string | null;
                /** @description 创建时间上限（含） */
                created_to?: string | null;
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
    upload_file_api_v1_files_post: {
        parameters: {
            query?: {
                /** @description 覆盖文件名（可选，缺省取上传文件名） */
                name?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_file_api_v1_files_post"];
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
    dedup_api_v1_files_dedup_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DedupRequest"];
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
    cleanup_orphans_api_v1_files_internal_cleanup_orphans_post: {
        parameters: {
            query?: {
                /** @description 单批清理上限 */
                limit?: number | null;
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
    initiate_multipart_api_v1_files_multipart_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复初始化复用首次会话） */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MultipartInitiateRequest"];
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
    multipart_status_api_v1_files_multipart__upload_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 上传会话标识 */
                upload_id: string;
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
    abort_multipart_api_v1_files_multipart__upload_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 上传会话标识 */
                upload_id: string;
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
    complete_multipart_api_v1_files_multipart__upload_id__complete_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 上传会话标识 */
                upload_id: string;
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
    upload_part_api_v1_files_multipart__upload_id__parts__part_no__put: {
        parameters: {
            query?: never;
            header: {
                /** @description 该分片 SHA256（64 位小写十六进制） */
                "X-Part-Sha256": string;
            };
            path: {
                /** @description 上传会话标识 */
                upload_id: string;
                /** @description 分片序号（从 1 起） */
                part_no: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_part_api_v1_files_multipart__upload_id__parts__part_no__put"];
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
    delete_file_api_v1_files__file_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 文件主键 */
                file_id: number;
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
    download_url_api_v1_files__file_id__download_url_get: {
        parameters: {
            query?: {
                /** @description 期望有效期（秒；不得超过参数上限） */
                expires_in?: number | null;
            };
            header?: never;
            path: {
                /** @description 文件主键 */
                file_id: number;
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
    preview_url_api_v1_files__file_id__preview_url_get: {
        parameters: {
            query?: {
                /** @description 期望有效期（秒；不得超过参数上限） */
                expires_in?: number | null;
            };
            header?: never;
            path: {
                /** @description 文件主键 */
                file_id: number;
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
