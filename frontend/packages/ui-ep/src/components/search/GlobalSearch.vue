<script setup lang="ts">
// 结果页容器（07_07）：顶栏入口 + 多域分组 / 页签 + 分页 + 降级 / 错误态 + 审计日志与文件内容页签。
// 07_01 冻结对外契约只向后兼容新增；仅注入 engine 时件内驱动真实编排（未注入用传入数据）。
import {
  SEARCH_DEGRADE_FALLBACK_TEXT,
  SEARCH_DEGRADE_TEXT,
  SEARCH_EMPTY_TEXT,
  SEARCH_PLACEHOLDER_TEXT,
  type BaseAccess,
  type SearchDomain,
  type SearchEngineAdapter,
  type SearchGroup,
  type SearchHit,
} from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseSearch } from '../../composables/useBaseSearch'
import SearchFileTab from './SearchFileTab.vue'
import SearchHitItem from './SearchHitItem.vue'
import SearchLogTab from './SearchLogTab.vue'

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 关键词。 */
  modelValue?: string
  /** 可检索域。 */
  domains?: SearchDomain[]
  /** 分组结果。 */
  groups?: SearchGroup[]
  /** 加载中。 */
  loading?: boolean
  /** 检索引擎降级（10103）。 */
  engineDegraded?: boolean
  /** 降级文案。 */
  degradeText?: string
  /** 当前域。 */
  activeDomain?: string
  /** 命中总数。 */
  total?: number
  /** 页码。 */
  page?: number
  /** 页长。 */
  pageSize?: number
  /** 错误态。 */
  error?: boolean
  /** 错误文案。 */
  errorText?: string
  /** 空态文案。 */
  emptyText?: string
  /** 显示分页。 */
  showPagination?: boolean
  /** 权限上下文（页签门控与域二次过滤）。 */
  access?: BaseAccess
  /** 检索引擎（注入后件内驱动真实编排）。 */
  engine?: SearchEngineAdapter
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  modelValue: '',
  domains: () => [],
  groups: () => [],
  loading: false,
  engineDegraded: false,
  degradeText: SEARCH_PLACEHOLDER_TEXT,
  activeDomain: 'all',
  total: 0,
  page: 1,
  pageSize: 20,
  error: false,
  errorText: '',
  emptyText: SEARCH_EMPTY_TEXT,
  showPagination: false,
  access: undefined,
  engine: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [keyword: string]
  search: [keyword: string]
  open: [hit: SearchHit]
  retry: []
  'update:activeDomain': [key: string]
  'update:page': [page: number]
  'update:pageSize': [pageSize: number]
  fallback: [domains: SearchDomain[]]
}>()

const base = useBaseSearch({
  ready: props.ready,
  keyword: props.modelValue,
  domains: props.domains,
  access: props.access,
  engine: props.engine,
})
const keyword = ref(props.modelValue)
const activeDomain = ref(props.activeDomain)

watch(
  () => props.ready,
  (value) => base.setReady(value),
)
watch(
  () => props.modelValue,
  (value) => {
    keyword.value = value
    base.setKeyword(value)
  },
)
watch(
  () => props.domains,
  (value) => base.setDomains(value),
)
watch(
  () => props.engine,
  (value) => base.setEngine(value),
)
watch(
  () => props.access,
  (value) => base.setAccess(value),
)
watch(
  () => props.activeDomain,
  (value) => {
    activeDomain.value = value
    base.setActiveDomain(value)
  },
)

/** 展示域（宿主传入；注入引擎时沿用同一清单）。 */
const displayDomains = computed(() => props.domains)

/** 展示分组（注入引擎时以基类为准）。 */
const displayGroups = computed(() => (base.groups.value.length > 0 ? base.groups.value : props.groups))

/** 是否降级（占位）。 */
const degraded = computed(() => base.degraded.value)

/** 是否检索引擎降级。 */
const degradedEngine = computed(() => props.engineDegraded || base.engineDegraded.value)

/** 是否加载中。 */
const loading = computed(() => props.loading || base.phase.value === 'loading')

/** 是否错误态。 */
const hasError = computed(() => props.error || base.phase.value === 'error')

/** 输入变更。 */
function onInput(value: string): void {
  keyword.value = value
  base.setKeyword(value)
  emit('update:modelValue', value)
}

/** 提交搜索。 */
function submit(): void {
  emit('search', keyword.value)
  if (props.engine === undefined) {
    return
  }
  base.setKeyword(keyword.value)
  base.addRecentKeyword(keyword.value)
  if (activeDomain.value === 'log') {
    void base.searchLogs()
  } else if (activeDomain.value === 'file') {
    void base.searchFiles()
  } else {
    void base.search()
  }
}

/** 切换域 / 页签。 */
function switchDomain(key: string): void {
  activeDomain.value = key
  base.setActiveDomain(key)
  emit('update:activeDomain', key)
}

/** 打开命中。 */
function openHit(hit: SearchHit): void {
  emit('open', hit)
}
</script>

