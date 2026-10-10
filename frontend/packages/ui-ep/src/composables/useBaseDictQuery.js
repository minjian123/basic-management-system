/** 字典高级查询投影：把核心高级查询编排基类 `BaseDictQuery` 投影为组合式（元数据 / 条件 / 执行 / 方案）。 */
import { BaseDictQuery, } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
/** 具体高级查询编排（可实例化）。 */
class DictQueryState extends BaseDictQuery {
}
/**
 * 使用字典高级查询投影。
 *
 * @param options 选项。
 * @returns 编排实例与响应式面。
 */
export function useBaseDictQuery(options = {}) {
    const query = new DictQueryState();
    if (options.ready !== undefined) {
        query.setReady(options.ready);
    }
    if (options.dictType !== undefined) {
        query.setDictType(options.dictType);
    }
    if (options.target !== undefined) {
        query.setTarget(options.target);
    }
    if (options.pageSize !== undefined) {
        query.setPageSize(options.pageSize);
    }
    if (options.source !== undefined) {
        query.setSource(options.source);
    }
    const ready = ref(query.ready);
    const degraded = ref(query.degraded);
    const requestCount = ref(query.requestCount);
    const dictType = ref(query.dictType);
    const target = ref(query.target);
    const attrs = ref([...query.attrs]);
    const providers = ref([...query.providers]);
    const conditions = ref(query.conditions);
    const providerKey = ref(query.providerKey);
    const providerParams = ref({ ...query.providerParams });
    const schemes = ref([...query.schemes]);
    const results = ref([...query.results]);
    const rows = ref([...query.rows]);
    const total = ref(query.total);
    const page = ref(query.page);
    const pageSize = ref(query.pageSize);
    const loading = ref(query.loading);
    const errorCode = ref(query.errorCode);
    const errorMessage = ref(query.errorMessage);
    /** 同步核心实例状态到响应式面。 */
    function sync() {
        ready.value = query.ready;
        degraded.value = query.degraded;
        requestCount.value = query.requestCount;
        dictType.value = query.dictType;
        target.value = query.target;
        attrs.value = [...query.attrs];
        providers.value = [...query.providers];
        conditions.value = query.conditions;
        providerKey.value = query.providerKey;
        providerParams.value = { ...query.providerParams };
        schemes.value = [...query.schemes];
        results.value = [...query.results];
        rows.value = [...query.rows];
        total.value = query.total;
        page.value = query.page;
        pageSize.value = query.pageSize;
        loading.value = query.loading;
        errorCode.value = query.errorCode;
        errorMessage.value = query.errorMessage;
    }
    const off = query.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(() => {
        off();
        query.dispose();
    });
    const error = computed(() => errorCode.value !== undefined);
    const errorText = computed(() => errorMessage.value);
    const empty = computed(() => !loading.value && errorCode.value === undefined && results.value.length === 0 && rows.value.length === 0);
    const metaLoaded = computed(() => attrs.value.length > 0 || providers.value.length > 0);
    const fieldOptions = computed(() => query.fieldOptions);
    return {
        query,
        ready,
        degraded,
        requestCount,
        dictType,
        target,
        attrs,
        providers,
        conditions,
        providerKey,
        providerParams,
        schemes,
        results,
        rows,
        total,
        page,
        pageSize,
        loading,
        error,
        errorText,
        empty,
        metaLoaded,
        fieldOptions,
        setSource: (next) => {
            query.setSource(next);
            sync();
        },
        setReady: (next) => {
            query.setReady(next);
            sync();
        },
        setDictType: (next) => {
            query.setDictType(next);
            sync();
        },
        setTarget: (next) => {
            query.setTarget(next);
            sync();
        },
        setConditions: (next) => {
            query.setConditions(next);
            sync();
        },
        setProvider: (key, params) => {
            query.setProvider(key, params);
            sync();
        },
        setPage: (next) => {
            query.setPage(next);
            sync();
        },
        setPageSize: (next) => {
            query.setPageSize(next);
            sync();
        },
        loadMeta: async () => {
            await query.loadMeta();
            sync();
        },
        run: async () => {
            await query.run();
            sync();
        },
        reset: () => {
            query.reset();
            sync();
        },
        loadSchemes: async () => {
            await query.loadSchemes();
            sync();
        },
        resolveDefaultScheme: async () => {
            await query.resolveDefaultScheme();
            sync();
        },
        applyScheme: (scheme) => {
            query.applyScheme(scheme);
            sync();
        },
        saveScheme: async (name, scope, shared) => {
            await query.saveScheme(name, scope, shared ?? false);
            sync();
        },
        deleteScheme: async (schemeId) => {
            await query.deleteScheme(schemeId);
            sync();
        },
        toBusinessFilter: () => query.toBusinessFilter(),
        selectedValues: () => query.selectedValues(),
        invalidate: () => {
            query.invalidate();
            sync();
        },
    };
}
