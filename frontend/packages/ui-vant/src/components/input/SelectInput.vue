<script setup lang="ts">
/**
 * 下拉框（移动端 / Vant 侧）：**静态选项**选择（《组件设计 · 下拉框》，与 `ui-ep` 同契约）。
 *
 * 触发区为只读 `van-field`（显示已选文本），点击打开底部 `van-popup` 自研列表：
 * 搜索（`filterable`）、分组标题、单选即选即关、多选草稿 + 确认；达上限的未选项灰显不可选。
 */

import {
  filterOptions,
  groupOptions,
  labelOfOption,
  normalizeOptionValue,
  reachMaxCount,
  type OptionItem,
  type OptionValue,
} from '@bms/core'

import { Button as VanButton } from 'vant/es/button'
import { Popup as VanPopup } from 'vant/es/popup'
import { Search as VanSearch } from 'vant/es/search'
import 'vant/es/button/style'
import 'vant/es/popup/style'
import 'vant/es/search/style'

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useComponentBase } from '@bms/vue'

import BaseInput from './BaseInput.vue'

defineOptions({ inheritAttrs: false })

interface ShellExpose {
  setValue(value: unknown): void
  clear(): void
  commit(): unknown
}

const props = withDefaults(
  defineProps<{
    /** 受控值（单选值 / 多选数组 / `null`） */
    modelValue?: OptionValue | OptionValue[] | null
    /** 静态选项（字典 / 远程来源归字段类） */
    options?: readonly OptionItem[]
    multiple?: boolean
    /** 本地过滤（面板内搜索框） */
    filterable?: boolean
    clearable?: boolean
    /** 多选上限（达上限拒绝再选） */
    maxCount?: number
    placeholder?: string
    disabled?: boolean
    readonly?: boolean
    readonlyMode?: 'text' | 'disabled'
    label?: string
    required?: boolean
    help?: string
    error?: string
    size?: 'small' | 'default' | 'large'
    density?: 'default' | 'compact'
    span?: number
    fieldKey?: string
  }>(),
  {
    modelValue: null,
    options: () => [],
    multiple: false,
    filterable: false,
    clearable: true,
    maxCount: undefined,
    placeholder: '',
    disabled: false,
    readonly: false,
    readonlyMode: 'text',
    label: '',
    required: false,
    help: '',
    error: '',
    size: 'default',
    density: 'default',
    span: 24,
    fieldKey: '',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: OptionValue | OptionValue[] | null]
  change: [value: OptionValue | OptionValue[] | null]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'select-input' })
const { t } = useI18n()

const shellRef = ref<ShellExpose | null>(null)
const current = ref<OptionValue | OptionValue[] | null>(props.modelValue)
watch(
  () => props.modelValue,
  (next) => {
    current.value = next ?? null
  },
)

function handleShellValue(value: unknown): void {
  current.value = (value ?? null) as OptionValue | OptionValue[] | null
  emit('update:modelValue', current.value)
}

const selectedValues = computed<OptionValue[]>(() => {
  const value = current.value
  if (Array.isArray(value)) {
    return value
  }
  return value === null || value === undefined ? [] : [value]
})

/** 触发区文本（只读态由壳渲染；此处用于触发按钮） */
/** 归一后的值（无效值剔除）：只读文本与上限判定共用 */
const normalizedValue = computed(() =>
  normalizeOptionValue(current.value, props.options, props.multiple),
)

const displayLabel = computed(() => labelOfOption(normalizedValue.value, props.options))

const placeholderText = computed(() =>
  props.placeholder === '' ? t('input.selectPlaceholder') : props.placeholder,
)

const helpText = computed(() => {
  if (props.multiple && reachMaxCount(selectedValues.value, props.maxCount)) {
    return t('input.maxCount', { max: props.maxCount })
  }
  return props.help
})

const showPanel = ref(false)
const keyword = ref('')
const draftValues = ref<OptionValue[]>([])

const filteredGroups = computed(() => groupOptions(filterOptions(props.options, keyword.value)))

function isSelected(value: OptionValue): boolean {
  const pool = props.multiple && showPanel.value ? draftValues.value : selectedValues.value
  return pool.includes(value)
}

function isSelectable(item: OptionItem): boolean {
  if (item.disabled === true) {
    return false
  }
  if (!props.multiple) {
    return true
  }
  if (isSelected(item.value)) {
    return true
  }
  const pool = showPanel.value ? draftValues.value : selectedValues.value
  return !reachMaxCount(pool, props.maxCount)
}

function openPanel(slot: { disabled: boolean; readonly: boolean }): void {
  if (slot.disabled || slot.readonly || showPanel.value) {
    return
  }
  draftValues.value = [...selectedValues.value]
  keyword.value = ''
  showPanel.value = true
}

