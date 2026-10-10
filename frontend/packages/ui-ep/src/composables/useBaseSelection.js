/** 选中集合投影：把核心选中集合能力基类 `BaseSelection` 投影为组合式（选中键 / 计数 / 摘要 / 跨页全选）。 */
import { BaseSelection } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体选中集合（可实例化）。 */
class Selection extends BaseSelection {
}
/**
 * 使用选中集合投影。
 *
 * @param options 选项。
 * @returns 选中集合基类实例与响应式面。
 */
export function useBaseSelection(options = {}) {
    const selection = new Selection();
    if (options.mode !== undefined) {
        selection.setMode(options.mode);
    }
    if (options.total !== undefined) {
        selection.setTotal(options.total);
    }
    if (options.pageKeys !== undefined) {
        selection.setPageKeys(options.pageKeys);
    }
    if (options.selected !== undefined) {
        selection.replace(options.selected);
    }
    const selected = ref([...selection.selected]);
    const count = ref(selection.count);
    const summary = ref(selection.summary);
    const isEmpty = ref(selection.isEmpty);
    const isAllPageSelected = ref(selection.isAllPageSelected);
    const somePageSelected = ref(selection.somePageSelected);
    const mode = ref(selection.mode);
    const pageKeys = ref([...selection.pageKeys]);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        selected.value = [...selection.selected];
        count.value = selection.count;
        summary.value = selection.summary;
        isEmpty.value = selection.isEmpty;
        isAllPageSelected.value = selection.isAllPageSelected;
        somePageSelected.value = selection.somePageSelected;
        mode.value = selection.mode;
        pageKeys.value = [...selection.pageKeys];
    };
    const off = selection.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        selection,
        selected,
        count,
        summary,
        isEmpty,
        isAllPageSelected,
        somePageSelected,
        mode,
        pageKeys,
        setMode: (next) => {
            selection.setMode(next);
            sync();
        },
        setTotal: (total) => {
            selection.setTotal(total);
            sync();
        },
        setPageKeys: (keys) => {
            selection.setPageKeys(keys);
            sync();
        },
        select: (key, isSelected) => {
            selection.select(key, isSelected);
            sync();
        },
        toggle: (key) => {
            selection.toggle(key);
            sync();
        },
        selectPage: () => {
            selection.selectPage();
            sync();
        },
        deselectPage: () => {
            selection.deselectPage();
            sync();
        },
        invertPage: () => {
            selection.invertPage();
            sync();
        },
        selectAllAcrossPages: () => {
            selection.selectAllAcrossPages();
            sync();
        },
        clear: () => {
            selection.clear();
            sync();
        },
        replace: (keys) => {
            selection.replace(keys);
            sync();
        },
        isSelected: (key) => selection.isSelected(key),
    };
}
