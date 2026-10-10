/** 树数据投影：把核心树组件基类 `BaseTreeData` 投影为组合式（节点 / 数据状态 / 过滤 / 展开）。 */
import { BaseTreeData } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体树件（可实例化）。 */
class TreeState extends BaseTreeData {
}
/**
 * 使用树数据投影。
 *
 * @param options 选项。
 * @returns 树基类实例与响应式面。
 */
export function useBaseTreeData(options = {}) {
    const tree = new TreeState();
    if (options.nodes !== undefined) {
        tree.load(options.nodes);
    }
    if (options.filterText !== undefined) {
        tree.filterText = options.filterText;
    }
    const nodes = ref(tree.nodes);
    const filterText = ref(tree.filterText);
    const state = ref(tree.state);
    tree.onStateChange((next) => {
        state.value = next;
    });
    const off = tree.onLifecycle((event) => {
        if (event === 'update') {
            nodes.value = tree.nodes;
            filterText.value = tree.filterText;
        }
    });
    onScopeDispose(off);
    function setNodes(next) {
        tree.load(next);
        const token = tree.begin();
        tree.settle(token, tree.nodes.length === 0 ? 'empty' : 'ready');
    }
    return {
        tree,
        nodes,
        filterText,
        state,
        setNodes,
        setFilterText: (text) => {
            tree.filterText = text;
            tree.notifyLifecycle('update');
        },
        setExpanded: (key, expanded = true) => {
            tree.expand(key, expanded);
            tree.notifyLifecycle('update');
        },
        setChecked: (key, checked = true) => {
            tree.check(key, checked);
            tree.notifyLifecycle('update');
        },
    };
}
