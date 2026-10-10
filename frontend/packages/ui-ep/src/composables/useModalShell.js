/**
 * 模态壳投影：把核心模态组件基类 `BaseModalShell` 投影为组合式（响应式显隐 + 关闭拦截）。
 */
import { BaseModalShell } from '@bms/core';
import { ref } from 'vue';
/** 具体模态壳（可实例化）。 */
class ModalShell extends BaseModalShell {
}
/**
 * 使用模态壳投影。
 *
 * @returns 模态壳实例与响应式面。
 */
export function useModalShell() {
    const shell = new ModalShell();
    const visible = ref(shell.open);
    shell.onToggle((open) => {
        visible.value = open;
    });
    return {
        shell,
        visible,
        open: () => shell.show(),
        close: (reason = 'close') => shell.hide(reason),
        requestClose: (reason = 'close') => shell.requestClose(reason),
        setBeforeClose: (guard) => {
            shell.beforeClose = guard;
        },
    };
}
