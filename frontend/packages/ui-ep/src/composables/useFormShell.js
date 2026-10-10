/** 表单框架壳组合式：列表固定页签 + 详情多开页签（基于 `useTabNav`，不重复造页签逻辑）。 */
import { computed, ref } from 'vue';
import { useTabNav } from './useTabNav';
/**
 * 使用表单框架壳。
 *
 * @param options 选项。
 * @returns 列表 / 详情页签与操作方法。
 */
export function useFormShell(options = {}) {
    const listKey = options.listKey ?? 'list';
    const listTab = { key: listKey, title: options.listTitle ?? '列表', path: listKey, closable: false };
    const nav = useTabNav();
    nav.open(listTab);
    const refreshToken = ref(0);
    const detailTabs = computed(() => nav.tabs.value.filter((item) => item.key !== listKey));
    const cachedDetailKeys = computed(() => nav.cachedKeys.value.filter((key) => key !== listKey));
    function openDetail(record) {
        const key = `detail:${record.id}`;
        nav.open({ key, title: record.title, path: key, keepAlive: options.cacheDetail === true, dirty: record.dirty });
        return key;
    }
    async function closeDetail(key) {
        return nav.close(key);
    }
    function activeDetail() {
        const active = nav.activeKey.value;
        return active === listKey ? undefined : detailTabs.value.find((item) => item.key === active);
    }
    return {
        listTab,
        detailTabs,
        activeKey: nav.activeKey,
        cachedDetailKeys,
        openDetail,
        closeDetail,
        markDirty: (key, dirty = true) => nav.markDirty(key, dirty),
        activeDetail,
        refreshToken,
        requestRefresh: () => {
            refreshToken.value += 1;
        },
    };
}
