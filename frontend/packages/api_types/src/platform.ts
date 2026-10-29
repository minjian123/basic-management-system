/**
 * 服务契约生成类型：platform
 *
 * 本文件由 `frontend/packages/api_types/scripts/generate.mjs` 生成，请勿手工修改。
 * 来源：deploy/contracts/platform.json（服务契约快照，唯一事实源）。
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
    "/api/v1/account-locks": {
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
        get: operations["list_locks_api_v1_account_locks_get"];
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
        post: operations["lock_account_api_v1_account_locks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/account-locks/{lock_id}": {
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
        get: operations["get_lock_api_v1_account_locks__lock_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/account-locks/{lock_id}/unlock": {
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
        put: operations["unlock_account_api_v1_account_locks__lock_id__unlock_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/actions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Actions
         * @description 动作码清单（全局字典；平台维护视图 / 租户只读）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为动作码清单。
         */
        get: operations["list_actions_api_v1_actions_get"];
        put?: never;
        /**
         * Create Action
         * @description 新增动作码。
         *
         *     Args:
         *         req: 新增请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为动作码行。
         */
        post: operations["create_action_api_v1_actions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/actions/{action_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Action
         * @description 更新动作码（`code` 不可改；停用时连带停用其权限码）。
         *
         *     Args:
         *         action_id: 动作码主键。
         *         req: 更新请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为动作码行。
         */
        put: operations["update_action_api_v1_actions__action_id__put"];
        post?: never;
        /**
         * Delete Action
         * @description 删除动作码（有条件删除）。
         *
         *     Args:
         *         action_id: 动作码主键。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["delete_action_api_v1_actions__action_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/businesses": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Businesses
         * @description 业务权限码清单（租户侧可见、只读）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为业务码清单。
         */
        get: operations["list_businesses_api_v1_businesses_get"];
        put?: never;
        /**
         * Create Business
         * @description 新增业务码。
         *
         *     Args:
         *         req: 新增请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为业务码行。
         */
        post: operations["create_business_api_v1_businesses_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/businesses/{business_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Business
         * @description 更新业务码（`code` 不可改；停用时连带停用其权限码）。
         *
         *     Args:
         *         business_id: 业务码主键。
         *         req: 更新请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为业务码行。
         */
        put: operations["update_business_api_v1_businesses__business_id__put"];
        post?: never;
        /**
         * Delete Business
         * @description 删除业务码（有条件删除）。
         *
         *     Args:
         *         business_id: 业务码主键。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["delete_business_api_v1_businesses__business_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/buttons": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Buttons
         * @description 按钮清单（按表单过滤）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *         form_id: 表单主键（可空 = 全部）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为按钮清单。
         */
        get: operations["list_buttons_api_v1_buttons_get"];
        put?: never;
        /**
         * Create Button
         * @description 新增按钮（表单 + 动作 1:1）。
         *
         *     Args:
         *         req: 新增请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为按钮行。
         */
        post: operations["create_button_api_v1_buttons_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/buttons/{button_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Button
         * @description 更新按钮。
         *
         *     Args:
         *         button_id: 按钮主键。
         *         req: 更新请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后的按钮行。
         */
        put: operations["update_button_api_v1_buttons__button_id__put"];
        post?: never;
        /**
         * Delete Button
         * @description 删除按钮（软删除）。
         *
         *     Args:
         *         button_id: 按钮主键。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["delete_button_api_v1_buttons__button_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/capability-grants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Capability Grants
         * @description 授权记录清单（只读，分页 + 筛选）。
         *
         *     需要 `capability-grant:query` 权限；只读会话取平台库（授权记录跨租户共享）。
         *
         *     Args:
         *         session: 平台库只读会话。
         *         query: 分页与排序请求（排序白名单校验、非法忽略）。
         *         audit: 审计捕获器（占位注入；只读端点不产生审计事件）。
         *         capability_name: 能力名筛选。
         *         consumer_key: 消费方筛选。
         *         status: 状态筛选。
         *         source: 来源筛选。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
         */
        get: operations["list_capability_grants_api_v1_capability_grants_get"];
        put?: never;
        /**
         * Grant Capability
         * @description 人工授予（同一「能力 × 消费方」幂等 UPSERT；临时授权必填有效期与理由）。
         *
         *     需要 `capability-grant:manage` 权限；授予后清授权视图快照，撤销 / 授予在有界周期内生效。
         *
         *     Args:
         *         req: 授予请求（能力名 / 消费方 / 可选有效期与理由）。
         *         uow: 平台库工作单元（写事务边界）。
         *         audit: 审计捕获器。
         *         metrics: 指标器（刷新有效授权数）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为授权记录。
         *
         *     Raises:
         *         ParamError: 能力未登记 / 消费方未登记 / 有效期非法 / 临时授权缺理由（10001）。
         */
        post: operations["grant_capability_api_v1_capability_grants_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/capability-grants/{grant_id}": {
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
         * Revoke Capability
         * @description 撤销授权（软撤销：置 `disabled` + `revoked_at`，保留授权历史；重复撤销幂等）。
         *
         *     需要 `capability-grant:manage` 权限。
         *
         *     Args:
         *         grant_id: 授权记录主键。
         *         uow: 平台库工作单元（写事务边界）。
         *         audit: 审计捕获器。
         *         metrics: 指标器（刷新有效授权数）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为撤销后的授权记录。
         *
         *     Raises:
         *         NotFoundError: 记录不存在（10002）。
         */
        delete: operations["revoke_capability_api_v1_capability_grants__grant_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/code/validate-expression": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Validate Expression
         * @description 校验表达式（语法 / 字段 / 变量诊断，含位置）。
         *
         *     Args:
         *         validator: 代码校验基座。
         *         req: 表达式校验请求（表达式文本 / 上下文）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为校验结果（`ExpressionValidationResponse`）。
         */
        post: operations["validate_expression_api_v1_code_validate_expression_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/code/validate-sql": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Validate Sql
         * @description 校验 SQL 并做只读试算（先经限流基座判定配额）。
         *
         *     Args:
         *         request: 请求对象（限流目标取客户端地址）。
         *         validator: 代码校验基座。
         *         limiter: 限流基座。
         *         tenant: 解析链租户上下文（限流键租户位）。
         *         req: SQL 校验请求（SQL 文本 / 目标数据源）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为校验结果（`SqlValidationResponse`）。
         */
        post: operations["validate_sql_api_v1_code_validate_sql_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Data Sources
         * @description 列统一数据源登记清单（供数据权限左列 / 通用页面）。
         *
         *     Args:
         *         kind: 类型过滤（`dict` / `form`；空 = 全部）。
         *
         *     Returns:
         *         ApiResponse[DataSourceListResponse]: 统一响应，data 为登记清单（`items` 保序）。
         *
         *     Raises:
         *         ParamError: 类型取值非法。
         */
        get: operations["list_data_sources_api_v1_data_sources_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/demos": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Demos
         * @description demo 列表。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为记录数组。
         */
        get: operations["list_demos_api_v1_demos_get"];
        put?: never;
        /**
         * Create Demo
         * @description 创建 demo。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 {id, name}。
         */
        post: operations["create_demo_api_v1_demos_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/demos/{demo_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Demo
         * @description demo 详情。
         *
         *     Args:
         *         demo_id: 记录 ID。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 {id, name}。
         *
         *     Raises:
         *         NotFoundError: 记录不存在（全局处理器转 404）。
         */
        get: operations["get_demo_api_v1_demos__demo_id__get"];
        /**
         * Update Demo
         * @description 更新 demo 名称。
         *
         *     Args:
         *         demo_id: 记录 ID。
         *         req: 更新请求。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 {id, name}。
         *
         *     Raises:
         *         NotFoundError: 记录不存在（全局处理器转 404）。
         */
        put: operations["update_demo_api_v1_demos__demo_id__put"];
        post?: never;
        /**
         * Delete Demo
         * @description 删除 demo。
         *
         *     Args:
         *         demo_id: 记录 ID。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 null。
         *
         *     Raises:
         *         NotFoundError: 记录不存在（全局处理器转 404）。
         */
        delete: operations["delete_demo_api_v1_demos__demo_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/batch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Batch Dicts
         * @description 批量合并取字典（一次请求多标识；版本一致的标识 items 返回 null）。
         *
         *     Args:
         *         source: 字典取数契约。
         *         query: 批量取数参数（types / version / locale）。
         *         request: 请求对象（语言解析）。
         *
         *     Returns:
         *         ApiResponse[DictBatchResult]: 统一响应，data 为批量结果。
         */
        post: operations["batch_dicts_api_v1_dicts_batch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/query-providers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Query Providers
         * @description 列可用查询提供者（按标识过滤；含参数 schema 子集）。
         *
         *     Args:
         *         registry: 查询提供者注册表。
         *         data_source_key: 字典标识（可选）。
         *
         *     Returns:
         *         ApiResponse[DictQueryProviderListResponse]: 统一响应，data 为提供者清单（`items` 保序）。
         */
        get: operations["list_query_providers_api_v1_dicts_query_providers_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/{data_source_key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Dict By Type
         * @description 按字典标识取字典（版本比对 / 关键字 / 级联 / 按条目 id 子集 / 上限）。
         *
         *     Args:
         *         source: 字典取数契约。
         *         data_source_key: 字典标识。
         *         request: 请求对象（语言解析）。
         *         version: 客户端本地版本号。
         *         keyword: 关键字。
         *         parent_id: 上级条目 ID（0 = 顶层）。
         *         ids: 逗号分隔的条目 id 子集（正整数）。
         *         limit: 返回条数上限。
         *
         *     Returns:
         *         ApiResponse[DictTypeResult]: 统一响应，data 为单标识取数结果。
         */
        get: operations["get_dict_by_type_api_v1_dicts__data_source_key__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/{data_source_key}/advanced-query": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Advanced Query Dict
         * @description 字典高级查询（items 条件引擎 / business 提供者）。
         *
         *     Args:
         *         query_service: 高级查询服务。
         *         registry: 查询提供者注册表。
         *         data_source_key: 字典标识。
         *         payload: 查询请求体。
         *         request: 请求对象（语言解析）。
         *
         *     Returns:
         *         ApiResponse[DictAdvQueryResult]: 统一响应，data 为分页结果。
         */
        post: operations["advanced_query_dict_api_v1_dicts__data_source_key__advanced_query_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/{data_source_key}/attrs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Dict Attrs
         * @description 取字典查询字段 schema（供高级查询条件构建；本期为固定字段）。
         *
         *     Args:
         *         query_service: 高级查询服务。
         *         data_source_key: 字典标识。
         *         request: 请求对象（语言解析）。
         *
         *     Returns:
         *         ApiResponse[DictAttrListResponse]: 统一响应，data 为字段清单（`items` 保序）。
         */
        get: operations["get_dict_attrs_api_v1_dicts__data_source_key__attrs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/fields": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Fields
         * @description 字段清单（按表单过滤）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *         form_id: 表单主键（可空 = 全部）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为字段清单。
         */
        get: operations["list_fields_api_v1_fields_get"];
        put?: never;
        /**
         * Create Field
         * @description 新增字段（表单内字段键唯一）。
         *
         *     Args:
         *         req: 新增请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为字段行。
         */
        post: operations["create_field_api_v1_fields_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/fields/{field_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Field
         * @description 更新字段。
         *
         *     Args:
         *         field_id: 字段主键。
         *         req: 更新请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后的字段行。
         */
        put: operations["update_field_api_v1_fields__field_id__put"];
        post?: never;
        /**
         * Delete Field
         * @description 删除字段（软删除）。
         *
         *     Args:
         *         field_id: 字段主键。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["delete_field_api_v1_fields__field_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/form-keys": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Form Keys
         * @description 列表单标识清单（供通用页面路由：`form_key → data_source_key`）。
         *
         *     取数口径＝**应用级视图**（`app.state.form_registry`：`FORM_CATALOG` + 本服务经 `form_records()`
         *     注入的产品登记项），非直接读构建期清单常量。
         *
         *     Args:
         *         request: 请求（取应用级清单视图）。
         *         kind: 类型过滤（`dict` / `form`；空 = 全部）。
         *
         *     Returns:
         *         ApiResponse[FormKeyListResponse]: 统一响应，data 为表单标识清单（`items` 保序）。
         *
         *     Raises:
         *         ParamError: 类型取值非法。
         */
        get: operations["list_form_keys_api_v1_form_keys_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/forms": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Forms
         * @description 表单清单（`menu_id` 非空时按菜单关联过滤；可空 = 全量，含无入口表单）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *         menu_id: 菜单主键（可空 = 全量）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为表单清单。
         */
        get: operations["list_forms_api_v1_forms_get"];
        put?: never;
        /**
         * Create Form
         * @description 新增表单（业务 1:1；菜单入口多对多）。
         *
         *     Args:
         *         req: 新增请求（关联菜单入口清单 / 业务码 / 组件 / 状态）。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为表单行。
         */
        post: operations["create_form_api_v1_forms_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/forms/{form_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Form
         * @description 更新表单（菜单入口关联全量替换）。
         *
         *     Args:
         *         form_id: 表单主键。
         *         req: 更新请求（关联菜单入口清单 / 业务码 / 组件 / 状态）。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后的表单行。
         */
        put: operations["update_form_api_v1_forms__form_id__put"];
        post?: never;
        /**
         * Delete Form
         * @description 删除表单（软删除）。
         *
         *     Args:
         *         form_id: 表单主键。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["delete_form_api_v1_forms__form_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/icons": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Icons
         * @description 取图标清单（可按分组 / 状态过滤，关键字匹配图标键 / 名称 / 标签）。
         *
         *     Args:
         *         registry: 图标注册表基座。
         *         category: 图标分组查询参数（可选）。
         *         status: 图标状态查询参数（可选）。
         *         keyword: 关键字查询参数（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为图标清单（`IconListResponse`）。
         */
        get: operations["list_icons_api_v1_icons_get"];
        put?: never;
        /**
         * Create Icon
         * @description 新增自定义图标（可按幂等键复用首次结果）。
         *
         *     Args:
         *         registry: 图标注册表基座。
         *         idempotency: 幂等基座（首次结果复用）。
         *         tenant: 解析链租户上下文（幂等键作用域位）。
         *         req: 新增请求（图标键 / 名称 / 分组 / 标签 / SVG 内容）。
         *         idempotency_key: 幂等键请求头（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为图标定义（`IconResponse`）。
         *
         *     Raises:
         *         ParamError: 图标键格式非法（10001）。
         */
        post: operations["create_icon_api_v1_icons_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/icons/{code}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Icon
         * @description 取单图标定义。
         *
         *     Args:
         *         registry: 图标注册表基座。
         *         code: 图标键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为图标定义（`IconResponse`）。
         *
         *     Raises:
         *         ParamError: 图标键格式非法（10001）。
         */
        get: operations["get_icon_api_v1_icons__code__get"];
        /**
         * Update Icon
         * @description 更新自定义图标（未提供字段保持不变；可按幂等键复用首次结果）。
         *
         *     Args:
         *         registry: 图标注册表基座。
         *         idempotency: 幂等基座（首次结果复用）。
         *         tenant: 解析链租户上下文（幂等键作用域位）。
         *         code: 图标键。
         *         req: 更新请求（全字段可选）。
         *         idempotency_key: 幂等键请求头（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为图标定义（`IconResponse`）。
         *
         *     Raises:
         *         ParamError: 图标键格式非法（10001）。
         */
        put: operations["update_icon_api_v1_icons__code__put"];
        post?: never;
        /**
         * Delete Icon
         * @description 删除自定义图标（可按幂等键复用首次结果）。
         *
         *     Args:
         *         registry: 图标注册表基座。
         *         idempotency: 幂等基座（首次结果复用）。
         *         tenant: 解析链租户上下文（幂等键作用域位）。
         *         code: 图标键。
         *         idempotency_key: 幂等键请求头（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为删除结果（`IconDeleteResponse`）。
         *
         *     Raises:
         *         ParamError: 图标键格式非法（10001）。
         */
        delete: operations["delete_icon_api_v1_icons__code__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/menus": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Menus
         * @description 菜单树（平台维护视图，含 hidden 与 disabled）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为菜单树。
         */
        get: operations["list_menus_api_v1_menus_get"];
        put?: never;
        /**
         * Create Menu
         * @description 新增菜单。
         *
         *     Args:
         *         req: 新增请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为菜单行。
         */
        post: operations["create_menu_api_v1_menus_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/menus/my": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * My Menus
         * @description 当前用户动态菜单树 + 表单元数据 + 权限码集合。
         *
         *     Args:
         *         request: 请求对象（解析语言）。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *         config: 系统参数读取基座（缓存 TTL）。
         *         checker: 权限检查器。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为动态菜单。
         */
        get: operations["my_menus_api_v1_menus_my_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/menus/{menu_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Menu
         * @description 更新菜单。
         *
         *     Args:
         *         menu_id: 菜单主键。
         *         req: 更新请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后的菜单行。
         */
        put: operations["update_menu_api_v1_menus__menu_id__put"];
        post?: never;
        /**
         * Delete Menu
         * @description 删除菜单（软删除）。
         *
         *     Args:
         *         menu_id: 菜单主键。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["delete_menu_api_v1_menus__menu_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/modules": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Modules
         * @description 服务目录清单（只读，分页 + 筛选）。
         *
         *     Args:
         *         session: 平台库只读会话。
         *         query: 分页与排序请求（page / size / order_by / order；排序白名单逐项校验、非法忽略）。
         *         status: 状态筛选；缺省返回全部。
         *         group: 归属分组筛选；缺省返回全部。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
         */
        get: operations["list_modules_api_v1_modules_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/modules/snapshot": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Catalog Snapshot
         * @description 服务目录快照（只读，全量清单不分页；带参分支一并下发产品段与能力段）。
         *
         *     供各服务启动接库校验对账（`validate_catalog`）：字段与 `sys_module` 登记一致，
         *     响应 `data` 为清单数组（**注意**：路径须先于 `/modules/{service_key}` 注册，避免被明细路由吞掉）。
         *
         *     带参分支（`?with=products,collaborations`）：`data` 为
         *     `{modules, products, collaborations, snapshot_version, warnings}`——产品段与能力段来自**运行时视图**
         *     （产品清单装载的内存投影，不落库），因此必须在装载完成后才有效；未装载时为空数组并在 `warnings`
         *     给出提示（不静默）。`with` 取值集合外的值按参数非法拒绝（10001），不静默回退数组契约。
         *
         *     **契约形态**：返回注解为两分支联合（`ApiResponse[CatalogSnapshotResponse]` 为带参形态、
         *     `ApiResponse[list[ModuleResponse]]` 为缺省数组形态），使公开契约与前端生成类型同时覆盖两种形态
         *     （`03_02` 消费）。
         *
         *     Args:
         *         session: 平台库只读会话。
         *         with_: 附带段（逗号分隔多值；缺省保持原数组契约）。
         *
         *     Returns:
         *         ApiResponse: 统一响应。缺省形态 data 为服务目录记录数组（`ModuleResponse`）；
         *         带参形态 data 为 `CatalogSnapshotResponse`。
         *
         *     Raises:
         *         ParamError: `with` 出现未支持的段名（10001）。
         */
        get: operations["catalog_snapshot_api_v1_modules_snapshot_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/modules/{service_key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Module
         * @description 单条服务目录明细（只读；未登记 404）。
         *
         *     Args:
         *         session: 平台库只读会话。
         *         service_key: 服务标识（service_key 优先，未命中回退 module_key）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为服务目录记录（`ModuleResponse`）。
         *
         *     Raises:
         *         NotFoundError: 未登记（10002 / 404，全局处理器统一转响应）。
         */
        get: operations["get_module_api_v1_modules__service_key__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/outbox/dead-letters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Dead Letters
         * @description 死信列表（只读，分页 + 筛选，按主键倒序）。
         *
         *     Args:
         *         session: 请求数据库会话。
         *         store: 发件箱存储。
         *         query: 分页请求（page / size）。
         *         status: 处置状态筛选；缺省全部。
         *         source: 来源筛选；缺省全部。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
         */
        get: operations["list_dead_letters_api_v1_outbox_dead_letters_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/outbox/dead-letters/{dead_letter_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Dead Letter
         * @description 死信详情（只读；未命中 404）。
         *
         *     Args:
         *         session: 请求数据库会话。
         *         store: 发件箱存储。
         *         dead_letter_id: 死信记录主键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为死信记录（`DeadLetterResponse`）。
         *
         *     Raises:
         *         NotFoundError: 死信记录不存在。
         */
        get: operations["get_dead_letter_api_v1_outbox_dead_letters__dead_letter_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/outbox/dead-letters/{dead_letter_id}/ignore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ignore Dead Letter
         * @description 死信忽略：状态置 `ignored`。
         *
         *     Args:
         *         session: 请求数据库会话。
         *         store: 发件箱存储。
         *         dead_letter_id: 死信记录主键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后的死信记录。
         *
         *     Raises:
         *         NotFoundError: 死信记录不存在。
         *         ConflictError: 死信状态非 `pending`。
         */
        post: operations["ignore_dead_letter_api_v1_outbox_dead_letters__dead_letter_id__ignore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/outbox/dead-letters/{dead_letter_id}/replay": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Replay Dead Letter
         * @description 死信重投：状态置 `replayed`，并把对应发件箱记录重置为待投递。
         *
         *     Args:
         *         session: 请求数据库会话。
         *         store: 发件箱存储。
         *         dead_letter_id: 死信记录主键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后的死信记录。
         *
         *     Raises:
         *         NotFoundError: 死信记录不存在。
         *         ConflictError: 死信状态非 `pending`。
         */
        post: operations["replay_dead_letter_api_v1_outbox_dead_letters__dead_letter_id__replay_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/permissions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Permissions
         * @description 权限码清单（业务码 × 动作码组合；平台维护视图 / 租户只读）。
         *
         *     Args:
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *         business_id: 业务码主键（可空 = 全部）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为权限码清单。
         */
        get: operations["list_permissions_api_v1_permissions_get"];
        put?: never;
        /**
         * Create Permission
         * @description 手工新增权限码组合。
         *
         *     Args:
         *         req: 新增请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为权限码行。
         */
        post: operations["create_permission_api_v1_permissions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/permissions/generate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate Permissions
         * @description 批量补生成缺失的权限码组合。
         *
         *     Args:
         *         req: 范围与是否含停用项。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为新建 / 恢复 / 跳过计数。
         */
        post: operations["generate_permissions_api_v1_permissions_generate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/permissions/{permission_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Permission
         * @description 更新权限码（组合不可换绑，仅状态）。
         *
         *     Args:
         *         permission_id: 权限码主键。
         *         req: 更新请求。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为权限码行。
         */
        put: operations["update_permission_api_v1_permissions__permission_id__put"];
        post?: never;
        /**
         * Delete Permission
         * @description 删除权限码（有条件删除）。
         *
         *     Args:
         *         permission_id: 权限码主键。
         *         uow: 请求级工作单元。
         *         outbox: 发件箱存储。
         *         cache: 缓存 Region。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["delete_permission_api_v1_permissions__permission_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/account-locks/scan-inactive": {
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
        post: operations["scan_inactive_api_v1_platform_internal_account_locks_scan_inactive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/capability-grants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Capability Grant View
         * @description 按维度下发授权视图（`provider` / `consumer` 二选一）。
         *
         *     Args:
         *         request: 请求对象（登录态分支的权限码校验用）。
         *         session: 平台库只读会话。
         *         context: 入站身份（服务身份或登录态）。
         *         audit: 审计捕获器（占位注入；只读端点不产生审计事件）。
         *         provider: 提供方业务域（入站维度）。
         *         consumer: 消费方服务键（出站维度）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{provider, consumer, grants}`。
         *
         *     Raises:
         *         ParamError: `provider` / `consumer` 未二选一（10001）。
         *         PermissionError: 服务身份越界读取，或登录态缺少权限码（30001 / 403）。
         */
        get: operations["capability_grant_view_api_v1_platform_internal_capability_grants_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/configs/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resolve Configs
         * @description 批量取系统参数值（仅返回存在的键；缺失由调用方回落默认）。
         *
         *     Args:
         *         config: 系统参数取数实现。
         *         req: 批量取参数请求。
         *
         *     Returns:
         *         ApiResponse[ConfigResolveResponse]: 统一响应，data 为 `{values}`。
         */
        post: operations["resolve_configs_api_v1_platform_internal_configs_resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/credentials/login-state": {
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
        post: operations["apply_login_state_api_v1_platform_internal_credentials_login_state_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/credentials/update-password": {
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
        post: operations["update_password_api_v1_platform_internal_credentials_update_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/credentials/verify": {
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
        post: operations["verify_credential_api_v1_platform_internal_credentials_verify_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/declarations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Submit Declarations
         * @description 全量上报本产品声明（幂等；冲突即拒）。
         *
         *     Args:
         *         req: 上报请求（产品键 / 服务键 / 清单文本）。
         *         uow: 平台库工作单元（写事务边界）。
         *         context: 入站身份（服务键须与请求一致）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为逐类计数与警示。
         *
         *     Raises:
         *         ParamError: 产品键与清单不符、服务键与身份或清单不符（10001）。
         *         CatalogError: 校验不过或跨产品撞键（拒绝注册）。
         */
        put: operations["submit_declarations_api_v1_platform_internal_declarations_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/declarations/snapshot": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Declaration Snapshot
         * @description 下发注册表快照（服务身份专用；八类完整要素）。
         *
         *     Args:
         *         session: 平台库只读会话。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{snapshot_version, declarations}`。
         */
        get: operations["declaration_snapshot_api_v1_platform_internal_declarations_snapshot_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/permissions/invalidate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 失效权限快照
         * @description 失效当前租户的权限快照（版本 +1；可指定用户）。
         *
         *     Args:
         *         payload: 失效请求（`user_ids` 空 = 全租户）。
         *         tenant: 请求级租户上下文（由服务 JWT 的 tenant claim 解析）。
         *         cache: 缓存能力域。
         *
         *     Returns:
         *         ApiResponse[PermissionInvalidateResult]: 递增后的权限版本号。
         */
        post: operations["invalidate_permissions_api_v1_platform_internal_permissions_invalidate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/permissions/metadata": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 取权限元数据
         * @description 返回元数据索引（菜单 → 表单、权限码 id → 权限码）。
         *
         *     Args:
         *         request: 当前请求（构造请求级数据来源）。
         *         locale: 语言标识（缺省取实现缺省值）。
         *
         *     Returns:
         *         ApiResponse[PermissionMetadataResult]: 元数据索引。
         */
        get: operations["read_permission_metadata_api_v1_platform_internal_permissions_metadata_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/permissions/subject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 按用户取权限数据
         * @description 按用户返回聚合所需原始数据（角色 / 类型 / 授权 / 数据范围 / 字段收窄）。
         *
         *     Args:
         *         payload: 请求（用户主键）。
         *         request: 当前请求（构造请求级数据来源）。
         *
         *     Returns:
         *         ApiResponse[PermissionSubjectResult]: 原始数据。
         */
        post: operations["read_permission_subject_api_v1_platform_internal_permissions_subject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/seeds/orchestrate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Orchestrate Seeds
         * @description 统一执行全部种子（一个 XA 全局事务；串行 prepare、统一提交 / 整体回滚）。
         *
         *     **依赖注入**（2026-10-27 修复）：事务管理器 / 参与方 / 引擎注册表在此（有请求上下文）
         *     从应用 state 解析后注入服务——服务层拿不到 `Request`，故不在编排器内零参调用基座取用器。
         *
         *     Args:
         *         payload: 编排请求（租户 / 筛选 / dry-run / 超时）。
         *         context: 入站身份（服务身份或登录态）。
         *         request: 请求对象（取应用 state 中的事务与引擎依赖）。
         *
         *     Returns:
         *         ApiResponse: 编排结果（退出码 + 逐项报告 + 错误 / 冲突明细）。
         *
         *     Raises:
         *         ParamError: 参数非法（筛选引用了不存在的种子）。
         */
        post: operations["orchestrate_seeds_api_v1_platform_internal_seeds_orchestrate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/tenant-topologies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Topology Snapshot
         * @description 下发拓扑全量快照（各租户当前版本 + 默认版本）。
         *
         *     Args:
         *         request: 请求对象（登录态分支的权限码校验用）。
         *         session: 平台库只读会话。
         *         context: 入站身份（服务身份或登录态）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{default_version, snapshots}`。
         *
         *     Raises:
         *         PermissionError: 登录态缺少权限码（30001 / 403）。
         */
        get: operations["topology_snapshot_api_v1_platform_internal_tenant_topologies_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/users/create": {
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
        post: operations["create_user_api_v1_platform_internal_users_create_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/users/profile": {
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
        post: operations["user_profile_api_v1_platform_internal_users_profile_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/users/query": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Query Users
         * @description 按关键字 / 状态 / 限定集合分页查询用户（**服务间只读出口**）。
         *
         *     供产品组织域只读出口（组织数据源 `users` / 名称回显 `resolve_names(user)` / 按用户解析角色）
         *     取用户明细——**不跨库读** `sys_user`。仅接受持有本能力有效分配的服务票据；只读、不写库、不产事件；
         *     联系方式**原样返回**（脱敏归消费方产品出口）。
         *
         *     Args:
         *         req: 查询请求（关键字 / 状态 / 限定集合 / 分页）。
         *         uow: 请求级工作单元。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页用户只读行（主键升序）。
         */
        post: operations["query_users_api_v1_platform_internal_users_query_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/internal/users/reset-target": {
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
        post: operations["reset_target_api_v1_platform_internal_users_reset_target_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/plugins": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Plugins
         * @description 插件清单（按能力分组，只读）。
         *
         *     Args:
         *         request: 请求对象。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为能力分组数组（`plugin_key` 升序）。
         */
        get: operations["list_plugins_api_v1_plugins_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/plugins/aggregate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Aggregate Plugins
         * @description 跨服务插件聚合视图（触发式接口占位，只读）。
         *
         *     汇总各服务插件清单供平台超管统一查看（需求 01-4）。**当前为触发前占位**：
         *     恒定返回空聚合与占位标记，不读注册表、不发起任何服务调用；真实实现（经服务间
         *     公开契约 `service_client` 调用各服务 `GET /api/v1/plugins`）归触发时。**注意**：
         *     本路由须先于 `/plugins/{plugin_key}` 注册，避免被明细动态路由吞掉。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{"placeholder": true, "services": []}`。
         */
        get: operations["aggregate_plugins_api_v1_plugins_aggregate_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/plugins/{plugin_key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Plugin
         * @description 单能力插件明细（只读）。
         *
         *     Args:
         *         request: 请求对象。
         *         plugin_key: 能力域键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为单能力分组。
         *
         *     Raises:
         *         NotFoundError: 未登记能力（10002 / 404，全局处理器统一转响应）。
         */
        get: operations["get_plugin_api_v1_plugins__plugin_key__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/preferences/{key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Preference
         * @description 读取单个偏好（未设置回退默认值）。
         *
         *     Args:
         *         store: 用户偏好存储。
         *         key: 偏好键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{key, value}`。
         */
        get: operations["get_preference_api_v1_preferences__key__get"];
        /**
         * Set Preference
         * @description 写入 / 覆盖单个偏好（upsert）。
         *
         *     Args:
         *         store: 用户偏好存储。
         *         key: 偏好键。
         *         req: 偏好值请求。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{key, value}`。
         */
        put: operations["set_preference_api_v1_preferences__key__put"];
        post?: never;
        /**
         * Reset Preference
         * @description 重置单个偏好（清除该键，恢复默认）。
         *
         *     Args:
         *         store: 用户偏好存储。
         *         key: 偏好键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 null。
         */
        delete: operations["reset_preference_api_v1_preferences__key__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/products": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Products
         * @description 产品档案清单（只读，分页 + 筛选）。
         *
         *     Args:
         *         session: 平台库只读会话。
         *         query: 分页与排序请求（page / size / order_by / order；排序白名单逐项校验、非法忽略）。
         *         status: 状态筛选；缺省返回全部。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
         */
        get: operations["list_products_api_v1_products_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/products/{product_key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Product
         * @description 单条产品档案明细（只读；未登记 404）。
         *
         *     Args:
         *         session: 平台库只读会话。
         *         product_key: 产品标识。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为产品档案记录（`ProductResponse`）。
         *
         *     Raises:
         *         NotFoundError: 未登记（10002 / 404，全局处理器统一转响应）。
         */
        get: operations["get_product_api_v1_products__product_key__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/query-schemes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Query Schemes
         * @description 列查询方案（按目标、可选按表单标识过滤）。
         *
         *     Args:
         *         store: 查询方案存储。
         *         target: 方案目标。
         *         field_key: 表单标识。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为方案数组。
         */
        get: operations["list_query_schemes_api_v1_query_schemes_get"];
        put?: never;
        /**
         * Save Query Scheme
         * @description 新建 / 保存方案。
         *
         *     Args:
         *         store: 查询方案存储。
         *         scheme: 方案（`id` 为空表示新建）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为保存后的方案。
         */
        post: operations["save_query_scheme_api_v1_query_schemes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/query-schemes/default": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Resolve Default Scheme
         * @description 按三级优先级（个人 > 租户 > 平台）解析默认方案。
         *
         *     Args:
         *         store: 查询方案存储。
         *         target: 方案目标。
         *         field_key: 表单标识。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为方案或 null。
         */
        get: operations["resolve_default_scheme_api_v1_query_schemes_default_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/query-schemes/{scheme_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Query Scheme
         * @description 查询方案详情。
         *
         *     Args:
         *         store: 查询方案存储。
         *         scheme_id: 方案 ID。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为方案。
         *
         *     Raises:
         *         NotFoundError: 方案不存在（10002 / 404，全局处理器统一转响应）。
         */
        get: operations["get_query_scheme_api_v1_query_schemes__scheme_id__get"];
        /**
         * Update Query Scheme
         * @description 更新方案。
         *
         *     Args:
         *         store: 查询方案存储。
         *         scheme_id: 方案 ID。
         *         scheme: 方案（以路径 ID 为准）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为保存后的方案。
         */
        put: operations["update_query_scheme_api_v1_query_schemes__scheme_id__put"];
        post?: never;
        /**
         * Delete Query Scheme
         * @description 删除方案。
         *
         *     Args:
         *         store: 查询方案存储。
         *         scheme_id: 方案 ID。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 null。
         */
        delete: operations["delete_query_scheme_api_v1_query_schemes__scheme_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Roles
         * @description 角色列表（关键字 / 状态筛选 + 分页；含内置标记与主体数）。
         *
         *     Args:
         *         query: 分页与排序参数。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数。
         *         kw: 关键字（角色码 / 名称）。
         *         status: 状态（enabled/disabled）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页角色列表。
         */
        get: operations["list_roles_api_v1_roles_get"];
        put?: never;
        /**
         * Create Role
         * @description 新增角色（角色码唯一 + 格式校验；内置角色码不可自建）。
         *
         *     Args:
         *         req: 新增请求（角色码 / 名称 / 状态）。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为角色详情。
         */
        post: operations["create_role_api_v1_roles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/roles/{role_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Role
         * @description 角色详情（含乐观锁版本与审计字段）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为角色详情。
         */
        get: operations["get_role_api_v1_roles__role_id__get"];
        /**
         * Update Role
         * @description 修改角色（角色码 / 名称 / 状态；乐观锁 + 内置角色保护）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         req: 修改请求（角色码 / 名称 / 状态 / 版本）。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为角色详情。
         */
        put: operations["update_role_api_v1_roles__role_id__put"];
        post?: never;
        /**
         * Delete Role
         * @description 删除角色（内置保护 + 用户分配保护）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["delete_role_api_v1_roles__role_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/roles/{role_id}/assignments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Apply Role Assignments
         * @description 角色保存编排（分段全量覆盖；跨服务原子）。
         *
         *     `provider = "xa"` 时经 TM 全局事务（platform 分支进程内 + 组织域分支经参与端点）；
         *     `provider = null`（dev / test）时顺序提交（platform 本地事务 → 组织域内部写通道）。
         *     权限码**分段校验**：`role` 段另需 `role:update`（端点级挂 `role:grant`）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         req: 分段全量覆盖请求。
         *         uow: 请求级工作单元。
         *         config: 系统参数取数（角色码格式）。
         *         cache: 缓存能力域（角色 / 分配变更后权限版本递增）。
         *         client: 服务间调用客户端（组织域分支执行 / 内部写通道）。
         *         manager: 事务管理器（`provider=null` 时为 Null 实现）。
         *         participant: 事务参与方（platform 自身分支进程内执行）。
         *         checker: 权限校验器（`role` 段命令式复校 `role:update`）。
         *         audit: 审计捕获器（三权拒绝留痕）。
         *         idem_key: 幂等键请求头（透传给组织域内部写通道）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为角色详情、生效后用户清单与本次参与分段名。
         *
         *     Raises:
         *         PermissionError: 缺少 `role:update`（30001）。
         *         ParamError: 未提供任何分段（10001）。
         *         TransactionUnavailableError: 分支未达 `PREPARED`（10013）。
         *         ServiceUnavailableError: 跨服务调用失败（10007）。
         */
        put: operations["apply_role_assignments_api_v1_roles__role_id__assignments_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/roles/{role_id}/data-permissions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Data Scopes
         * @description 角色数据权限条目（按字典 × 策略）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         uow: 请求级工作单元。
         *         platform_uow: 平台库工作单元（元数据校验器构造，本端点只读）。
         *         cache: 缓存能力域。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为数据权限条目清单。
         */
        get: operations["list_data_scopes_api_v1_roles__role_id__data_permissions_get"];
        /**
         * Replace Data Scopes
         * @description 全量覆盖角色数据权限（单事务先删后插）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         req: 数据权限全量请求。
         *         uow: 请求级工作单元。
         *         platform_uow: 平台库工作单元（元数据校验器构造）。
         *         cache: 缓存能力域（权限版本 +1）。
         *         audit: 审计捕获器（三权拒绝留痕）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为重建后的数据权限条目清单。
         */
        put: operations["replace_data_scopes_api_v1_roles__role_id__data_permissions_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/roles/{role_id}/fields": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Fields
         * @description 角色字段权限条目（仅收窄项）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         uow: 请求级工作单元。
         *         platform_uow: 平台库工作单元（元数据校验器构造，本端点只读）。
         *         cache: 缓存能力域。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为字段权限条目清单。
         */
        get: operations["list_fields_api_v1_roles__role_id__fields_get"];
        /**
         * Replace Fields
         * @description 全量覆盖角色字段权限（单事务先删后插）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         req: 字段权限全量请求。
         *         uow: 请求级工作单元。
         *         platform_uow: 平台库工作单元（字段归属校验）。
         *         cache: 缓存能力域（权限版本 +1）。
         *         audit: 审计捕获器（三权拒绝留痕）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为重建后的字段权限条目清单。
         */
        put: operations["replace_fields_api_v1_roles__role_id__fields_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/roles/{role_id}/permissions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Permissions
         * @description 角色授权条目（菜单 / 表单 / 操作，含来源）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         uow: 请求级工作单元。
         *         platform_uow: 平台库工作单元（元数据校验器构造，本端点只读）。
         *         cache: 缓存能力域。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为授权条目清单。
         */
        get: operations["list_permissions_api_v1_roles__role_id__permissions_get"];
        /**
         * Replace Permissions
         * @description 全量覆盖角色授权（单事务先删后插；可按幂等键复用首次结果）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         req: 授权全量请求（条目清单）。
         *         uow: 请求级工作单元。
         *         platform_uow: 平台库工作单元（授权目标校验）。
         *         cache: 缓存能力域（权限版本 +1）。
         *         idempotency: 幂等基座（首次结果复用）。
         *         audit: 审计捕获器（三权拒绝留痕）。
         *         idempotency_key: 幂等键请求头（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为重建后的授权条目清单。
         */
        put: operations["replace_permissions_api_v1_roles__role_id__permissions_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/roles/{role_id}/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Assigned Users
         * @description 角色已分配用户列表（同库取用户账号 / 姓名 / 状态）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         query: 分页与排序参数。
         *         uow: 请求级工作单元。
         *         cache: 缓存能力域（依赖注入占位）。
         *         kw: 关键字（用户账号 / 姓名）。
         *         status: 用户状态（enabled/disabled）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页用户列表。
         */
        get: operations["list_assigned_users_api_v1_roles__role_id__users_get"];
        put?: never;
        /**
         * Assign Users
         * @description 批量分配用户（幂等 upsert；可按幂等键复用首次结果）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         req: 分配请求（用户主键清单）。
         *         uow: 请求级工作单元。
         *         cache: 缓存能力域（权限版本 +1）。
         *         idempotency: 幂等基座（首次结果复用）。
         *         tenant: 解析链租户上下文（幂等键作用域位）。
         *         audit: 审计捕获器（三权拒绝留痕）。
         *         idempotency_key: 幂等键请求头（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分配后的用户清单。
         */
        post: operations["assign_users_api_v1_roles__role_id__users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/roles/{role_id}/users/{user_id}": {
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
         * Unassign User
         * @description 解绑用户（软删分配行；未分配时幂等无操作）。
         *
         *     Args:
         *         role_id: 角色主键。
         *         user_id: 用户主键。
         *         uow: 请求级工作单元。
         *         cache: 缓存能力域（权限版本 +1）。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为空）。
         */
        delete: operations["unassign_user_api_v1_roles__role_id__users__user_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-topologies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Topologies
         * @description 拓扑记录清单（只读，分页 + 筛选）。
         *
         *     需要 `tenant-topology:query` 权限；只读会话取平台库（拓扑跨租户共享）。
         *
         *     Args:
         *         session: 平台库只读会话。
         *         query: 分页与排序请求（排序白名单校验、非法忽略）。
         *         tenant_id: 租户筛选。
         *         domain_key: 业务域筛选。
         *         unit_key: 部署单元筛选。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
         */
        get: operations["list_topologies_api_v1_tenant_topologies_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-topologies/{tenant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Topology
         * @description 按租户导出当前版本（部署编排 / 迁移输入）。
         *
         *     需要 `tenant-topology:query` 权限；该租户无记录时回退默认拓扑（`tenant_id=0`）。
         *
         *     Args:
         *         tenant_id: 租户主键（0 = 默认拓扑）。
         *         session: 平台库只读会话。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为 `{tenant_id, version, rows}`。
         *
         *     Raises:
         *         NotFoundError: 该租户与默认拓扑都没有记录（10002）。
         */
        get: operations["export_topology_api_v1_tenant_topologies__tenant_id__get"];
        /**
         * Replace Topology
         * @description 整批替换某租户的拓扑（`rows` 或 `template` 二选一；写入即生效）。
         *
         *     需要 `tenant-topology:manage` 权限。整批替换语义：旧行软删除、新行同版本写入、版本递增；
         *     失败即整体回滚（不会出现半新半旧的中间态）。
         *
         *     Args:
         *         tenant_id: 租户主键（0 = 默认拓扑）。
         *         req: 写入请求。
         *         uow: 平台库工作单元（写事务边界）。
         *         audit: 审计捕获器。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为生效后的 `{tenant_id, version, rows}`。
         *
         *     Raises:
         *         ParamError: 参数非法 / 域未登记 / 单元命名非法 / 未知模板 / 默认拓扑缺域（10001）。
         *         ConflictError: 同域重复或版本回退（10003）。
         */
        put: operations["replace_topology_api_v1_tenant_topologies__tenant_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/txn/branches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Recover Branches
         * @description 列举悬挂分支（对账）。
         *
         *     Args:
         *         participant: 应用装配的参与方。
         *         db_key: 目标库键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为悬挂分支清单。
         */
        get: operations["recover_branches_api_v1_txn_branches_get"];
        put?: never;
        /**
         * Execute Branch
         * @description 执行分支（单请求内 `XA_START → 业务写 → XA_END → XA_PREPARE`）。
         *
         *     Args:
         *         req: 分支执行请求。
         *         participant: 应用装配的参与方。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分支状态。
         */
        post: operations["execute_branch_api_v1_txn_branches_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/txn/branches/{xid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Branch State
         * @description 查询分支状态（TM 决定点前核验）。
         *
         *     Args:
         *         xid: 分支事务标识。
         *         participant: 应用装配的参与方。
         *         db_key: 目标库键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分支状态。
         */
        get: operations["branch_state_api_v1_txn_branches__xid__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/txn/branches/{xid}/commit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Commit Branch
         * @description 提交分支（TM 驱动）。
         *
         *     Args:
         *         xid: 分支事务标识。
         *         participant: 应用装配的参与方。
         *         db_key: 目标库键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分支状态。
         */
        post: operations["commit_branch_api_v1_txn_branches__xid__commit_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/txn/branches/{xid}/rollback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Rollback Branch
         * @description 回滚分支（TM 驱动）。
         *
         *     Args:
         *         xid: 分支事务标识。
         *         participant: 应用装配的参与方。
         *         db_key: 目标库键。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分支状态。
         */
        post: operations["rollback_branch_api_v1_txn_branches__xid__rollback_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/user-extensions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List User Extensions
         * @description 按用户列示扩展信息。
         *
         *     Args:
         *         user_id: 用户主键。
         *         uow: 请求级工作单元。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为扩展信息列表（保序）。
         */
        get: operations["list_user_extensions_api_v1_user_extensions_get"];
        put?: never;
        /**
         * Create User Extension
         * @description 新增一条扩展信息（同用户同标签冲突即拒绝）。
         *
         *     Args:
         *         req: 新增请求（用户主键 + 标签 + 备注）。
         *         uow: 请求级工作单元。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为扩展信息行。
         *
         *     Raises:
         *         ConflictError: 同用户同标签已存在（10003）。
         */
        post: operations["create_user_extension_api_v1_user_extensions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/user-extensions/{extension_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update User Extension
         * @description 更新一条扩展信息（整体替换标签与备注）。
         *
         *     Args:
         *         extension_id: 扩展信息主键。
         *         req: 更新请求（标签 + 备注）。
         *         uow: 请求级工作单元。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后的扩展信息行。
         *
         *     Raises:
         *         NotFoundError: 记录不存在（10002）。
         *         ConflictError: 改后与既有行同标签（10003）。
         */
        put: operations["update_user_extension_api_v1_user_extensions__extension_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Users
         * @description 用户列表（关键字「用户名 / 姓名 / 邮箱 / 手机号」+ 状态筛选 + 分页）。
         *
         *     Args:
         *         query: 分页与排序参数。
         *         uow: 请求级工作单元。
         *         kw: 关键字（四字段模糊，大小写不敏感）。
         *         status: 账号状态（enabled/disabled）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页用户列表。
         */
        get: operations["list_users_api_v1_users_get"];
        put?: never;
        /**
         * Create User
         * @description 新建用户（初始密码可选；支持 `Idempotency-Key` 幂等）。
         *
         *     Args:
         *         req: 新建用户请求。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希器。
         *         policy: 密码策略。
         *         outbox: 事务性发件箱存储。
         *         client: 服务间调用客户端。
         *         idempotency: 幂等存储。
         *         audit: 审计捕获（占位）。
         *         idem_key: 幂等键请求头。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为新建用户详情与（后端生成的）初始密码。
         *
         *     Raises:
         *         ConflictError: 同一幂等键的首个请求仍在处理中（10003）。
         *         UsernameExistsError: 用户名已存在（30003）。
         */
        post: operations["create_user_api_v1_users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get User Detail
         * @description 用户详情（含联系方式与乐观锁版本）。
         *
         *     Args:
         *         user_id: 用户主键。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希器（服务构造用）。
         *         policy: 密码策略（服务构造用）。
         *         outbox: 发件箱（服务构造用）。
         *         client: 服务间调用客户端（服务构造用）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为用户详情。
         */
        get: operations["get_user_detail_api_v1_users__user_id__get"];
        /**
         * Update User
         * @description 修改用户基本资料（昵称 / 邮箱 / 手机；乐观锁）。
         *
         *     Args:
         *         user_id: 用户主键。
         *         req: 修改请求。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希器（服务构造用）。
         *         policy: 密码策略（服务构造用）。
         *         outbox: 发件箱（服务构造用）。
         *         client: 服务间调用客户端（服务构造用）。
         *         audit: 审计捕获（占位）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后的用户详情。
         */
        put: operations["update_user_api_v1_users__user_id__put"];
        post?: never;
        /**
         * Delete User
         * @description 软删除用户（引用校验 + 关闭未解锁锁定记录 + 失效全部会话）。
         *
         *     Args:
         *         user_id: 用户主键。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希器（服务构造用）。
         *         policy: 密码策略（服务构造用）。
         *         outbox: 发件箱（服务构造用）。
         *         client: 服务间调用客户端（会话失效）。
         *         audit: 审计捕获（占位）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为删除与会话撤销结果。
         */
        delete: operations["delete_user_api_v1_users__user_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/{user_id}/assignments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Apply User Assignments
         * @description 用户保存编排（分段全量覆盖；跨服务原子）。
         *
         *     `provider = "xa"` 时经 TM 全局事务（platform 分支进程内 + 组织域分支经参与端点）；
         *     `provider = null`（dev / test）时顺序提交（platform 本地事务 → 组织域内部写通道）。
         *     权限码**分段校验**：`profile` 段另需 `user:update`。
         *
         *     Args:
         *         user_id: 用户主键。
         *         req: 分段全量覆盖请求。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希器（占位：保持构造口径一致）。
         *         policy: 密码策略（占位）。
         *         outbox: 事务性发件箱存储。
         *         client: 服务间调用客户端（组织域分支执行 / 内部写通道；提交后会话失效）。
         *         cache: 缓存能力域（角色分配变更后权限版本递增）。
         *         manager: 事务管理器（`provider=null` 时为 Null 实现）。
         *         participant: 事务参与方（platform 自身分支进程内执行）。
         *         checker: 权限校验器（`profile` 段命令式复校）。
         *         audit: 审计捕获（占位）。
         *         idem_key: 幂等键请求头（透传给组织域内部写通道）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为用户详情、生效后角色清单与本次参与分段名。
         *
         *     Raises:
         *         PermissionError: 缺少 `user:update`（30001）。
         *         ParamError: 未提供任何分段 / 主要项不在集合内（10001）。
         *         TransactionUnavailableError: 分支未达 `PREPARED`（10013）。
         *         ServiceUnavailableError: 跨服务调用失败（10007）。
         */
        put: operations["apply_user_assignments_api_v1_users__user_id__assignments_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/{user_id}/password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Reset User Password
         * @description 重置密码（策略校验 + 强制首登改密 + 失效全部会话）。
         *
         *     Args:
         *         user_id: 用户主键。
         *         req: 重置密码请求。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希器。
         *         policy: 密码策略。
         *         outbox: 发件箱（服务构造用）。
         *         client: 服务间调用客户端（会话失效）。
         *         audit: 审计捕获（占位）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为重置与会话撤销结果。
         */
        put: operations["reset_user_password_api_v1_users__user_id__password_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/{user_id}/roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List User Roles
         * @description 查看该用户直接绑定的角色（只读；维护归角色管理）。
         *
         *     Args:
         *         user_id: 用户主键。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希器（服务构造用）。
         *         policy: 密码策略（服务构造用）。
         *         outbox: 发件箱（服务构造用）。
         *         client: 服务间调用客户端（服务构造用）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为直接角色清单。
         */
        get: operations["list_user_roles_api_v1_users__user_id__roles_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/{user_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update User Status
         * @description 启用 / 停用账号（停用即时失效该用户全部会话）。
         *
         *     Args:
         *         user_id: 用户主键。
         *         req: 状态请求。
         *         uow: 请求级工作单元。
         *         hasher: 口令哈希器（服务构造用）。
         *         policy: 密码策略（服务构造用）。
         *         outbox: 发件箱（服务构造用）。
         *         client: 服务间调用客户端（会话失效）。
         *         audit: 审计捕获（占位）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为更新后的用户详情与会话撤销结果。
         */
        put: operations["update_user_status_api_v1_users__user_id__status_put"];
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
         * ActionCreateRequest
         * @description 新增动作码请求（`code` 创建后只读）。
         */
        ActionCreateRequest: {
            /**
             * Code
             * @description 动作码（snake_case：小写字母开头，仅小写字母 / 数字 / 下划线；创建后只读）
             */
            code: string;
            /**
             * I18N
             * @description 多语言名称映射（locale → 文案）；必含请求语言文案
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * ActionItem
         * @description 动作码行（全局动词维度）。
         */
        ActionItem: {
            /**
             * Code
             * @description 动作码
             */
            code: string;
            /**
             * I18N
             * @description 多语言名称（locale → 文案）
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Id
             * @description 动作码主键
             */
            id: string;
            /**
             * Name
             * @description 名称（默认文案）
             */
            name: string;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
        };
        /**
         * ActionList
         * @description 动作码清单。
         */
        ActionList: {
            /**
             * Items
             * @description 动作码行列表
             */
            items?: components["schemas"]["ActionItem"][];
        };
        /**
         * ActionUpdateRequest
         * @description 更新动作码请求（`code` 不可改，只改名称与状态）。
         */
        ActionUpdateRequest: {
            /**
             * I18N
             * @description 多语言名称映射（locale → 文案）；必含请求语言文案
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
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
        /** ApiResponse[ActionItem] */
        ApiResponse_ActionItem_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["ActionItem"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[ActionList] */
        ApiResponse_ActionList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["ActionList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[BasePageResponse[AssignedUserItem]] */
        ApiResponse_BasePageResponse_AssignedUserItem__: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BasePageResponse_AssignedUserItem_"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[BasePageResponse[InternalUserItem]] */
        ApiResponse_BasePageResponse_InternalUserItem__: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BasePageResponse_InternalUserItem_"] | null;
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
        /** ApiResponse[BasePageResponse[RoleItem]] */
        ApiResponse_BasePageResponse_RoleItem__: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BasePageResponse_RoleItem_"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[BasePageResponse[UserItem]] */
        ApiResponse_BasePageResponse_UserItem__: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BasePageResponse_UserItem_"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[BranchRecoverView] */
        ApiResponse_BranchRecoverView_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BranchRecoverView"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[BranchStateView] */
        ApiResponse_BranchStateView_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BranchStateView"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[BusinessItem] */
        ApiResponse_BusinessItem_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BusinessItem"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[BusinessList] */
        ApiResponse_BusinessList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["BusinessList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[ButtonItem] */
        ApiResponse_ButtonItem_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["ButtonItem"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[ButtonList] */
        ApiResponse_ButtonList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["ButtonList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[CatalogSnapshotResponse] */
        ApiResponse_CatalogSnapshotResponse_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["CatalogSnapshotResponse"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[ConfigResolveResponse] */
        ApiResponse_ConfigResolveResponse_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["ConfigResolveResponse"] | null;
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
        /** ApiResponse[DataSourceListResponse] */
        ApiResponse_DataSourceListResponse_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["DataSourceListResponse"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[DictAdvQueryResult] */
        ApiResponse_DictAdvQueryResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["DictAdvQueryResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[DictAttrListResponse] */
        ApiResponse_DictAttrListResponse_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["DictAttrListResponse"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[DictBatchResult] */
        ApiResponse_DictBatchResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["DictBatchResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[DictQueryProviderListResponse] */
        ApiResponse_DictQueryProviderListResponse_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["DictQueryProviderListResponse"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[DictTypeResult] */
        ApiResponse_DictTypeResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["DictTypeResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[FieldItem] */
        ApiResponse_FieldItem_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["FieldItem"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[FieldList] */
        ApiResponse_FieldList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["FieldList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[FormItem] */
        ApiResponse_FormItem_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["FormItem"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[FormKeyListResponse] */
        ApiResponse_FormKeyListResponse_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["FormKeyListResponse"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[FormList] */
        ApiResponse_FormList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["FormList"] | null;
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
        /** ApiResponse[MenuItem] */
        ApiResponse_MenuItem_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["MenuItem"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[MenuTree] */
        ApiResponse_MenuTree_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["MenuTree"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[MyMenuResponse] */
        ApiResponse_MyMenuResponse_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["MyMenuResponse"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[NoneType] */
        ApiResponse_NoneType_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            /** Data */
            data?: null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[PermissionGenerateResult] */
        ApiResponse_PermissionGenerateResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["PermissionGenerateResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[PermissionInvalidateResult] */
        ApiResponse_PermissionInvalidateResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["PermissionInvalidateResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[PermissionItem] */
        ApiResponse_PermissionItem_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["PermissionItem"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[PermissionList] */
        ApiResponse_PermissionList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["PermissionList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[PermissionMetadataResult] */
        ApiResponse_PermissionMetadataResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["PermissionMetadataResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[PermissionSubjectResult] */
        ApiResponse_PermissionSubjectResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["PermissionSubjectResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[RoleAssignedUsers] */
        ApiResponse_RoleAssignedUsers_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["RoleAssignedUsers"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[RoleAssignmentsResult] */
        ApiResponse_RoleAssignmentsResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["RoleAssignmentsResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[RoleDataScopes] */
        ApiResponse_RoleDataScopes_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["RoleDataScopes"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[RoleDetail] */
        ApiResponse_RoleDetail_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["RoleDetail"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[RoleFields] */
        ApiResponse_RoleFields_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["RoleFields"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[RolePermissions] */
        ApiResponse_RolePermissions_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["RolePermissions"] | null;
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
        /** ApiResponse[UserAdminCreateResult] */
        ApiResponse_UserAdminCreateResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserAdminCreateResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UserAssignmentsResult] */
        ApiResponse_UserAssignmentsResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserAssignmentsResult"] | null;
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
        /** ApiResponse[UserDeleteResult] */
        ApiResponse_UserDeleteResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserDeleteResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UserDetail] */
        ApiResponse_UserDetail_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserDetail"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UserExtensionItem] */
        ApiResponse_UserExtensionItem_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserExtensionItem"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UserExtensionList] */
        ApiResponse_UserExtensionList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserExtensionList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UserPasswordResetResult] */
        ApiResponse_UserPasswordResetResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserPasswordResetResult"] | null;
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
        /** ApiResponse[UserRoleList] */
        ApiResponse_UserRoleList_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserRoleList"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[UserStatusResult] */
        ApiResponse_UserStatusResult_: {
            /**
             * Code
             * @default 0
             */
            code: number;
            data?: components["schemas"]["UserStatusResult"] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /** ApiResponse[list[ModuleResponse]] */
        ApiResponse_list_ModuleResponse__: {
            /**
             * Code
             * @default 0
             */
            code: number;
            /** Data */
            data?: components["schemas"]["ModuleResponse"][] | null;
            /**
             * Message
             * @default ok
             */
            message: string;
        };
        /**
         * AssignedUserItem
         * @description 角色已分配用户行（最小字段，同库取 `sys_user`）。
         */
        AssignedUserItem: {
            /**
             * Name
             * @description 用户昵称 / 显示名
             */
            name: string;
            /**
             * Status
             * @description 账号状态（enabled/disabled）
             */
            status: string;
            /**
             * User Id
             * @description 用户主键
             */
            user_id: string;
            /**
             * Username
             * @description 登录账号
             */
            username: string;
        };
        /** BasePageResponse[AssignedUserItem] */
        BasePageResponse_AssignedUserItem_: {
            /** List */
            list: components["schemas"]["AssignedUserItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** BasePageResponse[InternalUserItem] */
        BasePageResponse_InternalUserItem_: {
            /** List */
            list: components["schemas"]["InternalUserItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
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
        /** BasePageResponse[RoleItem] */
        BasePageResponse_RoleItem_: {
            /** List */
            list: components["schemas"]["RoleItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** BasePageResponse[UserItem] */
        BasePageResponse_UserItem_: {
            /** List */
            list: components["schemas"]["UserItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /**
         * BranchExecuteRequest
         * @description 分支执行请求（由发起方给出；`ops` 按序在**同一分支**内执行）。
         *
         *     一个分支＝一条 XA 事务＝一条数据库连接，故分支内的全部操作必须一次请求提交；
         *     调用方可把同库的多个写入合并进同一分支（如「用户-岗位 + 用户-部门」）。
         */
        BranchExecuteRequest: {
            /** Db Key */
            db_key: string;
            /**
             * Ops
             * @description 分支操作清单（按序执行；非空）
             */
            ops?: components["schemas"]["BranchOpRequest"][];
            /** Xid */
            xid: string;
        };
        /**
         * BranchOpRequest
         * @description 分支内的单个业务操作（`op` 映射参与方**已有服务层方法**）。
         */
        BranchOpRequest: {
            /**
             * Args
             * @description 业务载荷（交给参与方已有服务层）
             */
            args?: {
                [key: string]: unknown;
            };
            /** Op */
            op: string;
        };
        /**
         * BranchRecoverView
         * @description 悬挂分支列举视图。
         */
        BranchRecoverView: {
            /** Db Key */
            db_key: string;
            /**
             * Xids
             * @description 悬挂分支 `xid` 文本形态清单
             */
            xids?: string[];
        };
        /**
         * BranchStateView
         * @description 分支状态视图。
         */
        BranchStateView: {
            /** State */
            state: string;
            /** Xid */
            xid: string;
        };
        /**
         * BusinessCreateRequest
         * @description 新增业务码请求（`code` 创建后只读）。
         */
        BusinessCreateRequest: {
            /**
             * Code
             * @description 业务码（snake_case：小写字母开头，仅小写字母 / 数字 / 下划线；创建后只读）
             */
            code: string;
            /**
             * I18N
             * @description 多语言名称映射（locale → 文案）；必含请求语言文案
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * BusinessItem
         * @description 业务码行（纯资源维度）。
         */
        BusinessItem: {
            /**
             * Code
             * @description 业务码
             */
            code: string;
            /**
             * I18N
             * @description 多语言名称（locale → 文案）
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Id
             * @description 业务码主键
             */
            id: string;
            /**
             * Name
             * @description 名称（默认文案）
             */
            name: string;
            /**
             * Permission Count
             * @description 该业务码下的权限码数量（含停用）
             * @default 0
             */
            permission_count: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
        };
        /**
         * BusinessList
         * @description 业务码清单。
         */
        BusinessList: {
            /**
             * Items
             * @description 业务码行列表
             */
            items?: components["schemas"]["BusinessItem"][];
        };
        /**
         * BusinessUpdateRequest
         * @description 更新业务码请求（`code` 不可改，只改名称与状态）。
         */
        BusinessUpdateRequest: {
            /**
             * I18N
             * @description 多语言名称映射（locale → 文案）；必含请求语言文案
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * ButtonCreateRequest
         * @description 新增按钮请求（挂表单 / 挂权限码）。
         */
        ButtonCreateRequest: {
            /**
             * Form Id
             * @description 所属表单 ID
             */
            form_id: number;
            /**
             * Name
             * @description 按钮名（界面可见文本）
             */
            name: string;
            /**
             * Permission Id
             * @description 挂接权限码 ID
             */
            permission_id: number;
            /**
             * Sort
             * @description 同表内排序（升序）
             * @default 0
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
            /**
             * Type
             * @description 按钮形态（toolbar/interface）
             * @default toolbar
             * @enum {string}
             */
            type: "toolbar" | "interface";
        };
        /**
         * ButtonItem
         * @description 按钮行。
         */
        ButtonItem: {
            /**
             * Form Id
             * @description 所属表单 ID
             */
            form_id: string;
            /**
             * Id
             * @description 按钮主键
             */
            id: string;
            /**
             * Name
             * @description 按钮名
             */
            name: string;
            /**
             * Permission Id
             * @description 挂接权限码 ID
             */
            permission_id: string;
            /**
             * Sort
             * @description 同表内排序
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
            /**
             * Type
             * @description 按钮形态（toolbar/interface）
             */
            type: string;
        };
        /**
         * ButtonList
         * @description 按钮清单。
         */
        ButtonList: {
            /**
             * Items
             * @description 按钮行列表
             */
            items?: components["schemas"]["ButtonItem"][];
        };
        /**
         * ButtonUpdateRequest
         * @description 更新按钮请求。
         */
        ButtonUpdateRequest: {
            /**
             * Name
             * @description 按钮名
             */
            name: string;
            /**
             * Permission Id
             * @description 挂接权限码 ID
             */
            permission_id: number;
            /**
             * Sort
             * @description 同表内排序（升序）
             * @default 0
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
            /**
             * Type
             * @description 按钮形态（toolbar/interface）
             * @default toolbar
             * @enum {string}
             */
            type: "toolbar" | "interface";
        };
        /**
         * CapabilityGrantCreateRequest
         * @description 人工授予请求（幂等 UPSERT 同一「能力 × 消费方」行）。
         *
         *     `expire_at` 与 `note` **成对出现**：临时授权（排障 / 迁移窗口）必须给有效期与理由，
         *     避免长期留存的排障授权；长期授权可不填有效期。
         */
        CapabilityGrantCreateRequest: {
            /**
             * Capability Name
             * @description 能力名（须已登记）
             */
            capability_name: string;
            /**
             * Consumer Key
             * @description 消费方服务键（须已登记）
             */
            consumer_key: string;
            /**
             * Expire At
             * @description 有效期截止（UTC；空=长期有效）
             */
            expire_at?: string | null;
            /**
             * Note
             * @description 授予理由（临时授权必填）
             * @default
             */
            note: string;
        };
        /**
         * CatalogSnapshotResponse
         * @description 带参快照响应（`GET /api/v1/modules/snapshot?with=`；**缺省形态仍为 `ModuleResponse` 数组**）。
         *
         *     口径：
         *
         *     - `modules` 恒下发（服务目录本体，来源不变）；
         *     - `products` / `collaborations` 仅在 `with` 中声明的段下发，未声明为空数组（不额外查询、不多暴露）；
         *     - `snapshot_version` 为带参形态的契约版本（形态变更时递增，便于消费方识别，避免与数组形态混用）；
         *     - `warnings` 承载降级提示（如产品声明未装载），不静默。
         */
        CatalogSnapshotResponse: {
            /** Collaborations */
            collaborations: components["schemas"]["CollaborationSnapshotItem"][];
            /** Modules */
            modules: components["schemas"]["ModuleResponse"][];
            /** Products */
            products: components["schemas"]["ProductSnapshotItem"][];
            /** Snapshot Version */
            snapshot_version: string;
            /** Warnings */
            warnings: string[];
        };
        /**
         * CollaborationSnapshotItem
         * @description 带参快照的能力段（前端取址 / 服务启动对账共用）。
         *
         *     **不含** `path`（不向浏览器暴露服务内部路径）与 `default_consumers` 等授权信息（分配出口归 `02_04`）。
         *     `kind` 供前端区分**能力种类**（`read` / `dataset` / `txn-branch`）——前端按「业务域 + 种类」取址，
         *     不在平台代码写死含产品键的能力名（`03_02`）。
         */
        CollaborationSnapshotItem: {
            /** Contract Version */
            contract_version: string;
            /** Domain */
            domain: string;
            /** Frontend Prefix */
            frontend_prefix: string | null;
            /** Kind */
            kind: string;
            /** Name */
            name: string;
            /** Product Key */
            product_key: string | null;
            /** Replacement */
            replacement: string | null;
            /** Status */
            status: string;
        };
        /**
         * ConfigResolveRequest
         * @description 批量取参数请求。
         */
        ConfigResolveRequest: {
            /**
             * Keys
             * @description 参数键序列
             */
            keys?: string[];
        };
        /**
         * ConfigResolveResponse
         * @description 批量取参数响应（只含存在的键）。
         */
        ConfigResolveResponse: {
            /**
             * Values
             * @description 参数键 → 值（仅存在的键）
             */
            values?: {
                [key: string]: string;
            };
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
        /**
         * DataSourceKind
         * @description 数据源类型（数据形态；预留其它）。
         * @enum {string}
         */
        DataSourceKind: "dict" | "form";
        /**
         * DataSourceListResponse
         * @description 统一数据源登记清单响应（保序：构建期清单序 + 注入序）。
         */
        DataSourceListResponse: {
            /**
             * Items
             * @description 数据源登记记录清单
             */
            items: components["schemas"]["DataSourceResponse"][];
        };
        /**
         * DataSourceOrigin
         * @description 数据源来源（数据所有者类别）。
         * @enum {string}
         */
        DataSourceOrigin: "platform" | "product";
        /**
         * DataSourceResponse
         * @description 数据源登记记录响应（与 `DataSourceRecord` 对齐）。
         */
        DataSourceResponse: {
            /**
             * Allowlist
             * @description 数据权限可匹配字段白名单
             * @default []
             */
            allowlist: string[];
            /**
             * Cascade
             * @description 是否级联（有无上级字段）
             * @default false
             */
            cascade: boolean;
            /**
             * Data Source
             * @description 数据出口标识（统一出口按此路由到具体实现）
             */
            data_source: string;
            /**
             * Data Source Key
             * @description 数据源标识（业务码字符串，全局唯一）
             */
            data_source_key: string;
            /**
             * Is Dict
             * @description 是否字典（由 `kind` 派生；供界面按数据形态套用字典记录页骨架，避免前端各写一套判定）。
             */
            readonly is_dict: boolean;
            /** @description 类型（dict 字典 / form 表单，预留其它） */
            kind: components["schemas"]["DataSourceKind"];
            /**
             * Name
             * @description 名称（数据权限左列 / 通用页面显示）
             */
            name: string;
            /** @description 来源（platform 平台内建 / product 产品提供） */
            origin: components["schemas"]["DataSourceOrigin"];
            /**
             * Path
             * @description 产品取数路径（origin=product 时前端经网关直取）
             */
            path?: string | null;
            /**
             * Product Key
             * @description 产品标识（origin=product 时非空）
             */
            product_key?: string | null;
            /**
             * @description 状态（enabled / disabled）
             * @default enabled
             */
            status: components["schemas"]["DataSourceStatus"];
            /**
             * Strategies
             * @description 可用策略集合（select / region / match / extension）
             * @default [
             *       "select"
             *     ]
             */
            strategies: components["schemas"]["DataSourceStrategy"][];
        };
        /**
         * DataSourceStatus
         * @description 数据源登记项状态。
         * @enum {string}
         */
        DataSourceStatus: "enabled" | "disabled";
        /**
         * DataSourceStrategy
         * @description 数据权限可用策略（供数据权限左列渲染，只选不编）。
         * @enum {string}
         */
        DataSourceStrategy: "select" | "region" | "match" | "extension";
        /**
         * DeclarationSubmitRequest
         * @description 全量上报请求（单次全量，服务端按「本产品维度整体对账」）。
         */
        DeclarationSubmitRequest: {
            /** Manifest Toml */
            manifest_toml: string;
            /** Product Key */
            product_key: string;
            /** Service Key */
            service_key: string;
        };
        /**
         * DemoCreateRequest
         * @description 创建 demo 请求。
         */
        DemoCreateRequest: {
            /**
             * Name
             * @description demo 名称
             */
            name: string;
        };
        /**
         * DemoUpdateRequest
         * @description 更新 demo 请求。
         */
        DemoUpdateRequest: {
            /**
             * Name
             * @description demo 名称
             */
            name: string;
        };
        /**
         * DictAdvItem
         * @description 高级查询结果条目（普通字段）。
         */
        DictAdvItem: {
            /**
             * Code
             * @description 条目编码
             * @default
             */
            code: string;
            /**
             * Color
             * @description 语义色
             */
            color?: string | null;
            /**
             * Label
             * @description 条目标签（按 locale）
             */
            label: string;
            /**
             * Parent Id
             * @description 上级条目 ID
             */
            parent_id?: string | null;
            /**
             * Sort
             * @description 排序值
             * @default 0
             */
            sort: number;
            /**
             * Status
             * @description 状态
             * @default enabled
             */
            status: string;
            /**
             * Value
             * @description 条目值
             */
            value: string;
        };
        /**
         * DictAdvQueryPayload
         * @description 高级查询请求体（统一入口）。
         */
        DictAdvQueryPayload: {
            /**
             * Conditions
             * @description 条件组 JSON
             */
            conditions?: {
                [key: string]: unknown;
            } | null;
            /**
             * Page
             * @description 页码（自 1）
             * @default 1
             */
            page: number;
            /**
             * Params
             * @description 提供者参数
             */
            params?: {
                [key: string]: unknown;
            } | null;
            /**
             * Provider
             * @description 查询提供者键（target=business）
             */
            provider?: string | null;
            /**
             * Size
             * @description 页长（≤ 100）
             * @default 20
             */
            size: number;
            /**
             * Target
             * @description 目标（items/business）
             * @default items
             */
            target: string;
        };
        /**
         * DictAdvQueryResult
         * @description 高级查询结果（`items` 取项 / `rows` 业务筛选二选一）。
         */
        DictAdvQueryResult: {
            /**
             * Items
             * @description 字典条目（target=items）
             * @default []
             */
            items: components["schemas"]["DictAdvItem"][];
            /**
             * Page
             * @description 页码（自 1）
             * @default 1
             */
            page: number;
            /**
             * Rows
             * @description 业务记录（target=business）
             * @default []
             */
            rows: {
                [key: string]: unknown;
            }[];
            /**
             * Size
             * @description 页长
             * @default 20
             */
            size: number;
            /**
             * Total
             * @description 命中总数
             * @default 0
             */
            total: number;
        };
        /**
         * DictAttrInfo
         * @description 属性 schema（高级查询条件字段；本期为固定字段）。
         */
        DictAttrInfo: {
            /**
             * Attr Key
             * @description 字段键
             */
            attr_key: string;
            /**
             * Data Type
             * @description 数据类型（text/number/enum）
             */
            data_type: string;
            /**
             * Name
             * @description 字段名
             */
            name: string;
            /**
             * Operators
             * @description 可用操作符
             * @default []
             */
            operators: string[];
            /**
             * Options
             * @description 枚举选项集
             * @default []
             */
            options: {
                [key: string]: unknown;
            }[];
            /**
             * Scope
             * @description 来源（platform/tenant）
             * @default platform
             */
            scope: string;
            /**
             * Sort
             * @description 排序值
             * @default 0
             */
            sort: number;
            /**
             * Widget
             * @description 值控件
             */
            widget?: string | null;
        };
        /**
         * DictAttrListResponse
         * @description 字典可查字段 schema 清单响应（保序；供 `GET /dicts/{data_source_key}/attrs`）。
         */
        DictAttrListResponse: {
            /**
             * Items
             * @description 固定字段 schema 清单
             */
            items: components["schemas"]["DictAttrInfo"][];
        };
        /**
         * DictBatchQuery
         * @description 批量合并取数参数对象（表单页多字典字段合并为一次请求）。
         */
        DictBatchQuery: {
            /**
             * Locale
             * @description 语言（默认 zh-CN）
             * @default zh-CN
             */
            locale: string;
            /**
             * Types
             * @description 字典类型码序列
             */
            types: string[];
            /**
             * Version
             * @description 客户端本地版本号；一致的类型 items 返回空
             */
            version?: number | null;
        };
        /**
         * DictBatchResult
         * @description 批量合并取数结果（内层 `DictTypeResult.version` 与批量全局 `version` 同值）。
         */
        DictBatchResult: {
            /**
             * Items
             * @description 按类型的取数结果；None＝该类型版本一致
             */
            items?: {
                [key: string]: components["schemas"]["DictTypeResult"] | null;
            };
            /**
             * Version
             * @description 当前全局版本号
             * @default 0
             */
            version: number;
        };
        /**
         * DictItem
         * @description 字典条目（普通运行时链路字段；不含扩展属性 `attr_json`）。
         *
         *     `parent_id` 为**上级条目 ID**（自引用同表 `id`；顶层 `None`），非父条目 `value`
         *     （2026-10-10 口径收口，任务 02_07）；`id` 供前端级联过滤、字典树构建与**字典字段绑定**使用
         *     （2026-10-21 任务 02_14：字段绑定 `id`，`value` / `code` 仅展示与外部交换）。
         */
        DictItem: {
            /**
             * Code
             * @description 条目编码（仅展示与外部交换，不参与字段绑定）
             * @default
             */
            code: string;
            /**
             * Color
             * @description 语义色（供状态标签取色，可空）
             */
            color?: string | null;
            /**
             * Id
             * @description 条目主键（雪花 ID，JSON 以字符串输出）
             * @default 0
             */
            id: string;
            /**
             * Label
             * @description 条目标签（按 locale）
             */
            label: string;
            /**
             * Parent Id
             * @description 上级条目 ID（自引用 id；None＝顶层）
             */
            parent_id?: string | null;
            /**
             * Sort
             * @description 排序值
             * @default 0
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled / disabled）
             * @default enabled
             */
            status: string;
            /**
             * Value
             * @description 条目值（仅展示与外部交换，不参与字段绑定）
             */
            value: string;
        };
        /**
         * DictQueryProviderInfo
         * @description 查询提供者清单项（发现—选择—调用）。
         */
        DictQueryProviderInfo: {
            /**
             * Data Source Keys
             * @description 适用字典标识（空 = 全部）
             * @default []
             */
            data_source_keys: string[];
            /**
             * Key
             * @description 提供者标识
             */
            key: string;
            /**
             * Name
             * @description 显示名
             */
            name: string;
            /**
             * Param Schema
             * @description 参数 JSON Schema 子集
             */
            param_schema?: {
                [key: string]: unknown;
            };
            /**
             * Target
             * @description 目标（items/business）
             * @default business
             */
            target: string;
        };
        /**
         * DictQueryProviderListResponse
         * @description 查询提供者清单响应（保序；供 `GET /dicts/query-providers`）。
         */
        DictQueryProviderListResponse: {
            /**
             * Items
             * @description 查询提供者清单
             */
            items: components["schemas"]["DictQueryProviderInfo"][];
        };
        /**
         * DictTypeResult
         * @description 单类型取数结果（`items=None` 表示版本一致，前端复用本地缓存）。
         */
        DictTypeResult: {
            /**
             * Has More
             * @description 是否还有更多（超过 limit 截断）
             * @default false
             */
            has_more: boolean;
            /**
             * Items
             * @description 条目集；None＝版本一致（省流量）；空元组＝确无数据
             */
            items?: components["schemas"]["DictItem"][] | null;
            /**
             * Total
             * @description 命中总数
             * @default 0
             */
            total: number;
            /**
             * Version
             * @description 当前全局版本号
             * @default 0
             */
            version: number;
        };
        /**
         * ExpressionContextPayload
         * @description 表达式校验上下文：`{scope?, fields?, variables?}`。
         */
        ExpressionContextPayload: {
            /**
             * Fields
             * @description 可用字段（场景侧下发）
             */
            fields?: string[];
            /**
             * Scope
             * @description 表达式场景（data_scope / workflow_condition / report / custom）
             * @default custom
             */
            scope: string;
            /**
             * Variables
             * @description 预置变量（场景侧下发）
             */
            variables?: string[];
        };
        /**
         * ExpressionValidateRequest
         * @description 表达式校验请求：`{expr, context?}`。
         */
        ExpressionValidateRequest: {
            /** @description 校验上下文（缺省按自定义场景） */
            context?: components["schemas"]["ExpressionContextPayload"] | null;
            /**
             * Expr
             * @description 表达式文本（字段 + 运算符 + 预置变量）
             */
            expr: string;
        };
        /**
         * FieldCreateRequest
         * @description 新增字段请求（只提交多语言文案映射）。
         */
        FieldCreateRequest: {
            /**
             * Field Key
             * @description 字段键（表单内唯一）
             */
            field_key: string;
            /**
             * Form Id
             * @description 所属表单 ID
             */
            form_id: number;
            /**
             * I18N
             * @description 多语言文案映射（locale → 文案）；必含请求语言（登录用户语言）的文案
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Sort
             * @description 同表内排序（升序）
             * @default 0
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
            /**
             * Type
             * @description 字段类型（组件语义键）
             */
            type: string;
        };
        /**
         * FieldItem
         * @description 字段行。
         */
        FieldItem: {
            /**
             * Field Key
             * @description 字段键（表单内唯一）
             */
            field_key: string;
            /**
             * Form Id
             * @description 所属表单 ID
             */
            form_id: string;
            /**
             * I18N
             * @description 多语言名称（locale → 文案）
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Id
             * @description 字段主键
             */
            id: string;
            /**
             * Name
             * @description 字段名（默认文案）
             */
            name: string;
            /**
             * Sort
             * @description 同表内排序
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
            /**
             * Type
             * @description 字段类型（组件语义键）
             */
            type: string;
        };
        /**
         * FieldList
         * @description 字段清单。
         */
        FieldList: {
            /**
             * Items
             * @description 字段行列表
             */
            items?: components["schemas"]["FieldItem"][];
        };
        /**
         * FieldUpdateRequest
         * @description 更新字段请求（只提交多语言文案映射）。
         */
        FieldUpdateRequest: {
            /**
             * I18N
             * @description 多语言文案映射（locale → 文案）；必含请求语言（登录用户语言）的文案
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Sort
             * @description 同表内排序（升序）
             * @default 0
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
            /**
             * Type
             * @description 字段类型（组件语义键）
             */
            type: string;
        };
        /**
         * FormCreateRequest
         * @description 新增表单请求（挂业务；菜单入口多对多，可空 = 孤儿表单）。
         */
        FormCreateRequest: {
            /**
             * Business Id
             * @description 所属业务码 ID
             */
            business_id: number;
            /**
             * Component
             * @description 表单视图组件标识
             */
            component?: string | null;
            /**
             * Menu Ids
             * @description 关联菜单入口 ID 清单（可空）
             */
            menu_ids?: number[];
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * FormItem
         * @description 表单行（菜单入口多对多）。
         */
        FormItem: {
            /**
             * Business Id
             * @description 所属业务码 ID
             */
            business_id: string;
            /**
             * Component
             * @description 表单视图组件标识
             */
            component: string | null;
            /**
             * Created At
             * Format: date-time
             * @description 创建时间（UTC）
             */
            created_at: string;
            /**
             * Id
             * @description 表单主键
             */
            id: string;
            /**
             * Menu Ids
             * @description 关联菜单入口 ID 清单（雪花 ID 字符串化；空 = 无入口表单）
             */
            menu_ids?: string[];
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
            /**
             * Updated At
             * Format: date-time
             * @description 更新时间（UTC）
             */
            updated_at: string;
        };
        /**
         * FormKeyListResponse
         * @description 表单标识清单响应（保序：构建期清单序 + 注入序）。
         */
        FormKeyListResponse: {
            /**
             * Items
             * @description 表单标识登记记录清单
             */
            items: components["schemas"]["FormKeyResponse"][];
        };
        /**
         * FormKeyResponse
         * @description 表单标识登记记录响应（与 `FormRecord` 对齐）。
         */
        FormKeyResponse: {
            /**
             * Data Source Key
             * @description 数据源标识（`form_key → data_source_key` 多对一）
             */
            data_source_key?: string | null;
            /**
             * Form Key
             * @description 表单标识（业务码字符串，全局唯一、保存后不变）
             */
            form_key: string;
            /**
             * Is Dict
             * @description 是否字典（由 `kind` 派生；供界面按数据形态套用字典记录页骨架，避免前端各写一套判定）。
             */
            readonly is_dict: boolean;
            /** @description 类型（dict 字典 / form 表单） */
            kind: components["schemas"]["FormKind"];
            /**
             * Name
             * @description 名称（通用页面展示）
             */
            name: string;
            /**
             * @description 状态（enabled / disabled）
             * @default enabled
             */
            status: components["schemas"]["FormStatus"];
            /**
             * Table
             * @description 物理表名（该标识所在实体表）
             */
            table: string;
        };
        /**
         * FormKind
         * @description 表单类型（数据形态）。
         * @enum {string}
         */
        FormKind: "dict" | "form";
        /**
         * FormList
         * @description 表单清单。
         */
        FormList: {
            /**
             * Items
             * @description 表单行列表
             */
            items?: components["schemas"]["FormItem"][];
        };
        /**
         * FormStatus
         * @description 表单登记项状态。
         * @enum {string}
         */
        FormStatus: "enabled" | "disabled";
        /**
         * FormUpdateRequest
         * @description 更新表单请求（菜单入口关联全量替换）。
         */
        FormUpdateRequest: {
            /**
             * Business Id
             * @description 所属业务码 ID
             */
            business_id: number;
            /**
             * Component
             * @description 表单视图组件标识
             */
            component?: string | null;
            /**
             * Menu Ids
             * @description 关联菜单入口 ID 清单（全量；空 = 解除全部入口）
             */
            menu_ids?: number[];
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * IconCreateRequest
         * @description 图标新增请求：`{code, name, category, tags?, svg}`。
         */
        IconCreateRequest: {
            /**
             * Category
             * @description 图标分组（分类）
             */
            category: string;
            /**
             * Code
             * @description 自建图标码（snake_case，租户内唯一）
             */
            code: string;
            /**
             * I18N
             * @description 多语言名称映射（locale → 文案）
             */
            i18n?: {
                [key: string]: string;
            };
            /**
             * Name
             * @description 图标名称
             */
            name: string;
            /**
             * Svg
             * @description SVG 内容（内联）
             */
            svg: string;
            /**
             * Tags
             * @description 标签（搜索用）
             */
            tags?: string[];
        };
        /**
         * IconUpdateRequest
         * @description 图标更新请求：`{name?, category?, tags?, svg?, status?}`（None 表示该项不变）。
         */
        IconUpdateRequest: {
            /**
             * Category
             * @description 图标分组
             */
            category?: string | null;
            /**
             * I18N
             * @description 多语言名称映射（locale → 文案；None 表示不变）
             */
            i18n?: {
                [key: string]: string;
            } | null;
            /**
             * Name
             * @description 图标名称
             */
            name?: string | null;
            /**
             * Status
             * @description 状态（active 启用 / disabled 停用）
             */
            status?: string | null;
            /**
             * Svg
             * @description SVG 内容
             */
            svg?: string | null;
            /**
             * Tags
             * @description 标签（搜索用）
             */
            tags?: string[] | null;
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
         * InternalUserItem
         * @description 内部用户只读行（服务间出口）：联系方式**原样返回**（脱敏归消费方），不含口令与锁定字段。
         *
         *     用户＝系统账号，**不含组织字段**（部门 / 岗位关系归产品组织域，需求 07-11）——用户-部门关系由
         *     产品自持（`org_user_dept`），不需 platform 回传。
         */
        InternalUserItem: {
            /**
             * Email
             * @description 邮箱（原样返回，脱敏归消费方）
             */
            email?: string | null;
            /**
             * Id
             * @description 用户主键
             */
            id: string;
            /**
             * Name
             * @description 昵称 / 显示名
             */
            name: string;
            /**
             * Phone
             * @description 手机号（原样返回，脱敏归消费方）
             */
            phone?: string | null;
            /**
             * Status
             * @description 账号状态（enabled / disabled）
             */
            status: string;
            /**
             * Username
             * @description 登录账号
             */
            username: string;
        };
        /**
         * InternalUserQueryRequest
         * @description 内部用户只读查询请求（服务间调用；租户经服务 JWT `tenant` claim 解析）。
         */
        InternalUserQueryRequest: {
            /**
             * Ids
             * @description 限定集合（空 = 不限定；非空时只在该集合内筛选）
             */
            ids?: number[];
            /**
             * Keyword
             * @description 关键字（账号 / 姓名，大小写不敏感）
             */
            keyword?: string | null;
            /**
             * Page
             * @description 页码（从 1 起）
             * @default 1
             */
            page: number;
            /**
             * Size
             * @description 每页条数（上限 200）
             * @default 20
             */
            size: number;
            /**
             * Status
             * @description 账号状态（enabled / disabled）
             */
            status?: string | null;
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
             * Name
             * @description 用户昵称 / 显示名（同库回显；用户已不存在为空串）
             * @default
             */
            name: string;
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
            /**
             * Username
             * @description 用户登录账号（`sys_user` 同库回显；用户已不存在为空串）
             * @default
             */
            username: string;
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
         * MenuCreateRequest
         * @description 新增菜单请求（只提交多语言文案映射；主表默认文案由服务端按优先级派生）。
         */
        MenuCreateRequest: {
            /**
             * Component
             * @description 视图组件标识（可空 = 目录节点）
             */
            component?: string | null;
            /**
             * Hidden
             * @description 仅隐藏侧栏入口（权限仍生效）
             * @default false
             */
            hidden: boolean;
            /**
             * I18N
             * @description 多语言文案映射（locale → 文案）；必含请求语言（登录用户语言）的文案
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Icon
             * @description 完整 icon key
             */
            icon?: string | null;
            /**
             * Parent Id
             * @description 父菜单 ID（0 为根）
             * @default 0
             */
            parent_id: number;
            /**
             * Path
             * @description 前端路由路径（/ 开头）
             */
            path: string;
            /**
             * Sort
             * @description 同级排序（升序）
             * @default 0
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * MenuItem
         * @description 菜单节点（平台维护视图，树形嵌套）。
         */
        MenuItem: {
            /**
             * Children
             * @description 子菜单（树形）
             */
            children?: components["schemas"]["MenuItem"][];
            /**
             * Component
             * @description 视图组件标识
             */
            component: string | null;
            /**
             * Hidden
             * @description 仅隐藏侧栏入口
             */
            hidden: boolean;
            /**
             * I18N
             * @description 多语言名称（locale → 文案）
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Icon
             * @description 完整 icon key
             */
            icon: string | null;
            /**
             * Id
             * @description 菜单主键（雪花 ID，JSON 以字符串输出）
             */
            id: string;
            /**
             * Name
             * @description 菜单名（默认文案）
             */
            name: string;
            /**
             * Parent Id
             * @description 父菜单 ID（0 为根）
             */
            parent_id: string;
            /**
             * Path
             * @description 前端路由路径
             */
            path: string;
            /**
             * Sort
             * @description 同级排序
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
        };
        /**
         * MenuTree
         * @description 菜单树（平台维护视图）。
         */
        MenuTree: {
            /**
             * Items
             * @description 根级菜单（子节点嵌套）
             */
            items?: components["schemas"]["MenuItem"][];
        };
        /**
         * MenuUpdateRequest
         * @description 更新菜单请求（整体替换；只提交多语言文案映射）。
         */
        MenuUpdateRequest: {
            /**
             * Component
             * @description 视图组件标识
             */
            component?: string | null;
            /**
             * Hidden
             * @description 仅隐藏侧栏入口
             * @default false
             */
            hidden: boolean;
            /**
             * I18N
             * @description 多语言文案映射（locale → 文案）；必含请求语言（登录用户语言）的文案
             */
            i18n: {
                [key: string]: string;
            };
            /**
             * Icon
             * @description 完整 icon key
             */
            icon?: string | null;
            /**
             * Parent Id
             * @description 父菜单 ID（0 为根）
             */
            parent_id: number;
            /**
             * Path
             * @description 前端路由路径（/ 开头）
             */
            path: string;
            /**
             * Sort
             * @description 同级排序（升序）
             * @default 0
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * ModuleResponse
         * @description 服务目录登记记录响应（与 `sys_module` 对齐）。
         *
         *     `tenant_base` 为**派生标记**：平台模块取自 `TENANT_BASE_MODULE_KEYS`，产品模块取自恒开通清单
         *     （`tenant_base_module_keys()`，其来源是服务行落库的 `tenant_base` 声明）；租户服务据此判定恒开通。
         */
        ModuleResponse: {
            /** Build Batch */
            build_batch: number;
            /** Business Code */
            business_code: string | null;
            /** Contract Version */
            contract_version: string;
            /** Errcode Segment */
            errcode_segment: string | null;
            /** Event Domain */
            event_domain: string;
            /** Module Key */
            module_key: string;
            /** Name */
            name: string;
            /** Product Key */
            product_key: string | null;
            /** Service Group */
            service_group: string;
            /** Service Key */
            service_key: string | null;
            /** Service Version */
            service_version: string;
            /** Status */
            status: string;
            /** Table Prefix */
            table_prefix: string;
            /**
             * Tenant Base
             * @default false
             */
            tenant_base: boolean;
        };
        /**
         * MyMenuButton
         * @description 动态菜单下的按钮元数据（按权限码标记可见）。
         */
        MyMenuButton: {
            /**
             * Id
             * @description 按钮主键
             */
            id: string;
            /**
             * Name
             * @description 按钮名
             */
            name: string;
            /**
             * Permission Code
             * @description 权限码（业务码:动作码）
             */
            permission_code: string;
            /**
             * Permission Id
             * @description 挂接权限码 ID
             */
            permission_id: string;
            /**
             * Sort
             * @description 同表内排序
             */
            sort: number;
            /**
             * Type
             * @description 按钮形态（toolbar/interface）
             */
            type: string;
            /**
             * Visible
             * @description 当前用户是否持有该权限码
             */
            visible: boolean;
        };
        /**
         * MyMenuField
         * @description 动态菜单下的字段元数据（按字段权限标记可见 / 可编辑）。
         */
        MyMenuField: {
            /**
             * Editable
             * @description 字段是否可编辑
             */
            editable: boolean;
            /**
             * Field Key
             * @description 字段键
             */
            field_key: string;
            /**
             * Id
             * @description 字段主键
             */
            id: string;
            /**
             * Name
             * @description 字段名（按 locale 本地化，缺省回退默认文案）
             */
            name: string;
            /**
             * Sort
             * @description 同表内排序
             */
            sort: number;
            /**
             * Type
             * @description 字段类型（组件语义键）
             */
            type: string;
            /**
             * Visible
             * @description 字段是否可见
             */
            visible: boolean;
        };
        /**
         * MyMenuForm
         * @description 动态菜单下的表单元数据（一个菜单入口可关联多个表单）。
         */
        MyMenuForm: {
            /**
             * Business Code
             * @description 业务权限码
             */
            business_code: string;
            /**
             * Business Id
             * @description 所属业务码 ID
             */
            business_id: string;
            /**
             * Buttons
             * @description 按钮元数据（按动作权限标记）
             */
            buttons?: components["schemas"]["MyMenuButton"][];
            /**
             * Component
             * @description 表单视图组件标识
             */
            component: string | null;
            /**
             * Fields
             * @description 字段元数据（按字段权限标记）
             */
            fields?: components["schemas"]["MyMenuField"][];
            /**
             * Id
             * @description 表单主键
             */
            id: string;
            /**
             * Menu Id
             * @description 关联菜单入口 ID（即当前节点 ID）
             */
            menu_id: string;
        };
        /**
         * MyMenuNode
         * @description 动态菜单节点（过滤后菜单树，含表单元数据，多对多）。
         */
        MyMenuNode: {
            /**
             * Children
             * @description 子菜单（树形）
             */
            children?: components["schemas"]["MyMenuNode"][];
            /**
             * Component
             * @description 视图组件标识
             */
            component: string | null;
            /**
             * Forms
             * @description 该入口关联的表单元数据（挂接链完整时非空）
             */
            forms?: components["schemas"]["MyMenuForm"][];
            /**
             * Hidden
             * @description 仅隐藏侧栏入口（路由可直达）
             */
            hidden: boolean;
            /**
             * Icon
             * @description 完整 icon key
             */
            icon: string | null;
            /**
             * Id
             * @description 菜单主键
             */
            id: string;
            /**
             * Name
             * @description 菜单名（按 locale 本地化，缺省回退默认文案）
             */
            name: string;
            /**
             * Parent Id
             * @description 父菜单 ID（0 为根）
             */
            parent_id: string;
            /**
             * Path
             * @description 前端路由路径
             */
            path: string;
            /**
             * Sort
             * @description 同级排序
             */
            sort: number;
        };
        /**
         * MyMenuResponse
         * @description 动态菜单响应：菜单树 + 表单元数据 + 当前用户权限码集合。
         */
        MyMenuResponse: {
            /**
             * Locale
             * @description 解析后的语言标识
             */
            locale: string;
            /**
             * Menus
             * @description 过滤后的菜单树（子节点嵌套）
             */
            menus?: components["schemas"]["MyMenuNode"][];
            /**
             * Permissions
             * @description 当前用户权限码集合（业务码:动作码）
             */
            permissions?: string[];
            /**
             * Version
             * @description 元数据版本号（缓存版本）
             */
            version: number;
        };
        /**
         * PermissionCreateRequest
         * @description 手工新增权限码组合（组合创建后只读）。
         */
        PermissionCreateRequest: {
            /**
             * Action Id
             * @description 动作码 ID
             */
            action_id: number;
            /**
             * Business Id
             * @description 业务码 ID
             */
            business_id: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * PermissionDataScopeItem
         * @description 数据范围规则（字典类型 + 策略 + 规则行）。
         */
        PermissionDataScopeItem: {
            /**
             * Config
             * @description 规则行（原样，交策略求值器解析）
             */
            config?: {
                [key: string]: unknown;
            }[];
            /**
             * Data Source Key
             * @description 字典类型主键（字符串化）
             */
            data_source_key: string;
            /**
             * Policy Type
             * @description 策略类型：select / region / match / extension
             */
            policy_type: string;
        };
        /**
         * PermissionFieldItem
         * @description 字段权限收窄项（未列出即全开）。
         */
        PermissionFieldItem: {
            /**
             * Editable
             * @description 写时是否接受
             */
            editable: boolean;
            /**
             * Field Key
             * @description 字段键
             */
            field_key: string;
            /**
             * Form Id
             * @description 表单主键
             */
            form_id: string;
            /**
             * Visible
             * @description 读时是否返回
             */
            visible: boolean;
        };
        /**
         * PermissionGenerateRequest
         * @description 批量补生成缺失权限码组合请求（范围为空 = 全部启用项）。
         */
        PermissionGenerateRequest: {
            /**
             * Action Ids
             * @description 限定动作码 ID 清单（空 = 全部启用动作码）
             */
            action_ids?: number[];
            /**
             * Business Ids
             * @description 限定业务码 ID 清单（空 = 全部启用业务码）
             */
            business_ids?: number[];
            /**
             * Include Disabled
             * @description 是否包含停用的业务 / 动作码
             * @default false
             */
            include_disabled: boolean;
        };
        /**
         * PermissionGenerateResult
         * @description 批量补生成结果计数。
         */
        PermissionGenerateResult: {
            /**
             * Created
             * @description 新建组合数
             */
            created: number;
            /**
             * Restored
             * @description 恢复软删除组合数
             */
            restored: number;
            /**
             * Skipped
             * @description 已存在跳过数
             */
            skipped: number;
        };
        /**
         * PermissionGrantItem
         * @description 授权行（授权类型 + 目标主键）。
         */
        PermissionGrantItem: {
            /**
             * Perm Type
             * @description 授权类型：menu / form / permission
             */
            perm_type: string;
            /**
             * Target Id
             * @description 目标主键（按 perm_type 解释）
             */
            target_id: string;
        };
        /**
         * PermissionInvalidateRequest
         * @description 权限快照失效请求（服务间内部契约）。
         */
        PermissionInvalidateRequest: {
            /**
             * User Ids
             * @description 受影响用户主键（空 = 全租户版本 +1）
             */
            user_ids?: number[];
        };
        /**
         * PermissionInvalidateResult
         * @description 权限快照失效结果（服务间内部契约）。
         */
        PermissionInvalidateResult: {
            /**
             * Version
             * @description 递增后的租户权限版本号
             */
            version: number;
        };
        /**
         * PermissionItem
         * @description 权限码行（业务码 × 动作码组合，真正权限码）。
         */
        PermissionItem: {
            /**
             * Action Code
             * @description 动作码
             */
            action_code: string;
            /**
             * Action Id
             * @description 动作码 ID
             */
            action_id: string;
            /**
             * Business Code
             * @description 业务码
             */
            business_code: string;
            /**
             * Business Id
             * @description 业务码 ID
             */
            business_id: string;
            /**
             * Code
             * @description 权限码（业务码:动作码）
             */
            code: string;
            /**
             * Id
             * @description 权限码主键
             */
            id: string;
            /**
             * Name
             * @description 权限码名称（业务名·动作名，按 locale 本地化）
             * @default
             */
            name: string;
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
        };
        /**
         * PermissionList
         * @description 权限码清单。
         */
        PermissionList: {
            /**
             * Items
             * @description 权限码行列表
             */
            items?: components["schemas"]["PermissionItem"][];
        };
        /**
         * PermissionMetadataResult
         * @description 权限元数据索引（服务间内部契约）。
         */
        PermissionMetadataResult: {
            /**
             * Menu Forms
             * @description 菜单主键（字符串化）→ 关联表单主键列表
             */
            menu_forms?: {
                [key: string]: number[];
            };
            /**
             * Permission Codes
             * @description 权限码主键（字符串化）→ 权限码字符串
             */
            permission_codes?: {
                [key: string]: string;
            };
            /**
             * Version
             * @description 元数据版本号
             */
            version: number;
        };
        /**
         * PermissionSubjectRequest
         * @description 按用户取聚合输入的请求（服务间内部契约）。
         */
        PermissionSubjectRequest: {
            /**
             * User Id
             * @description 用户主键
             */
            user_id: number;
        };
        /**
         * PermissionSubjectResult
         * @description 按用户取回的聚合输入（服务间内部契约）。
         */
        PermissionSubjectResult: {
            /**
             * Data Scope Rules
             * @description 数据范围规则列表
             */
            data_scope_rules?: components["schemas"]["PermissionDataScopeItem"][];
            /**
             * Field Perms
             * @description 字段权限收窄项（空 = 全开）
             */
            field_perms?: components["schemas"]["PermissionFieldItem"][];
            /**
             * Grants
             * @description 授权行列表
             */
            grants?: components["schemas"]["PermissionGrantItem"][];
            /**
             * Role Ids
             * @description 主体链收敛后的角色主键集合
             */
            role_ids?: number[];
            /**
             * Role Types
             * @description 角色主键（字符串化）→ 角色类型
             */
            role_types?: {
                [key: string]: string;
            };
        };
        /**
         * PermissionUpdateRequest
         * @description 更新权限码（组合不可换绑，仅状态）。
         */
        PermissionUpdateRequest: {
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * PreferenceValueRequest
         * @description 偏好写入请求：`{value}`。
         */
        PreferenceValueRequest: {
            /**
             * Value
             * @description 偏好值（JSON 可序列化的任意结构）
             */
            value?: unknown;
        };
        /**
         * ProductSnapshotItem
         * @description 带参快照的产品段（前端产品键来源；**不含** `frontend_package_source` 等构建期信息）。
         */
        ProductSnapshotItem: {
            /** Name */
            name: string;
            /** Product Key */
            product_key: string;
            /** Status */
            status: string;
        };
        /**
         * QueryScheme
         * @description 查询方案数据契约（一份 `sys_query_scheme` 供字典高级查询与列表筛选共用）。
         */
        QueryScheme: {
            /**
             * Conditions
             * @description 条件组 JSON
             */
            conditions?: {
                [key: string]: unknown;
            } | null;
            /**
             * Data Source Key
             * @description 字典标识（target=items 时填）
             */
            data_source_key?: string | null;
            /**
             * Field Key
             * @description 表单标识（target=business 时为 form_key）
             */
            field_key?: string | null;
            /**
             * Id
             * @description 方案 ID（新建为空，落库生成）
             */
            id?: number | null;
            /**
             * Is Default
             * @description 是否默认方案
             * @default false
             */
            is_default: boolean;
            /**
             * Layout
             * @description 展示配置 JSON
             */
            layout?: {
                [key: string]: unknown;
            } | null;
            /**
             * Name
             * @description 方案名
             */
            name: string;
            /**
             * Owner Id
             * @description 归属用户 ID（个人方案）
             */
            owner_id?: number | null;
            /**
             * Params
             * @description 额外参数 JSON
             */
            params?: {
                [key: string]: unknown;
            } | null;
            /**
             * Provider Key
             * @description 查询提供者键（字典高级查询可选）
             */
            provider_key?: string | null;
            /**
             * @description 作用域（个人 / 租户 / 平台）
             * @default user
             */
            scope: components["schemas"]["QuerySchemeScope"];
            /**
             * Shared
             * @description 是否共享
             * @default false
             */
            shared: boolean;
            /**
             * Status
             * @description 状态
             * @default enabled
             */
            status: string;
            /** @description 目标（items 字典条目 / business 列表筛选） */
            target: components["schemas"]["QuerySchemeTarget"];
        };
        /**
         * QuerySchemeScope
         * @description 查询方案作用域。
         * @enum {string}
         */
        QuerySchemeScope: "user" | "tenant" | "platform";
        /**
         * QuerySchemeTarget
         * @description 查询方案目标。
         * @enum {string}
         */
        QuerySchemeTarget: "items" | "business";
        /**
         * RoleAssignRequest
         * @description 批量分配用户请求（幂等 upsert）。
         */
        RoleAssignRequest: {
            /**
             * User Ids
             * @description 用户主键清单
             */
            user_ids?: number[];
        };
        /**
         * RoleAssignedUsers
         * @description 批量分配结果（分配后的用户清单）。
         */
        RoleAssignedUsers: {
            /**
             * Items
             * @description 分配后的用户清单
             */
            items?: components["schemas"]["AssignedUserItem"][];
        };
        /**
         * RoleAssignmentDepts
         * @description 分配编排请求的角色-部门分段（全量覆盖；角色侧无主要项）。
         */
        RoleAssignmentDepts: {
            /**
             * Dept Ids
             * @description 部门主键集合（全量覆盖；空集 = 清空）
             */
            dept_ids?: number[];
        };
        /**
         * RoleAssignmentPosts
         * @description 分配编排请求的角色-岗位分段（全量覆盖；角色侧无主要项）。
         */
        RoleAssignmentPosts: {
            /**
             * Post Ids
             * @description 岗位主键集合（全量覆盖；空集 = 清空）
             */
            post_ids?: number[];
        };
        /**
         * RoleAssignmentProfile
         * @description 分配编排请求的角色本体分段（字段语义同 `RoleUpdateRequest`；`None` 表示不改）。
         */
        RoleAssignmentProfile: {
            /**
             * Code
             * @description 角色码（None = 不改；格式受 role.code_pattern 约束，租户内唯一）
             */
            code?: string | null;
            /**
             * Name
             * @description 角色名称（None = 不改）
             */
            name?: string | null;
            /**
             * Status
             * @description 状态（None = 不改；内置角色改状态被拒）
             */
            status?: ("enabled" | "disabled") | null;
            /**
             * Version
             * @description 客户端版本（乐观锁比对）
             */
            version: number;
        };
        /**
         * RoleAssignmentsRequest
         * @description 角色保存编排请求（分段全量覆盖；未出现的分段不参与，不写）。
         *
         *     分段语义：`role` / `user_ids` / `role_posts` / `role_depts` 为 `None` 表示**不改该段**；
         *     `user_ids` 为空集表示清空该角色全部用户分配。权限码**分段校验**（`role` → `role:update`，
         *     其余段 → `role:grant`）。
         */
        RoleAssignmentsRequest: {
            /** @description 角色本体分段（None = 不改） */
            role?: components["schemas"]["RoleAssignmentProfile"] | null;
            /** @description 角色-部门分段（None = 不改） */
            role_depts?: components["schemas"]["RoleAssignmentDepts"] | null;
            /** @description 角色-岗位分段（None = 不改） */
            role_posts?: components["schemas"]["RoleAssignmentPosts"] | null;
            /**
             * User Ids
             * @description 角色直接用户全量集合（None = 不改；空集 = 清空）
             */
            user_ids?: number[] | null;
        };
        /**
         * RoleAssignmentsResult
         * @description 角色保存编排结果（回带 platform 侧生效后集合）。
         *
         *     组织分配段（岗位 / 部门）的生效后集合由调用方（前端）在保存成功后经产品读契约取回——
         *     XA 分支执行端点契约只回分支状态、不回业务集合。
         */
        RoleAssignmentsResult: {
            /**
             * Applied
             * @description 本次参与的分段名（role / user_ids / role_posts / role_depts）
             */
            applied?: string[];
            /** @description 生效后角色详情 */
            role: components["schemas"]["RoleDetail"];
            /** @description 生效后已分配用户清单 */
            users: components["schemas"]["RoleAssignedUsers"];
        };
        /**
         * RoleCreateRequest
         * @description 新增角色请求（角色码租户内唯一；新角色类型恒为 `custom`，契约不透出）。
         */
        RoleCreateRequest: {
            /**
             * Code
             * @description 角色码（租户内唯一，格式受 role.code_pattern 约束）
             */
            code: string;
            /**
             * Name
             * @description 角色名称
             */
            name: string;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * RoleDataScopeEntryItem
         * @description 数据权限条目行（响应）。
         */
        RoleDataScopeEntryItem: {
            /**
             * Config
             * @description 结构化策略配置
             */
            config?: {
                [key: string]: unknown;
            }[];
            /**
             * Data Source Key
             * @description 字典标识（业务码字符串）
             */
            data_source_key: string;
            /**
             * Id
             * @description 数据权限行主键
             */
            id: string;
            /**
             * Policy Type
             * @description 策略类型（select/region/match/extension）
             */
            policy_type: string;
        };
        /**
         * RoleDataScopeEntryRequest
         * @description 一条数据权限条目（角色 × 字典 × 策略 → 结构化配置，只选不编）。
         */
        RoleDataScopeEntryRequest: {
            /**
             * Config
             * @description 结构化策略配置（按策略分结构）
             */
            config?: {
                [key: string]: unknown;
            }[];
            /**
             * Data Source Key
             * @description 字典标识（业务码字符串，如 org_dept / role）
             */
            data_source_key: string;
            /**
             * Policy Type
             * @description 策略类型（select/region/match/extension）
             * @enum {string}
             */
            policy_type: "select" | "region" | "match" | "extension";
        };
        /**
         * RoleDataScopeRequest
         * @description 数据权限全量覆盖请求。
         */
        RoleDataScopeRequest: {
            /**
             * Entries
             * @description 数据权限条目清单（全量）
             */
            entries?: components["schemas"]["RoleDataScopeEntryRequest"][];
        };
        /**
         * RoleDataScopes
         * @description 角色数据权限条目清单（按字典 × 策略）。
         */
        RoleDataScopes: {
            /**
             * Items
             * @description 数据权限条目清单
             */
            items?: components["schemas"]["RoleDataScopeEntryItem"][];
        };
        /**
         * RoleDetail
         * @description 角色详情（含乐观锁版本与审计字段，供记录页「系统信息」）。
         */
        RoleDetail: {
            /**
             * Builtin
             * @description 是否内置角色（按 role_type 判定）
             */
            builtin: boolean;
            /**
             * Code
             * @description 角色码
             */
            code: string;
            /**
             * Created At
             * Format: date-time
             * @description 创建时间（UTC）
             */
            created_at: string;
            /**
             * Created By
             * @description 创建人
             */
            created_by: number | null;
            /**
             * Id
             * @description 角色主键
             */
            id: string;
            /**
             * Name
             * @description 角色名称
             */
            name: string;
            /**
             * Role Type
             * @description 角色类型（custom/system/security/audit）
             * @enum {string}
             */
            role_type: "custom" | "system" | "security" | "audit" | "platform_admin";
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
            /**
             * Subject Count
             * @description 已分配用户数
             */
            subject_count: number;
            /**
             * Updated At
             * Format: date-time
             * @description 更新时间（UTC）
             */
            updated_at: string;
            /**
             * Updated By
             * @description 更新人
             */
            updated_by: number | null;
            /**
             * Version
             * @description 乐观锁版本
             */
            version: number;
        };
        /**
         * RoleFieldEntryItem
         * @description 字段权限条目行（响应）。
         */
        RoleFieldEntryItem: {
            /**
             * Editable
             * @description 是否可编辑
             */
            editable: boolean;
            /**
             * Field Id
             * @description 字段 ID
             */
            field_id: string;
            /**
             * Form Id
             * @description 表单 ID
             */
            form_id: string;
            /**
             * Id
             * @description 字段权限行主键
             */
            id: string;
            /**
             * Source Menu Id
             * @description 来源菜单入口 ID（0 = 表单级直接授予）
             */
            source_menu_id: string;
            /**
             * Visible
             * @description 是否可见
             */
            visible: boolean;
        };
        /**
         * RoleFieldEntryRequest
         * @description 一条字段权限条目（只落收窄项）。
         */
        RoleFieldEntryRequest: {
            /**
             * Editable
             * @description 是否可编辑（不可见即不可编辑）
             * @default true
             */
            editable: boolean;
            /**
             * Field Id
             * @description 字段 ID
             */
            field_id: number;
            /**
             * Form Id
             * @description 表单 ID
             */
            form_id: number;
            /**
             * Source Menu Id
             * @description 来源菜单入口 ID（0 = 表单级直接授予）
             * @default 0
             */
            source_menu_id: number;
            /**
             * Visible
             * @description 是否可见
             * @default true
             */
            visible: boolean;
        };
        /**
         * RoleFieldRequest
         * @description 字段权限全量覆盖请求。
         */
        RoleFieldRequest: {
            /**
             * Entries
             * @description 字段权限条目清单（全量）
             */
            entries?: components["schemas"]["RoleFieldEntryRequest"][];
        };
        /**
         * RoleFields
         * @description 角色字段权限条目清单（仅收窄项）。
         */
        RoleFields: {
            /**
             * Items
             * @description 字段权限条目清单
             */
            items?: components["schemas"]["RoleFieldEntryItem"][];
        };
        /**
         * RoleItem
         * @description 角色列表行。
         */
        RoleItem: {
            /**
             * Builtin
             * @description 是否内置角色（按 role_type 判定，非 custom 即内置）
             */
            builtin: boolean;
            /**
             * Code
             * @description 角色码
             */
            code: string;
            /**
             * Id
             * @description 角色主键
             */
            id: string;
            /**
             * Name
             * @description 角色名称
             */
            name: string;
            /**
             * Role Type
             * @description 角色类型（custom/system/security/audit）
             * @enum {string}
             */
            role_type: "custom" | "system" | "security" | "audit" | "platform_admin";
            /**
             * Status
             * @description 状态（enabled/disabled）
             */
            status: string;
            /**
             * Subject Count
             * @description 已分配用户数
             */
            subject_count: number;
        };
        /**
         * RolePermissionEntryItem
         * @description 授权条目行（响应）。
         */
        RolePermissionEntryItem: {
            /**
             * Id
             * @description 授权行主键
             */
            id: string;
            /**
             * Perm Type
             * @description 授权类型（menu/form/permission）
             */
            perm_type: string;
            /**
             * Source Menu Id
             * @description 来源菜单入口 ID（0 = 表单级直接授予）
             */
            source_menu_id: string;
            /**
             * Target Id
             * @description 授权目标 ID
             */
            target_id: string;
        };
        /**
         * RolePermissionEntryRequest
         * @description 一条授权条目（菜单 / 表单 / 权限码）。
         */
        RolePermissionEntryRequest: {
            /**
             * Perm Type
             * @description 授权类型（menu/form/permission）
             * @enum {string}
             */
            perm_type: "menu" | "form" | "permission";
            /**
             * Source Menu Id
             * @description 来源菜单入口 ID（0 = 表单级直接授予）
             * @default 0
             */
            source_menu_id: number;
            /**
             * Target Id
             * @description 授权目标 ID
             */
            target_id: number;
        };
        /**
         * RolePermissionRequest
         * @description 授权全量覆盖请求（单事务先删后插）。
         */
        RolePermissionRequest: {
            /**
             * Entries
             * @description 授权条目清单（全量）
             */
            entries?: components["schemas"]["RolePermissionEntryRequest"][];
        };
        /**
         * RolePermissions
         * @description 角色授权条目清单（含来源）。
         */
        RolePermissions: {
            /**
             * Items
             * @description 授权条目清单
             */
            items?: components["schemas"]["RolePermissionEntryItem"][];
        };
        /**
         * RoleUpdateRequest
         * @description 修改角色请求（角色码 / 名称 / 状态；乐观锁）；角色类型不可改。
         */
        RoleUpdateRequest: {
            /**
             * Code
             * @description 角色码（None 表示不改；格式受 role.code_pattern 约束，租户内唯一）
             */
            code?: string | null;
            /**
             * Name
             * @description 角色名称
             */
            name: string;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
            /**
             * Version
             * @description 客户端版本（乐观锁比对）
             */
            version: number;
        };
        /**
         * SeedOrchestrationRequestSchema
         * @description 编排请求（内部端点入参）。
         */
        SeedOrchestrationRequestSchema: {
            /**
             * Dry Run
             * @description 只做装载 + 排序 + 冲突预检，不开事务不执行
             * @default false
             */
            dry_run: boolean;
            /**
             * Only
             * @description 只执行这些种子（空表示不限制）
             */
            only?: string[];
            /**
             * Require
             * @description 人工强制前置（必须在本批之前完成）
             */
            require?: string[];
            /**
             * Skip
             * @description 跳过这些种子
             */
            skip?: string[];
            /**
             * Tenant
             * @description 目标租户；空串取 [platform_tenant].code
             * @default
             */
            tenant: string;
            /**
             * Timeout Seconds
             * @description 全局事务超时（秒）
             * @default 300
             */
            timeout_seconds: number;
        };
        /**
         * SqlValidateRequest
         * @description SQL 校验请求：`{sql, datasource?}`。
         */
        SqlValidateRequest: {
            /**
             * Datasource
             * @description 目标数据源标识（缺省按场景缺省）
             */
            datasource?: string | null;
            /**
             * Sql
             * @description SQL 文本（仅只读语句）
             */
            sql: string;
        };
        /**
         * TenantTopologyRowRequest
         * @description 整批写入的单行（部署单元由调用方指定，库名不落库）。
         */
        TenantTopologyRowRequest: {
            /**
             * Domain Key
             * @description 业务域标识（须已登记）
             */
            domain_key: string;
            /**
             * Note
             * @description 说明（可选）
             * @default
             */
            note: string;
            /**
             * Status
             * @description 状态（enabled / disabled，缺省 enabled）
             * @default enabled
             */
            status: string;
            /**
             * Unit Key
             * @description 部署单元标识（小写字母开头）
             */
            unit_key: string;
        };
        /**
         * TenantTopologyWriteRequest
         * @description 整批写入请求：`rows` 与 `template` **二选一**（模板先展开，再按需人工调整）。
         *
         *     `version` 留空表示「当前版本 + 1」；显式给值时必须大于当前版本（拒绝回退）。
         */
        TenantTopologyWriteRequest: {
            /**
             * Note
             * @description 本批次说明（可选）
             * @default
             */
            note: string;
            /**
             * Rows
             * @description 整批行（与 template 二选一）
             */
            rows?: components["schemas"]["TenantTopologyRowRequest"][] | null;
            /**
             * Template
             * @description 参照模板名（single / grouped / isolated；与 rows 二选一）
             */
            template?: string | null;
            /**
             * Version
             * @description 拓扑版本（空=当前版本+1；须递增）
             */
            version?: number | null;
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
         * UserAdminCreateRequest
         * @description 新建用户请求（初始密码可选；缺省后端随机生成并一次性回显）。
         */
        UserAdminCreateRequest: {
            /**
             * Email
             * @description 邮箱（可空）
             */
            email?: string | null;
            /**
             * Name
             * @description 昵称 / 显示名
             */
            name: string;
            /**
             * Password
             * @description 初始密码（不传则由后端随机生成并在响应中一次性返回）
             */
            password?: string | null;
            /**
             * Phone
             * @description 手机号（可空）
             */
            phone?: string | null;
            /**
             * Pwd Reset Required
             * @description 是否强制下次登录改密
             * @default true
             */
            pwd_reset_required: boolean;
            /**
             * Status
             * @description 初始状态（enabled/disabled）
             * @default enabled
             * @enum {string}
             */
            status: "enabled" | "disabled";
            /**
             * Username
             * @description 登录账号（租户内唯一；软删除后原账号可复用）
             */
            username: string;
        };
        /**
         * UserAdminCreateResult
         * @description 新建用户结果（后端生成的初始密码仅本次返回）。
         */
        UserAdminCreateResult: {
            /**
             * Initial Password
             * @description 后端生成的初始密码（仅本次返回；调用方自行指定密码时为 null）
             */
            initial_password?: string | null;
            /** @description 新建用户详情 */
            user: components["schemas"]["UserDetail"];
        };
        /**
         * UserAssignmentDepts
         * @description 分配编排请求的用户-部门分段（全量覆盖 + 至多一个主要部门）。
         */
        UserAssignmentDepts: {
            /**
             * Dept Ids
             * @description 部门主键集合（全量覆盖；空集 = 清空）
             */
            dept_ids?: number[];
            /**
             * Primary Dept Id
             * @description 主要部门主键（须在 dept_ids 内；None = 不设）
             */
            primary_dept_id?: number | null;
        };
        /**
         * UserAssignmentPosts
         * @description 分配编排请求的用户-岗位分段（全量覆盖 + 至多一个主要岗位）。
         */
        UserAssignmentPosts: {
            /**
             * Post Ids
             * @description 岗位主键集合（全量覆盖；空集 = 清空）
             */
            post_ids?: number[];
            /**
             * Primary Post Id
             * @description 主要岗位主键（须在 post_ids 内；None = 不设）
             */
            primary_post_id?: number | null;
        };
        /**
         * UserAssignmentProfile
         * @description 分配编排请求的用户基础资料分段（字段语义同 `UserUpdateRequest`；`status` 为 `None` 表示不改）。
         */
        UserAssignmentProfile: {
            /**
             * Email
             * @description 邮箱（None = 不改；空串 = 清空）
             */
            email?: string | null;
            /**
             * Name
             * @description 昵称 / 显示名（None = 不改）
             */
            name?: string | null;
            /**
             * Phone
             * @description 手机号（None = 不改；空串 = 清空）
             */
            phone?: string | null;
            /**
             * Status
             * @description 账号状态（None = 不改；停用即失效会话）
             */
            status?: ("enabled" | "disabled") | null;
            /**
             * Version
             * @description 客户端版本（乐观锁比对）
             */
            version: number;
        };
        /**
         * UserAssignmentsRequest
         * @description 用户保存编排请求（分段全量覆盖；未出现的分段不参与，不写）。
         *
         *     分段语义：`profile` / `role_ids` / `user_posts` / `user_depts` 为 `None` 表示**不改该段**；
         *     `role_ids` 为空集表示清空该用户全部直接角色。权限码**分段校验**（`profile` → `user:update`，
         *     其余段 → `user:assign_role`）。
         */
        UserAssignmentsRequest: {
            /** @description 用户基础资料分段（None = 不改） */
            profile?: components["schemas"]["UserAssignmentProfile"] | null;
            /**
             * Role Ids
             * @description 用户直接角色全量集合（None = 不改；空集 = 清空）
             */
            role_ids?: number[] | null;
            /** @description 用户-部门分段（None = 不改） */
            user_depts?: components["schemas"]["UserAssignmentDepts"] | null;
            /** @description 用户-岗位分段（None = 不改） */
            user_posts?: components["schemas"]["UserAssignmentPosts"] | null;
        };
        /**
         * UserAssignmentsResult
         * @description 用户保存编排结果（回带 platform 侧生效后集合）。
         *
         *     组织分配段（岗位 / 部门）的生效后集合由调用方（前端）在保存成功后经产品读契约取回——
         *     XA 分支执行端点契约只回分支状态、不回业务集合。
         */
        UserAssignmentsResult: {
            /**
             * Applied
             * @description 本次参与的分段名（profile / role_ids / user_posts / user_depts）
             */
            applied?: string[];
            /** @description 生效后用户直接角色清单 */
            roles: components["schemas"]["UserRoleList"];
            /** @description 生效后用户详情 */
            user: components["schemas"]["UserDetail"];
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
         * UserDeleteResult
         * @description 软删除结果（`session_revoked` 表示会话撤销是否成功）。
         */
        UserDeleteResult: {
            /**
             * Deleted
             * @description 是否删除成功
             */
            deleted: boolean;
            /**
             * Session Revoked
             * @description 是否已失效该用户全部会话
             */
            session_revoked: boolean;
        };
        /**
         * UserDetail
         * @description 用户详情（含联系方式与乐观锁版本；联系方式按脱敏标记掩码，`data:plain` 权限见明文）。
         */
        UserDetail: {
            /**
             * Created At
             * Format: date-time
             * @description 创建时间（UTC）
             */
            created_at: string;
            /**
             * Email
             * @description 邮箱（按脱敏标记掩码）
             */
            email?: string | null;
            /**
             * Id
             * @description 用户主键
             */
            id: string;
            /**
             * Last Login At
             * @description 最近登录时间（UTC；从未登录为 null）
             */
            last_login_at?: string | null;
            /**
             * Name
             * @description 昵称 / 显示名
             */
            name: string;
            /**
             * Phone
             * @description 手机号（按脱敏标记掩码）
             */
            phone?: string | null;
            /**
             * Status
             * @description 账号状态（enabled/disabled）
             * @enum {string}
             */
            status: "enabled" | "disabled";
            /**
             * Updated At
             * Format: date-time
             * @description 更新时间（UTC）
             */
            updated_at: string;
            /**
             * Username
             * @description 登录账号
             */
            username: string;
            /**
             * Version
             * @description 乐观锁版本
             */
            version: number;
        };
        /**
         * UserExtensionCreateRequest
         * @description 新增用户扩展信息请求。
         */
        UserExtensionCreateRequest: {
            /**
             * Label
             * @description 扩展标签（用户维度内唯一）
             */
            label: string;
            /**
             * Remark
             * @description 备注
             */
            remark?: string | null;
            /**
             * User Id
             * @description 用户主键
             */
            user_id: number;
        };
        /**
         * UserExtensionItem
         * @description 用户扩展信息行。
         */
        UserExtensionItem: {
            /**
             * Created At
             * Format: date-time
             * @description 创建时间（UTC）
             */
            created_at: string;
            /**
             * Id
             * @description 主键（雪花 ID，JSON 以字符串输出）
             */
            id: string;
            /**
             * Label
             * @description 扩展标签
             */
            label: string;
            /**
             * Remark
             * @description 备注
             */
            remark: string | null;
            /**
             * Updated At
             * Format: date-time
             * @description 更新时间（UTC）
             */
            updated_at: string;
            /**
             * User Id
             * @description 用户主键
             */
            user_id: string;
        };
        /**
         * UserExtensionList
         * @description 用户扩展信息列表（按用户列示，保序）。
         */
        UserExtensionList: {
            /**
             * Items
             * @description 扩展信息行列表
             */
            items: components["schemas"]["UserExtensionItem"][];
        };
        /**
         * UserExtensionUpdateRequest
         * @description 更新用户扩展信息请求（整体替换：`label` 必填、`remark` 传 null 即清空）。
         */
        UserExtensionUpdateRequest: {
            /**
             * Label
             * @description 扩展标签（用户维度内唯一）
             */
            label: string;
            /**
             * Remark
             * @description 备注（null 即清空）
             */
            remark?: string | null;
        };
        /**
         * UserItem
         * @description 用户列表行（管理面；选择用户弹窗 / 已分配列表回显 / 用户列表共用；不含联系方式）。
         */
        UserItem: {
            /**
             * Id
             * @description 用户主键
             */
            id: string;
            /**
             * Last Login At
             * @description 最近登录时间（UTC；从未登录为 null）
             */
            last_login_at?: string | null;
            /**
             * Name
             * @description 用户昵称 / 显示名
             */
            name: string;
            /**
             * Status
             * @description 账号状态（enabled/disabled）
             * @enum {string}
             */
            status: "enabled" | "disabled";
            /**
             * Username
             * @description 登录账号
             */
            username: string;
        };
        /**
         * UserPasswordResetRequest
         * @description 重置密码请求（复杂度与历史策略校验 + 强制首登改密 + 失效全部会话）。
         */
        UserPasswordResetRequest: {
            /**
             * Force Change
             * @description 是否强制下次登录改密
             * @default true
             */
            force_change: boolean;
            /**
             * New Password
             * @description 新密码（复杂度 30005 / 历史重复 30006）
             */
            new_password: string;
        };
        /**
         * UserPasswordResetResult
         * @description 重置密码结果（不回显新密码）。
         */
        UserPasswordResetResult: {
            /**
             * Reset
             * @description 是否重置成功
             */
            reset: boolean;
            /**
             * Session Revoked
             * @description 是否已失效该用户全部会话
             */
            session_revoked: boolean;
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
        /**
         * UserRoleItem
         * @description 用户直接角色行（同库 `sys_user_role` ⋈ `sys_role`；只读，维护归角色管理）。
         */
        UserRoleItem: {
            /**
             * Role Code
             * @description 角色码
             */
            role_code: string;
            /**
             * Role Id
             * @description 角色主键
             */
            role_id: string;
            /**
             * Role Name
             * @description 角色名称
             */
            role_name: string;
            /**
             * Role Type
             * @description 角色类型（custom/system/security/audit）
             */
            role_type: string;
        };
        /**
         * UserRoleList
         * @description 用户直接角色清单。
         */
        UserRoleList: {
            /**
             * Items
             * @description 直接角色清单
             */
            items?: components["schemas"]["UserRoleItem"][];
        };
        /**
         * UserStatusResult
         * @description 启用 / 停用结果（停用时 `session_revoked` 有意义）。
         */
        UserStatusResult: {
            /**
             * Session Revoked
             * @description 是否已失效该用户全部会话
             */
            session_revoked: boolean;
            /** @description 更新后的用户详情 */
            user: components["schemas"]["UserDetail"];
        };
        /**
         * UserStatusUpdateRequest
         * @description 启用 / 停用请求（停用即失效该用户全部会话）。
         */
        UserStatusUpdateRequest: {
            /**
             * Status
             * @description 目标状态（enabled / disabled）
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /**
         * UserUpdateRequest
         * @description 修改用户请求（昵称 / 邮箱 / 手机；乐观锁比对版本）。
         */
        UserUpdateRequest: {
            /**
             * Email
             * @description 邮箱（None = 不改；空串 = 清空）
             */
            email?: string | null;
            /**
             * Name
             * @description 昵称 / 显示名（None = 不改）
             */
            name?: string | null;
            /**
             * Phone
             * @description 手机号（None = 不改；空串 = 清空）
             */
            phone?: string | null;
            /**
             * Version
             * @description 客户端版本（乐观锁比对）
             */
            version: number;
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
    list_locks_api_v1_account_locks_get: {
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
    lock_account_api_v1_account_locks_post: {
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
    get_lock_api_v1_account_locks__lock_id__get: {
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
    unlock_account_api_v1_account_locks__lock_id__unlock_put: {
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
    list_actions_api_v1_actions_get: {
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
                    "application/json": components["schemas"]["ApiResponse_ActionList_"];
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
    create_action_api_v1_actions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ActionCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_ActionItem_"];
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
    update_action_api_v1_actions__action_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                action_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ActionUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_ActionItem_"];
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
    delete_action_api_v1_actions__action_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                action_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
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
    list_businesses_api_v1_businesses_get: {
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
                    "application/json": components["schemas"]["ApiResponse_BusinessList_"];
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
    create_business_api_v1_businesses_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BusinessCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_BusinessItem_"];
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
    update_business_api_v1_businesses__business_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                business_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BusinessUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_BusinessItem_"];
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
    delete_business_api_v1_businesses__business_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                business_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
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
    list_buttons_api_v1_buttons_get: {
        parameters: {
            query?: {
                /** @description 表单主键（可空 = 全部） */
                form_id?: number | null;
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
                    "application/json": components["schemas"]["ApiResponse_ButtonList_"];
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
    create_button_api_v1_buttons_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ButtonCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_ButtonItem_"];
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
    update_button_api_v1_buttons__button_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                button_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ButtonUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_ButtonItem_"];
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
    delete_button_api_v1_buttons__button_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                button_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
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
    list_capability_grants_api_v1_capability_grants_get: {
        parameters: {
            query?: {
                /** @description 能力名筛选；缺省全部 */
                capability_name?: string | null;
                /** @description 消费方标识筛选；缺省全部 */
                consumer_key?: string | null;
                /** @description 状态筛选（enabled / disabled）；缺省全部 */
                status?: string | null;
                /** @description 来源筛选（declared / manual）；缺省全部 */
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
    grant_capability_api_v1_capability_grants_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CapabilityGrantCreateRequest"];
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
    revoke_capability_api_v1_capability_grants__grant_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 授权记录主键（雪花 ID） */
                grant_id: number;
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
    validate_expression_api_v1_code_validate_expression_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExpressionValidateRequest"];
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
    validate_sql_api_v1_code_validate_sql_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SqlValidateRequest"];
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
    list_data_sources_api_v1_data_sources_get: {
        parameters: {
            query?: {
                /** @description 按类型过滤（dict / form；空 = 全部） */
                kind?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_DataSourceListResponse_"];
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
    list_demos_api_v1_demos_get: {
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
    create_demo_api_v1_demos_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DemoCreateRequest"];
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
    get_demo_api_v1_demos__demo_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                demo_id: number;
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
    update_demo_api_v1_demos__demo_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                demo_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DemoUpdateRequest"];
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
    delete_demo_api_v1_demos__demo_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                demo_id: number;
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
    batch_dicts_api_v1_dicts_batch_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DictBatchQuery"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_DictBatchResult_"];
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
    list_query_providers_api_v1_dicts_query_providers_get: {
        parameters: {
            query?: {
                /** @description 按字典标识过滤（空 = 全部） */
                data_source_key?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_DictQueryProviderListResponse_"];
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
    get_dict_by_type_api_v1_dicts__data_source_key__get: {
        parameters: {
            query?: {
                /** @description 客户端本地版本号（一致时 items 返回 null） */
                version?: number | null;
                /** @description 关键字（label / value / code） */
                keyword?: string | null;
                /** @description 上级条目 ID（0 = 顶层；不传 = 不按父过滤） */
                parent_id?: number | null;
                /** @description 指定条目 id 子集（逗号分隔的正整数） */
                ids?: string | null;
                /** @description 返回条数上限（探针传 2001） */
                limit?: number | null;
            };
            header?: never;
            path: {
                data_source_key: string;
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
                    "application/json": components["schemas"]["ApiResponse_DictTypeResult_"];
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
    advanced_query_dict_api_v1_dicts__data_source_key__advanced_query_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                data_source_key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DictAdvQueryPayload"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_DictAdvQueryResult_"];
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
    get_dict_attrs_api_v1_dicts__data_source_key__attrs_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                data_source_key: string;
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
                    "application/json": components["schemas"]["ApiResponse_DictAttrListResponse_"];
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
    list_fields_api_v1_fields_get: {
        parameters: {
            query?: {
                /** @description 表单主键（可空 = 全部） */
                form_id?: number | null;
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
                    "application/json": components["schemas"]["ApiResponse_FieldList_"];
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
    create_field_api_v1_fields_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FieldCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_FieldItem_"];
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
    update_field_api_v1_fields__field_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                field_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FieldUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_FieldItem_"];
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
    delete_field_api_v1_fields__field_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                field_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
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
    list_form_keys_api_v1_form_keys_get: {
        parameters: {
            query?: {
                /** @description 按类型过滤（dict / form；空 = 全部） */
                kind?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_FormKeyListResponse_"];
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
    list_forms_api_v1_forms_get: {
        parameters: {
            query?: {
                /** @description 菜单主键（可空 = 全部） */
                menu_id?: number | null;
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
                    "application/json": components["schemas"]["ApiResponse_FormList_"];
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
    create_form_api_v1_forms_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FormCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_FormItem_"];
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
    update_form_api_v1_forms__form_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                form_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FormUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_FormItem_"];
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
    delete_form_api_v1_forms__form_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                form_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
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
    list_icons_api_v1_icons_get: {
        parameters: {
            query?: {
                /** @description 图标分组（缺省全部） */
                category?: string | null;
                /** @description 图标状态（active 启用 / disabled 停用；缺省全部） */
                status?: string | null;
                /** @description 关键字（匹配图标键 / 名称 / 标签） */
                keyword?: string | null;
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
    create_icon_api_v1_icons_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复提交复用首次结果） */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IconCreateRequest"];
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
    get_icon_api_v1_icons__code__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 自建图标码（snake_case，见详情） */
                code: string;
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
    update_icon_api_v1_icons__code__put: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复提交复用首次结果） */
                "Idempotency-Key"?: string | null;
            };
            path: {
                /** @description 自建图标码（snake_case，见详情） */
                code: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IconUpdateRequest"];
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
    delete_icon_api_v1_icons__code__delete: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复提交复用首次结果） */
                "Idempotency-Key"?: string | null;
            };
            path: {
                /** @description 自建图标码（snake_case，见详情） */
                code: string;
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
    list_menus_api_v1_menus_get: {
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
                    "application/json": components["schemas"]["ApiResponse_MenuTree_"];
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
    create_menu_api_v1_menus_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MenuCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_MenuItem_"];
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
    my_menus_api_v1_menus_my_get: {
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
                    "application/json": components["schemas"]["ApiResponse_MyMenuResponse_"];
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
    update_menu_api_v1_menus__menu_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                menu_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MenuUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_MenuItem_"];
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
    delete_menu_api_v1_menus__menu_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                menu_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
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
    list_modules_api_v1_modules_get: {
        parameters: {
            query?: {
                /** @description 状态筛选（enabled / disabled / planned）；缺省全部 */
                status?: string | null;
                /** @description 归属分组筛选（foundation / capability / product）；缺省全部 */
                group?: string | null;
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
    catalog_snapshot_api_v1_modules_snapshot_get: {
        parameters: {
            query?: {
                /** @description 附带段（逗号分隔多值：modules / products / collaborations）；缺省保持原数组契约 */
                with?: string | null;
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
                    "application/json": components["schemas"]["ApiResponse_CatalogSnapshotResponse_"] | components["schemas"]["ApiResponse_list_ModuleResponse__"];
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
    get_module_api_v1_modules__service_key__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 服务标识（service_key；未命中回退 module_key） */
                service_key: string;
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
    list_dead_letters_api_v1_outbox_dead_letters_get: {
        parameters: {
            query?: {
                /** @description 处置状态筛选（pending / replayed / ignored）；缺省全部 */
                status?: string | null;
                /** @description 来源筛选（outbox / consumer）；缺省全部 */
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
    get_dead_letter_api_v1_outbox_dead_letters__dead_letter_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 死信记录主键 */
                dead_letter_id: number;
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
    ignore_dead_letter_api_v1_outbox_dead_letters__dead_letter_id__ignore_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 死信记录主键 */
                dead_letter_id: number;
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
    replay_dead_letter_api_v1_outbox_dead_letters__dead_letter_id__replay_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 死信记录主键 */
                dead_letter_id: number;
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
    list_permissions_api_v1_permissions_get: {
        parameters: {
            query?: {
                /** @description 业务码主键（可空 = 全部） */
                business_id?: number | null;
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
                    "application/json": components["schemas"]["ApiResponse_PermissionList_"];
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
    create_permission_api_v1_permissions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PermissionCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_PermissionItem_"];
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
    generate_permissions_api_v1_permissions_generate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PermissionGenerateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_PermissionGenerateResult_"];
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
    update_permission_api_v1_permissions__permission_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                permission_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PermissionUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_PermissionItem_"];
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
    delete_permission_api_v1_permissions__permission_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                permission_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
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
    scan_inactive_api_v1_platform_internal_account_locks_scan_inactive_post: {
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
    capability_grant_view_api_v1_platform_internal_capability_grants_get: {
        parameters: {
            query?: {
                /** @description 提供方业务域（入站维度；与 consumer 二选一） */
                provider?: string | null;
                /** @description 消费方服务键（出站维度；与 provider 二选一） */
                consumer?: string | null;
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
    resolve_configs_api_v1_platform_internal_configs_resolve_post: {
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
                "application/json": components["schemas"]["ConfigResolveRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_ConfigResolveResponse_"];
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
    apply_login_state_api_v1_platform_internal_credentials_login_state_post: {
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
    update_password_api_v1_platform_internal_credentials_update_password_post: {
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
    verify_credential_api_v1_platform_internal_credentials_verify_post: {
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
    submit_declarations_api_v1_platform_internal_declarations_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeclarationSubmitRequest"];
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
    declaration_snapshot_api_v1_platform_internal_declarations_snapshot_get: {
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
    invalidate_permissions_api_v1_platform_internal_permissions_invalidate_post: {
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
                "application/json": components["schemas"]["PermissionInvalidateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_PermissionInvalidateResult_"];
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
    read_permission_metadata_api_v1_platform_internal_permissions_metadata_get: {
        parameters: {
            query?: {
                locale?: string;
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
                    "application/json": components["schemas"]["ApiResponse_PermissionMetadataResult_"];
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
    read_permission_subject_api_v1_platform_internal_permissions_subject_post: {
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
                "application/json": components["schemas"]["PermissionSubjectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_PermissionSubjectResult_"];
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
    orchestrate_seeds_api_v1_platform_internal_seeds_orchestrate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SeedOrchestrationRequestSchema"];
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
    topology_snapshot_api_v1_platform_internal_tenant_topologies_get: {
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
    create_user_api_v1_platform_internal_users_create_post: {
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
    user_profile_api_v1_platform_internal_users_profile_post: {
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
    query_users_api_v1_platform_internal_users_query_post: {
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
                "application/json": components["schemas"]["InternalUserQueryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_InternalUserItem__"];
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
    reset_target_api_v1_platform_internal_users_reset_target_post: {
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
    list_plugins_api_v1_plugins_get: {
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
    aggregate_plugins_api_v1_plugins_aggregate_get: {
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
    get_plugin_api_v1_plugins__plugin_key__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 能力域键（如 object_storage） */
                plugin_key: string;
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
    get_preference_api_v1_preferences__key__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 偏好键（域.键，如 list.user_form / ui.theme） */
                key: string;
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
    set_preference_api_v1_preferences__key__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 偏好键（域.键，如 list.user_form / ui.theme） */
                key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PreferenceValueRequest"];
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
    reset_preference_api_v1_preferences__key__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 偏好键（域.键，如 list.user_form / ui.theme） */
                key: string;
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
    list_products_api_v1_products_get: {
        parameters: {
            query?: {
                /** @description 状态筛选（enabled / disabled / planned / retired）；缺省全部 */
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
    get_product_api_v1_products__product_key__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 产品标识（product_key） */
                product_key: string;
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
    list_query_schemes_api_v1_query_schemes_get: {
        parameters: {
            query: {
                /** @description 方案目标（items 字典条目 / business 列表筛选） */
                target: components["schemas"]["QuerySchemeTarget"];
                /** @description 表单标识（business 时取 form_key） */
                field_key?: string | null;
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
    save_query_scheme_api_v1_query_schemes_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["QueryScheme"];
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
    resolve_default_scheme_api_v1_query_schemes_default_get: {
        parameters: {
            query: {
                /** @description 方案目标（items 字典条目 / business 列表筛选） */
                target: components["schemas"]["QuerySchemeTarget"];
                /** @description 表单标识（business 时取 form_key） */
                field_key?: string | null;
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
    get_query_scheme_api_v1_query_schemes__scheme_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scheme_id: number;
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
    update_query_scheme_api_v1_query_schemes__scheme_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scheme_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["QueryScheme"];
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
    delete_query_scheme_api_v1_query_schemes__scheme_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scheme_id: number;
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
    list_roles_api_v1_roles_get: {
        parameters: {
            query?: {
                /** @description 关键字（角色码 / 名称；用户账号 / 姓名） */
                kw?: string | null;
                /** @description 状态（enabled/disabled） */
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
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_RoleItem__"];
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
    create_role_api_v1_roles_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_RoleDetail_"];
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
    get_role_api_v1_roles__role_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_RoleDetail_"];
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
    update_role_api_v1_roles__role_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_RoleDetail_"];
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
    delete_role_api_v1_roles__role_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
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
    apply_role_assignments_api_v1_roles__role_id__assignments_put: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复提交复用首次结果） */
                "Idempotency-Key"?: string | null;
            };
            path: {
                role_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleAssignmentsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_RoleAssignmentsResult_"];
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
    list_data_scopes_api_v1_roles__role_id__data_permissions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_RoleDataScopes_"];
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
    replace_data_scopes_api_v1_roles__role_id__data_permissions_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleDataScopeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_RoleDataScopes_"];
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
    list_fields_api_v1_roles__role_id__fields_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_RoleFields_"];
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
    replace_fields_api_v1_roles__role_id__fields_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleFieldRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_RoleFields_"];
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
    list_permissions_api_v1_roles__role_id__permissions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_RolePermissions_"];
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
    replace_permissions_api_v1_roles__role_id__permissions_put: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复提交复用首次结果） */
                "Idempotency-Key"?: string | null;
            };
            path: {
                role_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RolePermissionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_RolePermissions_"];
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
    list_assigned_users_api_v1_roles__role_id__users_get: {
        parameters: {
            query?: {
                /** @description 关键字（角色码 / 名称；用户账号 / 姓名） */
                kw?: string | null;
                /** @description 状态（enabled/disabled） */
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
            path: {
                role_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_AssignedUserItem__"];
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
    assign_users_api_v1_roles__role_id__users_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description 幂等键（可选；重复提交复用首次结果） */
                "Idempotency-Key"?: string | null;
            };
            path: {
                role_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleAssignRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_RoleAssignedUsers_"];
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
    unassign_user_api_v1_roles__role_id__users__user_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_NoneType_"];
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
    list_topologies_api_v1_tenant_topologies_get: {
        parameters: {
            query?: {
                /** @description 租户筛选；缺省全部 */
                tenant_id?: number | null;
                /** @description 业务域筛选；缺省全部 */
                domain_key?: string | null;
                /** @description 部署单元筛选；缺省全部 */
                unit_key?: string | null;
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
    export_topology_api_v1_tenant_topologies__tenant_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 租户主键（0 = 平台级默认拓扑） */
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
    replace_topology_api_v1_tenant_topologies__tenant_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 租户主键（0 = 平台级默认拓扑） */
                tenant_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantTopologyWriteRequest"];
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
    recover_branches_api_v1_txn_branches_get: {
        parameters: {
            query: {
                /** @description 目标库键（不透明库键） */
                db_key: string;
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
                    "application/json": components["schemas"]["ApiResponse_BranchRecoverView_"];
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
    execute_branch_api_v1_txn_branches_post: {
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
                "application/json": components["schemas"]["BranchExecuteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_BranchStateView_"];
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
    branch_state_api_v1_txn_branches__xid__get: {
        parameters: {
            query: {
                /** @description 目标库键（不透明库键） */
                db_key: string;
            };
            header?: {
                Authorization?: string | null;
            };
            path: {
                xid: string;
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
                    "application/json": components["schemas"]["ApiResponse_BranchStateView_"];
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
    commit_branch_api_v1_txn_branches__xid__commit_post: {
        parameters: {
            query: {
                /** @description 目标库键（不透明库键） */
                db_key: string;
            };
            header?: {
                Authorization?: string | null;
            };
            path: {
                xid: string;
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
                    "application/json": components["schemas"]["ApiResponse_BranchStateView_"];
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
    rollback_branch_api_v1_txn_branches__xid__rollback_post: {
        parameters: {
            query: {
                /** @description 目标库键（不透明库键） */
                db_key: string;
            };
            header?: {
                Authorization?: string | null;
            };
            path: {
                xid: string;
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
                    "application/json": components["schemas"]["ApiResponse_BranchStateView_"];
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
    list_user_extensions_api_v1_user_extensions_get: {
        parameters: {
            query: {
                /** @description 用户主键（必填） */
                user_id: number;
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
                    "application/json": components["schemas"]["ApiResponse_UserExtensionList_"];
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
    create_user_extension_api_v1_user_extensions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserExtensionCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserExtensionItem_"];
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
    update_user_extension_api_v1_user_extensions__extension_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                extension_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserExtensionUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserExtensionItem_"];
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
    list_users_api_v1_users_get: {
        parameters: {
            query?: {
                /** @description 关键字（用户名/姓名/邮箱/手机号，大小写不敏感） */
                kw?: string | null;
                /** @description 账号状态（enabled/disabled） */
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
                    "application/json": components["schemas"]["ApiResponse_BasePageResponse_UserItem__"];
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
    create_user_api_v1_users_post: {
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
                "application/json": components["schemas"]["UserAdminCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserAdminCreateResult_"];
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
    get_user_detail_api_v1_users__user_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
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
                    "application/json": components["schemas"]["ApiResponse_UserDetail_"];
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
    update_user_api_v1_users__user_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserDetail_"];
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
    delete_user_api_v1_users__user_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
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
                    "application/json": components["schemas"]["ApiResponse_UserDeleteResult_"];
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
    apply_user_assignments_api_v1_users__user_id__assignments_put: {
        parameters: {
            query?: never;
            header?: {
                "Idempotency-Key"?: string | null;
            };
            path: {
                user_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserAssignmentsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserAssignmentsResult_"];
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
    reset_user_password_api_v1_users__user_id__password_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserPasswordResetRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserPasswordResetResult_"];
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
    list_user_roles_api_v1_users__user_id__roles_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
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
                    "application/json": components["schemas"]["ApiResponse_UserRoleList_"];
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
    update_user_status_api_v1_users__user_id__status_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserStatusUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiResponse_UserStatusResult_"];
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
