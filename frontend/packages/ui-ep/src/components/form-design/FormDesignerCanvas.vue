<script setup lang="ts">
// 表单设计器画布（08_06）：三视图（主表 / 查询区 / 明细区）+ 分区 / 列数 / 跨列 / 排序。
// 由 FormDesigner 异步懒加载的独立分包入口（分包标记 `data-subpackage="designer"`）。
// 拖拽经 SortableJS：件层只把列表事件适配为落点 / 排序事件上抛，落点判定归编排基类与领域纯函数。
import type { FormField, LayoutDetailColumn, LayoutSection, LayoutDetailColumnInput } from '@bms/core'
import { normalizeColumns } from '@bms/core'
import { ElButton, ElOption, ElRadioButton, ElRadioGroup, ElSelect, ElTag } from 'element-plus'
import { computed, ref, watch } from 'vue'
import draggable from 'vuedraggable'

import { useBaseDataState } from '../../composables/useBaseDataState'
import type { DesignerSelection, FormLayoutShape } from './FormDesigner.vue'

/** 画布视图。 */
export type DesignerView = 'main' | 'query' | 'detail'

/** 拖拽落点事件载荷。 */
export interface DesignerMoveEvent {
  /** 字段键。 */
  fieldKey: string
  /** 来源分区键。 */
  fromSectionKey: string
  /** 目标分区键。 */
  toSectionKey: string
  /** 目标索引（已按移出后列表修正）。 */
  index: number
  /** 是否跨分区。 */
  crossZone: boolean
}

interface Props {
  /** 字段清单。 */
  fields?: FormField[]
  /** 当前层级布局。 */
  layout?: FormLayoutShape | undefined
  /** 只读（平台默认层级 / 无权限）。 */
  readOnly?: boolean
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 画布选中对象。 */
  selection?: DesignerSelection | null
  /** 视图（缺省主表）。 */
  view?: DesignerView
  /** 已注册字段类型（空数组视为不限；未注册类型置灰）。 */
  registeredTypes?: readonly string[]
}

const props = withDefaults(defineProps<Props>(), {
  fields: () => [],
  layout: undefined,
  readOnly: false,
  dirty: false,
  selection: null,
  view: 'main',
  registeredTypes: () => [],
})

const emit = defineEmits<{
  select: [target: DesignerSelection | null]
  move: [input: DesignerMoveEvent]
  'columns-change': [payload: { sectionKey: string; columns: number }]
  'colspan-change': [payload: { fieldKey: string }]
  'add-section': []
  'remove-section': [payload: { sectionKey: string }]
  reorder: [payload: { view: DesignerView; keys: string[] }]
}>()

/** 本地可写分区副本（Sortable 就地重排，随布局同步）。 */
const sections = ref<LayoutSection[]>([])
/** 本地可写查询区键副本。 */
const queryKeys = ref<string[]>([])
/** 本地可写明细列副本。 */
const detailColumns = ref<LayoutDetailColumn[]>([])

watch(
  () => props.layout,
  (layout) => {
    sections.value = (layout?.main.sections ?? []).map((section: LayoutSection) => ({ ...section, fields: section.fields.map((field) => ({ ...field })) }))
    queryKeys.value = [...(layout?.query?.fields ?? [])]
    detailColumns.value = (layout?.detail?.columns ?? []).map((column: LayoutDetailColumnInput) =>
      typeof column === 'string' ? { key: column } : { key: column.key ?? '', width: column.width },
    )
  },
  { immediate: true, deep: true },
)

/** 字段名映射。 */
const labelOf = computed(() => new Map(props.fields.map((field) => [field.key, field.label])))
/** 当前选中项键（用于高亮）。 */
const selectedKey = computed(() => props.selection?.key ?? '')
/** 字段调板与画布共用的拖拽组。 */
const DRAG_GROUP = 'designer-fields'

/** 画布数据状态（分区空 → `empty`，有分区 → `ready`）。 */
const { state, setState } = useBaseDataState()
watch(
  () => props.layout?.main.sections?.length ?? 0,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)

/**
 * 字段是否可拖入（未注册类型 / 停用 / 建列失败不可拖入）。
 *
 * @param key 字段键。
 */
function draggableField(key: string): boolean {
  const field = props.fields.find((item) => item.key === key)
  if (field === undefined) {
    return true
  }
  if (field.disabled === true || (field.status !== undefined && field.status !== 'active')) {
    return false
  }
  return props.registeredTypes.length === 0 || props.registeredTypes.includes(field.type)
}

/**
 * 字段名（未知名回落键）。
 *
 * @param key 字段键。
 */
function fieldLabel(key: string): string {
  return labelOf.value.get(key) ?? key
}

/**
 * 分区内 / 跨分区拖拽结束：按移出后索引修正并上抛落点。
 *
 * @param section 目标分区。
 * @param event Sortable 结束事件。
 */
