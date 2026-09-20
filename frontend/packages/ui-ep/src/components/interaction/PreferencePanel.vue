<script setup lang="ts">
// 偏好面板壳：抽屉（宽屏）/ 弹窗（窄屏）+ 分组偏好项 + 即时预览 + 保存 / 取消 / 恢复默认（二次确认）+ 租户策略受控。
import type { PreferenceKey, PreferencePolicyMap, PreferenceValues } from '@bms/core'
import {
  ElButton,
  ElCheckbox,
  ElDialog,
  ElDrawer,
  ElOption,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElSwitch,
} from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseDesignToken } from '../../composables/useBaseDesignToken'
import { useBaseLocale } from '../../composables/useBaseLocale'
import { useConfirm } from '../../composables/useConfirm'
import { usePreferences } from '../../composables/usePreferences'
import { useResponsive } from '../../composables/useResponsive'
import { resolvePreferenceGroups, type PreferenceGroupDef, type PreferenceItem } from '../../utils/preferenceItems'
import { prefersDark } from '../../utils/media'
import PreferenceGroup from './PreferenceGroup.vue'

interface Props {
  /** 显隐（`v-model`）。 */
  modelValue: boolean
  /** 当前偏好值（`v-model:values`）。 */
  values?: Partial<PreferenceValues>
  /** 平台默认覆盖 / 租户默认值。 */
  defaults?: Partial<PreferenceValues>
  /** 租户策略（不可见 / 不可选项）。 */
  policy?: PreferencePolicyMap
  /** 分组与项定义（缺省内置全量分组）。 */
  items?: PreferenceGroupDef[]
  /** 分组裁剪（分组键清单，缺省全部）。 */
  groups?: string[]
  /** 面板标题（缺省「偏好设置」）。 */
  title?: string
  /** 远端保存注入点（未注入时保存只写本地并置待同步标记）。 */
  remoteSaver?: (value: unknown) => Promise<void>
  /** 本地存储键（缺省 `bms_preferences`）。 */
  storageKey?: string
}

const props = withDefaults(defineProps<Props>(), {
  values: undefined,
  defaults: undefined,
  policy: undefined,
  items: undefined,
  groups: undefined,
  title: '偏好设置',
  remoteSaver: undefined,
  storageKey: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:values': [value: PreferenceValues]
  change: [payload: { key: PreferenceKey; value: unknown; values: PreferenceValues }]
  save: [value: PreferenceValues]
  reset: [value: PreferenceValues]
  cancel: []
  'sync-pending': []
}>()

/** 抽屉宽度。 */
const DRAWER_SIZE = '380px'
/** 弹窗宽度。 */
const DIALOG_WIDTH = '420px'

const { isNarrow } = useResponsive()
const { confirm } = useConfirm()
const designToken = useBaseDesignToken()
const localeContext = useBaseLocale()

const { values, draft, pendingSync, persisted, setValue, replace, save, cancel, reset, read, isVisible, isEnabled } =
  usePreferences({
    defaults: props.defaults,
    policy: props.policy,
    remoteSaver: props.remoteSaver,
    storageKey: props.storageKey,
  })

/** 生效分组。 */
const resolvedGroups = computed(() => props.items ?? resolvePreferenceGroups(props.groups))

/** 面板壳组件（宽屏抽屉 / 窄屏弹窗）。 */
const shellComponent = computed(() => (isNarrow.value ? ElDialog : ElDrawer))

/** 显隐（受控双向绑定）。 */
const panelVisible = computed(() => props.modelValue)

/** 控制台根元素（不可用时跳过预览写入）。 */
const rootElement = typeof document === 'undefined' ? undefined : document.documentElement

/**
 * 解析跟随系统的生效主题。
 *
 * @returns 生效主题（`matchMedia` 不可用时回退亮色）。
 */
function resolveSystemTheme(): 'light' | 'dark' {
  return prefersDark() ? 'dark' : 'light'
}

/**
 * 即时预览：写根元素令牌属性 + 同步设计令牌 / 语言上下文投影。
 *
 * @param next 待预览偏好值。
 */
function applyPreview(next: PreferenceValues): void {
  if (rootElement !== undefined) {
    rootElement.dataset.theme = next.themeMode === 'system' ? resolveSystemTheme() : next.themeMode
    rootElement.dataset.density = next.listDensity === 'comfortable' ? 'default' : next.listDensity
    rootElement.lang = next.locale
  }
  designToken.setTheme(next.themeMode)
  localeContext.setLocale(next.locale)
  localeContext.setTimezone(next.timezone)
}

/**
 * 面板壳显隐回写。
 *
 * @param value 目标显隐。
 */
function onShellUpdate(value: boolean): void {
  if (value) {
    return
  }
  emit('update:modelValue', false)
}

/** 面板壳属性（抽屉 / 弹窗差异项）。 */
const shellProps = computed<Record<string, unknown>>(() => ({
  modelValue: panelVisible.value,
  'onUpdate:modelValue': onShellUpdate,
  title: props.title,
  appendToBody: true,
  ...(isNarrow.value ? { width: DIALOG_WIDTH } : { size: DRAWER_SIZE, direction: 'rtl' }),
}))

/** 打开面板：同步外部偏好值、记录快照并应用即时预览。 */
function onOpen(): void {
  replace(props.values ?? {})
  persisted.snapshot()
  applyPreview(draft.value)
}

/** 关闭面板。 */
function close(): void {
  emit('update:modelValue', false)
}

/** 写入单项并广播变更（不可选项不生效）。 */
function onItemChange(key: PreferenceKey, value: unknown): void {
  if (!isEnabled(key)) {
    return
  }
  setValue(key, value)
  emit('change', { key, value, values: draft.value })
}

/**
 * 生成单项写入回调（供 `item-<key>` 插槽透传）。
 *
 * @param key 偏好项键。
 * @returns 写入回调。
 */
function itemSetter(key: PreferenceKey): (value: unknown) => void {
  return (value) => onItemChange(key, value)
}

/** 保存：写本地 + 远端占位；未同步成功时广播待同步。 */
async function onSave(): Promise<void> {
  const synced = await save()
  emit('update:values', values.value)
  emit('save', values.value)
  if (!synced) {
    emit('sync-pending')
  }
  close()
}

/** 取消：编辑副本回滚到已保存值并撤销预览。 */
function onCancel(): void {
  cancel()
  applyPreview(draft.value)
  emit('cancel')
  close()
}

/** 恢复默认：二次确认后取平台默认 ∩ 租户默认（跳过不可选项）并保存。 */
async function onRestoreDefaults(): Promise<void> {
  const confirmed = await confirm({ content: '恢复默认偏好设置？未保存的修改将一并重置。', confirmText: '恢复默认' })
  if (!confirmed) {
    return
  }
  const synced = await reset()
  applyPreview(draft.value)
  emit('update:values', values.value)
  emit('reset', values.value)
  if (!synced) {
    emit('sync-pending')
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      onOpen()
    }
  },
  { immediate: true },
)
watch(
  () => props.values,
  (next) => {
    if (next !== undefined && !props.modelValue) {
      replace(next)
    }
  },
)
watch(draft, (next) => applyPreview(next))

