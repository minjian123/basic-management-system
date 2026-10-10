<script setup lang="ts">
// 多语言文案字段（06_08，单行形态）：字段恒占一行——文本框就地编辑必填语言
// （＝当前登录用户语言，未启用或为空时回退系统默认语言）的文案 + 图标按钮打开多语言明细弹框；
// 字段标签不标注「多语言」，按钮以悬停提示给出完整度或缺失语言。
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
  /** 启用语言清单（宿主可先给，再经 `load` 刷新）。 */
  locales?: readonly LocaleOptionInput[]
  /** 当前登录用户语言（决定必填语言）。 */
  userLocale?: string
  /** 语言清单数据源（未注入即占位零请求）。 */
  source?: I18nLocaleSourceAdapter
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 是否必填（必填语言文案非空）。 */
  required?: boolean
  /** 是否多行形态（内层为文本域）。 */
  multiline?: boolean
  /** 单条文案长度上限（Unicode 码点）。 */
  maxLength?: number
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
  multiline: false,
  maxLength: 128,
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
  multiline: props.multiline,
  maxLength: props.maxLength,
  source: props.source,
  disabled: props.disabled,
})

/** 生效就绪态：显式传入为准；否则「给了语言清单或数据源」即视为就绪（未给即占位降级）。 */
const effectiveReady = computed(
  () => props.ready ?? ((props.locales?.length ?? 0) > 0 || props.source !== undefined),
)

watch(effectiveReady, (next) => api.setReady(next), { immediate: true })
watch(
  () => props.modelValue,
  (next) => api.setNames(next ?? {}),
)
watch(
  () => props.userLocale,
  (next) => api.setUserLocale(next),
)
watch(
  () => props.required,
  (next) => api.setRequired(next),
)
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
  (valid) => {
    if (valid) {
      emit('invalid', `缺少必填语言文案：${api.requiredLocale.value}`)
    }
  },
  { immediate: true },
)

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : api.invalid.value ? `缺少必填语言文案：${api.requiredLocale.value}` : ''))
const placeholder = computed(() => props.placeholder !== '' ? props.placeholder : I18N_NAME_PLACEHOLDER)
const actionHint = computed(() => (api.localeDegraded.value ? I18N_LOCALE_FAILED_TEXT : api.hintText.value))

function onInput(event: Event): void {
  api.setText((event.target as HTMLInputElement | HTMLTextAreaElement).value)
}
</script>

<template>
  <div
    class="bms-multilingual-name"
    :class="{ 'bms-multilingual-name--multiline': multiline }"
    :data-invalid="resolvedError !== ''"
    :data-degraded="api.localeDegraded.value"
    data-test="multilingual-name"
  >
    <div class="bms-multilingual-name__control">
      <input
        v-if="!multiline"
        class="bms-multilingual-name__input"
        data-test="multilingual-name-input"
        :value="readonly ? api.displayText.value : api.text.value"
        :placeholder="placeholder"
        :maxlength="maxLength"
        :disabled="api.disabled.value"
        :readonly="readonly"
        :dir="api.rows.value[0]?.rtl ? 'rtl' : 'ltr'"
        @input="onInput"
      />
      <textarea
        v-else
        class="bms-multilingual-name__input"
        data-test="multilingual-name-input"
        :value="readonly ? api.displayText.value : api.text.value"
        :placeholder="placeholder"
        :maxlength="maxLength"
        :disabled="api.disabled.value"
        :readonly="readonly"
        rows="3"
        @input="onInput"
      ></textarea>
      <button
        type="button"
        class="bms-multilingual-name__action"
        data-test="multilingual-name-action"
        :title="actionHint"
        :aria-label="actionHint"
        :disabled="api.disabled.value && !api.localeDegraded.value"
        @click="api.openDetail()"
      >
        🌐
      </button>
    </div>
    <p v-if="resolvedError !== ''" class="bms-multilingual-name__error" data-test="multilingual-name-error">
      {{ resolvedError }}
    </p>
    <MultilingualDetailDialog
      :visible="api.detailVisible.value"
      :rows="api.draftRows.value"
      :required-code="api.requiredLocale.value"
      :default-code="api.defaultLocale.value"
      :multiline="multiline"
      :max-length="maxLength"
      @edit="api.setDraftName"
      @confirm="api.confirmDetail()"
      @cancel="api.closeDetail()"
    />
  </div>
</template>
