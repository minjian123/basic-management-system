/**
 * 服务契约生成类型：notification
 *
 * 本文件由 `frontend/packages/api_types/scripts/generate.mjs` 生成，请勿手工修改。
 * 来源：deploy/contracts/notification.json（服务契约快照，唯一事实源）。
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
         *     显式声明 `x-error-codes: []`：本端点不触达业务判定，没有产品码可声明
         *     （与探针同性质，区别于「漏声明」）。
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
    "/api/v1/mail/internal/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Internal Send
         * @description 内部发送（邮件 raw / 短信模板）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         dispatcher: 外发调度服务。
         *         req: 内部发送请求。
         *
         *     Returns:
         *         ApiResponse: 受理结果。
         *
         *     Raises:
         *         ParamError: 短信缺模板 / 邮件正文为空（10001）。
         */
        post: operations["internal_send_api_v1_mail_internal_send_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/mail/logs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Mail Logs
         * @description 邮件发送记录列表。
         */
        get: operations["list_mail_logs_api_v1_mail_logs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/mail/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send Mail
         * @description 发送邮件（异步：落日志 + 提交作业）。
         */
        post: operations["send_mail_api_v1_mail_send_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/mail/templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Mail Templates
         * @description 邮件模板合并列表。
         */
        get: operations["list_mail_templates_api_v1_mail_templates_get"];
        put?: never;
        /**
         * Create Mail Template
         * @description 新建邮件模板（code 与内置默认相同即覆盖）。
         */
        post: operations["create_mail_template_api_v1_mail_templates_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/mail/templates/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Preview Mail Template
         * @description 按 code 沙箱渲染（含内置默认；不发送）。
         */
        post: operations["preview_mail_template_api_v1_mail_templates_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/mail/templates/{template_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Mail Template
         * @description 邮件模板详情。
         */
        get: operations["get_mail_template_api_v1_mail_templates__template_id__get"];
        /**
         * Update Mail Template
         * @description 编辑邮件模板（code 不可改）。
         */
        put: operations["update_mail_template_api_v1_mail_templates__template_id__put"];
        post?: never;
        /**
         * Delete Mail Template
         * @description 软删除邮件模板（删除覆盖后回落内置默认）。
         */
        delete: operations["delete_mail_template_api_v1_mail_templates__template_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/mail/templates/{template_id}/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Test Mail Template
         * @description 按 id 沙箱渲染（不发送）。
         */
        post: operations["test_mail_template_api_v1_mail_templates__template_id__test_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notices": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Notices
         * @description 管理列表（无 `notice:update` 时只看发布中）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         registry: 选项集注册表。
         *         checker: 权限检查器（判定是否可见管理态）。
         *         page: 分页契约。
         *         locale: 显式语言。
         *         accept_language: 请求头语言。
         *         keyword: 标题关键字。
         *         status: 状态筛选。
         *         notice_type: 类型筛选。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页列表。
         */
        get: operations["list_notices_api_v1_notices_get"];
        put?: never;
        /**
         * Create Notice
         * @description 新建公告（草稿或直接发布）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         registry: 选项集注册表。
         *         req: 新建请求。
         *         locale: 显式语言（必填语言口径）。
         *         accept_language: 请求头语言。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为公告详情。
         */
        post: operations["create_notice_api_v1_notices_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notices/internal/expire": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Expire Notices
         * @description 过期扫描：批量置下线并发布 `offline` 事件（服务间调用）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         registry: 选项集注册表。
         *         req: 扫描请求（单批上限 / 基准时间）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{expired}`。
         */
        post: operations["expire_notices_api_v1_notices_internal_expire_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notices/published": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Published Notices
         * @description 全员发布中列表（置顶优先，登录即可）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         registry: 选项集注册表。
         *         page: 分页契约。
         *         locale: 显式语言。
         *         accept_language: 请求头语言。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页列表。
         */
        get: operations["list_published_notices_api_v1_notices_published_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notices/{notice_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Notice Detail
         * @description 公告详情（发布中对全员可见；草稿 / 下线仅 `notice:update` 可见）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         registry: 选项集注册表。
         *         checker: 权限检查器。
         *         notice_id: 公告主键。
         *         locale: 显式语言。
         *         accept_language: 请求头语言。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为公告详情。
         */
        get: operations["get_notice_detail_api_v1_notices__notice_id__get"];
        /**
         * Update Notice
         * @description 编辑公告（含置顶、草稿发布、已发布重新发布）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         registry: 选项集注册表。
         *         notice_id: 公告主键。
         *         req: 编辑请求。
         *         locale: 显式语言。
         *         accept_language: 请求头语言。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为公告详情。
         */
        put: operations["update_notice_api_v1_notices__notice_id__put"];
        post?: never;
        /**
         * Delete Notice
         * @description 软删除公告（连带软删多语言附表）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         registry: 选项集注册表。
         *         notice_id: 公告主键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{deleted: true}`。
         */
        delete: operations["delete_notice_api_v1_notices__notice_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notices/{notice_id}/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Mark Notice Read
         * @description 提交已读回执（幂等；仅发布中公告）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         registry: 选项集注册表。
         *         notice_id: 公告主键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为回执。
         */
        post: operations["mark_notice_read_api_v1_notices__notice_id__read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notices/{notice_id}/read-stats": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Notice Read Stats
         * @description 已读统计（应读 / 已读 / 未读人数）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         registry: 选项集注册表。
         *         audience: 应读人数读取器。
         *         notice_id: 公告主键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为统计结果。
         */
        get: operations["get_notice_read_stats_api_v1_notices__notice_id__read_stats_get"];
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
    "/api/v1/notifications/internal/unread-count": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Internal Unread Count
         * @description 按显式用户取未读数（服务间专用，不走登录态上下文）。
         *
         *     Args:
         *         uow: 请求级工作单元（租户库）。
         *         user_id: 用户主键。
         *
         *     Returns:
         *         ApiResponse[UnreadCountResponse]: 统一响应，data 为 `{count}`。
         */
        get: operations["internal_unread_count_api_v1_notifications_internal_unread_count_get"];
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
         * @description 当前未读总数（服务端唯一口径；登录即可）。
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
         *         ApiResponse: 统一响应，data 为通知。
         */
        get: operations["get_notification_detail_api_v1_notifications__notification_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Notification
         * @description 删除单条通知（软删除，仅本人）。
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
    "/api/v1/sms/logs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Sms Logs
         * @description 短信发送记录列表。
         */
        get: operations["list_sms_logs_api_v1_sms_logs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sms/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send Sms
         * @description 发送短信（异步：落日志 + 提交作业；渠道取配置）。
         */
        post: operations["send_sms_api_v1_sms_send_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sms/templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Sms Templates
         * @description 短信模板合并列表。
         */
        get: operations["list_sms_templates_api_v1_sms_templates_get"];
        put?: never;
        /**
         * Create Sms Template
         * @description 新建短信模板。
         */
        post: operations["create_sms_template_api_v1_sms_templates_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sms/templates/{template_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Sms Template
         * @description 短信模板详情。
         */
        get: operations["get_sms_template_api_v1_sms_templates__template_id__get"];
        /**
         * Update Sms Template
         * @description 编辑短信模板（code / 渠道不可改）。
         */
        put: operations["update_sms_template_api_v1_sms_templates__template_id__put"];
        post?: never;
        /**
         * Delete Sms Template
         * @description 软删除短信模板。
         */
        delete: operations["delete_sms_template_api_v1_sms_templates__template_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sms/templates/{template_id}/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Test Sms Template
         * @description 按 id 沙箱渲染（不发送）。
         */
        post: operations["test_sms_template_api_v1_sms_templates__template_id__test_post"];
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
         *     显式声明 `x-error-codes: []`：探针不触达业务判定，没有产品码可声明（区别于漏声明）。
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
         *     显式声明 `x-error-codes: []`：探针不触达业务判定，没有产品码可声明（区别于漏声明）。
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
        /** ApiResponse[BasePageResponse[MailLogItem]] */
        ApiResponse_BasePageResponse_MailLogItem__: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BasePageResponse_MailLogItem_"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[BasePageResponse[MailTemplateListItem]] */
        ApiResponse_BasePageResponse_MailTemplateListItem__: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BasePageResponse_MailTemplateListItem_"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[BasePageResponse[SmsLogItem]] */
        ApiResponse_BasePageResponse_SmsLogItem__: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BasePageResponse_SmsLogItem_"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[BasePageResponse[SmsTemplateListItem]] */
        ApiResponse_BasePageResponse_SmsTemplateListItem__: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BasePageResponse_SmsTemplateListItem_"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[InternalSendResult] */
        ApiResponse_InternalSendResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["InternalSendResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[MailSendResult] */
        ApiResponse_MailSendResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["MailSendResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[MailTemplateDetail] */
        ApiResponse_MailTemplateDetail_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["MailTemplateDetail"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[MailTemplatePreviewResult] */
        ApiResponse_MailTemplatePreviewResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["MailTemplatePreviewResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[MailTemplateTestResult] */
        ApiResponse_MailTemplateTestResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["MailTemplateTestResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[SmsSendResult] */
        ApiResponse_SmsSendResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["SmsSendResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[SmsTemplateDetail] */
        ApiResponse_SmsTemplateDetail_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["SmsTemplateDetail"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[SmsTemplateTestResult] */
        ApiResponse_SmsTemplateTestResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["SmsTemplateTestResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UnreadCountResponse] */
        ApiResponse_UnreadCountResponse_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UnreadCountResponse"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** BasePageResponse[MailLogItem] */
        BasePageResponse_MailLogItem_: {
            /** List */
            list: components["schemas"]["MailLogItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** BasePageResponse[MailTemplateListItem] */
        BasePageResponse_MailTemplateListItem_: {
            /** List */
            list: components["schemas"]["MailTemplateListItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** BasePageResponse[SmsLogItem] */
        BasePageResponse_SmsLogItem_: {
            /** List */
            list: components["schemas"]["SmsLogItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** BasePageResponse[SmsTemplateListItem] */
        BasePageResponse_SmsTemplateListItem_: {
            /** List */
            list: components["schemas"]["SmsTemplateListItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * InternalSendRequest
         * @description 内部发送请求（服务间调用；租户由服务 JWT 解析）。
         */
        InternalSendRequest: {
            /**
             * Biz Id
             * @description 业务标识
             */
            biz_id?: string | null;
            /**
             * Biz Type
             * @description 业务类型
             */
            biz_type?: string | null;
            /**
             * Channel
             * @description 渠道（email / sms）
             */
            channel: string;
            /**
             * Content
             * @description 已渲染正文（邮件 raw / 短信日志用）
             * @default
             */
            content: string;
            /**
             * Html
             * @description 邮件正文是否 HTML
             * @default false
             */
            html: boolean;
            /**
             * Idempotency Key
             * @description 幂等键
             */
            idempotency_key?: string | null;
            /**
             * Params
             * @description 模板参数
             */
            params?: {
                [key: string]: string;
            };
            /**
             * Recipient
             * @description 收件地址（邮箱 / 手机号）
             */
            recipient: string;
            /**
             * Template Code
             * @description 短信模板 code（短信必填）
             */
            template_code?: string | null;
            /**
             * Title
             * @description 标题 / 邮件主题
             * @default
             */
            title: string;
            /**
             * Transactional
             * @description 事务性消息（跳过渠道开关与免打扰）
             * @default true
             */
            transactional: boolean;
            /**
             * User Id
             * @description 收件用户主键（可空）
             */
            user_id?: number | null;
        };
        /**
         * InternalSendResult
         * @description 内部发送受理结果。
         */
        InternalSendResult: {
            /**
             * Log Id
             * @description 发送记录主键
             */
            log_id: string;
            /**
             * Status
             * @description 状态（pending / skipped）
             */
            status: string;
        };
        /**
         * MailLogItem
         * @description 邮件发送记录行。
         */
        MailLogItem: {
            /**
             * Attempts
             * @description 已尝试次数
             */
            attempts: number;
            /**
             * Channel
             * @description 发送渠道（smtp）
             */
            channel: string;
            /**
             * Created At
             * Format: date-time
             * @description 创建时间（UTC）
             */
            created_at: string;
            /**
             * Error Msg
             * @description 失败原因摘要
             */
            error_msg?: string | null;
            /**
             * Id
             * @description 记录主键
             */
            id: string;
            /**
             * Locale
             * @description 渲染语言
             */
            locale?: string | null;
            /**
             * Recipient
             * @description 收件邮箱
             */
            recipient?: string | null;
            /**
             * Sent At
             * @description 发送成功时间（UTC）
             */
            sent_at?: string | null;
            /**
             * Status
             * @description 状态（pending/success/failed/skipped）
             */
            status: string;
            /**
             * Subject
             * @description 渲染后的主题
             */
            subject?: string | null;
            /**
             * Template Code
             * @description 模板 code
             */
            template_code?: string | null;
            /**
             * User Id
             * @description 收件用户主键
             */
            user_id?: string | null;
        };
        /**
         * MailSendRequest
         * @description 邮件模板发送请求。
         */
        MailSendRequest: {
            /**
             * Locale
             * @description 显式语言
             */
            locale?: string | null;
            /**
             * Params
             * @description 渲染参数（值统一按字符串）
             */
            params?: {
                [key: string]: string;
            };
            /**
             * Recipient
             * @description 显式收件邮箱
             */
            recipient?: string | null;
            /**
             * Template Code
             * @description 模板 code
             */
            template_code: string;
            /**
             * Transactional
             * @description 事务性消息（跳过渠道开关与免打扰）
             * @default false
             */
            transactional: boolean;
            /**
             * User Id
             * @description 收件用户主键（用于地址 / 语言解析）
             */
            user_id?: number | null;
        };
        /**
         * MailSendResult
         * @description 发送受理结果。
         */
        MailSendResult: {
            /**
             * Log Id
             * @description 发送记录主键
             */
            log_id: string;
            /**
             * Status
             * @description 状态（pending / skipped）
             */
            status: string;
        };
        /**
         * MailTemplateCreateRequest
         * @description 新建邮件模板请求（code 与内置默认相同即覆盖）。
         */
        MailTemplateCreateRequest: {
            /**
             * Code
             * @description 模板 code（创建后不可改）
             */
            code: string;
            /**
             * I18N
             * @description 语言标识 → 主题 / 正文（至少一种语言）
             */
            i18n: {
                [key: string]: components["schemas"]["MailTextInput"];
            };
            /**
             * Name
             * @description 模板名称
             */
            name: string;
            /**
             * Remark
             * @description 备注
             */
            remark?: string | null;
            /**
             * Sample Params
             * @description 样例参数（提供时保存前严格渲染一次）
             */
            sample_params?: {
                [key: string]: string;
            };
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             */
            status: string;
        };
        /**
         * MailTemplateDetail
         * @description 邮件模板详情（含正文与完整多语言映射）。
         */
        MailTemplateDetail: {
            /**
             * Code
             * @description 模板 code
             */
            code: string;
            /**
             * Content
             * @description 当前语言正文
             * @default
             */
            content: string;
            /**
             * I18N
             * @description 完整多语言映射
             */
            i18n?: {
                [key: string]: components["schemas"]["MailTextOutput"];
            };
            /**
             * Id
             * @description 租户模板主键；内置默认为 null
             */
            id?: string | null;
            /**
             * Name
             * @description 模板名称
             */
            name: string;
            /**
             * Remark
             * @description 备注
             */
            remark?: string | null;
            /**
             * Source
             * @description 来源（tenant / builtin）
             */
            source: string;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
            /**
             * Subject
             * @description 当前语言主题
             */
            subject: string;
            /**
             * Updated At
             * @description 更新时间（内置默认为 null）
             */
            updated_at?: string | null;
        };
        /**
         * MailTemplateListItem
         * @description 邮件模板列表行（租户行与内置默认合并）。
         */
        MailTemplateListItem: {
            /**
             * Code
             * @description 模板 code
             */
            code: string;
            /**
             * Id
             * @description 租户模板主键；内置默认为 null
             */
            id?: string | null;
            /**
             * Name
             * @description 模板名称
             */
            name: string;
            /**
             * Remark
             * @description 备注
             */
            remark?: string | null;
            /**
             * Source
             * @description 来源（tenant / builtin）
             */
            source: string;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
            /**
             * Subject
             * @description 当前语言主题
             */
            subject: string;
            /**
             * Updated At
             * @description 更新时间（内置默认为 null）
             */
            updated_at?: string | null;
        };
        /**
         * MailTemplatePreviewRequest
         * @description 按 code 预览（可命中内置默认）。
         */
        MailTemplatePreviewRequest: {
            /**
             * Code
             * @description 模板 code
             */
            code: string;
            /**
             * Locale
             * @description 语言标识（缺省系统默认语言）
             */
            locale?: string | null;
            /**
             * Params
             * @description 渲染参数
             */
            params?: {
                [key: string]: string;
            };
        };
        /**
         * MailTemplatePreviewResult
         * @description 按 code 预览结果。
         */
        MailTemplatePreviewResult: {
            /**
             * Code
             * @description 模板 code
             */
            code: string;
            /**
             * Content
             * @description 渲染后的正文
             */
            content: string;
            /**
             * Subject
             * @description 渲染后的主题
             */
            subject: string;
        };
        /**
         * MailTemplateTestRequest
         * @description 邮件模板渲染测试请求（不发送）。
         */
        MailTemplateTestRequest: {
            /**
             * Locale
             * @description 语言标识（缺省系统默认语言）
             */
            locale?: string | null;
            /**
             * Params
             * @description 渲染参数
             */
            params?: {
                [key: string]: string;
            };
        };
        /**
         * MailTemplateTestResult
         * @description 模板渲染结果（不发送）。
         */
        MailTemplateTestResult: {
            /**
             * Content
             * @description 渲染后的正文
             */
            content: string;
            /**
             * Subject
             * @description 渲染后的主题
             */
            subject: string;
        };
        /**
         * MailTemplateUpdateRequest
         * @description 编辑邮件模板请求（code 不可改；`i18n` 提供时整体替换）。
         */
        MailTemplateUpdateRequest: {
            /**
             * I18N
             * @description 语言标识 → 主题 / 正文（提供时整体替换）
             */
            i18n?: {
                [key: string]: components["schemas"]["MailTextInput"];
            };
            /**
             * Name
             * @description 模板名称
             */
            name?: string | null;
            /**
             * Remark
             * @description 备注
             */
            remark?: string | null;
            /**
             * Sample Params
             * @description 样例参数（提供时保存前严格渲染一次）
             */
            sample_params?: {
                [key: string]: string;
            };
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status?: string | null;
        };
        /**
         * MailTextInput
         * @description 邮件单语言文案入参。
         */
        MailTextInput: {
            /**
             * Content
             * @description 正文 Jinja2 / HTML（该语言）
             * @default
             */
            content: string;
            /**
             * Subject
             * @description 主题（该语言）
             */
            subject: string;
        };
        /**
         * MailTextOutput
         * @description 邮件单语言文案出参。
         */
        MailTextOutput: {
            /**
             * Content
             * @description 正文 Jinja2 / HTML（该语言）
             * @default
             */
            content: string;
            /**
             * Subject
             * @description 主题（该语言）
             */
            subject: string;
        };
        /**
         * NoticeCreateRequest
         * @description 新建公告请求（草稿或直接发布）。
         */
        NoticeCreateRequest: {
            /**
             * Expire At
             * @description 过期时间（UTC；空 = 永不过期）
             */
            expire_at?: string | null;
            /**
             * I18N
             * @description 语言标识 → 文案（至少一种语言；发布时正文必填）
             */
            i18n: {
                [key: string]: components["schemas"]["NoticeTextInput"];
            };
            /**
             * Is Top
             * @description 是否置顶
             * @default false
             */
            is_top: boolean;
            /**
             * Priority
             * @description 优先级（选项集值）
             * @default normal
             */
            priority: string;
            /**
             * Publish
             * @description 是否直接发布（false = 保存草稿）
             * @default true
             */
            publish: boolean;
            /**
             * Publish At
             * @description 发布时间（UTC；缺省当前时间）
             */
            publish_at?: string | null;
            /**
             * Type
             * @description 公告类型（选项集值）
             * @default system
             */
            type: string;
        };
        /**
         * NoticeExpireRequest
         * @description 内部过期扫描请求。
         */
        NoticeExpireRequest: {
            /**
             * Limit
             * @description 单批上限
             * @default 200
             */
            limit: number;
            /**
             * Now
             * @description 基准时间（UTC；缺省服务端当前时间，测试用）
             */
            now?: string | null;
        };
        /**
         * NoticeTextInput
         * @description 公告单语言文案入参。
         */
        NoticeTextInput: {
            /**
             * Content
             * @description 正文 HTML（该语言；草稿可空）
             * @default
             */
            content: string;
            /**
             * Title
             * @description 标题（该语言）
             */
            title: string;
        };
        /**
         * NoticeUpdateRequest
         * @description 编辑公告请求（字段均可选；`i18n` 提供时整体替换）。
         */
        NoticeUpdateRequest: {
            /**
             * Expire At
             * @description 过期时间（UTC；显式 null 表示清除）
             */
            expire_at?: string | null;
            /**
             * I18N
             * @description 语言标识 → 文案（提供时整体替换；空映射表示不改文案）
             */
            i18n?: {
                [key: string]: components["schemas"]["NoticeTextInput"];
            };
            /**
             * Is Top
             * @description 是否置顶
             */
            is_top?: boolean | null;
            /**
             * Priority
             * @description 优先级（选项集值）
             */
            priority?: string | null;
            /**
             * Publish
             * @description true = 草稿发布；false = 拒绝；缺省保持状态
             */
            publish?: boolean | null;
            /**
             * Publish At
             * @description 发布时间（UTC；缺省保持原值）
             */
            publish_at?: string | null;
            /**
             * Type
             * @description 公告类型（选项集值）
             */
            type?: string | null;
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
        /**
         * SmsLogItem
         * @description 短信发送记录行。
         */
        SmsLogItem: {
            /**
             * Attempts
             * @description 已尝试次数
             */
            attempts: number;
            /**
             * Channel
             * @description 实际发送渠道
             */
            channel: string;
            /**
             * Content
             * @description 脱敏后的正文
             */
            content?: string | null;
            /**
             * Created At
             * Format: date-time
             * @description 创建时间（UTC）
             */
            created_at: string;
            /**
             * Error Msg
             * @description 失败原因摘要
             */
            error_msg?: string | null;
            /**
             * Id
             * @description 记录主键
             */
            id: string;
            /**
             * Recipient
             * @description 收件手机号
             */
            recipient?: string | null;
            /**
             * Scene
             * @description 场景
             */
            scene?: string | null;
            /**
             * Sent At
             * @description 发送成功时间（UTC）
             */
            sent_at?: string | null;
            /**
             * Status
             * @description 状态（pending/success/failed/skipped）
             */
            status: string;
            /**
             * Template Code
             * @description 模板 code
             */
            template_code?: string | null;
            /**
             * User Id
             * @description 收件用户主键
             */
            user_id?: string | null;
        };
        /**
         * SmsSendRequest
         * @description 短信模板发送请求（渠道取配置的当前生效渠道）。
         */
        SmsSendRequest: {
            /**
             * Params
             * @description 渲染参数（值统一按字符串）
             */
            params?: {
                [key: string]: string;
            };
            /**
             * Recipient
             * @description 显式收件手机号
             */
            recipient?: string | null;
            /**
             * Template Code
             * @description 模板 code
             */
            template_code: string;
            /**
             * Transactional
             * @description 事务性消息（跳过渠道开关与免打扰）
             * @default false
             */
            transactional: boolean;
            /**
             * User Id
             * @description 收件用户主键（用于地址解析）
             */
            user_id?: number | null;
        };
        /**
         * SmsSendResult
         * @description 发送受理结果。
         */
        SmsSendResult: {
            /**
             * Log Id
             * @description 发送记录主键
             */
            log_id: string;
            /**
             * Status
             * @description 状态（pending / skipped）
             */
            status: string;
        };
        /**
         * SmsTemplateCreateRequest
         * @description 新建短信模板请求。
         */
        SmsTemplateCreateRequest: {
            /**
             * Channel
             * @description 渠道（aliyun/tencent）
             * @default aliyun
             */
            channel: string;
            /**
             * Code
             * @description 模板 code
             */
            code: string;
            /**
             * Content
             * @description 正文 Jinja2（单语言）
             */
            content: string;
            /**
             * Name
             * @description 模板名称
             */
            name: string;
            /**
             * Provider Param Keys
             * @description 厂商参数名顺序（≤20，去重）
             */
            provider_param_keys?: string[];
            /**
             * Provider Template Id
             * @description 厂商模板 ID
             */
            provider_template_id?: string | null;
            /**
             * Remark
             * @description 备注
             */
            remark?: string | null;
            /**
             * Scene
             * @description 场景（选项集值）
             * @default notify
             */
            scene: string;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             */
            status: string;
        };
        /**
         * SmsTemplateDetail
         * @description 短信模板详情。
         */
        SmsTemplateDetail: {
            /**
             * Channel
             * @description 渠道（aliyun/tencent）
             */
            channel: string;
            /**
             * Code
             * @description 模板 code
             */
            code: string;
            /**
             * Content
             * @description 正文 Jinja2
             * @default
             */
            content: string;
            /**
             * Id
             * @description 租户模板主键；内置默认为 null
             */
            id?: string | null;
            /**
             * Name
             * @description 模板名称
             */
            name: string;
            /**
             * Provider Param Keys
             * @description 厂商参数名顺序
             */
            provider_param_keys?: string[];
            /**
             * Provider Template Id
             * @description 厂商模板 ID
             */
            provider_template_id?: string | null;
            /**
             * Remark
             * @description 备注
             */
            remark?: string | null;
            /**
             * Scene
             * @description 场景（选项集值）
             */
            scene: string;
            /**
             * Source
             * @description 来源（tenant / builtin）
             */
            source: string;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
            /**
             * Updated At
             * @description 更新时间（内置默认为 null）
             */
            updated_at?: string | null;
        };
        /**
         * SmsTemplateListItem
         * @description 短信模板列表行（租户模板与内置事务性模板合并）。
         */
        SmsTemplateListItem: {
            /**
             * Channel
             * @description 渠道（aliyun/tencent）
             */
            channel: string;
            /**
             * Code
             * @description 模板 code
             */
            code: string;
            /**
             * Id
             * @description 租户模板主键；内置默认为 null
             */
            id?: string | null;
            /**
             * Name
             * @description 模板名称
             */
            name: string;
            /**
             * Remark
             * @description 备注
             */
            remark?: string | null;
            /**
             * Scene
             * @description 场景（选项集值）
             */
            scene: string;
            /**
             * Source
             * @description 来源（tenant / builtin）
             */
            source: string;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
            /**
             * Updated At
             * @description 更新时间（内置默认为 null）
             */
            updated_at?: string | null;
        };
        /**
         * SmsTemplateTestRequest
         * @description 短信模板渲染测试请求（不发送）。
         */
        SmsTemplateTestRequest: {
            /**
             * Params
             * @description 渲染参数
             */
            params?: {
                [key: string]: string;
            };
        };
        /**
         * SmsTemplateTestResult
         * @description 短信模板渲染结果（不发送）。
         */
        SmsTemplateTestResult: {
            /**
             * Code
             * @description 模板 code
             */
            code: string;
            /**
             * Content
             * @description 渲染后的正文
             */
            content: string;
        };
        /**
         * SmsTemplateUpdateRequest
         * @description 编辑短信模板请求（code / channel 不可改）。
         */
        SmsTemplateUpdateRequest: {
            /**
             * Content
             * @description 正文 Jinja2
             */
            content?: string | null;
            /**
             * Name
             * @description 模板名称
             */
            name?: string | null;
            /**
             * Provider Param Keys
             * @description 厂商参数名顺序（提供时整体替换）
             */
            provider_param_keys?: string[] | null;
            /**
             * Provider Template Id
             * @description 厂商模板 ID
             */
            provider_template_id?: string | null;
            /**
             * Remark
             * @description 备注
             */
            remark?: string | null;
            /**
             * Scene
             * @description 场景（选项集值）
             */
            scene?: string | null;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status?: string | null;
        };
        /**
         * UnreadCountResponse
         * @description 未读计数响应（`unread_count` 及已读接口返回的操作后未读总数）。
         */
        UnreadCountResponse: {
            /**
             * Count
             * @description 未读通知数
             * @default 0
             */
            count: number;
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
    internal_send_api_v1_mail_internal_send_post: {
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
                "application/json": components["schemas"]["InternalSendRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_InternalSendResult_"];
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
    list_mail_logs_api_v1_mail_logs_get: {
        parameters: {
            query?: {
                /** @description 状态 */
                status?: string | null;
                /** @description 模板 code */
                template_code?: string | null;
                /** @description 收件地址（模糊） */
                recipient?: string | null;
                /** @description 收件用户主键 */
                user_id?: number | null;
                /** @description 创建时间下限（UTC） */
                start_at?: string | null;
                /** @description 创建时间上限（UTC） */
                end_at?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_MailLogItem__"];
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
    send_mail_api_v1_mail_send_post: {
        parameters: {
            query?: never;
            header?: {
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MailSendRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_MailSendResult_"];
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
    list_mail_templates_api_v1_mail_templates_get: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
                /** @description code / 名称关键字 */
                keyword?: string | null;
                /** @description 状态（enabled/disabled） */
                status?: string | null;
                /** @description 来源（tenant/builtin） */
                source?: string | null;
                /** @description 页码（从 1 起） */
                page?: number;
                /** @description 每页条数（默认 20，上限 200） */
                size?: number;
                /** @description 排序字段，逗号分隔多值（如 status,created_at） */
                order_by?: string | null;
                /** @description 排序方向数组，与 order_by 位置一一对应 */
                order?: string[] | null;
            };
            header?: {
                "Accept-Language"?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_MailTemplateListItem__"];
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
    create_mail_template_api_v1_mail_templates_post: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
            };
            header?: {
                "Accept-Language"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MailTemplateCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_MailTemplateDetail_"];
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
    preview_mail_template_api_v1_mail_templates_preview_post: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
            };
            header?: {
                "Accept-Language"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MailTemplatePreviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_MailTemplatePreviewResult_"];
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
    get_mail_template_api_v1_mail_templates__template_id__get: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
            };
            header?: {
                "Accept-Language"?: string | null;
            };
            path: {
                template_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_MailTemplateDetail_"];
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
    update_mail_template_api_v1_mail_templates__template_id__put: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
            };
            header?: {
                "Accept-Language"?: string | null;
            };
            path: {
                template_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MailTemplateUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_MailTemplateDetail_"];
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
    delete_mail_template_api_v1_mail_templates__template_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                template_id: number;
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
    test_mail_template_api_v1_mail_templates__template_id__test_post: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
            };
            header?: {
                "Accept-Language"?: string | null;
            };
            path: {
                template_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MailTemplateTestRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_MailTemplateTestResult_"];
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
    list_notices_api_v1_notices_get: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
                /** @description 标题关键字 */
                keyword?: string | null;
                /** @description 状态（draft/published/offline） */
                status?: string | null;
                /** @description 公告类型（选项集值） */
                type?: string | null;
                /** @description 页码（从 1 起） */
                page?: number;
                /** @description 每页条数（默认 20，上限 200） */
                size?: number;
                /** @description 排序字段，逗号分隔多值（如 status,created_at） */
                order_by?: string | null;
                /** @description 排序方向数组，与 order_by 位置一一对应 */
                order?: string[] | null;
            };
            header?: {
                "Accept-Language"?: string | null;
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
    create_notice_api_v1_notices_post: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
            };
            header?: {
                "Accept-Language"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NoticeCreateRequest"];
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
    expire_notices_api_v1_notices_internal_expire_post: {
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
                "application/json": components["schemas"]["NoticeExpireRequest"];
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
    list_published_notices_api_v1_notices_published_get: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
                /** @description 页码（从 1 起） */
                page?: number;
                /** @description 每页条数（默认 20，上限 200） */
                size?: number;
                /** @description 排序字段，逗号分隔多值（如 status,created_at） */
                order_by?: string | null;
                /** @description 排序方向数组，与 order_by 位置一一对应 */
                order?: string[] | null;
            };
            header?: {
                "Accept-Language"?: string | null;
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
    get_notice_detail_api_v1_notices__notice_id__get: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
            };
            header?: {
                "Accept-Language"?: string | null;
            };
            path: {
                notice_id: number;
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
    update_notice_api_v1_notices__notice_id__put: {
        parameters: {
            query?: {
                /** @description 语言标识（缺省按 Accept-Language） */
                locale?: string | null;
            };
            header?: {
                "Accept-Language"?: string | null;
            };
            path: {
                notice_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NoticeUpdateRequest"];
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
    delete_notice_api_v1_notices__notice_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                notice_id: number;
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
    mark_notice_read_api_v1_notices__notice_id__read_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                notice_id: number;
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
    get_notice_read_stats_api_v1_notices__notice_id__read_stats_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                notice_id: number;
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
    list_notifications_api_v1_notifications_get: {
        parameters: {
            query?: {
                /** @description 关键字（匹配标题） */
                keyword?: string | null;
                /** @description 筛选条件 JSON（FilterSpec 数组） */
                filters?: string | null;
                /** @description 通知类型（system/approval/alert/import） */
                type?: string | null;
                /** @description 已读状态（true / false） */
                is_read?: boolean | null;
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
    internal_unread_count_api_v1_notifications_internal_unread_count_get: {
        parameters: {
            query: {
                /** @description 用户主键（由调用方服务身份担保） */
                user_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_UnreadCountResponse_"];
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
    list_sms_logs_api_v1_sms_logs_get: {
        parameters: {
            query?: {
                /** @description 状态 */
                status?: string | null;
                /** @description 渠道 */
                channel?: string | null;
                /** @description 场景 */
                scene?: string | null;
                /** @description 模板 code */
                template_code?: string | null;
                /** @description 收件手机号（模糊） */
                recipient?: string | null;
                /** @description 收件用户主键 */
                user_id?: number | null;
                /** @description 创建时间下限（UTC） */
                start_at?: string | null;
                /** @description 创建时间上限（UTC） */
                end_at?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_SmsLogItem__"];
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
    send_sms_api_v1_sms_send_post: {
        parameters: {
            query?: never;
            header?: {
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SmsSendRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_SmsSendResult_"];
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
    list_sms_templates_api_v1_sms_templates_get: {
        parameters: {
            query?: {
                /** @description code / 名称关键字 */
                keyword?: string | null;
                /** @description 状态（enabled/disabled） */
                status?: string | null;
                /** @description 渠道（aliyun/tencent） */
                channel?: string | null;
                /** @description 场景（选项集值） */
                scene?: string | null;
                /** @description 来源（tenant/builtin） */
                source?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_SmsTemplateListItem__"];
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
    create_sms_template_api_v1_sms_templates_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SmsTemplateCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_SmsTemplateDetail_"];
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
    get_sms_template_api_v1_sms_templates__template_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                template_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_SmsTemplateDetail_"];
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
    update_sms_template_api_v1_sms_templates__template_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                template_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SmsTemplateUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_SmsTemplateDetail_"];
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
    delete_sms_template_api_v1_sms_templates__template_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                template_id: number;
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
    test_sms_template_api_v1_sms_templates__template_id__test_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                template_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SmsTemplateTestRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_SmsTemplateTestResult_"];
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
