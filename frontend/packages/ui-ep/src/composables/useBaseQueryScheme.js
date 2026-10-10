/** 查询方案投影：把核心查询方案组件基类 `BaseQueryScheme` 投影为组合式（条件 / 方案 CRUD / 摘要 / 查询参数）。 */
import { BaseQueryScheme, buildQueryParams, resolveDefaultScheme, summarizeConditions, } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
/** 具体查询方案件（可实例化）。 */
class Scheme extends BaseQueryScheme {
}
/**
 * 使用查询方案投影。
 *
 * @param options 选项。
 * @returns 查询方案基类实例与响应式面。
 */
export function useBaseQueryScheme(options = {}) {
    const scheme = new Scheme();
    if (options.defaults !== undefined) {
        scheme.setDefaults(options.defaults);
    }
    if (options.conditions !== undefined) {
        scheme.setConditions(options.conditions);
    }
    if (options.keyword !== undefined) {
        scheme.setKeyword(options.keyword);
    }
    if (options.schemes !== undefined) {
        scheme.setSchemes(options.schemes);
    }
    const conditions = ref(scheme.conditions.map((item) => ({ ...item })));
    const keyword = ref(scheme.keyword);
    const schemes = ref([]);
    const activeScheme = ref(scheme.activeScheme);
    /** 方案内态 → 契约形态。 */
    const entries = () => scheme.schemes.map((item) => ({
        id: item.id,
        name: item.name,
        scope: item.scope ?? 'user',
        target: 'business',
        conditions: item.conditions.map((condition) => ({ ...condition })),
        isDefault: item.isDefault === true,
        shared: item.shared === true,
        ownerId: item.ownerId,
    }));
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        conditions.value = scheme.conditions.map((item) => ({ ...item }));
        keyword.value = scheme.keyword;
        schemes.value = entries();
        activeScheme.value = scheme.activeScheme;
    };
    const off = scheme.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    sync();
    return {
        scheme,
        conditions,
        keyword,
        schemes,
        activeScheme,
        defaultSchemeName: computed(() => resolveDefaultScheme(schemes.value)?.name),
        summaries: computed(() => summarizeConditions(conditions.value, options.fields ?? [])),
        queryParams: computed(() => buildQueryParams(conditions.value, keyword.value)),
        setConditions: (next) => {
            scheme.setConditions(next);
            sync();
        },
        setKeyword: (value) => {
            scheme.setKeyword(value);
            sync();
        },
        resetConditions: () => {
            scheme.resetConditions();
            sync();
        },
        setDefaults: (next) => {
            scheme.setDefaults(next);
            sync();
        },
        prune: () => {
            const removed = scheme.prune(options.fields ?? []);
            sync();
            return removed;
        },
        saveScheme: (name, scope, isDefault) => {
            scheme.saveScheme({
                name,
                scope,
                conditions: scheme.conditions.map((item) => ({ ...item })),
                isDefault,
            });
            scheme.activeScheme = name;
            sync();
        },
        applyScheme: (name) => {
            const applied = scheme.applyScheme(name);
            sync();
            return applied;
        },
        removeScheme: (name) => {
            const removed = scheme.removeScheme(name);
            sync();
            return removed;
        },
        renameScheme: (oldName, newName) => {
            const renamed = scheme.renameScheme(oldName, newName);
            sync();
            return renamed;
        },
        setDefaultScheme: (name) => {
            scheme.setDefaultScheme(name);
            sync();
        },
        setSchemes: (next) => {
            scheme.setSchemes(next);
            sync();
        },
    };
}
