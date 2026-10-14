<script setup lang="ts">
// 动态字典件（08-4-4，新口径）：按字典类型动态渲染字典数据（供数据选择 / 区域 / 匹配使用）；取数经字典组件基类投影。
import type { BaseDictStore, DictSourceAdapter } from '@bms/core'
import { ElCheckbox, ElRadio } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseDictSelect, type DictSelectValue } from '../../composables/useBaseDictSelect'

interface Props {
  /** 字典类型码。 */
  dataSourceKey?: string
  /** 选中值（`v-model`）。 */
  modelValue?: string | string[]
  /** 是否多选。 */
  multiple?: boolean
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 字典数据源（注入式；未注入即占位零请求）。 */
  source?: DictSourceAdapter
  /** 字典缓存能力。 */
  store?: BaseDictStore
  /** 是否禁用。 */
  disabled?: boolean
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  dataSourceKey: '',
  modelValue: '',
  multiple: false,
  ready: false,
  source: undefined,
  store: undefined,
  disabled: false,
  emptyText: '暂无字典数据',
})

const emit = defineEmits<{ 'update:modelValue': [value: string | string[]] }>()

const { items, degraded, disabled: effectiveDisabled, setDictType, setSource, setReady, syncValue, toggle, load } =
  useBaseDictSelect({
    ready: props.ready,
    dataSourceKey: props.dataSourceKey,
    multiple: props.multiple,
    value: props.modelValue,
    source: props.source,
    store: props.store,
    disabled: props.disabled,
  })

/** 选中值集合。 */
const selected = computed<Set<string>>(() =>
  new Set(Array.isArray(props.modelValue) ? props.modelValue : props.modelValue === '' ? [] : [props.modelValue]),
)

watch(
  () => props.dataSourceKey,
  (value) => {
    setDictType(value)
    void load()
  },
  { immediate: true },
)

watch(
  () => props.source,
  (value) => setSource(value),
)

watch(
  () => props.ready,
  (value) => setReady(value),
)

watch(
  () => props.modelValue,
  (value) => syncValue(value as DictSelectValue),
  { immediate: true },
)

/** 切换字典数据选择。 */
function onToggle(value: string): void {
  if (props.multiple) {
    const next = new Set(selected.value)
    if (next.has(value)) {
      next.delete(value)
    } else {
      next.add(value)
    }
    emit('update:modelValue', [...next])
  } else {
    emit('update:modelValue', selected.value.has(value) ? '' : value)
  }
  toggle(value)
}
</script>

<template>
  <div class="bms-dynamic-dict" data-test="dynamic-dict" :data-degraded="degraded || undefined">
    <p v-if="items.length === 0" class="bms-dynamic-dict__empty" data-test="empty">{{ emptyText }}</p>
    <div class="bms-dynamic-dict__items">
      <label
        v-for="item in items"
        :key="item.value"
        class="bms-dynamic-dict__item"
        :data-test="`dict-item-${item.value}`"
      >
        <el-checkbox
          v-if="multiple"
          :model-value="selected.has(item.value)"
          :disabled="effectiveDisabled"
          @update:model-value="onToggle(item.value)"
        />
        <el-radio
          v-else
          :model-value="selected.has(item.value)"
          :disabled="effectiveDisabled"
          @update:model-value="onToggle(item.value)"
        >
          {{ item.label }}
        </el-radio>
      </label>
    </div>
  </div>
</template>

<style scoped>
.bms-dynamic-dict {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  min-width: 0;
}

.bms-dynamic-dict__items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-1) var(--bms-space-4);
}

.bms-dynamic-dict__item {
  display: inline-flex;
  align-items: center;
  min-height: var(--bms-control-height);
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
}

.bms-dynamic-dict__empty {
  margin: 0;
  padding: var(--bms-space-4) 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  text-align: center;
}
</style>

