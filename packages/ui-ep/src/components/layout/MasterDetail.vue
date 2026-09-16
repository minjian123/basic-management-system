<script setup lang="ts">
/**
 * 树形主从布局壳：左主（树）右从（列表 / 详情）。
 *
 * 契约见《组件设计 · 树形主从布局》§3：可调分割（`resizable`）、折叠、窄屏抽屉、空态占位；
 * 主树渲染与维护入口归 `MasterTree`（`master` 插槽），从区（表格 / 详情）由使用方提供
 * （`detail` 插槽，`hasSelection=false` 且 `emptyText` 非空时显示占位）。
 */

import { ElButton, ElDrawer } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/drawer/style/css'

import { useI18n } from 'vue-i18n'
import { computed, onBeforeUnmount, onMounted, ref, useAttrs } from 'vue'

import { useComponentBase } from '@bms/vue'
import EmptyState from '../feedback/EmptyState.vue'

import { useMasterDetail, type TreeNode } from './useMasterDetail'

const props = withDefaults(
  defineProps<{
    /** 主区宽度（px 或百分比；`resizable` 时为初始值） */
    masterWidth?: number | string
    /** 可拖动分割条调整比例 */
    resizable?: boolean
    /** 主区可折叠 / 展开 */
    collapsible?: boolean
    /** 主区标题（如「组织」；窄屏抽屉标题与唤起按钮文案） */
    masterTitle?: string
    /** 从区未选中占位文案 */
    emptyText?: string
    /** 分割比例 / 折叠持久化键（用户偏好） */
    splitStorageKey?: string
    /** 从区是否已有选中（false 且 `emptyText` 非空时显示占位） */
    hasSelection?: boolean
  }>(),
  {
    masterWidth: 260,
    resizable: false,
    collapsible: true,
    masterTitle: '',
    emptyText: '',
    splitStorageKey: '',
    hasSelection: true,
  },
)

const emit = defineEmits<{
  'master-select': [node: TreeNode | null]
  'collapse-change': [collapsed: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'master-detail' })
const { t } = useI18n()
const attrs = useAttrs()

const master = useMasterDetail({
  splitStorageKey: props.splitStorageKey,
  collapsible: props.collapsible,
})

const containerRef = ref<HTMLElement | null>(null)
const isNarrow = ref(false)
let mql: MediaQueryList | null = null

function onMqlChange(event: MediaQueryListEvent): void {
  isNarrow.value = event.matches
}

onMounted(() => {
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    mql = window.matchMedia('(max-width: 767px)')
    isNarrow.value = mql.matches
    mql.addEventListener('change', onMqlChange)
  }
})

onBeforeUnmount(() => {
  mql?.removeEventListener('change', onMqlChange)
})

const masterStyle = computed(() => {
  if (props.resizable) {
    return { width: `${Math.round(master.ratio.value * 100)}%` }
  }
  return {
    width: typeof props.masterWidth === 'number' ? `${props.masterWidth}px` : props.masterWidth,
  }
})

const dragging = ref(false)

function onSplitterDown(event: PointerEvent): void {
  if (!props.resizable) {
    return
  }
  dragging.value = true
  ;(event.target as HTMLElement).setPointerCapture?.(event.pointerId)
}

function onSplitterMove(event: PointerEvent): void {
  if (!dragging.value) {
    return
  }
  const rect = containerRef.value?.getBoundingClientRect()
  if (!rect || rect.width === 0) {
    return
  }
  master.setRatio((event.clientX - rect.left) / rect.width)
}

function onSplitterUp(event: PointerEvent): void {
  if (!dragging.value) {
    return
  }
  dragging.value = false
  ;(event.target as HTMLElement).releasePointerCapture?.(event.pointerId)
}

function toggleCollapse(): void {
  master.toggleCollapse()
  emit('collapse-change', master.collapsed.value)
}

const showDetailEmpty = computed(() => !props.hasSelection && Boolean(props.emptyText))

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('master-detail'), cls], style: sty, ...rest })
})

defineExpose({
  openMaster: master.openDrawer,
  closeMaster: master.closeDrawer,
})
</script>

<template>
  <div ref="containerRef" v-bind="elAttrs" :class="base.nsClass('master-detail')">
    <aside
      v-if="!isNarrow && !master.collapsed.value"
      :class="base.nsClass('master-detail-master')"
      :style="masterStyle"
    >
      <div v-if="masterTitle" :class="base.nsClass('master-detail-title')">{{ masterTitle }}</div>
      <div :class="base.nsClass('master-detail-master-body')">
        <slot name="master" :master="master" />
      </div>
    </aside>

    <div
      v-if="resizable && !isNarrow && !master.collapsed.value"
      :class="[base.nsClass('master-detail-splitter'), dragging && 'is-dragging']"
      role="separator"
      aria-orientation="vertical"
      @pointerdown="onSplitterDown"
      @pointermove="onSplitterMove"
      @pointerup="onSplitterUp"
      @pointercancel="onSplitterUp"
    />

    <div :class="base.nsClass('master-detail-detail')">
      <div :class="base.nsClass('master-detail-detail-toolbar')">
        <el-button v-if="isNarrow" size="small" @click="master.openDrawer">
          {{ masterTitle || t('tree.browse') }}
        </el-button>
        <el-button v-if="collapsible" size="small" text @click="toggleCollapse">
          {{ master.collapsed.value ? t('tree.expand') : t('tree.collapse') }}
        </el-button>
      </div>
      <EmptyState v-if="showDetailEmpty" type="custom" :title="emptyText" size="small" />
      <slot v-else name="detail" />
    </div>

    <el-drawer
      v-model="master.drawerVisible.value"
      direction="ltr"
      :title="masterTitle || t('tree.browse')"
      size="280px"
    >
      <slot name="master" :master="master" />
    </el-drawer>
  </div>
</template>

<style scoped>
.bms-master-detail {
  display: flex;
  align-items: stretch;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.bms-master-detail-master {
  display: flex;
  flex: none;
  flex-direction: column;
  min-width: 0;
  border-right: 1px solid var(--bms-color-border);
  background: var(--bms-color-bg);
}

.bms-master-detail-title {
  padding: var(--bms-space-2) var(--bms-space-3);
  border-bottom: 1px solid var(--bms-color-border);
  font-size: var(--bms-font-size-sm);
  font-weight: var(--bms-font-weight-semibold);
}

.bms-master-detail-master-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.bms-master-detail-splitter {
  flex: none;
  width: 5px;
  cursor: col-resize;
  background: transparent;
}

.bms-master-detail-splitter:hover,
.bms-master-detail-splitter.is-dragging {
  background: var(--bms-color-primary);
  opacity: 0.35;
}

.bms-master-detail-detail {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.bms-master-detail-detail-toolbar {
  display: flex;
  gap: var(--bms-space-1);
  align-items: center;
}
</style>
