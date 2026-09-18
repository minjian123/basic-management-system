<script setup lang="ts">
// 全局搜索（占位版，07_01）：契约先行冻结；数据通路未就绪时不请求、降级提示。
import { ref, watch } from 'vue'

import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'

/** 可检索域。 */
export interface SearchDomain {
  /** 域标识。 */
  key: string
  /** 域名称。 */
  label: string
}

/** 命中项。 */
export interface SearchHit {
  /** 文档类型。 */
  docType: string
  /** 业务 ID。 */
  bizId: string
  /** 标题（可含高亮标签）。 */
  title: string
  /** 高亮片段（白名单清洗后渲染）。 */
  highlight?: string
  /** 更新时间。 */
  updatedAt?: string
}

/** 分组结果。 */
export interface SearchGroup {
  /** 域标识。 */
  key: string
  /** 域名称。 */
  label: string
  /** 命中项。 */
  items: SearchHit[]
}

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
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  modelValue: '',
  domains: () => [],
  groups: () => [],
  loading: false,
  engineDegraded: false,
  degradeText: '搜索服务未就绪（占位）',
})

const emit = defineEmits<{
  'update:modelValue': [keyword: string]
  search: [keyword: string]
  open: [hit: SearchHit]
  retry: []
}>()

const placeholder = useDisplayPlaceholder({ ready: props.ready })
const keyword = ref(props.modelValue)

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

watch(
  () => props.modelValue,
  (next) => {
    keyword.value = next
  },
)

function onInput(value: string): void {
  keyword.value = value
  emit('update:modelValue', value)
}

function submit(): void {
  emit('search', keyword.value)
}
</script>

<template>
  <div class="bms-global-search" :data-ready="placeholder.ready.value" :data-degraded="placeholder.degraded.value">
    <slot v-if="placeholder.degraded.value" name="degrade">
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
      <div v-if="domains.length > 0" class="bms-global-search__domains" data-test="domains">
        <span v-for="domain in domains" :key="domain.key" :data-test="`domain-${domain.key}`">
          {{ domain.label }}
        </span>
      </div>
      <div v-if="engineDegraded" class="bms-global-search__degraded" data-test="engine-degraded">
        <span>检索服务降级，结果可能不完整</span>
        <button type="button" data-test="retry" @click="emit('retry')">重试</button>
      </div>
      <div v-if="groups.length > 0" class="bms-global-search__groups" data-test="groups">
        <section v-for="group in groups" :key="group.key" :data-test="`group-${group.key}`">
          <h4>{{ group.label }}</h4>
          <ul>
            <li
              v-for="hit in group.items"
              :key="`${hit.docType}-${hit.bizId}`"
              :data-test="`hit-${hit.docType}-${hit.bizId}`"
              @click="emit('open', hit)"
            >
              <span data-test="hit-title">{{ hit.title }}</span>
            </li>
          </ul>
        </section>
      </div>
      <div v-else class="bms-global-search__empty" data-test="empty">
        <slot name="empty">未找到相关内容</slot>
      </div>
    </template>
  </div>
</template>
