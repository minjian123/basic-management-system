<script setup lang="ts">
// 字段属性面板（08_06）：随画布选中联动——字段属性 / 分区属性 / 查询区与明细区入口。
// 由 FormDesigner 异步懒加载的独立分包入口；只编辑属性补丁并上抛，落点与校验归编排基类与领域纯函数。
import type { FormField, LabelPosition, LayoutDetailColumnInput, LayoutSection } from '@bms/core'
import { LABEL_WIDTH_RANGE, SECTION_FIELD_HINT, extFieldNeedsOptions } from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import type { DesignerSelection, FormLayoutShape } from './FormDesigner.vue'

/** 字段属性补丁（组件类型切换与值兼容性由编排基类裁决）。 */
export interface FieldPropertyPatch {
  /** 是否必填。 */
  required?: boolean
  /** 默认值。 */
  defaultValue?: unknown
  /** 提示文案。 */
  placeholder?: string
  /** 校验规则。 */
  rule?: string
  /** 组件类型。 */
  widget?: string
  /** 选项集（字典类型或自定义选项文本）。 */
  options?: string
  /** 是否只读。 */
  readonly?: boolean
  /** 是否隐藏。 */
  hidden?: boolean
}

/** 分区属性补丁。 */
export interface SectionPropertyPatch {
  /** 分区标题。 */
  title?: string
  /** 分区列数。 */
  columns?: number
}

/** 画布全局属性补丁。 */
export interface CanvasPropertyPatch {
  /** 标签位置。 */
  labelPosition?: LabelPosition
  /** 标签宽度。 */
  labelWidth?: number
}

interface Props {
  /** 画布选中对象。 */
  selection?: DesignerSelection | null
  /** 字段清单。 */
  fields?: FormField[]
  /** 当前层级布局。 */
  layout?: FormLayoutShape | undefined
  /** 只读。 */
  readOnly?: boolean
  /** 占位（数据通路未就绪）。 */
  disabled?: boolean
  /** 字段属性值（受控；按字段键索引）。 */
  values?: Record<string, FieldPropertyPatch>
}

const props = withDefaults(defineProps<Props>(), {
  selection: null,
  fields: () => [],
  layout: undefined,
  readOnly: false,
  disabled: false,
  values: () => ({}),
})

const emit = defineEmits<{
  'field-change': [payload: { fieldKey: string; patch: FieldPropertyPatch }]
  'section-change': [payload: { sectionKey: string; patch: SectionPropertyPatch }]
  'canvas-change': [payload: CanvasPropertyPatch]
  'query-change': [payload: { keys: string[] }]
  'detail-change': [payload: { columns: LayoutDetailColumnInput[] }]
}>()

/** 生效禁用（只读 / 占位）。 */
const locked = computed(() => props.readOnly || props.disabled)
/** 面板数据状态（未选中 → `empty`）。 */
const { state, setState } = useBaseDataState()
watch(
  () => props.selection,
  (selection) => setState(selection === null ? 'empty' : 'ready'),
  { immediate: true },
)
/** 选中字段。 */
const selectedField = computed<FormField | undefined>(() => {
  if (props.selection?.kind !== 'field') {
    return undefined
  }
  return props.fields.find((field) => field.key === props.selection?.key)
})
/** 选中分区。 */
const selectedSection = computed<LayoutSection | undefined>(() => {
  if (props.selection?.kind !== 'section') {
    return undefined
  }
  return (props.layout?.main.sections ?? []).find((section: LayoutSection) => section.key === props.selection?.key)
})
/** 选中字段的属性值。 */
const fieldValues = computed<FieldPropertyPatch>(() => (selectedField.value === undefined ? {} : (props.values[selectedField.value.key] ?? {})))
/** 选中字段是否需选项集（下拉单选 / 多选）。 */
const needsOptions = computed(() => selectedField.value !== undefined && extFieldNeedsOptions(selectedField.value.type))
/** 标签宽度上下限（供输入控件约束）。 */
const labelWidthRange = computed(() => LABEL_WIDTH_RANGE)
/** 分区字段数建议上限。 */
const fieldHint = computed(() => SECTION_FIELD_HINT)

/**
 * 上抛字段属性补丁。
 *
 * @param patch 补丁。
 */
function patchField(patch: FieldPropertyPatch): void {
  if (locked.value || selectedField.value === undefined) {
    return
  }
  emit('field-change', { fieldKey: selectedField.value.key, patch })
}

/**
 * 上抛分区属性补丁。
 *
 * @param patch 补丁。
 */
function patchSection(patch: SectionPropertyPatch): void {
  if (locked.value || selectedSection.value === undefined) {
    return
  }
  emit('section-change', { sectionKey: selectedSection.value.key, patch })
}

