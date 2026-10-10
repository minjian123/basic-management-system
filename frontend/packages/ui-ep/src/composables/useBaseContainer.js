/** 容器件投影：把核心容器组件基类 `BaseContainer` 投影为组合式（可折叠 / 折叠态 / 分栏）。 */
import { BaseContainer } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体容器件（可实例化）。 */
class ContainerState extends BaseContainer {
}
/**
 * 使用容器件投影。
 *
 * @param options 选项。
 * @returns 容器基类实例与响应式面。
 */
export function useBaseContainer(options = {}) {
    const container = new ContainerState();
    if (options.collapsible !== undefined) {
        container.collapsible = options.collapsible;
    }
    if (options.collapsed !== undefined) {
        container.collapsed = options.collapsed;
    }
    if (options.split !== undefined) {
        container.split = options.split;
    }
    const collapsible = ref(container.collapsible);
    const collapsed = ref(container.collapsed);
    const split = ref(container.split);
    const sizeToken = ref(container.sizeToken);
    const isCompact = ref(container.isCompact);
    const off = container.onLifecycle((event) => {
        if (event === 'update') {
            collapsible.value = container.collapsible;
            collapsed.value = container.collapsed;
            split.value = container.split;
            sizeToken.value = container.sizeToken;
            isCompact.value = container.isCompact;
        }
    });
    onScopeDispose(off);
    return {
        container,
        collapsible,
        collapsed,
        split,
        sizeToken,
        isCompact,
        setCollapsible: (value) => {
            container.collapsible = value;
            container.notifyLifecycle('update');
        },
        setCollapsed: (value) => {
            container.collapsed = value;
            container.notifyLifecycle('update');
        },
        toggle: () => container.toggleCollapse(),
    };
}
