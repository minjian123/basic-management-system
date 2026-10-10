/** 内容页签投影：核心页签能力基类 `BaseTabs` 的薄投影（打开 / 激活，供 `el-tabs` 薄封装复用）。 */
import { BaseTabs } from '@bms/core';
import { onScopeDispose } from 'vue';
/** 具体页签状态（可实例化）。 */
class ContentTabsState extends BaseTabs {
}
/**
 * 使用内容页签投影。
 *
 * @returns 页签状态与操作方法。
 */
export function useContentTabs() {
    const state = new ContentTabsState();
    onScopeDispose(() => state.dispose());
    return {
        state,
        open: (tab) => state.open({ key: tab.key, title: tab.title }),
        activate: (key) => state.activate(key),
    };
}
