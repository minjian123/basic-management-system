/** 组织选择投影：把核心组织选择族组件基类 `BaseOrgSelect` 投影为组合式（远程搜索 / 批量回显 / 缓存 / 多选与上限 / 部门树）。 */
import { BaseOrgSelect, BaseUserDisplay, ORG_EMPTY_VALUE, normalizeOrgIds, orgLimitText, orgSelectionText, } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
/** 具体组织选择族（可实例化）。 */
class OrgSelectState extends BaseOrgSelect {
}
/** 具体用户展示（内建花名册通道）。 */
class UserDisplayState extends BaseUserDisplay {
}
/**
 * 使用组织选择投影。
 *
 * @param options 选项。
 * @returns 组织选择族实例与响应式面。
 */
export function useBaseOrgSelect(options = {}) {
    const select = new OrgSelectState();
    const userDisplay = options.userDisplay ?? new UserDisplayState();
    const localDisabled = ref(options.disabled ?? false);
    select.setUserDisplay(userDisplay);
    if (options.ready !== undefined) {
        select.setReady(options.ready);
    }
    if (options.kind !== undefined) {
        select.setKind(options.kind);
    }
    if (options.multiple !== undefined) {
        select.setMultiple(options.multiple);
    }
    if (options.limit !== undefined) {
        select.setLimit(options.limit);
    }
    if (options.keyword !== undefined) {
        select.setKeyword(options.keyword);
    }
    if (options.deptId !== undefined || options.includeChildren !== undefined) {
        select.setDeptFilter(options.deptId ?? '', options.includeChildren ?? false);
    }
    if (options.status !== undefined) {
        select.setStatus(options.status);
    }
    if (options.source !== undefined) {
        select.setSource(options.source);
    }
    if (options.value !== undefined) {
        select.setValue(toBaseValue(options.value, select.multiple));
    }
    const ready = ref(select.ready);
    const degraded = ref(select.degraded);
    const requestCount = ref(select.requestCount);
    const value = ref(select.value);
    const items = ref([...select.items]);
    const deptNodes = ref([...select.deptNodes]);
    const keyword = ref(select.keyword);
    const loading = ref(select.loading);
    const errorCode = ref(select.errorCode);
    const errorMessage = ref(select.errorMessage);
    const limitExceeded = ref(select.limitExceeded);
    const limit = ref(select.limit);
    const page = ref(select.page);
    const total = ref(select.total);
    const kind = ref(select.kind);
    const multiple = ref(select.multiple);
    const status = ref(select.status);
    const deptId = ref(select.deptId);
    const includeChildren = ref(select.includeChildren);
    const selectedIds = ref(select.selectedIds);
    const selectedItems = ref(select.selectedItems);
    /** 同步核心实例状态到响应式面。 */
    function sync() {
        ready.value = select.ready;
        degraded.value = select.degraded;
        requestCount.value = select.requestCount;
        value.value = select.value;
        items.value = [...select.items];
        deptNodes.value = [...select.deptNodes];
        keyword.value = select.keyword;
        loading.value = select.loading;
        errorCode.value = select.errorCode;
        errorMessage.value = select.errorMessage;
        limitExceeded.value = select.limitExceeded;
        limit.value = select.limit;
        page.value = select.page;
        total.value = select.total;
        kind.value = select.kind;
        multiple.value = select.multiple;
        status.value = select.status;
        deptId.value = select.deptId;
        includeChildren.value = select.includeChildren;
        selectedIds.value = select.selectedIds;
        selectedItems.value = select.selectedItems;
    }
    const off = select.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    const offValue = select.onChange(() => sync());
    onScopeDispose(() => {
        off();
        offValue();
        select.dispose();
    });
    const disabled = computed(() => localDisabled.value || !ready.value);
    const error = computed(() => errorCode.value !== undefined);
    const errorText = computed(() => errorMessage.value);
    const empty = computed(() => !loading.value && errorCode.value === undefined && items.value.length === 0);
    const selectionText = computed(() => selectedItems.value.length === 0 ? ORG_EMPTY_VALUE : orgSelectionText(selectedItems.value));
    const limitText = computed(() => orgLimitText(kind.value, limit.value));
    const api = {
        select,
        userDisplay,
        ready,
        degraded,
        disabled,
        requestCount,
        value,
        items,
        deptNodes,
        keyword,
        loading,
        error,
        errorCode,
        errorMessage,
        errorText,
        empty,
        limitExceeded,
        limit,
        page,
        total,
        kind,
        multiple,
        status,
        deptId,
        includeChildren,
        selectedIds,
        selectedItems,
        selectionText,
        limitText,
        setReady: (next) => select.setReady(next),
        setSource: (next) => select.setSource(next),
        setUserDisplay: (next) => select.setUserDisplay(next),
        setKind: (next) => select.setKind(next),
        setKeyword: (next) => select.setKeyword(next),
        setDeptFilter: (next, children) => select.setDeptFilter(next, children),
        setStatus: (next) => select.setStatus(next),
        setMultiple: (next) => {
            select.setMultiple(next);
            sync();
        },
        setLimit: (next) => select.setLimit(next),
        setPage: (next) => select.setPage(next),
        setLimitExceeded: (value) => select.setLimitExceeded(value),
        setValue: (next) => select.setValue(toBaseValue(next, select.multiple)),
        syncValue: (next) => {
            select.setValue(toBaseValue(next, select.multiple));
            sync();
            if (select.selectedIds.length > 0) {
                void select.resolve();
            }
        },
        toggle: (id) => select.toggle(id),
        remove: (id) => select.remove(id),
        clearSelection: () => select.clearSelection(),
        load: () => select.load(),
        resolve: (ids) => select.resolve(ids),
        loadDeptTree: () => select.loadDeptTree(),
        invalidate: (target) => select.invalidate(target),
        labelOf: (id) => select.labelOf(id),
        tagSummary: (maxVisible) => select.tagSummary(maxVisible),
        onValueChange: (listener) => select.onChange(listener),
    };
    return api;
}
/**
 * 字段值归一为核心值（保留入参形状：数组 → 数组，单值 → 单值；空值 `undefined`）。
 *
 * @param value 字段值。
 * @param multiple 是否多选（多选时空数组归一为 `undefined`）。
 * @returns 核心值。
 */
function toBaseValue(value, multiple) {
    const ids = normalizeOrgIds(value, multiple);
    if (ids.length === 0) {
        return undefined;
    }
    return Array.isArray(value) ? ids : ids[0];
}
