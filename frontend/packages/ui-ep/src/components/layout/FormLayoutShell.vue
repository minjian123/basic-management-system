<script setup lang="ts">
// 表单框架壳：列表固定页签 + 详情多开双层页签（复用 `03_03` 的 `DualTabs`）。
import type { TabNavItem } from '../../composables/useTabNav'
import { useBaseLayout } from '../../composables/useBaseLayout'
import DualTabs from './DualTabs.vue'

interface Props {
  /** 列表页签（固定）。 */
  listTab: TabNavItem
  /** 详情页签。 */
  detailTabs: TabNavItem[]
  /** 激活页签键。 */
  activeDetailKey: string
  /** 详情打开方式。 */
  openMode?: 'tab' | 'drawer' | 'page'
  /** 详情页签是否参与缓存。 */
  cacheDetail?: boolean
}

const props = withDefaults(defineProps<Props>(), { openMode: 'tab', cacheDetail: false })

const emit = defineEmits<{
  select: [key: string]
  open: [record: unknown]
  save: [record: unknown]
  delete: [record: unknown]
  refresh: []
}>()

const { hidden } = useBaseLayout()

function onSelect(level: 'primary' | 'secondary', key: string): void {
  emit('select', level === 'primary' ? props.listTab.key : key)
}
</script>

<template>
  <div v-show="!hidden" class="bms-form-shell" :data-open-mode="openMode">
    <dual-tabs
      class="bms-form-shell__tabs"
      :primary="[listTab]"
      :primary-key="listTab.key"
      :secondary="detailTabs"
      :secondary-key="activeDetailKey"
      @select="onSelect"
    />
    <div class="bms-form-shell__body">
      <slot v-if="activeDetailKey === listTab.key" name="list" />
      <slot v-else name="detail" :detail-key="activeDetailKey" />
    </div>
  </div>
</template>
