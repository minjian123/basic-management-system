/**
 * 服务寻址契约（框架无关）：外部路径的「域 → 前缀」**单一来源**。
 *
 * 两类命名空间并列（模块 / 页面一律经本模块组装地址，**禁止自拼前缀**）：
 * - **平台服务**：`/api/{service_key}/v1/...`——网关按服务目录生成外部路由（重写为服务内 `/api/v1`）；
 *   服务键与后端服务目录 `SERVICE_CATALOG`（`service_key`）中的**非产品分组平台服务**同源、
 *   顺序保持一致（8 个已启用服务）。
 * - **产品服务**：`/api/{product_key}/v1/{domain}/...`——网关只为产品服务生成**产品命名空间**路由，
 *   不为产品服务生成服务级路由；产品键在此登记，域段由**产品自持**（基座不维护产品内部域清单，
 *   避免双事实源）。`org` 随组织主数据归 mdm 产品服务后退出平台服务清单（2026-10-07，bms 11_01）。
 */
import { BaseError } from '../mechanisms/error';
import { ErrorCodes } from '../mechanisms/error-codes';
/** 服务键清单（顺序与服务目录一致：8 个已启用平台服务）。 */
export const SERVICE_KEYS = [
    'platform',
    'identity',
    'tenant',
    'file',
    'notification',
    'search',
    'ai',
    'report',
];
/** 产品键清单（与平台侧产品登记同源：新增产品接入时在此登记，同批落产品档案与网关产品路由）。 */
export const PRODUCT_KEYS = ['mdm'];
/** 外部路径版本段。 */
export const API_VERSION_SEGMENT = 'v1';
/** 产品域段格式（产品服务内部域：小写字母开头，可含数字 / 连字符 / 下划线）。 */
const PRODUCT_DOMAIN_PATTERN = /^[a-z][a-z0-9_-]*$/;
/**
 * 服务键判定（未知服务不静默放行）。
 *
 * @param value 待判定值。
 * @returns 是否为已登记服务键。
 */
export function isServiceKey(value) {
    return typeof value === 'string' && SERVICE_KEYS.includes(value);
}
/**
 * 产品键判定（未登记产品不静默放行）。
 *
 * @param value 待判定值。
 * @returns 是否为已登记产品键。
 */
export function isProductKey(value) {
    return typeof value === 'string' && PRODUCT_KEYS.includes(value);
}
/**
 * 路径归一（去首部斜杠、折叠重复斜杠；查询串与深层路径原样保留）。
 *
 * @param path 资源子路径。
 * @returns 归一后的路径。
 */
function normalizePath(path) {
    return path.replace(/^\/+/, '').replace(/\/{2,}/g, '/');
}
/**
 * 服务前缀（`/api/{service}/v1`）。
 *
 * @param service 服务键。
 * @returns 外部服务前缀。
 * @throws BaseError 未登记的服务键（`CAPABILITY_VIOLATION`，参数段位）。
 */
export function servicePrefix(service) {
    if (!isServiceKey(service)) {
        throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `未登记的服务键：${String(service)}`);
    }
    return `/api/${service}/${API_VERSION_SEGMENT}`;
}
/**
 * 服务段 URL 组装（`/api/{service}/v1{path}`）。
 *
 * 路径归一：去首部斜杠、折叠重复斜杠；空路径返回前缀本身。
 *
 * @param service 服务键。
 * @param path 资源子路径（可带或不带首部 `/`；缺省空）。
 * @returns 外部请求地址。
 * @throws BaseError 未登记的服务键（`CAPABILITY_VIOLATION`，参数段位）。
 */
export function serviceUrl(service, path = '') {
    const prefix = servicePrefix(service);
    const normalized = normalizePath(path);
    return normalized === '' ? prefix : `${prefix}/${normalized}`;
}
/**
 * 产品域段归一与校验（产品自持域：`org` / `sup` / `cus` / `mat` 等）。
 *
 * @param domain 域段（可带首尾 `/`，去空白后判定）。
 * @returns 归一后的域段。
 * @throws BaseError 域段缺失或格式非法（`CAPABILITY_VIOLATION`，参数段位）。
 */
export function productDomain(domain) {
    const segment = normalizePath(String(domain).trim()).replace(/\/+$/, '');
    if (!PRODUCT_DOMAIN_PATTERN.test(segment)) {
        throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `非法的产品域段：${String(domain)}`);
    }
    return segment;
}
/**
 * 产品命名空间前缀（`/api/{product}/v1/{domain}`）。
 *
 * @param product 产品键。
 * @param domain 域段（产品服务内部域）。
 * @returns 外部产品域前缀。
 * @throws BaseError 未登记的产品键 / 域段非法（`CAPABILITY_VIOLATION`，参数段位）。
 */
export function productPrefix(product, domain) {
    if (!isProductKey(product)) {
        throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `未登记的产品键：${String(product)}`);
    }
    return `/api/${product}/${API_VERSION_SEGMENT}/${productDomain(domain)}`;
}
/**
 * 产品段 URL 组装（`/api/{product}/v1/{domain}{path}`）。
 *
 * 路径归一与服务通道同口径。
 *
 * @param product 产品键。
 * @param domain 域段（产品服务内部域）。
 * @param path 资源子路径（可带或不带首部 `/`；缺省空）。
 * @returns 外部请求地址。
 * @throws BaseError 未登记的产品键 / 域段非法（`CAPABILITY_VIOLATION`，参数段位）。
 */
export function productUrl(product, domain, path = '') {
    const prefix = productPrefix(product, domain);
    const normalized = normalizePath(path);
    return normalized === '' ? prefix : `${prefix}/${normalized}`;
}
