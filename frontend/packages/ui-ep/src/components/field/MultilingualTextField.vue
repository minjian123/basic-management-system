<script setup lang="ts">
// 多语言文本字段（06_08，多行形态）：描述 / 备注 / 正文等长文案的同契约实现。
// 与单行件同口径（字段恒占一行 + 明细弹框），仅内层由文本框换为文本域；
// 语义（必填语言解析、缺省回退链、派生化口径）全在核心基类，本件只做渲染与事件转发。
import {
  I18N_LOCALE_FAILED_TEXT,
  I18N_NAME_PLACEHOLDER,
  type I18nLocaleSourceAdapter,
  type I18nNames,
  type LocaleOptionInput,
} from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseMultilingualName } from '../../composables/useBaseMultilingualName'
import MultilingualDetailDialog from './MultilingualDetailDialog.vue'

interface Props {
  /** 受控值（locale → 文案完整映射）。 */
  modelValue?: I18nNames
  /** 启用语言清单。 */
  locales?: readonly LocaleOptionInput[]
  /** 当前登录用户语言（决定必填语言）。 */
  userLocale?: string
  /** 语言清单数据源（未注入即占位零请求）。 */
  source?: I18nLocaleSourceAdapter
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 是否必填（必填语言文案非空）。 */
  required?: boolean
  /** 单条文案长度上限（Unicode 码点）。 */
  maxLength?: number
  /** 文本域行数。 */
  rows?: number
  /** 禁用。 */
  disabled?: boolean
  /** 只读（按当前语言回显单值）。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  locales: undefined,
  userLocale: '',
  source: undefined,
  ready: undefined,
  required: false,
  maxLength: 4000,
  rows: 3,
  disabled: false,
  readonly: false,
  placeholder: '',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: I18nNames]
  change: [value: I18nNames]
  invalid: [message: string]
}>()

const api = useBaseMultilingualName({
  value: props.modelValue,
  locales: props.locales,
  userLocale: props.userLocale,
  required: props.required,
  multiline: true,
  maxLength: props.maxLength,
  source: props.source,
  disabled: props.disabled,
})

/** 生效就绪态：显式传入为准；否则「给了语言清单或数据源」即视为就绪。 */
const effectiveReady = computed(
  () => props.ready ?? ((props.locales?.length ?? 0) > 0 || props.source !== undefined),
)

watch(effectiveReady, (next) => api.setReady(next), { immediate: true })
watch(() => props.modelValue, (next) => api.setNames(next ?? {}))
watch(() => props.userLocale, (next) => api.setUserLocale(next))
watch(() => props.required, (next) => api.setRequired(next))
watch(
  () => api.value.value,
  (next) => {
    if (next !== undefined) {
      emit('update:modelValue', next)
      emit('change', next)
    }
  },
)
watch(
  () => api.invalid.value,
  (isInvalid) => {
    if (isInvalid) {
      emit('invalid', `缺少必填语言文案：${api.requiredLocale.value}`)
    }
  },
  { immediate: true },
)

const resolvedError = computed(() =>
  props.errorMessage !== ''
    ? props.errorMessage
    : api.invalid.value
      ? `缺少必填语言文案：${api.requiredLocale.value}`
      : '',
)
const placeholder = computed(() => (props.placeholder !== '' ? props.placeholder : I18N_NAME_PLACEHOLDER))
const actionHint = computed(() => (api.localeDegraded.value ? I18N_LOCALE_FAILED_TEXT : api.hintText.value))

function onInput(event: Event): void {
  api.setText((event.target as HTMLTextAreaElement).value)
}
</script>

<template>
  <div
    class="bms-multilingual-text"
    :data-invalid="resolvedError !== ''"
    :data-degraded="api.localeDegraded.value"
    data-test="multilingual-text"
  >
    <div class="bms-multilingual-text__control">
      <textarea
        class="bms-multilingual-text__input"
        data-test="multilingual-text-input"
        :value="readonly ? api.displayText.value : api.text.value"
        :placeholder="placeholder"
        :maxlength="maxLength"
        :rows="rows"
        :disabled="api.disabled.value"
        :readonly="readonly"
        @input="onInput"
      ></textarea>
      <button
        type="button"
        class="bms-multilingual-text__action"
        data-test="multilingual-name-action"
        :title="actionHint"
        :aria-label="actionHint"
        :disabled="api.disabled.value && !api.localeDegraded.value"
        @click="api.openDetail()"
      >
        🌐
      </button>
    </div>
    <p v-if="resolvedError !== ''" class="bms-multilingual-text__error" data-test="multilingual-text-error">
      {{ resolvedError }}
    </p>
    <MultilingualDetailDialog
      :visible="api.detailVisible.value"
      :rows="api.draftRows.value"
      :required-code="api.requiredLocale.value"
      :default-code="api.defaultLocale.value"
      multiline
      :max-length="maxLength"
      @edit="api.setDraftName"
      @confirm="api.confirmDetail()"
      @cancel="api.closeDetail()"
    />
  </div>
</template>
