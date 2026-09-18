<script setup lang="ts">
// 树形主从布局：左侧树（可搜索）+ 右侧主区，选中联动；空树 / 未选中走空态。
import { ElInput, ElTree } from 'element-plus'
import { ref, watch } from 'vue'

import { useBaseLayout } from '../../composables/useBaseLayout'
import { useBaseTreeData } from '../../composables/useBaseTreeData'
import EmptyState from '../feedback/EmptyState.vue'
import SplitPane from './SplitPane.vue'

/** 树节点。 */
export interface MasterTreeNode {
  /** 节点键。 */
  key: string
  /** 节点文案。 */
  label: string
  /** 子节点。 */
  children?: MasterTreeNode[]
}

interface Props {
  /** 树数据。 */
  treeData: MasterTreeNode[]
  /** 选中节点键。 */
  selectedKey?: string
  /** 树区宽度。 */
  treeWidth?: number
  /** 最小宽度。 */
  minTreeWidth?: number
  /** 最大宽度。 */
  maxTreeWidth?: number
  /** 是否可调分割。 */
  resizable?: boolean
  /** 搜索占位。 */
  filterPlaceholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  selectedKey: '',
  treeWidth: 280,
  minTreeWidth: 200,
  maxTreeWidth: 480,
  resizable: true,
  filterPlaceholder: '请输入关键字过滤',
})

const emit = defineEmits<{
  select: [node: MasterTreeNode]
  'update:selectedKey': [key: string]
  'tree-width-change': [width: number]
}>()

const { hidden } = useBaseLayout()
const { setNodes, setFilterText, state: treeState } = useBaseTreeData()
const keyword = ref('')
const treeRef = ref<InstanceType<typeof ElTree>>()

watch(
  () => props.treeData,
  (data) => setNodes(data),
  { immediate: true },
)

watch(keyword, (value) => {
  setFilterText(value)
  treeRef.value?.filter(value)
})

watch(
  () => props.selectedKey,
  (value) => {
    treeRef.value?.setCurrentKey(value)
  },
)

function filterNode(value: string, data: Record<string, unknown>): boolean {
  if (!value) {
    return true
  }
  return String(data.label ?? '').includes(value)
}

function onNodeClick(node: MasterTreeNode): void {
  emit('select', node)
  emit('update:selectedKey', node.key)
}
</script>

<template>
  <split-pane
    v-show="!hidden"
    class="bms-tree-master-detail"
    :model-value="treeWidth"
    :min="minTreeWidth"
    :max="maxTreeWidth"
    :disabled="!resizable"
    @update:model-value="emit('tree-width-change', $event)"
  >
    <template #first>
      <div class="bms-tree-master-detail__tree">
        <div class="bms-tree-master-detail__tree-header">
          <slot name="tree-header">
            <el-input v-model="keyword" :placeholder="filterPlaceholder" clearable />
          </slot>
        </div>
        <empty-state v-if="treeState === 'empty'" type="data" />
        <el-tree
          v-else
          ref="treeRef"
          :data="treeData"
          node-key="key"
          highlight-current
          :filter-node-method="filterNode"
          @node-click="onNodeClick"
        />
      </div>
    </template>
    <empty-state v-if="!selectedKey" type="unselected" />
    <slot v-else />
  </split-pane>
</template>
