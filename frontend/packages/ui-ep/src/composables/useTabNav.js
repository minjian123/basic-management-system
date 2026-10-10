/** 多标签导航组合式：页签打开 / 关闭 / 刷新 / keep-alive 名单 / 会话内持久化。状态经核心页签能力基类 `BaseTabs`。 */
import { BaseTabs } from '@bms/core';
import { ref } from 'vue';
import { useBasePersistedState } from './useBasePersistedState';
import { useConfirm } from './useConfirm';
/** 具体页签状态（可实例化）。 */
class TabNavState extends BaseTabs {
    /** 页签完整信息。 */
    items = new Map();
    /** 固定页签键清单。 */
    get pinnedKeys() {
        return this.tabs.filter((tab) => tab.pinned === true).map((tab) => tab.key);
    }
    /** keep-alive 名单（按 `keepAlive` 过滤已打开页签）。 */
    cachedList() {
        return this.cacheKeys.filter((key) => this.items.get(key)?.keepAlive === true);
    }
}
/**
 * 使用多标签导航。
 *
 * @param options 选项。
 * @returns 页签状态与操作方法。
 */
export function useTabNav(options = {}) {
    const { confirm } = useConfirm();
    const storage = useBasePersistedState({ stateKey: options.storageKey ?? '', storage: 'session' });
    const state = new TabNavState();
    const tabs = ref([]);
    const activeKey = ref('');
    const cachedKeys = ref([]);
    const refreshing = ref('');
    function persist() {
        if (options.storageKey === undefined) {
            return;
        }
        storage.setLocal({ tabs: tabs.value, activeKey: activeKey.value });
        storage.persist();
    }
    function sync() {
        tabs.value = state.tabs.map((tab) => ({ ...state.items.get(tab.key), key: tab.key, title: tab.title }));
        activeKey.value = state.activeKey ?? '';
        cachedKeys.value = state.cachedList();
    }
    state.onLifecycle((event) => {
        if (event === 'update') {
            sync();
            persist();
        }
    });
    function open(item) {
        state.items.set(item.key, item);
        state.open({ key: item.key, title: item.title, pinned: item.closable === false });
    }
    function activate(key) {
        state.activate(key);
    }
    function markDirty(key, dirty = true) {
        const item = state.items.get(key);
        if (item !== undefined) {
            item.dirty = dirty;
            sync();
        }
    }
    async function close(key) {
        const item = state.items.get(key);
        if (item === undefined || item.closable === false) {
            return false;
        }
        if (item.dirty === true) {
            const confirmed = await confirm({ content: '该页签存在未保存的修改，确定关闭吗？' });
            if (!confirmed) {
                return false;
            }
        }
        state.close(key);
        state.items.delete(key);
        return true;
    }
    async function closeKeys(keys) {
        for (const key of keys) {
            await close(key);
        }
    }
    async function closeOthers(key) {
        await closeKeys(state.cacheKeys.filter((item) => item !== key && !state.pinnedKeys.includes(item)));
    }
    async function closeRight(key) {
        const index = state.cacheKeys.indexOf(key);
        if (index < 0) {
            return;
        }
        await closeKeys(state.cacheKeys.slice(index + 1).filter((item) => !state.pinnedKeys.includes(item)));
    }
    async function closeAll() {
        await closeKeys(state.cacheKeys.filter((item) => !state.pinnedKeys.includes(item)));
    }
    function refresh(key) {
        if (!state.cacheKeys.includes(key)) {
            return;
        }
        refreshing.value = key;
        cachedKeys.value = state.cachedList().filter((item) => item !== key);
        queueMicrotask(() => {
            refreshing.value = '';
            cachedKeys.value = state.cachedList();
        });
    }
    function restore() {
        const parsed = storage.restore() ? storage.local.value : undefined;
        const source = parsed?.tabs ?? options.initial ?? [];
        const storedActive = parsed?.activeKey ?? '';
        for (const item of source) {
            open({ ...item, dirty: false });
        }
        if (storedActive !== '' && state.cacheKeys.includes(storedActive)) {
            state.activate(storedActive);
        }
        sync();
    }
    try {
        restore();
    }
    catch {
        state.items.clear();
        state.tabs.splice(0, state.tabs.length);
        sync();
    }
    return {
        tabs,
        activeKey,
        cachedKeys,
        refreshing,
        open,
        activate,
        close,
        closeOthers,
        closeRight,
        closeAll,
        refresh,
        markDirty,
    };
}
