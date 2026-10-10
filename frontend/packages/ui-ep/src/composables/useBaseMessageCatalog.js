/** 文案目录投影：把核心编排能力基类 `BaseMessageCatalog` 投影为组合式（清单 / 网格 / 筛选 / 保存 / 缓存失效）。 */
import { BaseMessageCatalog, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体文案目录件（可实例化）。 */
class MessageCatalogState extends BaseMessageCatalog {
}
/**
 * 使用文案目录投影。
 *
 * @param options 选项。
 * @returns 文案目录基类实例与响应式面。
 */
export function useBaseMessageCatalog(options = {}) {
    const catalog = new MessageCatalogState();
    if (options.biz !== undefined) {
        catalog.biz = options.biz;
    }
    if (options.bizName !== undefined) {
        catalog.bizName = options.bizName;
    }
    if (options.defaultLocale !== undefined) {
        catalog.defaultLocale = options.defaultLocale;
    }
    if (options.page !== undefined) {
        catalog.page = Math.max(1, options.page);
    }
    if (options.pageSize !== undefined) {
        catalog.pageSize = Math.max(1, options.pageSize);
    }
    if (options.filter !== undefined) {
        catalog.filter = { ...catalog.filter, ...options.filter };
    }
    if (options.virtualThreshold !== undefined) {
        catalog.virtualThreshold = options.virtualThreshold;
    }
    if (options.locale !== undefined) {
        catalog.localeContext = markRaw(toRaw(options.locale));
    }
    if (options.jobs !== undefined) {
        catalog.jobs = options.jobs;
    }
    if (options.access !== undefined) {
        catalog.access = markRaw(toRaw(options.access));
    }
    if (options.notice !== undefined) {
        catalog.notice = markRaw(toRaw(options.notice));
    }
    catalog.setShowDisabledLocales(options.showDisabledLocales ?? false);
    if (options.activeLocale !== undefined && options.activeLocale !== '') {
        catalog.setActiveLocale(options.activeLocale);
    }
    else {
        catalog.activeLocale = '';
    }
    catalog.setReady(options.ready ?? false);
    const ready = ref(catalog.ready);
    const degraded = ref(catalog.degraded);
    const busy = ref(catalog.busy);
    const phase = ref(catalog.phase);
    const dirty = ref(catalog.dirty);
    const locales = ref(catalog.locales);
    const columns = ref(catalog.columns);
    const messages = ref(catalog.messages);
    const visibleMessages = ref(catalog.visibleMessages);
    const modifiedKeys = ref(catalog.modifiedKeys);
    const missingCodes = ref(catalog.missingCodes);
    const total = ref(catalog.total);
    const page = ref(catalog.page);
    const pageCount = ref(catalog.pageCount);
    const pageSize = ref(catalog.pageSize);
    const filter = ref({ ...catalog.filter });
    const activeLocale = ref(catalog.activeLocale);
    const showDisabledLocales = ref(catalog.showDisabledLocales);
    const virtualized = ref(catalog.virtualized);
    const idempotencyKey = ref(catalog.idempotencyKey);
    const canSave = ref(catalog.canSave);
    const errorMessage = ref(catalog.errorMessage);
    const errorCode = ref(catalog.errorCode);
    const messagesRevision = ref(catalog.messagesRevision);
    const exportParams = ref(catalog.exportParams);
    /** 从基类实例同步响应式面（集合一律重建，核心集合非响应式）。 */
    const sync = () => {
        ready.value = catalog.ready;
        degraded.value = catalog.degraded;
        busy.value = catalog.busy;
        phase.value = catalog.phase;
        dirty.value = catalog.dirty;
        locales.value = catalog.locales.map((item) => ({ ...item }));
        columns.value = catalog.columns.map((item) => ({ ...item }));
        messages.value = catalog.messages.map((row) => ({
            key: row.key,
            values: { ...row.values },
            missing: [...row.missing],
        }));
        visibleMessages.value = catalog.visibleMessages.map((row) => ({
            key: row.key,
            values: { ...row.values },
            missing: [...row.missing],
        }));
        modifiedKeys.value = catalog.modifiedKeys;
        missingCodes.value = catalog.missingCodes;
        total.value = catalog.total;
        page.value = catalog.page;
        pageCount.value = catalog.pageCount;
        pageSize.value = catalog.pageSize;
        filter.value = { ...catalog.filter };
        activeLocale.value = catalog.activeLocale;
        showDisabledLocales.value = catalog.showDisabledLocales;
        virtualized.value = catalog.virtualized;
        idempotencyKey.value = catalog.idempotencyKey;
        canSave.value = catalog.canSave;
        errorMessage.value = catalog.errorMessage;
        errorCode.value = catalog.errorCode;
        messagesRevision.value = catalog.messagesRevision;
        exportParams.value = catalog.exportParams;
    };
    const off = catalog.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        catalog,
        ready,
        degraded,
        busy,
        phase,
        dirty,
        locales,
        columns,
        messages,
        visibleMessages,
        modifiedKeys,
        missingCodes,
        total,
        page,
        pageCount,
        pageSize,
        filter,
        activeLocale,
        showDisabledLocales,
        virtualized,
        idempotencyKey,
        canSave,
        errorMessage,
        errorCode,
        messagesRevision,
        exportParams,
        setReady: (value) => {
            catalog.setReady(value);
            sync();
        },
        setJobs: (jobs) => {
            catalog.setJobs(jobs);
            sync();
        },
        setFilter: (value) => {
            catalog.setFilter(value);
            sync();
        },
        setActiveLocale: (code) => {
            catalog.setActiveLocale(code);
            sync();
        },
        setShowDisabledLocales: (value) => {
            catalog.setShowDisabledLocales(value);
            sync();
        },
        setVirtualThreshold: (value) => {
            catalog.setVirtualThreshold(value);
            sync();
        },
        setPage: (value) => {
            catalog.setPage(value);
            sync();
        },
        setPageSize: (value) => {
            catalog.setPageSize(value);
            sync();
        },
        load: async () => {
            const value = await catalog.load();
            sync();
            return value;
        },
        reload: async () => {
            const value = await catalog.reload();
            sync();
            return value;
        },
        editCell: (input) => {
            const value = catalog.editCell(input);
            sync();
            return value;
        },
        addKey: (input) => {
            const value = catalog.addKey(input);
            sync();
            return value;
        },
        removeKey: (key) => {
            const value = catalog.removeKey(key);
            sync();
            return value;
        },
        addLocale: (input) => {
            const value = catalog.addLocale(input);
            sync();
            return value;
        },
        updateLocale: (code, patch) => {
            const value = catalog.updateLocale(code, patch);
            sync();
            return value;
        },
        toggleLocale: (code, enabled) => {
            const value = catalog.toggleLocale(code, enabled);
            sync();
            return value;
        },
        removeLocale: (code) => {
            const value = catalog.removeLocale(code);
            sync();
            return value;
        },
        save: async () => {
            const value = await catalog.save();
            sync();
            return value;
        },
        retry: async () => {
            const value = await catalog.retry();
            sync();
            return value;
        },
        invalidateCache: async () => {
            const value = await catalog.invalidateCache();
            sync();
            return value;
        },
        reloadMessages: async () => {
            const value = await catalog.reloadMessages();
            sync();
            return value;
        },
        resetDirty: () => {
            catalog.resetDirty();
            sync();
        },
        reset: () => {
            catalog.reset();
            sync();
        },
        isAllowed: (perm) => catalog.isAllowed(perm),
    };
}
