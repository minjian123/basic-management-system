/**
 * 请求适配契约（框架无关）：统一响应 / 分页响应 / 适配器接口。
 *
 * 实际请求实现（Axios 实例、拦截器、401 刷新、提示注入）由宿主请求层注入；
 * 未注入适配器时 `request()` 抛 `BaseError(19001)`（占位不请求）。
 */
import { BaseError } from '../mechanisms/error';
import { ErrorCodes } from '../mechanisms/error-codes';
let adapter;
/**
 * 注入请求适配器（宿主装配期调用）。
 *
 * @param next 适配器。
 */
export function configureRequestAdapter(next) {
    adapter = next;
}
/** 读取当前请求适配器。 */
export function getRequestAdapter() {
    return adapter;
}
/**
 * 执行请求（经注入适配器；未注入则抛 `BaseError(NOT_IMPLEMENTED)`）。
 *
 * @param config 请求配置。
 */
export async function request(config) {
    if (adapter === undefined) {
        throw new BaseError(ErrorCodes.NOT_IMPLEMENTED, '请求适配器未注入');
    }
    return adapter.request(config);
}
