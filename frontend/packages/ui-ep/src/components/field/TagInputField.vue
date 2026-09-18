<script setup lang="ts">
// 标签输入（06_03）：建议与自由新建 / 去重 / 上下限 / 颜色映射 / 粘贴批量；`el-tag` + 自研输入壳。
import { ElTag } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

/** 标签类型（对齐 `el-tag`）。 */
export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

/** 颜色映射。 */
export type TagColorMap = Record<string, string> | ((tag: string) => string)

interface Props {
  /** 值（受控，标签数组）。 */
  modelValue?: string[]
  /** 静态建议。 */
  suggestions?: string[]
  /** 允许自由新建。 */
  allowCreate?: boolean
  /** 数量上限。 */
  max?: number
  /** 单个标签长度上限。 */
  maxLength?: number
  /** 颜色映射（映射表或函数）。 */
  colorMap?: TagColorMap
  /** 只读。 */
  readonly?: boolean
  /** 必填。 */
  required?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  suggestions: () => [],
  allowCreate: true,
  max: undefined,
  maxLength: undefined,
  colorMap: undefined,
  readonly: false,
  required: false,
  disabled: false,
  placeholder: '输入后回车添加',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
  change: [value: string[]]
  invalid: [message: string]
}>()

const { value, disabled, setValue } = useBaseInput<string[]>({ disabled: props.disabled })
const draft = ref('')
const limitError = ref('')

watch(
  () => props.modelValue,
  (next) => setValue(Array.isArray(next) ? next : []),
  { immediate: true },
)

const tags = computed<string[]>(() => (Array.isArray(value.value) ? value.value : []))

/** 过滤后的建议（排除已选）。 */
const filteredSuggestions = computed(() => {
  const keyword = draft.value.trim().toLowerCase()
  return props.suggestions
    .filter((item) => !tags.value.includes(item))
    .filter((item) => (keyword === '' ? true : item.toLowerCase().includes(keyword)))
    .slice(0, 8)
})

const internalError = computed<string>(() => {
  if (limitError.value !== '') {
    return limitError.value
  }
  return props.required && tags.value.length === 0 ? '该字段为必填项' : ''
})

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : internalError.value))

watch(
  internalError,
  (message) => {
    if (message !== '') {
      emit('invalid', message)
    }
  },
  { immediate: true },
)

/** 标签颜色。 */
function tagColor(tag: string): TagType {
  const map = props.colorMap
  if (map === undefined) {
    return 'info'
  }
  const color = typeof map === 'function' ? map(tag) : map[tag]
  return color === undefined || color === '' ? 'info' : (color as TagType)
}

function commit(next: string[]): void {
  limitError.value = ''
  setValue(next)
  emit('update:modelValue', next)
  emit('change', next)
}

function tryAppend(next: string[], raw: string): string[] | undefined {
  const tag = raw.trim()
  if (tag === '') {
    return next
  }
  if (next.includes(tag)) {
    return next
  }
  if (!props.allowCreate && !props.suggestions.includes(tag)) {
    return next
  }
  if (props.maxLength !== undefined && tag.length > props.maxLength) {
    limitError.value = `单个标签最多 ${props.maxLength} 字`
    emit('invalid', limitError.value)
    return undefined
  }
  if (props.max !== undefined && next.length + 1 > props.max) {
    limitError.value = `最多 ${props.max} 个标签`
    emit('invalid', limitError.value)
    return undefined
  }
  return [...next, tag]
}

function addTag(raw: string): void {
  const next = tryAppend(tags.value, raw)
  if (next !== undefined && next.length !== tags.value.length) {
    commit(next)
  }
}

function removeTag(tag: string): void {
  commit(tags.value.filter((item) => item !== tag))
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter') {
    event.preventDefault()
    addTag(draft.value)
    draft.value = ''
  }
}

function onPaste(event: ClipboardEvent): void {
  const text = event.clipboardData?.getData('text') ?? ''
  if (!/[,;\n]/.test(text)) {
    return
  }
  event.preventDefault()
  let next = [...tags.value]
  for (const part of text.split(/[,;\n]+/)) {
    const result = tryAppend(next, part)
    if (result === undefined) {
      break
    }
    next = result
  }
  if (next.length !== tags.value.length) {
    commit(next)
  }
  draft.value = ''
}

function onBlur(): void {
  if (draft.value.trim() !== '') {
    addTag(draft.value)
    draft.value = ''
  }
}
</script>

<template>
  <div class="bms-tag-input-field" :data-invalid="resolvedError !== ''" :data-readonly="readonly">
    <div class="bms-tag-input-field__tags">
      <el-tag
        v-for="tag in tags"
        :key="tag"
        class="bms-tag-input-field__tag"
        :type="tagColor(tag)"
        :closable="!readonly && !disabled"
        :data-test="`tag-${tag}`"
        @close="removeTag(tag)"
      >
        {{ tag }}
      </el-tag>

      <input
        v-if="!readonly"
        v-model="draft"
        class="bms-tag-input-field__input"
        data-test="tag-input"
        :disabled="disabled"
        :placeholder="placeholder"
        @keydown="onKeydown"
        @paste="onPaste"
        @blur="onBlur"
      />
    </div>

    <ul v-if="!readonly && filteredSuggestions.length > 0" class="bms-tag-input-field__suggestions" data-test="tag-suggestions">
      <li v-for="item in filteredSuggestions" :key="item">
        <button type="button" :data-test="`suggest-${item}`" @mousedown.prevent="addTag(item); draft = ''">
          {{ item }}
        </button>
      </li>
    </ul>

    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>