function onSectionEnd(section: LayoutSection, event: { item?: HTMLElement; oldIndex?: number; newIndex?: number; from?: HTMLElement }): void {
  const fieldKey = event.item?.dataset.fieldKey ?? ''
  if (fieldKey === '') {
    return
  }
  const fromKey = event.from?.dataset.sectionKey ?? section.key
  const oldIndex = event.oldIndex ?? 0
  const newIndex = event.newIndex ?? oldIndex
  const crossZone = fromKey !== section.key
  emit('move', {
    fieldKey,
    fromSectionKey: fromKey,
    toSectionKey: section.key,
    index: crossZone || newIndex <= oldIndex ? newIndex : Math.max(newIndex - 1, 0),
    crossZone,
  })
}

/**
 * 列表排序归一（移出 + 插入）。
 *
 * @param keys 原键列表。
 * @param oldIndex 原索引。
 * @param newIndex 新索引。
 */
function reorderKeys(keys: readonly string[], oldIndex: number, newIndex: number): string[] {
  const next = [...keys]
  const [moved] = next.splice(oldIndex, 1)
  if (moved === undefined) {
    return next
  }
  next.splice(Math.min(newIndex, next.length), 0, moved)
  return next
}

/**
 * 查询区排序。
 *
 * @param event Sortable 结束事件。
 */
function onQueryReorder(event: { item?: HTMLElement; oldIndex?: number; newIndex?: number }): void {
  const key = event.item?.dataset.fieldKey ?? ''
  if (key === '') {
    return
  }
  emit('reorder', { view: 'query', keys: reorderKeys(queryKeys.value, event.oldIndex ?? 0, event.newIndex ?? 0) })
}

/**
 * 明细区排序。
 *
 * @param event Sortable 结束事件。
 */
function onDetailReorder(event: { item?: HTMLElement; oldIndex?: number; newIndex?: number }): void {
  const key = event.item?.dataset.fieldKey ?? ''
  if (key === '') {
    return
  }
  emit('reorder', {
    view: 'detail',
    keys: reorderKeys(
      detailColumns.value.map((column) => column.key),
      event.oldIndex ?? 0,
      event.newIndex ?? 0,
    ),
  })
}
</script>

<template>
  <div
    class="bms-designer-canvas"
    data-test="designer-canvas"
    data-subpackage="designer"
    :data-view="view"
    :data-state="state"
    :data-readonly="readOnly"
    :data-dirty="dirty"
  >
    <div class="bms-designer-canvas__views" data-test="designer-views">
      <el-radio-group :model-value="view" :disabled="readOnly">
        <el-radio-button value="main" data-test="view-main">主表</el-radio-button>
        <el-radio-button value="query" data-test="view-query">查询区</el-radio-button>
        <el-radio-button value="detail" data-test="view-detail">明细区</el-radio-button>
      </el-radio-group>
    </div>

    <template v-if="view === 'main'">
      <p v-if="sections.length === 0" class="bms-designer-canvas__empty" data-test="canvas-empty">
        暂无布局分区，点「＋ 分区」开始
      </p>
      <draggable
        v-for="section in sections"
        :key="section.key"
        v-model="section.fields"
        :group="DRAG_GROUP"
        :disabled="readOnly"
        item-key="key"
        tag="div"
        class="bms-designer-canvas__section"
        :data-section-key="section.key"
        :data-test="`designer-section-${section.key}`"
        :data-columns="section.columns"
        :data-selected="selectedKey === section.key || undefined"
        @end="onSectionEnd(section, $event as never)"
      >
        <template #header>
          <div class="bms-designer-canvas__section-head">
            <el-button
              link
              data-test="section-title"
              @click="emit('select', { kind: 'section', key: section.key })"
            >
              {{ section.title || '未命名分区' }}
            </el-button>
            <el-select
              :data-test="`section-columns-${section.key}`"
              :model-value="section.columns"
              :disabled="readOnly"
              size="small"
              @update:model-value="
                emit('columns-change', { sectionKey: section.key, columns: normalizeColumns($event) })
              "
            >
              <el-option v-for="count in [1, 2, 3]" :key="count" :label="`${count} 列`" :value="count" />
            </el-select>
            <span class="bms-designer-canvas__section-count">{{ section.fields.length }} 字段</span>
            <el-button
              link
              type="danger"
              :data-test="`section-remove-${section.key}`"
              :disabled="readOnly"
              @click="emit('remove-section', { sectionKey: section.key })"
            >
              删除分区
            </el-button>
          </div>
        </template>
        <template #item="{ element }">
          <div
            class="bms-designer-canvas__field"
            :data-test="`designer-field-${element.key}`"
            :data-field-key="element.key"
            :data-colspan="element.colSpan || undefined"
            :data-selected="selectedKey === element.key || undefined"
            :data-draggable="draggableField(element.key)"
            @click.stop="emit('select', { kind: 'field', key: element.key })"
          >
            <span class="bms-designer-canvas__field-label">{{ fieldLabel(element.key) }}</span>
            <el-tag v-if="element.colSpan" size="small" type="warning">跨整行</el-tag>
            <el-button
              link
              size="small"
              :data-test="`field-colspan-${element.key}`"
              :disabled="readOnly"
              @click.stop="emit('colspan-change', { fieldKey: element.key })"
            >
              跨整行
            </el-button>
          </div>
        </template>
        <template #footer>
          <p v-if="section.fields.length === 0" class="bms-designer-canvas__drop-empty">拖字段到此处</p>
        </template>
      </draggable>
      <el-button :disabled="readOnly" data-test="section-add" @click="emit('add-section')">＋ 分区</el-button>
    </template>

    <template v-else-if="view === 'query'">
      <p v-if="queryKeys.length === 0" class="bms-designer-canvas__empty" data-test="query-empty">
        查询区未配置（回退默认前 3 项）
      </p>
      <draggable
        v-else
        v-model="queryKeys"
        :disabled="readOnly"
        item-key="0"
        tag="div"
        class="bms-designer-canvas__query"
        data-test="query-list"
        @end="onQueryReorder($event as never)"
      >
        <template #item="{ element }">
          <div class="bms-designer-canvas__row" :data-test="`query-field-${element}`" :data-field-key="element">
            {{ fieldLabel(element) }}
          </div>
        </template>
      </draggable>
    </template>

    <template v-else>
      <p v-if="detailColumns.length === 0" class="bms-designer-canvas__empty" data-test="detail-empty">
        明细区未配置（回退默认列）
      </p>
      <draggable
        v-else
        v-model="detailColumns"
        :disabled="readOnly"
        item-key="key"
        tag="div"
        class="bms-designer-canvas__detail"
        data-test="detail-list"
        @end="onDetailReorder($event as never)"
      >
        <template #item="{ element }">
          <div class="bms-designer-canvas__row" :data-test="`detail-column-${element.key}`" :data-field-key="element.key">
            {{ fieldLabel(element.key) }}
          </div>
        </template>
      </draggable>
    </template>
  </div>
