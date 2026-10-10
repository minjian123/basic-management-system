/** 表格投影：把核心表格组件基类 `BaseTable` 投影为组合式（分页 / 多列排序 / 列配置 / 多选 / 树形 / 密度 / 列表偏好）。 */
import { BaseTable, buildListPrefKey, buildTreeExpandKey, fromColumnPreferences, isListPreferenceOversized, mergeTableColumns, normalizeListPreference, pruneListPreference, toColumnPreferences, trimListPreference, withQuery, withoutQuery, } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
import { useBasePersistedState } from './useBasePersistedState';
/** 具体表格件（可实例化）。 */
class Table extends BaseTable {
}
/** 列声明 → 列种子。 */
function toSeeds(columns) {
    return columns.map((column) => ({ key: column.key, width: column.width, visible: column.visible }));
}
/**
 * 使用表格投影。
 *
 * @param options 选项。
 * @returns 表格基类实例与响应式面。
 */
export function useBaseTable(options = {}) {
    const table = new Table();
    table.setReady(options.ready ?? false);
    const columns = ref(mergeTableColumns(options.columns ?? [], options.columnMeta ?? []));
    if (options.rowKey !== undefined) {
        table.rowKey = options.rowKey;
    }
    if (options.pageSize !== undefined) {
        table.setPageSize(options.pageSize);
    }
    if (options.listDensity !== undefined) {
        table.setListDensity(options.listDensity);
    }
    if (options.tree !== undefined) {
        table.tree = options.tree;
    }
    if (options.childrenKey !== undefined) {
        table.childrenKey = options.childrenKey;
    }
    if (options.editable !== undefined) {
        table.editable = options.editable;
    }
    table.columnConfig.normalizeWith(toSeeds(columns.value));
    // 树形展开态本地记忆（仅客户端，不入服务端列表偏好；《组件设计 · 通用表格》§7）。
    const treeExpandState = useBasePersistedState({
        stateKey: options.treeExpandKey === undefined ? '' : buildTreeExpandKey(options.treeExpandKey),
        storage: 'local',
    });
    if (options.treeExpandThreshold !== undefined) {
        table.setTreeExpandThreshold(options.treeExpandThreshold);
    }
    if (treeExpandState.persisted.stateKey !== '') {
        treeExpandState.restore();
    }
    /** 是否有树形展开态本地记忆。 */
    function hasTreeMemory() {
        return treeExpandState.persisted.stateKey !== '' && treeExpandState.hasLocal.value && Array.isArray(treeExpandState.local.value);
    }
    /** 应用树形展开（有本地记忆用记忆，否则按规模自适应默认）。 */
    function applyTreeExpand() {
        if (hasTreeMemory()) {
            table.setExpandedKeys(treeExpandState.local.value.map((key) => String(key)));
        }
        else {
            table.applyDefaultExpand();
        }
        sync();
    }
    /** 写入树形展开态本地记忆。 */
    function persistTreeExpand() {
        if (treeExpandState.persisted.stateKey === '') {
            return;
        }
        treeExpandState.setLocal([...table.expandedKeys].map((key) => String(key)));
        treeExpandState.persist();
    }
    const preferenceState = useBasePersistedState({
        stateKey: options.formKey === undefined ? '' : buildListPrefKey(options.formKey),
        remoteSaver: options.remoteSaver,
    });
    /** 当前偏好（整份）。 */
    const preference = computed(() => normalizeListPreference(preferenceState.local.value));
    /** 由表状态与既有条件子键组装整份偏好。 */
    const composePreference = () => ({
        columns: toColumnPreferences(table.columnConfig.columns),
        page_size: table.pageSize,
        density: table.listDensity,
        query: preference.value.query,
    });
    /** 写回偏好（裁剪后落本地并防抖保存）。 */
    const commit = (next) => {
        preferenceState.setLocal(trimListPreference(next));
        preferenceState.saveDebounced();
    };
    /** 条件偏好变更后同步偏好。 */
    const commitFromTable = () => {
        commit(composePreference());
    };
    const rows = ref([...table.rows]);
    const total = ref(table.total);
    const page = ref(table.page);
    const pageSize = ref(table.pageSize);
    const sorts = ref([...table.sorts]);
    const listDensity = ref(table.listDensity);
    const editable = ref(table.editable);
    const selectedKeys = ref(table.selectedKeys);
    const summary = ref(table.selection.summary);
    const expandedKeys = ref([...table.expandedKeys].map((key) => String(key)));
    const treeExpandThreshold = ref(table.treeExpandThreshold);
    const columnPreferences = ref(toColumnPreferences(table.columnConfig.columns));
    const revision = ref(0);
    const ready = ref(table.ready);
    const degraded = ref(table.degraded);
    const requestCount = ref(table.requestCount);
    /** 从基类实例同步响应式面（并递增变更序号，供非响应式实例态驱动的重算）。 */
    const sync = () => {
        revision.value += 1;
        ready.value = table.ready;
        degraded.value = table.degraded;
        requestCount.value = table.requestCount;
        rows.value = [...table.rows];
        total.value = table.total;
        page.value = table.page;
        pageSize.value = table.pageSize;
        sorts.value = [...table.sorts];
        listDensity.value = table.listDensity;
        editable.value = table.editable;
        selectedKeys.value = table.selectedKeys;
        summary.value = table.selection.summary;
        expandedKeys.value = [...table.expandedKeys].map((key) => String(key));
        treeExpandThreshold.value = table.treeExpandThreshold;
        columnPreferences.value = toColumnPreferences(table.columnConfig.columns);
    };
    const offTable = table.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    const offSelection = table.selection.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    const offColumns = table.columnConfig.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(() => {
        offTable();
        offSelection();
        offColumns();
    });
    const visibleColumns = computed(() => {
        void revision.value;
        const state = new Map(table.columnConfig.columns.map((column) => [column.key, column]));
        const ordered = [...columns.value]
            .filter((column) => state.get(column.key)?.visible !== false)
            .sort((left, right) => (state.get(left.key)?.order ?? 0) - (state.get(right.key)?.order ?? 0));
        return ordered;
    });
    /** 是否全部可展开节点均已展开（读变更序号以触发重算）。 */
    const isTreeAllExpanded = computed(() => {
        void revision.value;
        return table.isAllExpanded();
    });
    /** 以偏好整份回填表状态（列 / 页长 / 密度）。 */
    const applyPreference = (value) => {
        const pref = normalizeListPreference(value);
        table.columnConfig.setColumns(fromColumnPreferences(pref.columns, columns.value));
        table.setPageSize(pref.page_size);
        table.setListDensity(pref.density);
        preferenceState.setLocal(pref);
        sync();
    };
    if (options.formKey !== undefined && preferenceState.hasLocal.value) {
        applyPreference(preferenceState.local.value);
    }
    return {
        table,
        ready,
        degraded,
        requestCount,
        rows,
        total,
        page,
        pageSize,
        sorts,
        listDensity,
        editable,
        columns,
        visibleColumns,
        selectedKeys,
        summary,
        expandedKeys,
        treeExpandThreshold,
        isTreeAllExpanded,
        columnPreferences,
        preference,
        queryConditions: computed(() => preference.value.query.conditions),
        keyword: computed(() => preference.value.query.keyword ?? ''),
        oversized: computed(() => isListPreferenceOversized(preference.value)),
        revision,
        setReady: (value) => {
            table.setReady(value);
            sync();
        },
        markLoaded: () => {
            table.markLoaded();
            sync();
        },
        setRows: (next, nextTotal) => {
            table.setRows(next, nextTotal);
            if (table.tree) {
                applyTreeExpand();
            }
            sync();
        },
        setPage: (next) => {
            table.setPage(next);
            sync();
        },
        setPageSize: (next) => {
            table.setPageSize(next);
            sync();
            commitFromTable();
        },
        resetToFirstPage: () => {
            table.resetToFirstPage();
            sync();
        },
        toggleSort: (column, additive) => {
            const result = table.toggleSort(column, additive);
            sync();
            return result;
        },
        clearSort: () => {
            table.clearSort();
            sync();
        },
        setListDensity: (density) => {
            table.setListDensity(density);
            sync();
            commitFromTable();
        },
        setVisible: (key, visible) => {
            table.columnConfig.setVisible(key, visible);
            sync();
            commitFromTable();
        },
        moveColumn: (key, offset) => {
            table.columnConfig.moveColumn(key, offset);
            sync();
            commitFromTable();
        },
        setWidth: (key, width) => {
            table.columnConfig.setWidth(key, width);
            sync();
            commitFromTable();
        },
        resetColumns: () => {
            table.columnConfig.resetColumns(toSeeds(columns.value));
            sync();
            commitFromTable();
        },
        normalizeColumns: () => {
            table.columnConfig.normalizeWith(toSeeds(columns.value));
            sync();
            commitFromTable();
        },
        setColumns: (next) => {
            columns.value = mergeTableColumns(next);
            table.columnConfig.normalizeWith(toSeeds(columns.value));
            sync();
        },
        setSorts: (next) => {
            table.sorts.length = 0;
            table.sorts.push(...next.map((item) => ({ ...item })));
            table.sort = table.sorts[0];
            sync();
        },
        toggleSelect: (key) => {
            table.toggleSelect(key);
            sync();
        },
        setRowKeys: (keys) => {
            table.setRowKeys(keys);
            sync();
        },
        selectAllAcrossPages: () => {
            table.selection.selectAllAcrossPages();
            sync();
        },
        clearSelection: () => {
            table.selection.clear();
            sync();
        },
        toggleExpand: (key) => {
            table.toggleExpand(key);
            sync();
        },
        expandAll: () => {
            table.expandAll();
            sync();
        },
        collapseAll: () => {
            table.collapseAll();
            sync();
        },
        setEditable: (value) => {
            table.setEditable(value);
            sync();
        },
        setTreeExpandThreshold: (threshold) => {
            table.setTreeExpandThreshold(threshold);
            sync();
        },
        defaultExpandKeys: () => table.defaultExpandKeys(),
        applyTreeExpand,
        toggleTreeExpandAll: () => {
            const wasAll = table.isAllExpanded();
            if (wasAll) {
                table.collapseAll();
            }
            else {
                table.setExpandedKeys(table.parentKeys());
            }
            persistTreeExpand();
            sync();
            return !wasAll;
        },
        persistTreeExpand,
        applyTreeSearch: (match) => {
            if (match === null) {
                applyTreeExpand();
                return;
            }
            table.expandAncestorsFor(match);
            sync();
        },
        expandAncestorsFor: (match) => {
            table.expandAncestorsFor(match);
            sync();
        },
        setQueryConditions: (conditions, keyword) => {
            commit(withQuery(composePreference(), conditions, keyword));
        },
        clearQuery: () => {
            commit(withoutQuery(composePreference()));
        },
        prunePreference: () => {
            const result = pruneListPreference(preference.value, options.fields ?? [], columns.value);
            commit(result.preference);
            return result.removedConditions;
        },
        applyPreference,
    };
}
