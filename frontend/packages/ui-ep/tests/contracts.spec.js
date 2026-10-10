/** 契约用例工厂在 PC 插件侧的跑通（02-7）：确认 / 反馈 / 容器契约。 */
import { describeConfirmContract, describeContainerContract, describeFeedbackContract, } from '@bms/core/testing';
import { useBaseContainer, useConfirm, useFeedback } from '../src';
describeConfirmContract('确认契约（useConfirm）', () => {
    const api = useConfirm();
    return {
        get open() {
            return api.state.visible.value;
        },
        confirm: (options) => api.confirm(options),
        resolve: (value) => api.resolveConfirm(value),
    };
});
describeFeedbackContract('反馈契约（useFeedback）', () => {
    const feedback = useFeedback();
    return {
        get state() {
            return feedback.state.value;
        },
        setState: (state) => {
            if (state === 'loading') {
                feedback.begin();
            }
            else if (state === 'ready') {
                feedback.ready();
            }
            else if (state === 'empty') {
                feedback.empty();
            }
            else {
                feedback.error();
            }
        },
        doRetry: () => feedback.retry(),
        get retry() {
            return undefined;
        },
        set retry(listener) {
            feedback.setRetry(listener);
        },
    };
});
describeContainerContract('容器契约（useBaseContainer）', () => {
    const container = useBaseContainer();
    return {
        get collapsible() {
            return container.collapsible.value;
        },
        set collapsible(value) {
            container.setCollapsible(value);
        },
        get collapsed() {
            return container.collapsed.value;
        },
        set collapsed(value) {
            container.setCollapsed(value);
        },
        toggleCollapse: () => container.toggle(),
    };
});