</template>

<style scoped>
.bms-designer-canvas {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  padding: var(--bms-space-3);
  min-width: 0;
  min-height: 420px;
  background: var(--bms-designer-canvas-bg);
  border-radius: var(--bms-radius-md);
}

.bms-designer-canvas__views {
  display: flex;
}

.bms-designer-canvas__empty,
.bms-designer-canvas__drop-empty {
  margin: 0;
  padding: var(--bms-space-4);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  text-align: center;
  border: 1px dashed var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
}

/* 分区容器（原型：虚线描边 + 圆角 + 内边距；选中态主色描边）。 */
.bms-designer-canvas__section {
  padding: var(--bms-space-3);
  margin-bottom: var(--bms-space-3);
  border: 1px dashed var(--bms-designer-section-border);
  border-radius: var(--bms-radius-md);
}

.bms-designer-canvas__section[data-selected] {
  border-color: var(--bms-designer-cell-selected-border);
}

.bms-designer-canvas__section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-2);
}

.bms-designer-canvas__section-count,
.bms-designer-canvas__hint {
  margin-left: auto;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

/* 字段单元格（原型：虚线描边 + 浅底 + 悬停 / 选中主色）。 */
.bms-designer-canvas__field {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-2);
  padding: var(--bms-space-2) var(--bms-space-3);
  margin-bottom: var(--bms-space-2);
  font-size: var(--bms-font-size-sm);
  background: var(--bms-designer-cell-bg);
  border: 1px dashed var(--bms-designer-cell-border);
  border-radius: var(--bms-radius-sm);
  cursor: grab;
}

.bms-designer-canvas__field:hover {
  border-color: var(--bms-designer-cell-selected-border);
}

.bms-designer-canvas__field[data-selected] {
  background: var(--bms-designer-cell-selected-bg);
  border-color: var(--bms-designer-cell-selected-border);
}

.bms-designer-canvas__field-label {
  color: var(--bms-color-text);
}

.bms-designer-canvas__query,
.bms-designer-canvas__detail {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
}

.bms-designer-canvas__row {
  padding: var(--bms-space-2) var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  background: var(--bms-designer-cell-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
  cursor: grab;
}

/* 窄容器单列（与 `useResponsive` 缺省窄屏阈值一致）。 */
@media (max-width: 992px) {
  .bms-designer-canvas__section-head {
    align-items: flex-start;
  }

  .bms-designer-canvas__section-count {
    margin-left: 0;
  }
}
</style>
