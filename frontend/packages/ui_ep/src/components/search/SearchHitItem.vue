<script setup lang="ts">
// 命中项（07_07）：域标识 / 高亮标题 / 高亮片段 / 时间 / 跳转；命令面板、结果页、日志与文件页签四处复用。
import { formatDateTime, formatRelativeTime, type SearchDomain, type SearchHit } from '@bms/core'
import { computed, watchEffect } from 'vue'

import { useBaseSearch } from '../../composables/useBaseSearch'
import { highlightHit } from '../../utils/searchHighlight'

interface Props {
  /** 命中项。 */
  hit: SearchHit
  /** 关键词（用于客户端高亮）。 */
  keyword?: string
  /** 紧凑形态（命令面板用）。 */
  compact?: boolean
  /** 显示域标识。 */
  showDomain?: boolean
  /** 显示时间。 */
  showTime?: boolean
  /** 可检索域（用于域名称翻译）。 */
  domains?: SearchDomain[]
}

const props = withDefaults(defineProps<Props>(), {
  keyword: '',
  compact: false,
  showDomain: true,
  showTime: true,
  domains: () => [],
})

const emit = defineEmits<{
  open: [hit: SearchHit]
}>()

const base = useBaseSearch({ ready: true })

watchEffect(() => base.setDomains(props.domains))

/** 高亮后的标题与摘要。 */
const highlighted = computed(() => highlightHit(props.hit, props.keyword))

/** 域展示名。 */
const domainLabel = computed(() => base.state.domainLabel(props.hit.docType))

/** 相对时间。 */
const relative = computed(() => (props.hit.updatedAt ? formatRelativeTime(props.hit.updatedAt) : ''))

/** 绝对时间（悬浮提示）。 */
const absolute = computed(() => (props.hit.updatedAt ? formatDateTime(props.hit.updatedAt) : ''))
</script>

<template>
  <div
    class="bms-search-hit"
    :data-test="`hit-${hit.docType}-${hit.bizId}`"
    :data-compact="compact || undefined"
    @click="emit('open', hit)"
  >
    <slot>
      <div class="bms-search-hit__body">
        <div class="bms-search-hit__meta">
          <span v-if="showDomain" class="bms-search-hit__domain" data-test="hit-domain" :title="hit.docType">
            {{ domainLabel }}
          </span>
          <span v-if="showTime && relative" class="bms-search-hit__time" data-test="hit-time" :title="absolute">
            {{ relative }}
          </span>
        </div>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div class="bms-search-hit__title" data-test="hit-title" v-html="highlighted.title" />
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div v-if="!compact && highlighted.summary" class="bms-search-hit__summary" data-test="hit-summary" v-html="highlighted.summary" />
      </div>
    </slot>
  </div>
</template>

<style scoped>
.bms-search-hit {
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--bms-color-border);
}
.bms-search-hit:hover {
  background: var(--bms-search-hit-hover-bg);
}
.bms-search-hit__meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}
.bms-search-hit__domain {
  color: var(--bms-color-primary);
}
.bms-search-hit__title {
  margin: 2px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--bms-color-text);
}
.bms-search-hit__summary {
  overflow: hidden;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bms-search-hit :deep(em) {
  padding: 0 1px;
  font-style: normal;
  color: var(--bms-search-highlight-color);
  background: var(--bms-search-highlight-bg);
  border-radius: 2px;
}
</style>
