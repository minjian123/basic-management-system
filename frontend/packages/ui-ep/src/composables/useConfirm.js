/** 通用二次确认组合式：`confirm()` 返回 Promise，由挂载的 `ConfirmDialog` 结算。 */
import { BaseModalShell } from '@bms/core';
import { ref } from 'vue';
const state = {
    visible: ref(false),
    title: ref('确认'),
    content: ref(''),
    danger: ref(false),
    confirmText: ref('确定'),
    cancelText: ref('取消'),
};
let resolver;
/** 确认模态壳（经核心 `BaseModalShell` 派生）。 */
class ConfirmShell extends BaseModalShell {
}
const shell = new ConfirmShell();
shell.onToggle((open) => {
    state.visible.value = open;
});
/**
 * 使用通用二次确认。
 *
 * @returns 状态与 `confirm` / `resolveConfirm`（后者由 `ConfirmDialog` 事件调用）。
 */
export function useConfirm() {
    async function confirm(options = {}) {
        state.title.value = options.title ?? '确认';
        state.content.value = options.content ?? '';
        state.danger.value = options.danger ?? false;
        state.confirmText.value = options.confirmText ?? '确定';
        state.cancelText.value = options.cancelText ?? '取消';
        shell.show();
        return new Promise((resolve) => {
            resolver = resolve;
        });
    }
    function resolveConfirm(value) {
        shell.hide('resolve');
        resolver?.(value);
        resolver = undefined;
    }
    return { state, confirm, resolveConfirm };
}
