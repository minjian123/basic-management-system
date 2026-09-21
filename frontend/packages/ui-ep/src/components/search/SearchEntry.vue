<script setup lang="ts">
// 顶栏入口（07_07）：常驻搜索框 + 快捷键呼出命令面板 + 可检索域提示 + 降级提示。
import { SEARCH_PLACEHOLDER_TEXT, type SearchDomain } from '@bms/core'
import { onMounted, ref, watch } from 'vue'

import { useBaseSearch } from '../../composables/useBaseSearch'

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 关键词。 */
  modelValue?: string
  /** 占位文案。 */
  placeholder?: string
  /** 快捷键（缺省 `mod+k`）。 */
  shortcut?: string
  /** 可检索域（标签提示）。 */
  domains?: SearchDomain[]
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  modelValue: '',
  placeholder: '搜索用户、部门、角色、字典、单据、文件…',
  shortcut: 'mod+k',
  domains: () => [],
  degradeText: SEARCH_PLACEHOLDER_TEXT,
})

const emit = defineEmits<{
  'update:modelValue': [keyword: string]
  search: [keyword: string]
  'open-panel': [keyword: string]
  focus: []
  fallback: []
}>()

const base = useBaseSearch({ ready: props.ready })
const keyword = ref(props.modelValue)
const inputRef = ref<HTMLInputElement>()

watch(
  () => props.ready,
  (value) => base.setReady(value),
)
watch(
  () => props.modelValue,
  (value) => {
    keyword.value = value
  },
)

/** 快捷键标签。 */
function shortcutLabel(): string {
  return props.shortcut
    .split('+')
    .map((part) => {
      const key = part.trim()
      if (key === 'mod') {
        return 'Ctrl/Cmd'
      }
      return key.length === 1 ? key.toUpperCase() : (key.charAt(0).toUpperCase() + key.slice(1))
    })
    .join(' + ')
}

/** 聚焦并呼出命令面板。 */
function openPanel(): void {
  inputRef.value?.focus()
  emit('open-panel', keyword.value)
}

/** 输入变更。 */
function onInput(value: string): void {
  keyword.value = value
  emit('update:modelValue', value)
}

/** 提交搜索。 */
function submit(): void {
  if (keyword.value.trim() === '') {
    return
  }
  emit('search', keyword.value)
}

onMounted(() => {
  base.registerShortcut(openPanel, props.shortcut)
})
</script>

<template>
  <div class="bms-search-entry" data-test="search-entry" :data-ready="ready" :data-degraded="base.degraded.value">
    <div v-if="base.degraded.value" class="bms-search-entry__degrade" data-test="search-entry-degrade">
      <slot name="degrade">{{ degradeText }}</slot>
    </div>
    <div v-else class="bms-search-entry__bar">
      <slot name="prefix">
        <span class="bms-search-entry__icon" aria-hidden="true">⌕</span>
      </slot>
      <input
        ref="inputRef"
        class="bms-search-entry__input"
        type="search"
        data-test="search-entry-input"
        :value="keyword"
        :placeholder="placeholder"
        @input="onInput(($event.target as HTMLInputElement).value)"
        @focus="emit('focus')"
        @keydown.enter="submit"
      />
      <span class="bms-search-entry__kbd" data-test="search-entry-kbd">{{ shortcutLabel() }}</span>
      <slot name="suffix" />
    </div>
    <div v-if="domains.length > 0" class="bms-search-entry__domains" data-test="search-entry-domains">
      <span v-for="domain in domains" :key="domain.key">{{ domain.label }}</span>
    </div>
  </div>
</template>

<style scoped>
.bms-search-entry {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.bms-search-entry__bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 10px;
  background: var(--bms-color-fill);
  border-radius: 6px;
}
.bms-search-entry__icon {
  color: var(--bms-color-text-secondary);
}
.bms-search-entry__input {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 13px;
  color: var(--bms-color-text);
  background: transparent;
  border: none;
  outline: none;
}
.bms-search-entry__kbd {
  padding: 0 5px;
  font-size: 11px;
  color: var(--bms-color-text-secondary);
  border: 1px solid var(--bms-color-border);
  border-radius: 4px;
}
.bms-search-entry__domains {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--bms-color-text-secondary);
}
.bms-search-entry__degrade {
  padding: 4px 10px;
  font-size: 12px;
  color: var(--bms-search-highlight-color);
  background: var(--bms-search-degrade-bg);
  border: 1px solid var(--bms-search-degrade-border);
  border-radius: 6px;
}
</style>
