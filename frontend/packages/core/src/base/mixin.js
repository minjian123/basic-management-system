/**
 * 混入：把 `BaseObject` 的公共能力（命名空间 / 版本 / 日志 / 上报 / 配置 / 生命周期）注入任意基类。
 *
 * 用于 TS 不支持多重继承的场景——如 `BaseError` 需同时保留 `instanceof Error` 与堆栈、
 * 又取得总基类能力（体系「唯一有理由的多重继承」）。
 */
import { getBaseSinks } from './BaseObject';
/**
 * 把 `BaseObject` 公共面混入 `Base`。
 *
 * @param Base 目标基类（如 `Error`）。
 * @param namespace 命名空间（缺省 `base`）。
 * @returns 具备 `BaseObject` 公共面的派生类。
 */
export function withBaseObject(Base, namespace = 'base') {
    return class BaseObjectMixed extends Base {
        /** 命名空间。 */
        namespace = namespace;
        /** 版本。 */
        version = '0.0.0';
        /** 是否已释放。 */
        #disposed = false;
        /** 是否已释放。 */
        get isDisposed() {
            return this.#disposed;
        }
        /** 统一日志。 */
        log(level, message, meta) {
            getBaseSinks().logger(level, `[${this.namespace}] ${message}`, meta);
        }
        /** 统一错误上报。 */
        reportError(error, meta) {
            getBaseSinks().reporter(error, meta);
        }
        /** 配置读取（未命中返回 `fallback`）。 */
        getConfig(key, fallback) {
            const value = getBaseSinks().config.get(key);
            return (value === undefined ? fallback : value);
        }
        /** 生命周期释放（幂等；首次调用触发一次 `onDispose`）。 */
        dispose() {
            if (this.#disposed) {
                return;
            }
            this.#disposed = true;
            this.onDispose();
        }
        /** 子类释放钩子（缺省空实现）。 */
        onDispose() { }
    };
}
