/** 偏好状态编排投影：全量偏好值 / 默认值与租户策略 / 编辑副本（即时预览）/ 保存与回滚 / 恢复默认。 */
import { applyPreferenceDefaults, diffPreferences, isPreferenceEnabled, isPreferenceVisible, readPreferenceValue, resolvePreferenceDefaults, sanitizePreferences, writePreferenceValue, } from '@bms/core';
import { computed, ref } from 'vue';
import { useBasePersistedState, } from './useBasePersistedState';
/** 缺省存储键（本地预读 / 保存一致）。 */
const DEFAULT_STORAGE_KEY = 'bms_preferences';
/**
 * 复制偏好值（切断嵌套 `notify` 引用）。
 *
 * @param values 偏好值。
 * @returns 副本。
 */
function clonePreferences(values) {
    return { ...values, notify: { ...values.notify } };
}
/**
 * 使用偏好状态编排投影。
 *
 * @param options 选项。
 * @returns 偏好响应式面与操作方法。
 */
export function usePreferences(options = {}) {
    const policy = ref(options.policy);
    const defaults = ref(resolvePreferenceDefaults(options.defaults, options.policy));
    const persisted = useBasePersistedState({
        stateKey: options.storageKey ?? DEFAULT_STORAGE_KEY,
        storage: options.storage ?? 'local',
        remoteSaver: options.remoteSaver,
    });
    const stored = persisted.local.value;
    const initial = sanitizePreferences((typeof stored === 'object' && stored !== null ? stored : {}), defaults.value);
    const values = ref(initial);
    const draft = ref(clonePreferences(initial));
    persisted.snapshot();
    const dirty = computed(() => diffPreferences(values.value, draft.value).length > 0);
    return {
        values,
        draft,
        defaults,
        policy,
        dirty,
        pendingSync: persisted.pendingSync,
        persisted: persisted.persisted,
        setValue: (key, value) => {
            if (!isPreferenceEnabled(key, policy.value)) {
                return;
            }
            draft.value = sanitizePreferences(writePreferenceValue(draft.value, key, value), defaults.value);
        },
        replace: (next) => {
            values.value = sanitizePreferences(next, defaults.value);
            draft.value = clonePreferences(values.value);
        },
        save: async () => {
            values.value = clonePreferences(draft.value);
            persisted.setLocal(values.value);
            return persisted.save();
        },
        cancel: () => {
            draft.value = clonePreferences(values.value);
        },
        reset: async () => {
            const next = applyPreferenceDefaults(draft.value, defaults.value, policy.value);
            values.value = clonePreferences(next);
            draft.value = clonePreferences(next);
            persisted.setLocal(values.value);
            return persisted.save();
        },
        read: (key) => readPreferenceValue(draft.value, key),
        isVisible: (key) => isPreferenceVisible(key, policy.value),
        isEnabled: (key) => isPreferenceEnabled(key, policy.value),
    };
}
