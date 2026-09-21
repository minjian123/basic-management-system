<script setup lang="ts">
// 文件内容页签（07_07）：文件类型筛选、命中文件 ID + 上下文高亮、不可检索文件提示（10106）。
import { SEARCH_FILE_UNSEARCHABLE_TEXT, type SearchHit } from '@bms/core'
import { ref, watch } from 'vue'

import { useBaseSearch } from '../../composables/useBaseSearch'
import SearchHitItem from './SearchHitItem.vue'

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 命中。 */
  items?: SearchHit[]
  /** 总数。 */
  total?: number
  /** 页码。 */
  page?: number
  /** 页长。 */
  pageSize?: number
  /** 加载中。 */
  loading?: boolean
  /** 错误态。 */
  error?: boolean
  /** 错误文案。 */
  errorText?: string
  /** 文件类型。 */
  fileType?: string
  /** 不可检索提示文案。 */
  unsearchableText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  items: () => [],
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false,
  error: false,
  errorText: '',
  fileType: '',
  unsearchableText: SEARCH_FILE_UNSEARCHABLE_TEXT,
})

const emit = defineEmits<{
  'update:fileType': [type: string]
  'update:page': [page: number]
  search: []
  retry: []
  open: [hit: SearchHit]
}>()

const base = useBaseSearch({ ready: props.ready })
const type = ref(props.fileType)

watch(
  () => props.fileType,
  (value) => {
    type.value = value
  },
)

/** 变更文件类型。 */
function onType(value: string): void {
  type.value = value
  emit('update:fileType', value)
}

/** 域标签（经搜索族基类展示语义）。 */
function labelOf(hit: SearchHit): string {
  return base.state.domainLabel(hit.docType)
}

/** 是否为不可检索文件（后端 10106 标记）。 */
function unsearchable(hit: SearchHit): boolean {
  return hit.unsearchable === true
}
</script>

<template>
  <div class="bms-search-file" data-test="search-file-tab" :data-ready="ready">
    <div class="bms-search-file__filter">
      <select
        class="bms-search-file__type"
        data-test="file-type"
        :value="type"
        @change="onType(($event.target as HTMLSelectElement).value)"
      >
        <option value="">全部文件</option>
        <option value="pdf">PDF</option>
        <option value="word">Word</option>
        <option value="excel">Excel</option>
        <option value="txt">TXT</option>
      </select>
      <button type="button" data-test="file-search" @click="emit('search')">检索</button>
    </div>
    <div v-if="error" class="bms-search-file__error" data-test="file-error">
      <span>{{ errorText || '检索失败' }}</span>
      <button type="button" data-test="file-retry" @click="emit('retry')">重试</button>
    </div>
    <div v-else-if="loading" class="bms-search-file__hint" data-test="file-skeleton">检索中…</div>
    <div v-else-if="items.length === 0" class="bms-search-file__hint" data-test="file-empty">未找到相关文件</div>
    <div v-else class="bms-search-file__hits" data-test="file-hits">
      <SearchHitItem
        v-for="hit in items"
        :key="`${hit.docType}-${hit.bizId}`"
        :hit="hit"
        :domains="[{ key: hit.docType, label: labelOf(hit) }]"
        @open="emit('open', $event)"
      />
    </div>
    <div v-if="items.some(unsearchable)" class="bms-search-file__hint" data-test="file-unsearchable">
      {{ unsearchableText }}
    </div>
    <div v-if="total > pageSize" class="bms-search-file__pagination" data-test="file-pagination">
      <button type="button" :disabled="page <= 1" @click="emit('update:page', page - 1)">上一页</button>
      <span>{{ page }}</span>
      <button type="button" @click="emit('update:page', page + 1)">下一页</button>
    </div>
  </div>
</template>

<style scoped>
.bms-search-file {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bms-search-file__filter {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}
.bms-search-file__hits {
  border: 1px solid var(--bms-color-border);
  border-radius: 6px;
}
.bms-search-file__hint {
  padding: 12px;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
  text-align: center;
}
.bms-search-file__error {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--bms-color-danger);
}
.bms-search-file__pagination {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  font-size: 12px;
}
</style>