<template>
  <div
    class="bms-global-search"
    data-test="global-search"
    :data-ready="ready"
    :data-degraded="degraded"
  >
    <slot v-if="degraded" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div class="bms-global-search__bar" data-test="search-bar">
        <input
          type="search"
          data-test="keyword"
          :value="keyword"
          placeholder="搜索用户、部门、单据…"
          @input="onInput(($event.target as HTMLInputElement).value)"
          @keydown.enter="submit"
        />
        <button type="button" data-test="search" @click="submit">搜索</button>
      </div>
      <div v-if="displayDomains.length > 0" class="bms-global-search__domains" data-test="domains">
        <button
          type="button"
          data-test="domain-all"
          :data-active="activeDomain === 'all' || undefined"
          @click="switchDomain('all')"
        >
          全部
        </button>
        <button
          v-for="domain in displayDomains"
          :key="domain.key"
          type="button"
          :data-test="`domain-${domain.key}`"
          :data-active="activeDomain === domain.key || undefined"
          @click="switchDomain(domain.key)"
        >
          {{ domain.label }}
        </button>
        <button
          v-if="base.hasLogPermission.value"
          type="button"
          data-test="log-tab"
          :data-active="activeDomain === 'log' || undefined"
          @click="switchDomain('log')"
        >
          审计日志
        </button>
        <button
          v-if="base.hasFilePermission.value"
          type="button"
          data-test="file-tab"
          :data-active="activeDomain === 'file' || undefined"
          @click="switchDomain('file')"
        >
          文件
        </button>
      </div>
      <div v-if="degradedEngine" class="bms-global-search__degraded" data-test="engine-degraded">
        <span>{{ SEARCH_DEGRADE_TEXT }}</span>
        <button type="button" data-test="retry" @click="emit('retry')">重试</button>
        <button
          v-if="base.fallbackDomains.value.length > 0"
          type="button"
          data-test="fallback"
          @click="emit('fallback', base.fallbackDomains.value)"
        >
          {{ SEARCH_DEGRADE_FALLBACK_TEXT }}
        </button>
      </div>
      <div v-if="hasError" class="bms-global-search__error" data-test="error">
        <span>{{ errorText || '检索失败' }}</span>
        <button type="button" data-test="retry" @click="emit('retry')">重试</button>
      </div>
      <SearchLogTab
        v-else-if="activeDomain === 'log'"
        :ready="ready"
        :items="base.logItems.value"
        :total="base.logTotal.value"
        :page="base.logPage.value"
        :page-size="base.logPageSize.value"
        :log-type="base.logType.value"
        :time-range="base.logRange.value"
        @update:log-type="base.setLogType($event)"
        @update:time-range="base.setLogRange($event)"
        @update:page="base.setLogPage($event)"
        @search="base.searchLogs()"
        @retry="emit('retry')"
        @open="openHit"
      />
      <SearchFileTab
        v-else-if="activeDomain === 'file'"
        :ready="ready"
        :items="base.fileItems.value"
        :total="base.fileTotal.value"
        :page="base.filePage.value"
        :page-size="base.filePageSize.value"
        :file-type="base.fileType.value"
        @update:file-type="base.setFileType($event)"
        @update:page="base.setFilePage($event)"
        @search="base.searchFiles()"
        @retry="emit('retry')"
        @open="openHit"
      />
      <div v-else-if="loading" class="bms-global-search__hint" data-test="skeleton">检索中…</div>
      <div v-else-if="displayGroups.length > 0" class="bms-global-search__groups" data-test="groups">
        <section v-for="group in displayGroups" :key="group.key" :data-test="`group-${group.key}`">
          <h4>{{ group.label }}</h4>
          <ul>
            <SearchHitItem
              v-for="hit in group.items"
              :key="`${hit.docType}-${hit.bizId}`"
              :hit="hit"
              :keyword="keyword"
              :domains="displayDomains"
              @open="openHit"
            />
          </ul>
        </section>
      </div>
      <div v-else class="bms-global-search__empty" data-test="empty">
        <slot name="empty">{{ emptyText }}</slot>
      </div>
      <div v-if="showPagination && total > pageSize" class="bms-global-search__pagination" data-test="pagination">
        <button type="button" :disabled="page <= 1" @click="emit('update:page', page - 1)">上一页</button>
        <span>{{ page }}</span>
        <button type="button" @click="emit('update:page', page + 1)">下一页</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bms-global-search {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bms-global-search__bar {
  display: flex;
  gap: 8px;
}
.bms-global-search__bar input {
  flex: 1 1 auto;
  padding: 4px 10px;
  font-size: 13px;
  color: var(--bms-color-text);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: 6px;
  outline: none;
}
.bms-global-search__domains {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--bms-color-border);
}
.bms-global-search__domains button {
  padding: 4px 2px;
  font-size: 13px;
  color: var(--bms-color-text-secondary);
  cursor: pointer;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
}
.bms-global-search__domains button[data-active] {
  color: var(--bms-color-primary);
  border-bottom-color: var(--bms-color-primary);
}
.bms-global-search__degraded {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
  font-size: 12px;
  color: var(--bms-search-highlight-color);
  background: var(--bms-search-degrade-bg);
  border: 1px solid var(--bms-search-degrade-border);
  border-radius: 6px;
}
.bms-global-search__error {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--bms-color-danger);
}
.bms-global-search__groups section h4 {
  margin: 8px 0;
  font-size: 13px;
  color: var(--bms-color-text-secondary);
}
.bms-global-search__groups ul {
  padding: 0;
  margin: 0;
  list-style: none;
  border: 1px solid var(--bms-color-border);
  border-radius: 6px;
}
.bms-global-search__hint,
.bms-global-search__empty {
  padding: 30px;
  font-size: 13px;
  color: var(--bms-color-text-secondary);
  text-align: center;
}
.bms-global-search__pagination {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  font-size: 12px;
}
</style>
