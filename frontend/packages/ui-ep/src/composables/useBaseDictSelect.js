/** 字典选择族投影：把核心选择族组件基类 `BaseDictSelect` 与缓存能力 `BaseDictStore` 投影为组合式（缓存 / 批量合并 / 版本比对 / 回显 / 级联父值）。 */
import { BaseDictSelect, BaseDictStore, bindDictStoreSource, normalizeDictValues, } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
import { localStorageDictChannel } from '../utils/dictStorage';
/** 具体字典选择族（可实例化）。 */
class DictSelectState extends BaseDictSelect {
}
/** 具体字典缓存（可实例化）。 */
class DictStoreState extends BaseDictStore {
}
/**
 * 使用字典选择投影。
 *
 * @param options 选项。
 * @returns 选择族实例与响应式面。
 */
export function useBaseDictSelect(options = {}) {
    const select = new DictSelectState();
    const store = options.store ?? new DictStoreState();
    const localDisabled = ref(options.disabled ?? false);
    // 显式传入 `storage`（含 `undefined`）以调用方为准；未传则用内建 localStorage 通道
    store.setStorage('storage' in options ? options.storage : localStorageDictChannel);
    select.setStore(store);
    if (options.locale !== undefined) {
        store.setLocale(options.locale);
    }
    if (options.ready !== undefined) {
        select.setReady(options.ready);
        store.setReady(options.ready);
    }
    if (options.dictType !== undefined) {
        select.setDictType(options.dictType);
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
    if (options.parentId !== undefined) {
        select.setParent(options.parentId);
    }
    if (options.source !== undefined) {
        select.setSource(options.source);
        bindDictStoreSource(store, options.source);
    }
    if (options.value !== undefined) {
        select.setValue(toBaseValue(options.value, select.multiple));
    }
    const ready = ref(select.ready);
    const degraded = ref(select.degraded);
    const requestCount = ref(select.requestCount);
    const value = ref(select.value);
    const items = ref([...select.items]);
    const selectedValues = ref(select.selectedValues);
    const selectedItems = ref(select.selectedItems);
    const keyword = ref(select.keyword);
    const parentId = ref(select.parentId);
    const loading = ref(select.loadingItems);
    const errorCode = ref(select.errorCode);
    const errorMessage = ref(select.errorMessage);
    const limitExceeded = ref(select.limitExceeded);
    const isLarge = ref(select.isLarge);
    /** 同步核心实例状态到响应式面。 */
    function sync() {
        ready.value = select.ready;
        degraded.value = select.degraded;
        requestCount.value = select.requestCount;
        value.value = select.value;
        items.value = [...select.items];
        selectedValues.value = select.selectedValues;
        selectedItems.value = select.selectedItems;
        keyword.value = select.keyword;
        parentId.value = select.parentId;
        loading.value = select.loadingItems;
        errorCode.value = select.errorCode;
        errorMessage.value = select.errorMessage;
        limitExceeded.value = select.limitExceeded;
        isLarge.value = select.isLarge;
    }
    const off = select.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    const offValue = select.onChange(() => sync());
    const offStore = store.onLifecycle((event) => {
        if (event === 'update') {
            select.syncStore();
            sync();
        }
    });
    onScopeDispose(() => {
        off();
        offValue();
        offStore();
        select.dispose();
        store.dispose();
    });
    const disabled = computed(() => localDisabled.value || !ready.value);
    const error = computed(() => errorCode.value !== undefined);
    const errorText = computed(() => errorMessage.value);
    const empty = computed(() => !loading.value && errorCode.value === undefined && items.value.length === 0);
    const limitText = computed(() => select.limitText());
    const api = {
        select,
        store,
        ready,
        degraded,
        disabled,
        requestCount,
        value,
        items,
        selectedValues,
        selectedItems,
        keyword,
        parentId,
        isLarge,
        loading,
        error,
        errorCode,
        errorMessage,
        errorText,
        empty,
        limitExceeded,
        limitText,
        setReady: (next) => {
            select.setReady(next);
            store.setReady(next);
        },
        setSource: (next) => {
            select.setSource(next);
            bindDictStoreSource(store, next);
        },
        setDictType: (next) => select.setDictType(next),
        setKeyword: (next) => select.setKeyword(next),
        setParent: (next) => select.setParent(next),
        setMultiple: (next) => select.setMultiple(next),
        setLimit: (next) => select.setLimit(next),
        setLimitExceeded: (next) => select.setLimitExceeded(next),
        setValue: (next) => select.setValue(toBaseValue(next, select.multiple)),
        syncValue: (next) => {
            select.setValue(toBaseValue(next, select.multiple));
            sync();
            if (select.selectedValues.length > 0) {
                void select.resolve();
            }
        },
        toggle: (next) => select.toggle(next),
        remove: (next) => select.remove(next),
        clearSelection: () => select.clearSelection(),
        load: () => select.load(),
        searchRemote: (next) => select.searchRemote(next),
        resolve: (extra) => select.resolve(extra),
        invalidate: () => select.invalidate(),
        labelOf: (next) => select.labelOf(next),
        selectionText: () => select.selectionText(),
        getLabel: (next) => select.getLabel(next),
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
    const values = normalizeDictValues(value, multiple);
    if (values.length === 0) {
        return undefined;
    }
    return Array.isArray(value) ? values : values[0];
}
