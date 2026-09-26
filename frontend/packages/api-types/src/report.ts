/**
 * 服务契约生成类型：report
 *
 * 本文件由 `frontend/packages/api-types/scripts/generate.mjs` 生成，请勿手工修改。
 * 来源：deploy/contracts/report.json（服务契约快照，唯一事实源）。
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
    "/api/v1/prints/batch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Batch Print
         * @description 批量打印多单据（可按幂等键复用首次结果）。
         *
         *     Args:
         *         exporter: 打印导出基座。
         *         idempotency: 幂等基座（首次结果复用）。
         *         tenant: 解析链租户上下文（幂等键作用域位）。
         *         req: 批量请求（模板键 / 单据键集合 / 批量模式 / 渲染选项）。
         *         idempotency_key: 幂等键请求头（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为批量结果（`PrintBatchResponse`）。
         */
        post: operations["batch_print_api_v1_prints_batch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prints/exports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Pdf
         * @description 导出单条单据 PDF（可按幂等键复用首次结果）。
         *
         *     Args:
         *         exporter: 打印导出基座。
         *         idempotency: 幂等基座（首次结果复用）。
         *         tenant: 解析链租户上下文（幂等键作用域位）。
         *         req: 导出请求（模板键 / 单据数据 / 渲染选项）。
         *         idempotency_key: 幂等键请求头（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为导出产物（`PrintExportResponse`）。
         */
        post: operations["export_pdf_api_v1_prints_exports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prints/templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Templates
         * @description 取打印模板清单（可按单据类型过滤）。
         *
         *     Args:
         *         provider: 打印模板来源基座。
         *         biz_type: 单据类型查询参数（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为模板清单（`PrintTemplateListResponse`）。
         */
        get: operations["list_templates_api_v1_prints_templates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/prints/templates/{template_key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Template
         * @description 取单模板定义（变量清单）。
         *
         *     Args:
         *         provider: 打印模板来源基座。
         *         template_key: 打印模板键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为模板定义（`PrintTemplateInfoResponse`）。
         */
        get: operations["get_template_api_v1_prints_templates__template_key__get"];
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
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * PrintBatchRequest
         * @description 批量打印请求：`{template_key, keys, mode?, options?}`。
         */
        PrintBatchRequest: {
            /**
             * Keys
             * @description 单据键集合（至少一条）
             */
            keys: string[];
            /**
             * Mode
             * @description 批量模式（separate 逐份 / merged 合并）
             * @default separate
             */
            mode: string;
            /** @description 渲染选项（缺省取平台缺省） */
            options?: components["schemas"]["PrintOptionsPayload"] | null;
            /**
             * Template Key
             * @description 打印模板键
             */
            template_key: string;
        };
        /**
         * PrintDocumentPayload
         * @description 单据数据（单据键 + 主表字段 + 明细行）。
         */
        PrintDocumentPayload: {
            /**
             * Biz Key
             * @description 单据键（产物 key / 文件名派生用）
             */
            biz_key?: string | null;
            /**
             * Fields
             * @description 主表字段
             */
            fields?: {
                [key: string]: unknown;
            };
            /**
             * Rows
             * @description 明细行
             */
            rows?: {
                [key: string]: unknown;
            }[];
        };
        /**
         * PrintExportRequest
         * @description 单条导出 PDF 请求：`{template_key, document, options?}`。
         */
        PrintExportRequest: {
            /** @description 单据数据 */
            document: components["schemas"]["PrintDocumentPayload"];
            /** @description 渲染选项（缺省取平台缺省） */
            options?: components["schemas"]["PrintOptionsPayload"] | null;
            /**
             * Template Key
             * @description 打印模板键
             */
            template_key: string;
        };
        /**
         * PrintOptionsPayload
         * @description 渲染选项（纸张 / 方向 / 色调 / 水印 / 打印人）。
         */
        PrintOptionsPayload: {
            /**
             * Orientation
             * @description 纸张方向（portrait 纵向 / landscape 横向）
             * @default portrait
             */
            orientation: string;
            /**
             * Paper
             * @description 纸张（A4 / A5 / custom）
             * @default A4
             */
            paper: string;
            /**
             * Printed By
             * @description 打印人
             */
            printed_by?: string | null;
            /**
             * Tone
             * @description 打印色调（color 彩色 / mono 黑白）
             * @default color
             */
            tone: string;
            /**
             * Watermark
             * @description 水印文案
             * @default
             */
            watermark: string;
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
    batch_print_api_v1_prints_batch_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复导出 / 批量复用首次结果） */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PrintBatchRequest"];
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
    export_pdf_api_v1_prints_exports_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复导出 / 批量复用首次结果） */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PrintExportRequest"];
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
    list_templates_api_v1_prints_templates_get: {
        parameters: {
            query?: {
                /** @description 单据类型（缺省全部） */
                biz_type?: string | null;
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
    get_template_api_v1_prints_templates__template_key__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 打印模板键 */
                template_key: string;
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