/**
 * 上抛画布全局属性补丁。
 *
 * @param patch 补丁。
 */
function patchCanvas(patch: CanvasPropertyPatch): void {
  if (locked.value) {
    return
  }
  emit('canvas-change', patch)
}
</script>

<template>
  <div
    class="bms-field-property-panel"
    data-test="property-panel"
    data-subpackage="property"
    :data-state="state"
    :data-readonly="locked"
    :data-selected="selection ? `${selection.kind}:${selection.key}` : undefined"
  >
    <p v-if="locked" data-test="property-readonly">当前层级只读或数据通路未就绪，属性不可编辑</p>

    <div v-if="selectedField" data-test="property-field" :data-test-key="selectedField.key">
      <strong :data-test="`property-field-${selectedField.key}`">{{ selectedField.label }}</strong>
      <label>
        <input
          type="checkbox"
          data-test="prop-required"
          :checked="fieldValues.required === true"
          :disabled="locked"
          @change="patchField({ required: ($event.target as HTMLInputElement).checked })"
        />
        必填
      </label>
      <label>
        默认值
        <input
          type="text"
          data-test="prop-default"
          :value="String(fieldValues.defaultValue ?? '')"
          :disabled="locked"
          @change="patchField({ defaultValue: ($event.target as HTMLInputElement).value })"
        />
      </label>
      <label>
        提示文案
        <input
          type="text"
          data-test="prop-placeholder"
          :value="fieldValues.placeholder ?? ''"
          :disabled="locked"
          @change="patchField({ placeholder: ($event.target as HTMLInputElement).value })"
        />
      </label>
      <label>
        校验规则
        <input
          type="text"
          data-test="prop-rule"
          :value="fieldValues.rule ?? ''"
          :disabled="locked"
          @change="patchField({ rule: ($event.target as HTMLInputElement).value })"
        />
      </label>
      <label>
        组件类型
        <input
          type="text"
          data-test="prop-widget"
          :value="fieldValues.widget ?? selectedField.type"
          :disabled="locked"
          @change="patchField({ widget: ($event.target as HTMLInputElement).value })"
        />
      </label>
      <label v-if="needsOptions">
        选项集
        <input
          type="text"
          data-test="prop-options"
          :value="fieldValues.options ?? ''"
          :disabled="locked"
          @change="patchField({ options: ($event.target as HTMLInputElement).value })"
        />
      </label>
      <label>
        <input
          type="checkbox"
          data-test="prop-readonly"
          :checked="fieldValues.readonly === true"
          :disabled="locked"
          @change="patchField({ readonly: ($event.target as HTMLInputElement).checked })"
        />
        只读
      </label>
      <label>
        <input
          type="checkbox"
          data-test="prop-hidden"
          :checked="fieldValues.hidden === true"
          :disabled="locked"
          @change="patchField({ hidden: ($event.target as HTMLInputElement).checked })"
        />
        隐藏
      </label>
    </div>

    <div v-else-if="selectedSection" data-test="property-section">
      <label>
        分区标题
        <input
          type="text"
          data-test="prop-section-title"
          :value="selectedSection.title"
          :disabled="locked"
          @change="patchSection({ title: ($event.target as HTMLInputElement).value })"
        />
      </label>
      <label>
        分区列数
        <select
          data-test="prop-section-columns"
          :value="selectedSection.columns"
          :disabled="locked"
          @change="patchSection({ columns: Number(($event.target as HTMLSelectElement).value) })"
        >
          <option v-for="count in [1, 2, 3]" :key="count" :value="count">{{ count }} 列</option>
        </select>
      </label>
      <span data-test="prop-section-hint">单分区字段建议不超过 {{ fieldHint }} 个</span>
    </div>

    <div v-else data-test="property-empty">
      <p>未选中对象</p>
      <label>
        标签位置
        <select
          data-test="prop-label-position"
          :value="layout?.main.labelPosition ?? 'top'"
          :disabled="locked"
          @change="patchCanvas({ labelPosition: ($event.target as HTMLSelectElement).value as LabelPosition })"
        >
          <option value="top">上方</option>
          <option value="left">左侧</option>
        </select>
      </label>
      <label>
        标签宽度（{{ labelWidthRange[0] }} ~ {{ labelWidthRange[1] }}）
        <input
          type="number"
          data-test="prop-label-width"
          :min="labelWidthRange[0]"
          :max="labelWidthRange[1]"
          :value="layout?.main.labelWidth ?? ''"
          :disabled="locked"
          @change="patchCanvas({ labelWidth: Number(($event.target as HTMLInputElement).value) })"
        />
      </label>
    </div>
  </div>
</template>
