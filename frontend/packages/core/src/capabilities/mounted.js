/**
 * 可挂载能力基类：挂载 / 卸载生命周期与释放登记统一入口。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 可挂载能力基类（抽象）。 */
export class BaseMounted extends BaseComponent {
    /** 能力键。 */
    identifier = 'mounted';
    /** 是否已挂载。 */
    #mounted = false;
    /** 待释放回调（卸载时逆序执行）。 */
    #releases = [];
    /** 挂载状态监听器。 */
    #listeners = new Set();
    /** 是否已挂载。 */
    get mounted() {
        return this.#mounted;
    }
    /** 挂载（幂等；首次广播 `mount`）。 */
    mount() {
        if (this.#mounted) {
            return;
        }
        this.#mounted = true;
        this.#broadcast(true);
        this.notifyLifecycle('mount');
    }
    /** 卸载（幂等；逆序释放登记项并广播 `unmount`）。 */
    unmount() {
        if (!this.#mounted) {
            return;
        }
        this.#mounted = false;
        while (this.#releases.length > 0) {
            const release = this.#releases.pop();
            try {
                release();
            }
            catch (error) {
                this.reportError(error, { scope: 'BaseMounted.unmount' });
            }
        }
        this.#broadcast(false);
        this.notifyLifecycle('unmount');
    }
    /**
     * 登记卸载释放回调。
     *
     * @param release 释放回调。
     */
    registerRelease(release) {
        this.#releases.push(release);
    }
    /**
     * 订阅挂载状态变化。
     *
     * @param listener 监听器。
     * @returns 取消函数（幂等）。
     */
    onMountChange(listener) {
        this.#listeners.add(listener);
        return () => {
            this.#listeners.delete(listener);
        };
    }
    /** 广播挂载状态。 */
    #broadcast(mounted) {
        for (const listener of [...this.#listeners]) {
            try {
                listener(mounted);
            }
            catch (error) {
                this.reportError(error, { scope: 'BaseMounted.onMountChange' });
            }
        }
    }
}