defineExpose({
  open: () => emit('update:modelValue', true),
  close,
  save: onSave,
  cancel: onCancel,
  restoreDefaults: onRestoreDefaults,
  setValue: onItemChange,
  read,
})

/** 分组内可见项（受租户策略过滤）。 */
function visibleItems(group: PreferenceGroupDef): PreferenceItem[] {
  return group.items.filter((item) => isVisible(item.key))
}

/** 控件值（EP 控件仅接受基本类型，收窄后绑定）。 */
export type PreferenceControlValue = string | number | boolean | undefined

/**
 * 读取单项控件值（收窄为控件可接受类型）。
 *
 * @param key 偏好项键。
 * @returns 控件值。
 */
function controlValue(key: PreferenceKey): PreferenceControlValue {
  const value = read(key)
  return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? value : undefined
}
</script>

<template>
  <component :is="shellComponent" v-bind="shellProps">
    <div class="bms-preference-panel" data-test="preference-panel">
      <p v-if="pendingSync" class="bms-preference-panel__pending" data-test="preference-sync-pending">
        偏好已保存在本地，尚未同步到服务端
      </p>
      <preference-group
        v-for="group in resolvedGroups"
        :key="group.key"
        :title="group.title"
        :description="group.description"
        :collapsible="isNarrow"
      >
        <div
          v-for="item in visibleItems(group)"
          :key="item.key"
          class="bms-preference-panel__item"
          :data-test="`preference-item-${item.key}`"
        >
          <span class="bms-preference-panel__label">{{ item.label }}</span>
          <div class="bms-preference-panel__control" :data-block="item.block ? 'true' : 'false'">
            <slot
              :name="`item-${item.key}`"
              :item="item"
              :value="controlValue(item.key)"
              :disabled="!isEnabled(item.key)"
              :set-value="itemSetter(item.key)"
            >
              <el-radio-group
                v-if="item.control === 'radio'"
                :data-test="`preference-input-${item.key}`"
                :model-value="controlValue(item.key)"
                :disabled="!isEnabled(item.key)"
                @update:model-value="onItemChange(item.key, $event)"
              >
                <el-radio-button v-for="option in item.options" :key="String(option.value)" :value="option.value">
                  {{ option.label }}
                </el-radio-button>
              </el-radio-group>
              <el-checkbox
                v-else-if="item.control === 'checkbox'"
                :data-test="`preference-input-${item.key}`"
                :model-value="controlValue(item.key)"
                :disabled="!isEnabled(item.key)"
                @update:model-value="onItemChange(item.key, $event)"
              />
              <el-switch
                v-else-if="item.control === 'switch'"
                :data-test="`preference-input-${item.key}`"
                :model-value="controlValue(item.key)"
                :disabled="!isEnabled(item.key)"
                @update:model-value="onItemChange(item.key, $event)"
              />
              <el-select
                v-else
                :data-test="`preference-input-${item.key}`"
                :model-value="controlValue(item.key)"
                :disabled="!isEnabled(item.key)"
                @update:model-value="onItemChange(item.key, $event)"
              >
                <el-option
                  v-for="option in item.options"
                  :key="String(option.value)"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </slot>
          </div>
        </div>
      </preference-group>
    </div>

    <template #footer>
      <slot name="footer" :save="onSave" :cancel="onCancel" :restore-defaults="onRestoreDefaults">
        <el-button data-test="preference-reset" @click="onRestoreDefaults">恢复默认</el-button>
        <el-button data-test="preference-cancel" @click="onCancel">取消</el-button>
        <el-button type="primary" data-test="preference-save" @click="onSave">保存</el-button>
      </slot>
    </template>
  </component>
</template>

<style scoped>
.bms-preference-panel__pending {
  margin: 0 0 var(--bms-spacing-md, 8px);
  color: var(--bms-color-warning);
  font-size: 12px;
}

.bms-preference-panel__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bms-spacing-md, 8px);
}

.bms-preference-panel__label {
  font-size: 13px;
}

.bms-preference-panel__control[data-block='true'] {
  flex: 1;
  max-width: 60%;
}
</style>
