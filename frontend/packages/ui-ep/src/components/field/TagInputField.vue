<script setup lang="ts">
// 标签输入（06_03）：建议与自由新建 / 去重 / 上下限 / 颜色映射 / 粘贴批量；`el-tag` + `el-input` 壳。
// 补：分隔符触发（中英文逗号）/ 退格删除末尾 / 只读顿号纯文本回显 / 历史脏值归一 / 内容操作暴露 / 变化明细。
import { ElButton, ElInput, ElTag } from 'element-plus'
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

/** 变化明细（新增 / 移除项）。 */
export interface TagChangeDetail {
  /** 方向。 */
  direction: 'add' | 'remove'
  /** 本次变化的标签。 */
  changed: string[]
}

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
  change: [value: string[], detail?: TagChangeDetail]
  invalid: [message: string]
}>()

const { value, disabled, setValue } = useBaseInput<string[]>({ disabled: props.disabled })
const draft = ref('')
const limitError = ref('')

/** 历史脏值归一（去空白 / 去空串 / 去重——节点 §5「归一」）。 */
function normalizeTags(next: unknown): string[] {
  if (!Array.isArray(next)) {
    return []
  }
  const result: string[] = []
  for (const item of next) {
    const tag = String(item).trim()
    if (tag !== '' && !result.includes(tag)) {
      result.push(tag)
    }
  }
  return result
}

watch(
  () => props.modelValue,
  (next) => setValue(normalizeTags(next)),
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
  const added = next.filter((tag) => !tags.value.includes(tag))
  const removed = tags.value.filter((tag) => !next.includes(tag))
  const detail: TagChangeDetail | undefined =
    added.length > 0
      ? { direction: 'add', changed: added }
      : removed.length > 0
        ? { direction: 'remove', changed: removed }
        : undefined
  setValue(next)
  emit('update:modelValue', next)
  emit('change', next, detail)
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

/**
 * 键盘处理（`el-input` 的 `keydown` 事件签名宽于 `KeyboardEvent`，此处收窄）。
 *
 * @param raw 原生事件。
 */
function onKeydown(raw: Event | KeyboardEvent): void {
  const event = raw as KeyboardEvent
  if (event.key === 'Enter') {
    event.preventDefault()
    addTag(draft.value)
    draft.value = ''
    return
  }
  // 分隔符触发创建（中英文逗号——节点 §3/§4）。
  if (event.key === ',' || event.key === '，') {
    event.preventDefault()
    addTag(draft.value)
    draft.value = ''
    return
  }
  // 退格删除末尾（草稿为空时——节点 §4「删除」）。
  if (event.key === 'Backspace' && draft.value === '' && tags.value.length > 0 && !props.readonly) {
    event.preventDefault()
    removeTag(tags.value[tags.value.length - 1])
  }
}

function onPaste(event: ClipboardEvent): void {
  const text = event.clipboardData?.getData('text') ?? ''
  if (!/[,，;；\n]/.test(text)) {
    return
  }
  event.preventDefault()
  let next = [...tags.value]
  for (const part of text.split(/[,，;；\n]+/)) {
    const result = tryAppend(next, part)
    if (result === undefined) {
      // 越限：停止解析但**保留已成功解析的项**（不丢弃全部）。
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

/** 清空全部标签（内容操作）。 */
function clear(): void {
  commit([])
}

/** 设置标签（内容操作；经归一）。 */
function setTags(next: string[]): void {
  commit(normalizeTags(next))
}

defineExpose({ add: addTag, remove: removeTag, clear, setValue: setTags })
</script>

<template>
  <div class="bms-tag-input-field" :data-invalid="resolvedError !== ''" :data-readonly="readonly">
    <div v-if="readonly" class="bms-tag-input-field__readonly" data-test="tag-readonly">
      <span v-if="tags.length === 0">—</span>
      <span v-else>{{ tags.join('、') }}</span>
    </div>

    <template v-else>
      <div class="bms-tag-input-field__tags">
        <el-tag
          v-for="tag in tags"
          :key="tag"
          class="bms-tag-input-field__tag"
          :type="tagColor(tag)"
          :closable="!disabled"
          :data-test="`tag-${tag}`"
          @close="removeTag(tag)"
        >
          {{ tag }}
        </el-tag>

        <el-input
          v-model="draft"
          class="bms-tag-input-field__input"
          data-test="tag-input"
          size="small"
          :disabled="disabled"
          :placeholder="placeholder"
          @keydown="onKeydown"
          @paste="onPaste"
          @blur="onBlur"
        />
      </div>

      <ul v-if="filteredSuggestions.length > 0" class="bms-tag-input-field__suggestions" data-test="tag-suggestions">
        <li v-for="item in filteredSuggestions" :key="item">
          <el-button
            class="bms-tag-input-field__suggestion"
            link
            size="small"
            :data-test="`suggest-${item}`"
            @click="addTag(item); draft = ''"
          >
            {{ item }}
          </el-button>
        </li>
      </ul>
    </template>

    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-tag-input-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-tag-input-field__tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-1);
  min-height: var(--bms-control-height);
  padding: var(--bms-space-1) var(--bms-space-2);
  background: var(--bms-richtext-content-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-tag-input-field[data-invalid='true'] .bms-tag-input-field__tags {
  border-color: var(--bms-field-error-color);
}

.bms-tag-input-field__tag {
  flex: none;
}

.bms-tag-input-field__input {
  flex: 1 1 120px;
  min-width: 120px;
}

.bms-tag-input-field__input :deep(.el-input__wrapper) {
  box-shadow: none;
}

.bms-tag-input-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
  word-break: break-all;
}

.bms-tag-input-field__suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-1);
  margin: 0;
  padding: var(--bms-space-2);
  list-style: none;
  background: var(--bms-field-suggest-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-tag-input-field__suggestion {
  font-size: var(--bms-font-size-xs);
}

.bms-tag-input-field__suggestions li:hover {
  background: var(--bms-field-suggest-hover-bg);
  border-radius: var(--bms-radius-sm);
}
</style>
