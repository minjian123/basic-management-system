/**
 * 拖拽基座能力基类：拖拽 / 排序 / 跨区事件骨架（表单设计器、报表与大屏设计器、工作台卡片共用）。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 拖拽能力基类（抽象）。 */
export class BaseDragDrop extends BaseComponent {
    /** 能力键。 */
    identifier = 'drag-drop';
    /** 是否拖拽中。 */
    dragging = false;
    /** 拖拽监听器。 */
    #listeners = new Set();
    /**
     * 广播拖拽事件。
     *
     * @param payload 事件载荷。
     */
    emitDrag(payload) {
        this.dragging = payload.phase === 'start' || payload.phase === 'over';
        for (const listener of [...this.#listeners]) {
            try {
                listener(payload);
            }
            catch (error) {
                this.reportError(error, { scope: 'BaseDragDrop.onDrag' });
            }
        }
    }
    /**
     * 订阅拖拽事件。
     *
     * @param listener 监听器。
     * @returns 取消函数（幂等）。
     */
    onDrag(listener) {
        this.#listeners.add(listener);
        return () => {
            this.#listeners.delete(listener);
        };
    }
}
