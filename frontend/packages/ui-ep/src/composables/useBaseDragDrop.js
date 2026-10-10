/** 拖拽投影：把核心拖拽能力基类 `BaseDragDrop` 投影为组合式（拖拽中 / 事件广播与订阅）。 */
import { BaseDragDrop } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体拖拽件（可实例化）。 */
class DragDropState extends BaseDragDrop {
}
/**
 * 使用拖拽投影。
 *
 * @returns 拖拽基类实例与响应式面。
 */
export function useBaseDragDrop() {
    const dragDrop = new DragDropState();
    const dragging = ref(dragDrop.dragging);
    const off = dragDrop.onLifecycle((event) => {
        if (event === 'update') {
            dragging.value = dragDrop.dragging;
        }
    });
    onScopeDispose(off);
    return {
        dragDrop,
        dragging,
        emitDrag: (payload) => {
            dragDrop.emitDrag(payload);
            dragging.value = dragDrop.dragging;
        },
        onDrag: (listener) => dragDrop.onDrag(listener),
    };
}
