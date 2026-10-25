/** 偏好状态编排投影：全量偏好值 / 默认值与租户策略 / 编辑副本（即时预览）/ 保存与回滚 / 恢复默认。 */

import {
  applyPreferenceDefaults,
  diffPreferences,
  isPreferenceEnabled,
  isPreferenceVisible,
  readPreferenceValue,
  resolvePreferenceDefaults,
  sanitizePreferences,
  writePreferenceValue,
  type PreferenceKey,
  type PreferencePolicyMap,
  type PreferenceValues,
} from '@bms/core'
import { computed, ref, type ComputedRef, type Ref } from 'vue'

import {
  useBasePersistedState,
  type PersistedStorageOption,
  type UseBasePersistedStateResult,
} from './useBasePersistedState'

/** 缺省存储键（本地预读 / 保存一致）。 */
const DEFAULT_STORAGE_KEY = 'bms_preferences'

/** 选项。 */
export interface UsePreferencesOptions {
  /** 平台默认覆盖 / 租户默认值。 */
  defaults?: Partial<PreferenceValues>
  /** 租户策略（不可见 / 不可选项）。 */
  policy?: PreferencePolicyMap
  /** 存储后端（缺省 `local`）。 */
  storage?: PersistedStorageOption
  /** 存储键（缺省 `bms_preferences`）。 */
  storageKey?: string
  /** 远端保存注入点（未注入时保存只写本地并置待同步标记）。 */
  remoteSaver?: (value: unknown) => Promise<void>
}

/** `usePreferences` 返回面。 */
export interface UsePreferencesResult {
  /** 已保存偏好值（响应式）。 */
  values: Ref<PreferenceValues>
  /** 编辑副本（即时预览源，响应式）。 */
  draft: Ref<PreferenceValues>
  /** 默认值（平台默认 ∩ 租户默认，响应式）。 */
  defaults: Ref<PreferenceValues>
  /** 租户策略（响应式）。 */
  policy: Ref<PreferencePolicyMap | undefined>
  /** 是否有未保存变更（响应式）。 */
  dirty: ComputedRef<boolean>
  /** 远端待同步标记（响应式）。 */
  pendingSync: Ref<boolean>
  /** 持久化投影实例。 */
  persisted: UseBasePersistedStateResult['persisted']
  /** 写入单项（不可选项不生效；只改编辑副本，落盘经 `save`）。 */
  setValue: (key: PreferenceKey, value: unknown) => void
  /** 整体替换（宿主下发，同步已保存值与编辑副本）。 */
  replace: (next: Partial<PreferenceValues>) => void
  /** 保存（写本地 + 远端占位）。 */
  save: () => Promise<boolean>
  /** 取消（编辑副本回滚到已保存值）。 */
  cancel: () => void
  /** 恢复默认（跳过不可选项）并保存。 */
  reset: () => Promise<boolean>
  /** 读取扁平键值（编辑副本）。 */
  read: (key: PreferenceKey) => unknown
  /** 项是否可见。 */
  isVisible: (key: PreferenceKey) => boolean
  /** 项是否可选。 */
  isEnabled: (key: PreferenceKey) => boolean
}

/**
 * 复制偏好值（切断嵌套 `notify` 引用）。
 *
 * @param values 偏好值。
 * @returns 副本。
 */
function clonePreferences(values: PreferenceValues): PreferenceValues {
  return { ...values, notify: { ...values.notify } }
}

/**
 * 使用偏好状态编排投影。
 *
 * @param options 选项。
 * @returns 偏好响应式面与操作方法。
 */
export function usePreferences(options: UsePreferencesOptions = {}): UsePreferencesResult {
  const policy = ref<PreferencePolicyMap | undefined>(options.policy)
  const defaults = ref<PreferenceValues>(resolvePreferenceDefaults(options.defaults, options.policy))
  const persisted = useBasePersistedState({
    stateKey: options.storageKey ?? DEFAULT_STORAGE_KEY,
    storage: options.storage ?? 'local',
    remoteSaver: options.remoteSaver,
  })

  const stored = persisted.local.value
  const initial = sanitizePreferences(
    (typeof stored === 'object' && stored !== null ? stored : {}) as Partial<PreferenceValues>,
    defaults.value,
  )
  const values = ref<PreferenceValues>(initial)
  const draft = ref<PreferenceValues>(clonePreferences(initial))
  persisted.snapshot()

  const dirty = computed(() => diffPreferences(values.value, draft.value).length > 0)

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
        return
      }
      draft.value = sanitizePreferences(writePreferenceValue(draft.value, key, value), defaults.value)
    },
    replace: (next) => {
      values.value = sanitizePreferences(next, defaults.value)
      draft.value = clonePreferences(values.value)
    },
    save: async () => {
      values.value = clonePreferences(draft.value)
      persisted.setLocal(values.value)
      return persisted.save()
    },
    cancel: () => {
      draft.value = clonePreferences(values.value)
    },
    reset: async () => {
      const next = applyPreferenceDefaults(draft.value, defaults.value, policy.value)
      values.value = clonePreferences(next)
      draft.value = clonePreferences(next)
      persisted.setLocal(values.value)
      return persisted.save()
    },
    read: (key) => readPreferenceValue(draft.value, key),
    isVisible: (key) => isPreferenceVisible(key, policy.value),
    isEnabled: (key) => isPreferenceEnabled(key, policy.value),
  }
}
