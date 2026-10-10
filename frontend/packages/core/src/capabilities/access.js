/**
 * 权限上下文能力基类：权限码集合与判定（`has` / `hasAny` / `hasAll`）。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 权限上下文能力基类（抽象）。 */
export class BaseAccess extends BaseComponent {
    /** 能力键。 */
    identifier = 'access';
    /** 权限码集合（唯一来源）。 */
    #codes = new Set();
    /** 权限码清单（只读）。 */
    get codes() {
        return [...this.#codes];
    }
    /**
     * 设置权限码集合（整体替换）。
     *
     * @param codes 权限码。
     */
    setCodes(codes) {
        this.#codes = new Set(codes);
        if (!this.isDisposed) {
            this.notifyLifecycle('update');
        }
    }
    /**
     * 是否具备某权限码。
     *
     * @param code 权限码。
     */
    has(code) {
        return this.#codes.has(code);
    }
    /**
     * 是否具备任一权限码。
     *
     * @param codes 权限码列表。
     */
    hasAny(codes) {
        return codes.some((code) => this.#codes.has(code));
    }
    /**
     * 是否具备全部权限码。
     *
     * @param codes 权限码列表。
     */
    hasAll(codes) {
        return codes.every((code) => this.#codes.has(code));
    }
}
