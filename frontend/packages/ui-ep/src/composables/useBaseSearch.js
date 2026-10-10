/** 搜索族组件基类投影：把核心 `BaseSearch` 投影为组合式（关键词 / 域 / 分组 / 建议 / 最近搜索 / 日志与文件检索）。 */
import { BaseAccess, BaseSearch, } from '@bms/core';
import { computed, markRaw, onScopeDispose, ref, toRaw } from 'vue';
import { onGlobalKeydown } from '../utils/keyboard';
import { useBasePersistedState } from './useBasePersistedState';
/** 缺省最近搜索存储键。 */
const DEFAULT_RECENT_KEY = 'bms_search_recent';
/** 具体搜索件（可实例化）。 */
class SearchState extends BaseSearch {
}
/**
 * 判断键盘事件是否匹配快捷键（`mod+k` / `alt+k` / `ctrl+shift+f` 等）。
 *
 * @param event 键盘事件。
 * @param shortcut 快捷键描述。
 * @returns 是否匹配。
 */
function matchesShortcut(event, shortcut) {
    const parts = shortcut
        .toLowerCase()
        .split('+')
        .map((part) => part.trim())
        .filter((part) => part !== '');
    const key = parts.filter((part) => !['mod', 'ctrl', 'control', 'meta', 'cmd', 'alt', 'shift'].includes(part)).at(-1);
    if (key === undefined || event.key.toLowerCase() !== key) {
        return false;
    }
    const wantMod = parts.includes('mod');
    const wantCtrl = parts.includes('ctrl') || parts.includes('control');
    const wantMeta = parts.includes('meta') || parts.includes('cmd');
    const wantAlt = parts.includes('alt');
    const wantShift = parts.includes('shift');
    if (wantMod && !(event.ctrlKey || event.metaKey)) {
        return false;
    }
    if (!wantMod && (wantCtrl || wantMeta) && !(event.ctrlKey || event.metaKey)) {
        return false;
    }
    if (wantAlt !== event.altKey) {
        return false;
    }
    if (wantShift !== event.shiftKey) {
        return false;
    }
    return true;
}
/**
 * 使用搜索族组件基类投影。
 *
 * @param options 选项。
 * @returns 搜索基类实例与响应式面。
 */
