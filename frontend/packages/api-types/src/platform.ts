/**
 * 服务契约生成类型：platform
 *
 * 本文件由 `frontend/packages/api-types/scripts/generate.mjs` 生成，请勿手工修改。
 * 来源：deploy/contracts/platform.json（服务契约快照，唯一事实源）。
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
    "/api/v1/dicts/attrs/{attr_id}": {
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
         * Delete Dict Attr
         * @description 软删除字典扩展属性。
         *
         *     Args:
         *         service: 字典写路径服务。
         *         attr_id: 属性 ID。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为 null）。
         */
        delete: operations["delete_dict_attr_api_v1_dicts_attrs__attr_id__delete"];
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
         * @description 批量合并取字典（一次请求多类型；版本一致的类型 items 返回 null）。
         *
         *     Args:
         *         source: 字典取数契约。
         *         query: 批量取数参数（types / version / locale）。
         *         request: 请求对象（语言解析）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为批量结果。
         */
        post: operations["batch_dicts_api_v1_dicts_batch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/items/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Dict Item
         * @description 修改字典条目（乐观锁）。
         *
         *     Args:
         *         service: 字典写路径服务。
         *         item_id: 条目 ID。
         *         payload: 条目载荷。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为条目行。
         */
        put: operations["update_dict_item_api_v1_dicts_items__item_id__put"];
        post?: never;
        /**
         * Delete Dict Item
         * @description 软删除字典条目。
         *
         *     Args:
         *         service: 字典写路径服务。
         *         item_id: 条目 ID。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为 null）。
         */
        delete: operations["delete_dict_item_api_v1_dicts_items__item_id__delete"];
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
         * @description 列可用查询提供者（按 type 过滤；含参数 schema 子集）。
         *
         *     Args:
         *         registry: 查询提供者注册表。
         *         dict_type: 字典类型码（可选）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为提供者清单数组。
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
    "/api/v1/dicts/types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Dict Type
         * @description 新增字典类型。
         *
         *     Args:
         *         service: 字典写路径服务。
         *         payload: 类型载荷。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为类型行。
         */
        post: operations["create_dict_type_api_v1_dicts_types_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/types/{dict_type}/attrs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upsert Dict Attr
         * @description 新增 / 更新字典扩展属性（按 `attr_key` upsert）。
         *
         *     Args:
         *         service: 字典写路径服务。
         *         dict_type: 字典类型码。
         *         payload: 属性载荷。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为属性行。
         */
        post: operations["upsert_dict_attr_api_v1_dicts_types__dict_type__attrs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/types/{dict_type}/items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Dict Item
         * @description 新增字典条目（类型内编码唯一）。
         *
         *     Args:
         *         service: 字典写路径服务。
         *         dict_type: 字典类型码。
         *         payload: 条目载荷。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为条目行。
         */
        post: operations["create_dict_item_api_v1_dicts_types__dict_type__items_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/types/{type_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Dict Type
         * @description 修改字典类型（乐观锁）。
         *
         *     Args:
         *         service: 字典写路径服务。
         *         type_id: 类型 ID。
         *         payload: 类型载荷。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为类型行。
         */
        put: operations["update_dict_type_api_v1_dicts_types__type_id__put"];
        post?: never;
        /**
         * Delete Dict Type
         * @description 软删除字典类型。
         *
         *     Args:
         *         service: 字典写路径服务。
         *         type_id: 类型 ID。
         *
         *     Returns:
         *         ApiResponse: 统一响应（data 为 null）。
         */
        delete: operations["delete_dict_type_api_v1_dicts_types__type_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/{dict_type}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Dict By Type
         * @description 按类型取字典（版本比对 / 关键字 / 级联 / 按值子集 / 上限）。
         *
         *     Args:
         *         source: 字典取数契约。
         *         dict_type: 字典类型码。
         *         request: 请求对象（语言解析）。
         *         version: 客户端本地版本号。
         *         keyword: 关键字。
         *         parent_id: 级联父值（空串 = 顶层）。
         *         values: 逗号分隔的 value 子集。
         *         limit: 返回条数上限。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为单类型取数结果。
         */
        get: operations["get_dict_by_type_api_v1_dicts__dict_type__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/{dict_type}/advanced-query": {
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
         *         dict_type: 字典类型码。
         *         payload: 查询请求体。
         *         request: 请求对象（语言解析）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为分页结果。
         */
        post: operations["advanced_query_dict_api_v1_dicts__dict_type__advanced_query_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dicts/{dict_type}/attrs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Dict Attrs
         * @description 取字典类型属性 schema（供高级查询条件构建）。
         *
         *     Args:
         *         query_service: 高级查询服务。
         *         dict_type: 字典类型码。
         *         request: 请求对象（语言解析）。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为属性清单。
         */
        get: operations["get_dict_attrs_api_v1_dicts__dict_type__attrs_get"];
        put?: never;
        post?: never;
        delete?: never;
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
         * @description 服务目录快照（只读，全量清单不分页）。
         *
         *     供各服务启动接库校验对账（`validate_catalog`）：字段与 `sys_module` 登记一致，
         *     响应 `data` 为清单数组（**注意**：路径须先于 `/modules/{service_key}` 注册，避免被明细路由吞掉）。
         *
         *     Args:
         *         session: 平台库只读会话。
         *
         *     Returns:
         *         ApiResponse: 统一响应，data 为服务目录记录数组（`ModuleResponse`）。
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
         * DictAttrPayload
         * @description 字典扩展属性写入载荷。
         */
        DictAttrPayload: {
            /**
             * Attr Key
             * @description 属性键
             */
            attr_key: string;
            /**
             * Data Type
             * @description 数据类型（text/number/date/enum/bool）
             */
            data_type: string;
            /**
             * Name
             * @description 属性名（默认语言）
             */
            name: string;
            /**
             * Operators
             * @description 可用操作符集合
             */
            operators?: string[] | null;
            /**
             * Options
             * @description enum 选项集
             */
            options?: {
                [key: string]: unknown;
            }[] | null;
            /**
             * Scope
             * @description 属性来源（platform/tenant）
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
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             */
            status: string;
            /**
             * Widget
             * @description 值控件
             */
            widget?: string | null;
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
         * DictItemPayload
         * @description 字典条目写入载荷。
         */
        DictItemPayload: {
            /**
             * Attr Json
             * @description 扩展属性值（普通链路不返回）
             */
            attr_json?: {
                [key: string]: unknown;
            } | null;
            /**
             * Code
             * @description 条目编码（类型内唯一）
             */
            code: string;
            /**
             * Color
             * @description 语义色
             */
            color?: string | null;
            /**
             * Label
             * @description 条目标签（默认语言）
             */
            label: string;
            /**
             * Parent Id
             * @description 级联父值
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
             * @description 状态（enabled/disabled）
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
         * DictTypePayload
         * @description 字典类型写入载荷。
         */
        DictTypePayload: {
            /**
             * Name
             * @description 类型名称（默认语言）
             */
            name: string;
            /**
             * Sort
             * @description 排序值
             * @default 0
             */
            sort: number;
            /**
             * Status
             * @description 状态（enabled/disabled）
             * @default enabled
             */
            status: string;
            /**
             * Type
             * @description 类型编码（唯一）
             */
            type: string;
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
             * @description 图标键（kebab-case，租户内唯一）
             */
            code: string;
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
             * Dict Type
             * @description 字典类型（target=items 时填）
             */
            dict_type?: string | null;
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
    delete_dict_attr_api_v1_dicts_attrs__attr_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                attr_id: number;
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
    update_dict_item_api_v1_dicts_items__item_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DictItemPayload"];
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
    delete_dict_item_api_v1_dicts_items__item_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
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
    list_query_providers_api_v1_dicts_query_providers_get: {
        parameters: {
            query?: {
                /** @description 按字典类型过滤（空 = 全部） */
                dict_type?: string | null;
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
    create_dict_type_api_v1_dicts_types_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DictTypePayload"];
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
    upsert_dict_attr_api_v1_dicts_types__dict_type__attrs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dict_type: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DictAttrPayload"];
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
    create_dict_item_api_v1_dicts_types__dict_type__items_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dict_type: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DictItemPayload"];
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
    update_dict_type_api_v1_dicts_types__type_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                type_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DictTypePayload"];
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
    delete_dict_type_api_v1_dicts_types__type_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                type_id: number;
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
    get_dict_by_type_api_v1_dicts__dict_type__get: {
        parameters: {
            query?: {
                /** @description 客户端本地版本号（一致时 items 返回 null） */
                version?: number | null;
                /** @description 关键字（label / value / code） */
                keyword?: string | null;
                /** @description 级联父值（引用父条目 value；空串 = 顶层） */
                parent_id?: string | null;
                /** @description 指定 value 子集（逗号分隔） */
                values?: string | null;
                /** @description 返回条数上限（探针传 2001） */
                limit?: number | null;
            };
            header?: never;
            path: {
                dict_type: string;
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
    advanced_query_dict_api_v1_dicts__dict_type__advanced_query_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dict_type: string;
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
    get_dict_attrs_api_v1_dicts__dict_type__attrs_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dict_type: string;
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
                /** @description 图标键（kebab-case，见详情） */
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
                /** @description 图标键（kebab-case，见详情） */
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
                /** @description 图标键（kebab-case，见详情） */
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
