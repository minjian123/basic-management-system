<script setup lang="ts">
// 审计日志页签（07_07）：时间范围必填、单次 ≤ 31 天（10107），命中复用命中项件。
import {
  SEARCH_LOG_RANGE_MAX_DAYS,
  SEARCH_LOG_RANGE_REQUIRED_TEXT,
  validateLogRange,
  type SearchHit,
  type SearchRange,
} from '@bms/core'
import { computed, ref, watch } from 'vue'

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
  /** 日志类型。 */
  logType?: string
  /** 时间范围。 */
  timeRange?: SearchRange
  /** 时间范围上限（天）。 */
  maxRangeDays?: number
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
  logType: '',
  timeRange: () => ({}),
  maxRangeDays: SEARCH_LOG_RANGE_MAX_DAYS,
})

const emit = defineEmits<{
  'update:logType': [type: string]
  'update:timeRange': [range: SearchRange]
  'update:page': [page: number]
  search: []
  retry: []
  open: [hit: SearchHit]
}>()

const base = useBaseSearch({ ready: props.ready })
const range = ref<SearchRange>({ ...props.timeRange })

watch(
  () => props.timeRange,
  (value) => {
    range.value = { ...value }
  },
)

/** 范围校验结果（必填 + 上限）。 */
const validation = computed(() => validateLogRange(range.value, props.maxRangeDays))

/** 校验提示（未填时不在初始态打扰）。 */
const rangeError = computed(() => {
  if (range.value.start === undefined && range.value.end === undefined) {
    return ''
  }
  if (validation.value.valid) {
    return ''
  }
  return validation.value.message ?? SEARCH_LOG_RANGE_REQUIRED_TEXT
})

/** 更新时间范围。 */
function onRange(field: 'start' | 'end', value: string): void {
  const next = { ...range.value, [field]: value }
  range.value = next
  emit('update:timeRange', next)
}

/** 提交检索（范围不合法时不触发）。 */
function submit(): void {
  if (!validation.value.valid) {
    return
  }
  emit('search')
}

/** 域标签（经搜索族基类展示语义）。 */
function labelOf(hit: SearchHit): string {
  return base.state.domainLabel(hit.docType)
}
</script>

<template>
  <div class="bms-search-log" data-test="search-log-tab" :data-ready="ready">
    <div class="bms-search-log__filter">
      <select
        class="bms-search-log__type"
        data-test="log-type"
        :value="logType"
        @change="emit('update:logType', ($event.target as HTMLSelectElement).value)"
      >
        <option value="">全部类型</option>
        <option value="login">登录日志</option>
        <option value="operation">操作日志</option>
        <option value="data_change">数据变更</option>
      </select>
      <label class="bms-search-log__range" data-test="log-range">
        <input
          type="date"
          data-test="log-range-start"
          :value="range.start ?? ''"
          @change="onRange('start', ($event.target as HTMLInputElement).value)"
        />
        <span>~</span>
        <input
          type="date"
          data-test="log-range-end"
          :value="range.end ?? ''"
          @change="onRange('end', ($event.target as HTMLInputElement).value)"
        />
      </label>
      <button type="button" data-test="log-search" :disabled="!validation.valid" @click="submit">检索</button>
    </div>
    <div v-if="rangeError" class="bms-search-log__error" data-test="log-range-error">{{ rangeError }}</div>
    <div v-if="error" class="bms-search-log__error" data-test="log-error">
      <span>{{ errorText || '检索失败' }}</span>
      <button type="button" data-test="log-retry" @click="emit('retry')">重试</button>
    </div>
    <div v-else-if="loading" class="bms-search-log__hint" data-test="log-skeleton">检索中…</div>
    <div v-else-if="items.length === 0" class="bms-search-log__hint" data-test="log-empty">未找到相关日志</div>
    <div v-else class="bms-search-log__hits" data-test="log-hits">
      <SearchHitItem
        v-for="hit in items"
        :key="`${hit.docType}-${hit.bizId}`"
        :hit="hit"
        :show-time="false"
        :domains="[{ key: hit.docType, label: labelOf(hit) }]"
        @open="emit('open', $event)"
      />
    </div>
    <div v-if="total > pageSize" class="bms-search-log__pagination" data-test="log-pagination">
      <button type="button" :disabled="page <= 1" @click="emit('update:page', page - 1)">上一页</button>
      <span>{{ page }}</span>
      <button type="button" @click="emit('update:page', page + 1)">下一页</button>
    </div>
  </div>
</template>

<style scoped>
.bms-search-log {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bms-search-log__filter {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}
.bms-search-log__range {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}
.bms-search-log__hits {
  border: 1px solid var(--bms-color-border);
  border-radius: 6px;
}
.bms-search-log__hint {
  padding: 20px;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
  text-align: center;
}
.bms-search-log__error {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--bms-color-danger);
}
.bms-search-log__pagination {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  font-size: 12px;
}
</style>
