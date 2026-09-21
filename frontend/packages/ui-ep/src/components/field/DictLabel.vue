<script setup lang="ts">
// 字典标签回显件（06_06）：单值 / 多值标签翻译（缓存命中直出、未命中异步回填不阻塞）、空值占位、标签形态。
import { DICT_EMPTY_VALUE, DICT_JOIN, type BaseDictStore, type DictSourceAdapter } from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseDictSelect } from '../../composables/useBaseDictSelect'

interface Props {
  /** 值（单值 / 数组）。 */
  value?: string | number | (string | number)[] | undefined
  /** 字典类型码。 */
  dictType?: string
  /** 字典数据源（未注入即占位零请求，原值展示）。 */
  source?: DictSourceAdapter
  /** 缓存能力（缺省由投影内建；跨件共享请外部传入）。 */
  store?: BaseDictStore
  /** 数据通路是否就绪（缺省 `true`：未注入数据源时原值展示）。 */
  ready?: boolean
  /** 多值连接符（缺省「、」）。 */
  separator?: string
  /** 空值占位（缺省「—」）。 */
  emptyText?: string
  /** 标签形态。 */
  tag?: boolean
  /** 标签形态是否展示语义色点。 */
  showColor?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  value: undefined,
  dictType: '',
  source: undefined,
  store: undefined,
  ready: true,
  separator: DICT_JOIN,
  emptyText: DICT_EMPTY_VALUE,
  tag: false,
  showColor: false,
})

const api = useBaseDictSelect({
  ready: props.ready,
  dictType: props.dictType,
  source: props.source,
  store: props.store,
  multiple: true,
})

watch(
  () => props.ready,
  (next) => api.setReady(next),
)
watch(
  () => props.dictType,
  (next) => api.setDictType(next),
)
watch(
  () => props.value,
  (next) => api.syncValue(next),
  { immediate: true },
)

/** 值列表（归一）。 */
const values = computed<string[]>(() => {
  const current = props.value
  if (current === undefined || current === null || current === '') {
    return []
  }
  return (Array.isArray(current) ? current : [current]).map((entry) => String(entry))
})

/** 展示项（label 未解析回退原值）。 */
const items = ref<{ value: string; label: string; resolved: boolean }[]>([])

watch(
  values,
  (next) => {
    items.value = next.map((value) => {
      const label = api.labelOf(value)
      return { value, label: label ?? value, resolved: label !== undefined }
    })
  },
  { immediate: true },
)

watch(
  () => api.items.value,
  () => {
    items.value = values.value.map((value) => {
      const label = api.labelOf(value)
      return { value, label: label ?? value, resolved: label !== undefined }
    })
  },
)

/** 文本（未解析时显示原值，不阻塞渲染）。 */
const text = computed(() => items.value.map((item) => item.label).join(props.separator))

/**
 * 条目语义色点类。
 *
 * @param value 条目值。
 */
function colorClass(value: string): string {
  const color = api.items.value.find((item) => item.value === value)
  return color?.color === undefined ? '' : `bms-dict-label__dot--${color.color}`
}
</script>

<template>
  <span class="bms-dict-label" :data-degraded="api.degraded.value" data-test="dict-label">
    <template v-if="items.length === 0">{{ emptyText }}</template>
    <template v-else-if="tag">
      <span v-for="item in items" :key="item.value" class="bms-dict-label__tag" :data-test="`dict-label-item-${item.value}`">
        <span v-if="showColor" class="bms-dict-label__dot" :class="colorClass(item.value)" />
        {{ item.label }}
      </span>
    </template>
    <template v-else>
      <slot :items="items" :text="text">{{ text }}</slot>
    </template>
  </span>
</template>

<style scoped>
.bms-dict-label {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm);
  color: var(--bms-color-text);
}
.bms-dict-label__tag {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
  padding: 0 var(--bms-spacing-sm);
  background: var(--bms-dict-tag-bg);
  border: 1px solid var(--bms-dict-border);
  border-radius: var(--bms-radius-sm);
}
.bms-dict-label__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--bms-color-text-secondary);
}
.bms-dict-label__dot--success {
  background: var(--bms-color-success);
}
.bms-dict-label__dot--warning {
  background: var(--bms-color-warning);
}
.bms-dict-label__dot--danger {
  background: var(--bms-color-danger);
}
.bms-dict-label__dot--info {
  background: var(--bms-color-info);
}
.bms-dict-label__dot--primary {
  background: var(--bms-color-primary);
}
</style>
