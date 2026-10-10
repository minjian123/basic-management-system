/**
 * 设计令牌能力基类：间距 / 色板 / 密度 / 断点 / 主题订阅（占位数据源）。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 设计令牌能力基类（抽象）。 */
export class BaseDesignToken extends BaseComponent {
    /** 能力键。 */
    identifier = 'design-token';
    /** 当前令牌集（宿主注入）。 */
    #tokens = {};
    /** 当前主题。 */
    #theme = 'light';
    /** 主题监听器。 */
    #listeners = new Set();
    /** 当前令牌集（只读）。 */
    get tokens() {
        return this.#tokens;
    }
    /** 当前主题。 */
    get theme() {
        return this.#theme;
    }
    /**
     * 注入令牌集（宿主装配期调用）。
     *
     * @param tokens 令牌分组。
     */
    setTokens(tokens) {
        this.#tokens = tokens;
        if (!this.isDisposed) {
            this.notifyLifecycle('update');
        }
    }
    /**
     * 切换主题。
     *
     * @param theme 主题名。
     */
    setTheme(theme) {
        if (theme === this.#theme) {
            return;
        }
        this.#theme = theme;
        for (const listener of [...this.#listeners]) {
            try {
                listener(theme);
            }
            catch (error) {
                this.reportError(error, { scope: 'BaseDesignToken.onThemeChange' });
            }
        }
        if (!this.isDisposed) {
            this.notifyLifecycle('update');
        }
    }
    /**
     * 订阅主题变更。
     *
     * @param listener 监听器。
     * @returns 取消函数（幂等）。
     */
    onThemeChange(listener) {
        this.#listeners.add(listener);
        return () => {
            this.#listeners.delete(listener);
        };
    }
}
