/**
 * 组织数据源：HTTP 内建实现 + 注册表默认实例（`fetch` 单一落点）。
 *
 * 端点与**组织主数据出口**同源——组织主数据归 mdm 产品，故默认端点经**寻址契约**组装为
 * **mdm 产品命名空间**（`productPrefix('mdm', 'org')` = `/api/mdm/v1/org`；见阶段二 `11_02`），
 * 路径为出口口径 `/data-source/{users,posts,dept-tree}` 与 `/resolve-names`
 * （**查询与批量回显分列两个出口**、**部门树一次性返回**）。
 * 宿主可经 `registerOrgSource` 登记定制实现（如组织 store 版）或覆盖内建键。
 */
import { BaseError, BaseOrgSource, OrgSourceProvider, OrgSourceRegistry, buildOrgResolveQuery, buildOrgSearchQuery, productPrefix, } from '@bms/core';
/** 链路内默认组织数据源注册表实例（宿主可登记定制实现或覆盖内建键）。 */
export const orgSourceRegistry = new OrgSourceRegistry();
/**
 * 登记组织数据源实现。
 *
 * @param key 数据源键（同键拒重）。
 * @param create 数据源工厂。
 */
export function registerOrgSource(key, create) {
    orgSourceRegistry.register(new OrgSourceProvider(key, create));
}
/** HTTP 内建组织数据源（未覆盖的方法不请求）。 */
class HttpOrgSource extends BaseOrgSource {
    /** 实现名。 */
    pluginName = 'http';
    /** 装载选项（端点 / 请求头）。 */
    #options;
    /**
     * 构造 HTTP 数据源。
     *
     * @param options 装载选项。
     */
    constructor(options = {}) {
        super();
        this.#options = options;
    }
    /**
     * 用户查询。
     *
     * @param query 查询入参。
     * @returns 原始结果。
     */
    async searchUsers(query) {
        return this.#get('/data-source/users', this.#searchParams('user', query));
    }
    /**
     * 岗位查询。
     *
     * @param query 查询入参。
     * @returns 原始结果。
     */
    async searchPosts(query) {
        return this.#get('/data-source/posts', this.#searchParams('post', query));
    }
    /**
     * 部门树查询。
     *
     * @param query 查询入参。
     * @returns 原始结果。
     */
    async loadDeptTree(query) {
        return this.#get('/data-source/dept-tree', query.status === undefined || query.status === '' ? {} : { status: query.status });
    }
    /**
     * 批量回显。
     *
     * @param query 查询入参。
     * @returns 原始结果。
     */
    async resolveNames(query) {
        return this.#get('/resolve-names', buildOrgResolveQuery(query.target, query.ids));
    }
    /**
     * 线参数构造（查询出口；与后端同源）。
     *
     * @param kind 对象类型。
     * @param query 查询入参。
     */
    #searchParams(kind, query) {
        return buildOrgSearchQuery({
            kind,
            keyword: query.keyword,
            deptId: query.deptId,
            includeChildren: query.includeChildren,
            status: query.status,
            page: query.page,
            pageSize: query.pageSize,
        });
    }
    /**
     * GET 请求并解统一响应包装。
     *
     * @param path 路径（相对端点前缀）。
     * @param params 查询参数。
     * @returns 数据体（无 `fetch` 能力时降级 `undefined`）。
     */
    async #get(path, params) {
        const fetchFn = globalThis.fetch;
        if (typeof fetchFn !== 'function') {
            return undefined;
        }
        // 默认端点＝mdm 产品命名空间（**经寻址契约组装**，不自拼前缀）；宿主可传 `endpoint` 覆盖
        const endpoint = (this.#options.endpoint ?? orgSourceEndpoint()).replace(/\/+$/, '');
        const search = new URLSearchParams();
        for (const [key, value] of Object.entries(params)) {
            if (value === undefined || value === null || value === '' || value === false) {
                continue;
            }
            search.set(key, value === true ? 'true' : String(value));
        }
        const query = search.size > 0 ? `?${search.toString()}` : '';
        const headers = typeof this.#options.headers === 'function' ? this.#options.headers() : this.#options.headers;
        const response = await fetchFn(`${endpoint}${path}${query}`, { method: 'GET', headers });
        if (!response.ok) {
            throw new BaseError(30101, '组织数据源不可用');
        }
        return unwrapResponse(await response.json());
    }
}
/**
 * 组织数据源默认端点（**组织主数据归 mdm 产品**）。
 *
 * 经寻址契约组装 **mdm 产品命名空间**（`/api/mdm/v1/org`）——产品服务只经产品命名空间对外暴露，
 * 页面 / 插件**不得自拼** `/api/...` 前缀（前端架构 §9 治理表）。
 *
 * @returns 端点前缀。
 */
export function orgSourceEndpoint() {
    return productPrefix('mdm', 'org');
}
/**
 * 创建 HTTP 内建组织数据源。
 *
 * @param options 装载选项（`endpoint` 缺省＝mdm 产品命名空间，见 `orgSourceEndpoint`）。
 * @returns 数据源实例。
 */
export function createHttpOrgSource(options = {}) {
    return new HttpOrgSource(options);
}
/** 登记内建 HTTP 数据源（默认键，宿主可覆盖）。 */
registerOrgSource('http', createHttpOrgSource);
/**
 * 解统一响应包装（`{ code, message, data }`；非包装原样返回；业务码非 0 / 200 抛错）。
 *
 * @param payload 原始响应体。
 * @returns 数据体。
 */
function unwrapResponse(payload) {
    if (payload !== null && typeof payload === 'object' && !Array.isArray(payload)) {
        const record = payload;
        if (typeof record.code === 'number') {
            if (record.code !== 0 && record.code !== 200) {
                throw new BaseError(record.code, typeof record.message === 'string' ? record.message : '');
            }
            return record.data;
        }
    }
    return payload;
}