/** 选中 / 取消（面板与契约共用）：达上限的未选项不可选 */
function selectOption(value: OptionValue): void {
  const item = props.options.find((option) => option.value === value)
  if (!item || item.disabled === true) {
    return
  }
  if (!props.multiple) {
    shellRef.value?.setValue(normalizeOptionValue(value, props.options, false))
    return
  }
  if (reachMaxCount(selectedValues.value, props.maxCount) && !selectedValues.value.includes(value)) {
    return
  }
  const next = selectedValues.value.includes(value)
    ? selectedValues.value.filter((item2) => item2 !== value)
    : [...selectedValues.value, value]
  shellRef.value?.setValue(normalizeOptionValue(next, props.options, true))
}

function toggleOption(value: OptionValue): void {
  if (!props.multiple) {
    selectOption(value)
    showPanel.value = false
    return
  }
  if (draftValues.value.includes(value)) {
    draftValues.value = draftValues.value.filter((item) => item !== value)
    return
  }
  if (reachMaxCount(draftValues.value, props.maxCount)) {
    return
  }
  draftValues.value = [...draftValues.value, value]
}

function confirmPanel(): void {
  shellRef.value?.setValue(normalizeOptionValue(draftValues.value, props.options, true))
  showPanel.value = false
}

function handleShellChange(value: unknown): void {
  emit('change', (value ?? null) as OptionValue | OptionValue[] | null)
}

defineExpose({ selectOption })
</script>

<template>
  <BaseInput
    ref="shellRef"
    v-bind="$attrs"
    :class="base.nsClass('select-input')"
    :model-value="modelValue"
    :label="label"
    :required="required"
    :help="helpText"
    :error="error"
    :disabled="disabled"
    :readonly="readonly"
    :readonly-mode="readonlyMode"
    :size="size"
    :density="density"
    :span="span"
    :trim="false"
    :field-key="fieldKey"
    :display-text="displayLabel"
    @update:model-value="handleShellValue"
    @change="handleShellChange"
    @validate="emit('validate', $event)"
  >
    <template #default="slot">
      <span
        :class="[base.nsClass('select-input-trigger'), slot.disabled ? 'is-disabled' : '']"
        data-testid="select-trigger"
        @click="openPanel(slot)"
        @focus="slot.onFocus"
      >
        <span v-if="displayLabel !== ''" :class="base.nsClass('select-input-value')">{{ displayLabel }}</span>
        <span v-else :class="base.nsClass('select-input-placeholder')">{{ placeholderText }}</span>
      </span>
      <VanPopup v-model:show="showPanel" position="bottom" round>
        <div :class="base.nsClass('select-input-panel')">
          <VanSearch
            v-if="filterable"
            v-model="keyword"
            :placeholder="t('input.searchPlaceholder')"
            :class="base.nsClass('select-input-search')"
          />
          <div :class="base.nsClass('select-input-options')">
            <template v-for="group in filteredGroups" :key="group.group">
              <p v-if="group.group !== ''" :class="base.nsClass('select-input-group')">{{ group.group }}</p>
              <label
                v-for="item in group.items"
                :key="String(item.value)"
                :class="[base.nsClass('select-input-option'), isSelectable(item) ? '' : 'is-disabled']"
              >
                <input
                  :type="multiple ? 'checkbox' : 'radio'"
                  :checked="isSelected(item.value)"
                  :disabled="!isSelectable(item)"
                  @change="toggleOption(item.value)"
                />
                <span>{{ item.label }}</span>
              </label>
            </template>
          </div>
          <div v-if="multiple" :class="base.nsClass('select-input-actions')">
            <VanButton block type="primary" @click="confirmPanel">
              {{ t('common.confirm') }}
            </VanButton>
          </div>
        </div>
      </VanPopup>
    </template>
  </BaseInput>
</template>

<style scoped>
.bms-select-input-trigger {
  display: flex;
  align-items: center;
  min-height: var(--bms-size-control-height);
  padding: var(--bms-space-1) var(--bms-space-2);
  font-size: var(--bms-font-size-base);
  color: var(--bms-color-text);
  cursor: pointer;
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
}
.bms-select-input-trigger.is-disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.bms-select-input-placeholder {
  color: var(--bms-color-text-secondary);
}
.bms-select-input-panel {
  display: flex;
  flex-direction: column;
  max-height: 70vh;
  padding-bottom: var(--bms-space-2);
}
.bms-select-input-options {
  flex: 1;
  overflow-y: auto;
}
.bms-select-input-group {
  margin: 0;
  padding: var(--bms-space-2);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  background: var(--bms-color-bg-page);
}
.bms-select-input-option {
  display: flex;
  gap: var(--bms-space-2);
  align-items: center;
  padding: var(--bms-space-2) var(--bms-space-3);
  font-size: var(--bms-font-size-base);
}
.bms-select-input-option.is-disabled {
  color: var(--bms-color-text-secondary);
  opacity: 0.6;
}
.bms-select-input-actions {
  padding: var(--bms-space-2) var(--bms-space-3) 0;
}
</style>
