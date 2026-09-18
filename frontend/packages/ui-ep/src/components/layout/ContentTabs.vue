<script setup lang="ts">
// 内容页签：`el-tabs` 薄封装；状态经核心页签能力基类 `BaseTabs`。
import { BaseTabs } from '@bms/core'
import { ElTabPane, ElTabs, type TabPaneName } from 'element-plus'
import { computed, watch } from 'vue'

/** 页签项。 */
export interface ContentTabItem {
  /** 键。 */
  key: string
  /** 标题。 */
  title: string
  /** 是否禁用。 */
  disabled?: boolean
}

/** 具体页签状态（可实例化）。 */
class ContentTabsState extends BaseTabs {}

interface Props {
  /** 当前激活键。 */
  modelValue: string
  /** 页签项。 */
  tabs: ContentTabItem[]
  /** 形态。 */
  type?: 'line' | 'card' | 'border-card'
  /** 懒加载面板。 */
  lazy?: boolean
}

const props = withDefaults(defineProps<Props>(), { type: 'line', lazy: true })
const emit = defineEmits<{ 'update:modelValue': [key: string]; change: [key: string] }>()

const state = new ContentTabsState()
watch(
  () => props.tabs,
  (tabs) => {
    for (const tab of tabs) {
      state.open({ key: tab.key, title: tab.title })
    }
  },
  { immediate: true, deep: true },
)
watch(
  () => props.modelValue,
  (key) => state.activate(key),
  { immediate: true },
)

/** `el-tabs` 形态（`line` 映射为空串）。 */
const tabType = computed(() => (props.type === 'line' ? '' : props.type))

function onChange(name: TabPaneName): void {
  const key = String(name)
  state.activate(key)
  emit('update:modelValue', key)
  emit('change', key)
}
</script>

<template>
  <el-tabs class="bms-content-tabs" :model-value="modelValue" :type="tabType" @tab-change="onChange">
    <el-tab-pane v-for="tab in tabs" :key="tab.key" :name="tab.key" :label="tab.title" :disabled="tab.disabled" :lazy="lazy">
      <slot :name="tab.key" />
    </el-tab-pane>
  </el-tabs>
</template>
