/**
 * 反馈组件基类（反馈族）：`loading → ready / empty / error` 反馈状态机与降级重试。
 */
import { BaseNotice } from './notice';
/** 反馈组件基类（抽象）。 */
export class BaseFeedback extends BaseNotice {
    /** 能力键（组件基类身份）。 */
    identifier = 'feedback';
    /** 当前反馈状态。 */
    state = 'loading';
    /** 重试回调（宿主注入）。 */
    retry;
    /**
     * 设置反馈状态。
     *
     * @param state 状态。
     */
    setState(state) {
        this.state = state;
        this.notifyLifecycle('update');
    }
    /** 触发重试（仅错误态且已注入重试时）。 */
    doRetry() {
        if (this.state !== 'error' || this.retry === undefined) {
            return false;
        }
        this.retry();
        return true;
    }
}
