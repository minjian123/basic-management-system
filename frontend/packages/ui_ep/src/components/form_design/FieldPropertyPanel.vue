<script setup lang="ts">
// 字段属性面板（08_06）：随画布选中联动——字段属性 / 分区属性 / 查询区与明细区入口。
// 由 FormDesigner 异步懒加载的独立分包入口；只编辑属性补丁并上抛，落点与校验归编排基类与领域纯函数。
import type { FormField, LabelPosition, LayoutDetailColumnInput, LayoutSection } from '@bms/core'
import { LABEL_WIDTH_RANGE, SECTION_FIELD_HINT, extFieldNeedsOptions } from '@bms/core'
import { computed, watch } from 'vue'
import { ElCheckbox, ElForm, ElFormItem, ElInput, ElInputNumber, ElOption, ElSelect } from 'element-plus'

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
    <p v-if="locked" class="bms-field-property-panel__readonly" data-test="property-readonly">
      当前层级只读或数据通路未就绪，属性不可编辑
    </p>

    <el-form v-if="selectedField" label-position="top" :disabled="locked" data-test="property-field">
      <section class="bms-field-property-panel__group">
        <h5 class="bms-field-property-panel__group-title">字段</h5>
        <p class="bms-field-property-panel__subject" :data-test="`property-field-${selectedField.key}`">
          {{ selectedField.label }}
          <span class="bms-field-property-panel__key">{{ selectedField.key }}</span>
        </p>
      </section>

      <section class="bms-field-property-panel__group">
        <h5 class="bms-field-property-panel__group-title">基本属性</h5>
        <el-form-item label="必填">
          <el-checkbox
            data-test="prop-required"
            :model-value="fieldValues.required === true"
            :disabled="locked"
            @update:model-value="patchField({ required: $event === true })"
          />
        </el-form-item>
        <el-form-item label="默认值">
          <el-input
            data-test="prop-default"
            :model-value="String(fieldValues.defaultValue ?? '')"
            :disabled="locked"
            @update:model-value="patchField({ defaultValue: $event })"
          />
        </el-form-item>
        <el-form-item label="提示文案">
          <el-input
            data-test="prop-placeholder"
            :model-value="fieldValues.placeholder ?? ''"
            :disabled="locked"
            @update:model-value="patchField({ placeholder: $event })"
          />
        </el-form-item>
      </section>

      <section class="bms-field-property-panel__group">
        <h5 class="bms-field-property-panel__group-title">校验与控件</h5>
        <el-form-item label="校验规则">
          <el-input
            data-test="prop-rule"
            placeholder="如：长度 ≤ 50"
            :model-value="fieldValues.rule ?? ''"
            :disabled="locked"
            @update:model-value="patchField({ rule: $event })"
          />
        </el-form-item>
        <el-form-item label="组件类型">
          <el-input
            data-test="prop-widget"
            :model-value="fieldValues.widget ?? selectedField.type"
            :disabled="locked"
            @update:model-value="patchField({ widget: $event })"
          />
        </el-form-item>
        <el-form-item v-if="needsOptions" label="选项集">
          <el-input
            data-test="prop-options"
            placeholder="引用字典 / 自定义"
            :model-value="fieldValues.options ?? ''"
            :disabled="locked"
            @update:model-value="patchField({ options: $event })"
          />
        </el-form-item>
      </section>

      <section class="bms-field-property-panel__group">
        <h5 class="bms-field-property-panel__group-title">显隐</h5>
        <el-form-item label="只读">
          <el-checkbox
            data-test="prop-readonly"
            :model-value="fieldValues.readonly === true"
            :disabled="locked"
            @update:model-value="patchField({ readonly: $event === true })"
          />
        </el-form-item>
        <el-form-item label="隐藏">
          <el-checkbox
            data-test="prop-hidden"
            :model-value="fieldValues.hidden === true"
            :disabled="locked"
            @update:model-value="patchField({ hidden: $event === true })"
          />
        </el-form-item>
      </section>
    </el-form>

    <el-form v-else-if="selectedSection" label-position="top" :disabled="locked" data-test="property-section">
      <section class="bms-field-property-panel__group">
        <h5 class="bms-field-property-panel__group-title">分区属性</h5>
        <el-form-item label="分区标题">
          <el-input
            data-test="prop-section-title"
            :model-value="selectedSection.title"
            :disabled="locked"
            @update:model-value="patchSection({ title: $event })"
          />
        </el-form-item>
        <el-form-item label="分区列数">
          <el-select
            data-test="prop-section-columns"
            :model-value="selectedSection.columns"
            :disabled="locked"
            @update:model-value="patchSection({ columns: Number($event) })"
          >
            <el-option v-for="count in [1, 2, 3]" :key="count" :label="`${count} 列`" :value="count" />
          </el-select>
        </el-form-item>
        <p class="bms-field-property-panel__hint" data-test="prop-section-hint">
          单分区字段建议不超过 {{ fieldHint }} 个
        </p>
      </section>
    </el-form>

    <el-form v-else label-position="top" :disabled="locked" data-test="property-empty">
      <section class="bms-field-property-panel__group">
        <h5 class="bms-field-property-panel__group-title">画布属性</h5>
        <p class="bms-field-property-panel__hint">未选中对象</p>
        <el-form-item label="标签位置">
          <el-select
            data-test="prop-label-position"
            :model-value="layout?.main.labelPosition ?? 'top'"
            :disabled="locked"
            @update:model-value="patchCanvas({ labelPosition: $event as LabelPosition })"
          >
            <el-option label="上方" value="top" />
            <el-option label="左侧" value="left" />
          </el-select>
        </el-form-item>
        <el-form-item :label="`标签宽度（${labelWidthRange[0]} ~ ${labelWidthRange[1]}）`">
          <el-input-number
            data-test="prop-label-width"
            :min="labelWidthRange[0]"
            :max="labelWidthRange[1]"
            :model-value="layout?.main.labelWidth"
            :disabled="locked"
            @update:model-value="patchCanvas({ labelWidth: Number($event) })"
          />
        </el-form-item>
      </section>
    </el-form>
  </div>
</template>

<style scoped>
.bms-field-property-panel {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-field-property-panel__readonly {
  margin: 0;
  padding: var(--bms-space-2);
  color: var(--bms-color-warning);
  font-size: var(--bms-font-size-xs);
  background: var(--bms-color-warning-bg);
  border-radius: var(--bms-radius-sm);
}

/* 属性分组（原型：分组标题 + 分隔线 + 分组间距）。 */
.bms-field-property-panel__group {
  padding-bottom: var(--bms-space-2);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-field-property-panel__group:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.bms-field-property-panel__group-title {
  margin: 0 0 var(--bms-space-2);
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
  font-weight: 600;
}

.bms-field-property-panel__subject {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--bms-space-2);
  margin: 0 0 var(--bms-space-2);
  color: var(--bms-color-text);
}

.bms-field-property-panel__key {
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-xs);
}

.bms-field-property-panel__hint {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-field-property-panel :deep(.el-form-item) {
  margin-bottom: var(--bms-space-2);
}

.bms-field-property-panel :deep(.el-form-item__label) {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}
</style>
