/** 布局件投影：把核心布局组件基类 `BaseLayout` 投影为组合式（栅格列数 / 间距 / 显隐）。 */
import { BaseLayout } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体布局件（可实例化）。 */
class LayoutState extends BaseLayout {
}
/**
 * 使用布局件投影。
 *
 * @param options 选项。
 * @returns 布局基类实例与响应式面。
 */
export function useBaseLayout(options = {}) {
    const layout = new LayoutState();
    if (options.columns !== undefined) {
        layout.columns = options.columns;
    }
    if (options.gap !== undefined) {
        layout.gap = options.gap;
    }
    const columns = ref(layout.columns);
    const gap = ref(layout.gap);
    const hidden = ref(layout.hidden);
    const off = layout.onLifecycle((event) => {
        if (event === 'update') {
            columns.value = layout.columns;
            gap.value = layout.gap;
            hidden.value = layout.hidden;
        }
    });
    onScopeDispose(off);
    return {
        layout,
        columns,
        gap,
        hidden,
        setColumns: (next) => {
            layout.columns = next;
            layout.notifyLifecycle('update');
        },
        setGap: (next) => {
            layout.gap = next;
            layout.notifyLifecycle('update');
        },
        setHidden: (next) => layout.setHidden(next),
    };
}
