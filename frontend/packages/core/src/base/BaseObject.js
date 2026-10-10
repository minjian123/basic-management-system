/**
 * 总基类：一切前端基类之根，公共方法唯一落点。
 *
 * 提供命名空间 / 版本、日志、错误上报、配置读取与生命周期（`dispose`）。
 * 普通类（非抽象），可被混合继承；只放所有基类共有的横切职责，子类自带实现优先。
 * 日志 / 上报 / 配置取源经模块级 sink 注入（宿主装配期调用 `configureBase`），缺省用 console / 空配置。
 */
/** 缺省日志 sink（console，按级别）。 */
const defaultLogger = (level, message, meta) => {
    const fn = level === 'error' ? console.error : level === 'warn' ? console.warn : level === 'debug' ? console.debug : console.info;
    if (meta === undefined) {
        fn(message);
    }
    else {
        fn(message, meta);
    }
};
/** 缺省错误上报 sink（`console.error`）。 */
const defaultReporter = (error, meta) => {
    if (meta === undefined) {
        console.error(error);
    }
    else {
        console.error(error, meta);
    }
};
/** 缺省配置源（恒空，`getConfig` 返回 `fallback`）。 */
const emptyConfig = { get: () => undefined };
let sinks = {
    logger: defaultLogger,
    reporter: defaultReporter,
    config: emptyConfig,
};
/** 注入基础 sink（宿主装配期调用；未提供项沿用当前值）。 */
export function configureBase(next) {
    sinks = {
        logger: next.logger ?? sinks.logger,
        reporter: next.reporter ?? sinks.reporter,
        config: next.config ?? sinks.config,
    };
}
/** 重置为缺省 sink（测试用）。 */
export function resetBaseSinks() {
    sinks = { logger: defaultLogger, reporter: defaultReporter, config: emptyConfig };
}
/** 读取当前基础 sink（供混入 `withBaseObject` 复用）。 */
export function getBaseSinks() {
    return sinks;
}
/** 总基类。 */
export class BaseObject {
    /** 命名空间（日志前缀 / 埋点域 / 错误定位）。 */
    namespace;
    /** 版本。 */
    version;
    /** 是否已释放（生命周期幂等标记）。 */
    disposed = false;
    constructor(namespace = 'base', version = '0.0.0') {
        this.namespace = namespace;
        this.version = version;
    }
    /** 是否已释放。 */
    get isDisposed() {
        return this.disposed;
    }
    /** 统一日志（委托注入 sink）。 */
    log(level, message, meta) {
        sinks.logger(level, `[${this.namespace}] ${message}`, meta);
    }
    /** 统一错误上报（委托注入 sink）。 */
    reportError(error, meta) {
        sinks.reporter(error, meta);
    }
    /** 配置读取（未命中返回 `fallback`）。 */
    getConfig(key, fallback) {
        const value = sinks.config.get(key);
        return (value === undefined ? fallback : value);
    }
    /** 生命周期释放（幂等；首次调用触发一次 `onDispose`）。 */
    dispose() {
        if (this.disposed) {
            return;
        }
        this.disposed = true;
        this.onDispose();
    }
    /** 子类释放钩子（缺省空实现）。 */
    onDispose() { }
}
