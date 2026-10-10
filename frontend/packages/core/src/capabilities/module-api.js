/**
 * 请求能力基类（抽象）：模块经宿主注入的请求能力按「服务键 + 路径」（平台服务）或
 * 「产品键 + 域 + 路径」（产品服务，`product()` 作用域）访问后端。
 *
 * - **凭据不下发**：前缀组装、令牌注入、统一响应解包、401 静默刷新与重放由宿主请求层处理；
 * - **请求执行经核心 `request()`**：适配器未注入时抛 `BaseError(NOT_IMPLEMENTED)`（占位零请求）；
 * - **幂等键口径是宿主实现点**：`createIdempotencyKey` 由宿主子类覆写（服务端要求可变），
 *   `target` 为「服务键」或「产品键:域」；
 * - **未登记不静默放行**：未知服务键 / 未登记产品键 / 非法域段抛参数段位错误（零请求）；
 * - **未注入即降级**：模块缺省上下文自行降级，不假定请求能力存在。
 */
import { request } from '../contracts/request';
import { isProductKey, productDomain, productUrl, serviceUrl } from '../contracts/service-endpoint';
import { BasePlaceholderState } from './placeholder-state';
import { BaseError } from '../mechanisms/error';
import { ErrorCodes } from '../mechanisms/error-codes';
/** 请求能力基类（抽象）。 */
export class BaseModuleApi extends BasePlaceholderState {
    /** 能力键。 */
    identifier = 'module-api';
    /**
     * GET 请求。
     *
     * @param service 服务键。
     * @param path 资源子路径（缺省为服务前缀本身）。
     * @param params 查询参数。
     */
    async get(service, path = '', params) {
        return this.request({ method: 'GET', service, path, params });
    }
    /**
     * POST 请求（自动生成幂等键）。
     *
     * @param service 服务键。
     * @param path 资源子路径。
     * @param data 请求体。
     */
    async post(service, path = '', data) {
        return this.request({
            method: 'POST',
            service,
            path,
            data,
            idempotencyKey: this.createIdempotencyKey(service, path),
        });
    }
    /**
     * PUT 请求（自动生成幂等键）。
     *
     * @param service 服务键。
     * @param path 资源子路径。
     * @param data 请求体。
     */
    async put(service, path = '', data) {
        return this.request({
            method: 'PUT',
            service,
            path,
            data,
            idempotencyKey: this.createIdempotencyKey(service, path),
        });
    }
    /**
     * DELETE 请求。
     *
     * @param service 服务键。
     * @param path 资源子路径。
     * @param params 查询参数。
     */
    async del(service, path = '', params) {
        return this.request({ method: 'DELETE', service, path, params });
    }
    /**
     * 通用请求（服务键 + 路径 → 外部地址；执行交核心适配器）。
     *
     * @param config 请求入参。
     */
    async request(config) {
        return request({
            method: config.method,
            url: serviceUrl(config.service, config.path ?? ''),
            params: config.params,
            data: config.data,
            headers: config.headers,
            idempotencyKey: config.idempotencyKey,
        });
    }
    /**
     * 产品域作用域（**产品服务**经产品命名空间 `/api/{产品键}/v1/{域}/...` 访问）。
     *
     * 未登记的产品键 / 非法域段在此**立即抛错**（参数段位、零请求）；域段由产品自持。
     *
     * @param product 产品键。
     * @param domain 域段（产品服务内部域）。
     */
    product(product, domain) {
        if (!isProductKey(product)) {
            throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `未登记的产品键：${String(product)}`);
        }
        const segment = productDomain(domain);
        const target = `${product}:${segment}`;
        /**
         * 产品域请求（地址经产品寻址单一来源组装；执行交核心适配器）。
         *
         * @param config 请求入参（`path` 相对产品域前缀）。
         * @param idempotencyKey 幂等键（缺省取 `config.idempotencyKey`）。
         */
        const send = (config, idempotencyKey) => request({
            method: config.method,
            url: productUrl(product, segment, config.path ?? ''),
            params: config.params,
            data: config.data,
            headers: config.headers,
            idempotencyKey: idempotencyKey ?? config.idempotencyKey,
        });
        return {
            get: (path = '', params) => send({ method: 'GET', path, params }),
            post: (path = '', data) => send({ method: 'POST', path, data }, this.createIdempotencyKey(target, path)),
            put: (path = '', data) => send({ method: 'PUT', path, data }, this.createIdempotencyKey(target, path)),
            patch: (path = '', data) => send({ method: 'PATCH', path, data }, this.createIdempotencyKey(target, path)),
            del: (path = '', params) => send({ method: 'DELETE', path, params }),
            request: (config) => send(config),
        };
    }
}
