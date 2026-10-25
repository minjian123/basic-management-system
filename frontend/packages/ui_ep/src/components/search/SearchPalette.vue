<script setup lang="ts">
// 命令面板（07_07）：即时建议（防抖由宿主驱动）/ 可检索域提示 / 最近搜索 / 键盘导航（↑↓ 环回、回车打开、Esc 关闭）。
import { SEARCH_EMPTY_TEXT, type SearchDomain, type SearchHit } from '@bms/core'
import { computed, nextTick, ref, watch } from 'vue'

import { useBaseSearch } from '../../composables/useBaseSearch'
import SearchHitItem from './SearchHitItem.vue'

interface Props {
  /** 显隐（v-model）。 */
  modelValue?: boolean
  /** 关键词。 */
  keyword?: string
  /** 即时建议。 */
  suggestions?: SearchHit[]
  /** 最近搜索。 */
  recentKeywords?: string[]
  /** 可检索域。 */
  domains?: SearchDomain[]
  /** 建议是否加载中。 */
  loading?: boolean
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: false,
  keyword: '',
  suggestions: () => [],
  recentKeywords: () => [],
  domains: () => [],
  loading: false,
  ready: false,
  emptyText: SEARCH_EMPTY_TEXT,
})

const emit = defineEmits<{
  'update:modelValue': [open: boolean]
  'update:keyword': [keyword: string]
  select: [hit: SearchHit]
  search: [keyword: string]
  'recent-select': [keyword: string]
  'recent-clear': []
  'domain-select': [key: string]
}>()

const base = useBaseSearch({ ready: props.ready })
const keyword = ref(props.keyword)
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement>()

watch(
  () => props.ready,
  (value) => base.setReady(value),
)

watch(
  () => props.keyword,
  (value) => {
    keyword.value = value
    activeIndex.value = 0
  },
)
watch(
  () => props.suggestions,
  () => {
    activeIndex.value = 0
  },
)
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      activeIndex.value = 0
      void nextTick(() => inputRef.value?.focus())
    }
  },
)

/** 命中项总数（键盘导航用）。 */
const total = computed(() => props.suggestions.length)

/** 输入变更。 */
function onInput(value: string): void {
  keyword.value = value
  emit('update:keyword', value)
}

/** 打开某命中。 */
function openHit(hit: SearchHit): void {
  emit('select', hit)
  emit('update:modelValue', false)
}

/** 提交搜索（查看全部）。 */
function submit(): void {
  if (keyword.value.trim() === '') {
    return
  }
  emit('search', keyword.value)
  emit('update:modelValue', false)
}

/** 键盘导航。 */
function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    activeIndex.value = total.value === 0 ? 0 : (activeIndex.value + 1) % total.value
    return
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = total.value === 0 ? 0 : (activeIndex.value - 1 + total.value) % total.value
    return
  }
  if (event.key === 'Enter') {
    event.preventDefault()
    const hit = props.suggestions[activeIndex.value]
    if (hit !== undefined) {
      openHit(hit)
    } else {
      submit()
    }
    return
  }
  if (event.key === 'Escape') {
    emit('update:modelValue', false)
  }
}
</script>

<template>
  <div v-if="modelValue" class="bms-search-palette" data-test="search-palette" :data-ready="base.ready.value">
    <input
      ref="inputRef"
      class="bms-search-palette__input"
      type="search"
      data-test="search-palette-keyword"
      :value="keyword"
      :placeholder="emptyText"
      @input="onInput(($event.target as HTMLInputElement).value)"
      @keydown="onKeydown"
    />
    <div v-if="domains.length > 0" class="bms-search-palette__domains" data-test="palette-domains">
      <button
        v-for="domain in domains"
        :key="domain.key"
        type="button"
        data-test="palette-domain"
        @click="emit('domain-select', domain.key)"
      >
        {{ domain.label }}
      </button>
    </div>
    <div class="bms-search-palette__section" data-test="palette-section-suggest">即时建议</div>
    <slot name="suggestions" :suggestions="suggestions">
      <div v-if="loading" class="bms-search-palette__hint">加载中…</div>
      <div v-else-if="suggestions.length === 0" class="bms-search-palette__hint" data-test="palette-empty">
        {{ emptyText }}
      </div>
      <div v-else class="bms-search-palette__list" data-test="palette-suggestions">
        <SearchHitItem
          v-for="(hit, index) in suggestions"
          :key="`${hit.docType}-${hit.bizId}`"
          :hit="hit"
          :keyword="keyword"
          :domains="domains"
          compact
          :data-active="index === activeIndex || undefined"
          @open="openHit"
        />
      </div>
    </slot>
    <template v-if="recentKeywords.length > 0">
      <div class="bms-search-palette__section">最近搜索</div>
      <div class="bms-search-palette__recent" data-test="palette-recent">
        <button
          v-for="(item, index) in recentKeywords"
          :key="item"
          type="button"
          :data-test="`palette-recent-${index}`"
          @click="emit('recent-select', item)"
        >
          {{ item }}
        </button>
        <button type="button" data-test="palette-clear-recent" @click="emit('recent-clear')">清除</button>
      </div>
    </template>
    <div class="bms-search-palette__footer">
      <slot name="footer">
        <button type="button" data-test="palette-view-all" @click="submit">查看全部结果 →</button>
      </slot>
    </div>
  </div>
</template>

<style scoped>
.bms-search-palette {
  width: 420px;
  overflow: hidden;
  background: var(--bms-search-panel-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: 8px;
  box-shadow: var(--bms-shadow-md);
}
.bms-search-palette__input {
  width: 100%;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--bms-color-text);
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--bms-color-border);
  outline: none;
}
.bms-search-palette__domains {
  display: flex;
  gap: 6px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--bms-color-border);
}
.bms-search-palette__domains button {
  font-size: 12px;
  color: var(--bms-color-primary);
  cursor: pointer;
  background: none;
  border: none;
}
.bms-search-palette__section {
  padding: 6px 12px;
  font-size: 11px;
  color: var(--bms-color-text-secondary);
}
.bms-search-palette__hint {
  padding: 8px 12px;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}
.bms-search-palette__list {
  max-height: 260px;
  overflow-y: auto;
}
.bms-search-palette__recent {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 12px 6px;
}
.bms-search-palette__recent button {
  padding: 2px 8px;
  font-size: 12px;
  cursor: pointer;
  background: var(--bms-color-fill);
  border: none;
  border-radius: 4px;
}
.bms-search-palette__footer {
  padding: 8px 12px;
  border-top: 1px solid var(--bms-color-border);
}
.bms-search-palette__footer button {
  font-size: 13px;
  color: var(--bms-color-primary);
  cursor: pointer;
  background: none;
  border: none;
}
</style>
