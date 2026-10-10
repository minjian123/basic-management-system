/**
 * 媒体组件基类（媒体族）：加载状态机 / 宽高比 / 过期重取 / 回退。
 */
import { BaseSized } from './sized';
/** 媒体组件基类（抽象）。 */
export class BaseMediaContent extends BaseSized {
    /** 能力键（组件基类身份）。 */
    identifier = 'media-content';
    /** 加载状态。 */
    state = 'loading';
    /** 资源地址。 */
    src = '';
    /** 宽高比（宽 / 高）。 */
    aspectRatio;
    /**
     * 设置资源地址（重置为加载中）。
     *
     * @param src 资源地址。
     */
    setSrc(src) {
        this.src = src;
        this.state = 'loading';
    }
    /** 标记加载完成。 */
    markReady() {
        this.state = 'ready';
    }
    /** 标记加载失败（回退由渲染层按占位呈现）。 */
    markError() {
        this.state = 'error';
    }
}