export function useBaseSearch(options = {}) {
    const search = new SearchState();
    const persisted = useBasePersistedState({
        stateKey: options.storageKey ?? DEFAULT_RECENT_KEY,
        storage: options.storage ?? 'local',
    });
    search.attachPersisted(persisted.persisted);
    if (options.recentKeywords !== undefined && options.recentKeywords.length > 0) {
        search.recentKeywords.splice(0, search.recentKeywords.length, ...options.recentKeywords);
    }
    if (options.domains !== undefined) {
        search.setDomains(options.domains);
    }
    if (options.groups !== undefined) {
        search.groups.splice(0, search.groups.length, ...options.groups);
    }
    if (options.keyword !== undefined) {
        search.setKeyword(options.keyword);
    }
    if (options.activeDomain !== undefined) {
        search.setActiveDomain(options.activeDomain);
    }
    if (options.page !== undefined) {
        search.setPage(options.page);
    }
    if (options.pageSize !== undefined) {
        search.setPageSize(options.pageSize);
    }
    if (options.engine !== undefined) {
        search.setEngine(markRaw(toRaw(options.engine)));
    }
    if (options.access !== undefined) {
        search.setAccess(markRaw(toRaw(options.access)));
    }
    search.setReady(options.ready ?? false);
    const ready = ref(search.ready);
    const degraded = ref(search.degraded);
    const requestCount = ref(search.requestCount);
    const phase = ref(search.phase);
    const errorMessage = ref(search.errorMessage);
    const keyword = ref(search.keyword);
    const activeDomain = ref(search.activeDomain);
    const groups = ref([...search.groups]);
    const total = ref(search.total);
    const page = ref(search.page);
    const pageSize = ref(search.pageSize);
    const suggestions = ref([...search.suggestions]);
    const recentKeywords = ref([...search.recentKeywords]);
    const logItems = ref([...search.logItems]);
    const logTotal = ref(search.logTotal);
    const logPage = ref(search.logPage);
    const logPageSize = ref(search.logPageSize);
    const logType = ref(search.logType);
    const logRange = ref({ ...search.logRange });
    const fileItems = ref([...search.fileItems]);
    const fileTotal = ref(search.fileTotal);
    const filePage = ref(search.filePage);
    const filePageSize = ref(search.filePageSize);
    const fileType = ref(search.fileType);
    const engineDegraded = ref(search.engineDegraded);
    const degradeReason = ref(search.degradeReason);
    const accessibleDomains = computed(() => search.accessibleDomains);
    const hasLogPermission = computed(() => search.hasLogPermission);
    const hasFilePermission = computed(() => search.hasFilePermission);
    const fallbackDomains = computed(() => search.fallbackDomains);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        ready.value = search.ready;
        degraded.value = search.degraded;
        requestCount.value = search.requestCount;
        phase.value = search.phase;
        errorMessage.value = search.errorMessage;
        keyword.value = search.keyword;
        activeDomain.value = search.activeDomain;
        groups.value = [...search.groups];
        total.value = search.total;
        page.value = search.page;
        pageSize.value = search.pageSize;
        suggestions.value = [...search.suggestions];
        recentKeywords.value = [...search.recentKeywords];
        logItems.value = [...search.logItems];
        logTotal.value = search.logTotal;
        logPage.value = search.logPage;
        logPageSize.value = search.logPageSize;
        logType.value = search.logType;
        logRange.value = { ...search.logRange };
        fileItems.value = [...search.fileItems];
        fileTotal.value = search.fileTotal;
        filePage.value = search.filePage;
        filePageSize.value = search.filePageSize;
        fileType.value = search.fileType;
        engineDegraded.value = search.engineDegraded;
        degradeReason.value = search.degradeReason;
    };
    const off = search.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(() => {
        off();
        search.dispose();
    });
    /** 包裹动作：执行后同步响应式面。 */
    const run = (action) => {
        const value = action();
        sync();
        return value;
    };
    return {
        state: search,
        ready,
        degraded,
        requestCount,
        phase,
        errorMessage,
        keyword,
        activeDomain,
        accessibleDomains,
        groups,
        total,
        page,
        pageSize,
        suggestions,
        recentKeywords,
        logItems,
        logTotal,
        logPage,
        logPageSize,
        logType,
        logRange,
        fileItems,
        fileTotal,
        filePage,
        filePageSize,
        fileType,
        engineDegraded,
        degradeReason,
        hasLogPermission,
        hasFilePermission,
        fallbackDomains,
        setReady: (value) => run(() => search.setReady(value)),
        setEngine: (engine) => run(() => search.setEngine(engine === undefined ? undefined : markRaw(toRaw(engine)))),
        setAccess: (access) => run(() => search.setAccess(access === undefined ? undefined : markRaw(toRaw(access)))),
        setDomains: (domains) => run(() => search.setDomains(domains)),
        setKeyword: (value) => run(() => search.setKeyword(value)),
        setActiveDomain: (key) => run(() => search.setActiveDomain(key)),
        setPage: (value) => run(() => search.setPage(value)),
        setPageSize: (size) => run(() => search.setPageSize(size)),
        setLogRange: (range) => run(() => search.setLogRange(range)),
        setLogType: (value) => run(() => search.setLogType(value)),
        setLogPage: (value) => run(() => search.setLogPage(value)),
        setLogPageSize: (size) => run(() => search.setLogPageSize(size)),
        setFileType: (value) => run(() => search.setFileType(value)),
        setFilePage: (value) => run(() => search.setFilePage(value)),
        setFilePageSize: (size) => run(() => search.setFilePageSize(size)),
        search: async () => {
            const value = await search.search();
            sync();
            return value;
        },
        suggest: async () => {
            const value = await search.suggest();
            sync();
            return value;
        },
        clearSuggestions: () => run(() => search.clearSuggestions()),
        searchLogs: async () => {
            const value = await search.searchLogs();
            sync();
            return value;
        },
        searchFiles: async () => {
            const value = await search.searchFiles();
            sync();
            return value;
        },
        addRecentKeyword: (value) => run(() => search.addRecentKeyword(value)),
        removeRecentKeyword: (value) => run(() => search.removeRecentKeyword(value)),
        clearRecentKeywords: () => run(() => search.clearRecentKeywords()),
        registerShortcut: (handler, shortcut = 'mod+k') => onGlobalKeydown((event) => {
            if (matchesShortcut(event, shortcut)) {
                event.preventDefault();
                handler();
            }
        }),
    };
}
