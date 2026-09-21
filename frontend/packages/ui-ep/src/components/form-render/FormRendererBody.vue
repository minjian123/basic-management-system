<script setup lang="ts">
// 表单渲染主体（08-6-2）：按渲染计划渲染分区 / 分组 / 栅格 / 字段分发 / 明细区。
// 由 FormRenderer 异步懒加载的独立分包入口（分包标记 `data-subpackage="renderer"`）。
// 字段仅做分发与组合（控件本体归字段类与基础控件类）；重控件经 utils/formWidgets 二次懒加载。
import type { FieldPermission, FieldRendererRegistry, RenderDetailColumn, RenderFieldPlan, RenderPlan } from '@bms/core'
import { MASK_TEXT, displayFieldText, orgKindOfFieldType, resolveFieldRenderState } from '@bms/core'
import { computed, ref, watch } from 'vue'

import DataTable from '../data/DataTable.vue'
import { MULTIPLE_WIDGETS, resolveFieldComponent } from '../../utils/formWidgets'
import { useBaseDataState } from '../../composables/useBaseDataState'

/** 渲染三态。 */
export type BodyRenderMode = 'create' | 'edit' | 'view'

/** 字段变更载荷。 */
export interface BodyFieldChange {
  /** 字段键。 */
  field: string
  /** 新值。 */
  value: unknown
}

/** 明细变更载荷。 */
export interface BodyDetailChange {
  /** 明细页签键。 */
  detailKey: string
  /** 行集合。 */
  rows: Record<string, unknown>[]
}

interface Props {
  /** 三态。 */
  mode?: BodyRenderMode
  /** 布局元数据（`layout-effective`，保持冻结形状）。 */
  meta?: unknown
  /** 渲染计划（缺省由件内按空计划渲染）。 */
  plan?: RenderPlan | null
  /** 主表数据。 */
  modelValue?: Record<string, unknown>
  /** 标签位置（保持冻结形状）。 */
  labelPosition?: 'top' | 'left'
  /** 强制只读（保持冻结形状）。 */
  forceReadOnly?: boolean
  /** 字段权限标记。 */
  permissions?: Record<string, FieldPermission>
  /** 件层字段覆盖（占位提示等）。 */
  fieldProps?: Record<string, { placeholder?: string }>
  /** 已注册字段类型。 */
  registeredTypes?: readonly string[]
  /** 字段渲染器注册表（自定义类型优先）。 */
  registry?: FieldRendererRegistry
  /** 明细数据。 */
  details?: Record<string, Record<string, unknown>[]>
  /** 主表字段错误（编排下发）。 */
  errors?: readonly { field: string; message: string }[]
  /** 明细行级错误（编排下发）。 */
  detailErrors?: readonly { detailKey: string; index: number; field: string; message: string }[]
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'create',
  meta: undefined,
  plan: null,
  modelValue: () => ({}),
  labelPosition: 'top',
  forceReadOnly: false,
  permissions: () => ({}),
  fieldProps: () => ({}),
  registeredTypes: () => [],
  registry: undefined,
  details: () => ({}),
  errors: () => [],
  detailErrors: () => [],
})

const emit = defineEmits<{
  'field-change': [payload: BodyFieldChange]
  'field-error': [payload: { field: string; message: string }]
  'detail-change': [payload: BodyDetailChange]
  'submit-row': [payload: { detailKey: string; index: number }]
}>()

/** 当前明细页签。 */
const activeDetail = ref('')
/** 字段级错误（编排下发优先，其次件内即时校验结果）。 */
const fieldErrors = computed<Record<string, string>>(() => {
  const result: Record<string, string> = {}
  for (const error of props.errors) {
    result[error.field] = error.message
  }
  return result
})
/** 明细行级错误映射（`页签:行:字段` → 文案）。 */
const detailErrorMap = computed<Record<string, string>>(() => {
  const result: Record<string, string> = {}
  for (const error of props.detailErrors) {
    result[`${error.detailKey}:${error.index}:${error.field}`] = error.message
  }
  return result
})

/** 生效计划（缺省空计划）。 */
const plan = computed<RenderPlan | null>(() => props.plan ?? null)
/** 分区。 */
const sections = computed(() => plan.value?.sections ?? [])
/** 明细列。 */
const detailColumns = computed<RenderDetailColumn[]>(() => plan.value?.detailColumns ?? [])
/** 明细页签键。 */
const detailKeys = computed(() => Object.keys(props.details))
/** 可见字段总数（含分组）。 */
const visibleCount = computed(() =>
  sections.value.reduce((sum, section) => sum + section.fields.filter((field) => field.visible).length, 0),
)
/** 明细总行数。 */
const detailRowCount = computed(() => Object.values(props.details).reduce((sum, rows) => sum + rows.length, 0))
/** 数据状态（无可见字段 → `empty`，否则 `ready`）。 */
const { state, setState } = useBaseDataState()
watch(
  () => visibleCount.value,
  (count) => setState(count > 0 || detailKeys.value.length > 0 ? 'ready' : 'empty'),
  { immediate: true },
)

watch(
  () => detailKeys.value.length,
  (count) => {
    if (count === 0) {
      activeDetail.value = ''
      return
    }
    if (!detailKeys.value.includes(activeDetail.value)) {
      activeDetail.value = detailKeys.value[0] ?? ''
    }
  },
  { immediate: true },
)

/**
 * 取字段当前值。
 *
 * @param field 字段渲染项。
 */
function valueOf(field: RenderFieldPlan): unknown {
  if (field.key in props.modelValue) {
    return props.modelValue[field.key]
  }
  return field.value
}

/**
 * 字段展示文本（脱敏 / 只读回显 / 空值占位）。
 *
 * @param field 字段渲染项。
 */
function textOf(field: RenderFieldPlan): string {
  return field.masked ? MASK_TEXT : displayFieldText(valueOf(field))
}

/**
 * 取字段组件（未映射返回 `undefined`，由件层渲染纯文本）。
 *
 * @param field 字段渲染项。
 */
function componentOf(field: RenderFieldPlan): unknown {
  return resolveFieldComponent({
    widget: field.widget,
    fieldType: field.base.type,
    registry: props.registry,
  })
}

/**
 * 字段占位提示（件层覆盖优先）。
 *
 * @param field 字段渲染项。
 */
function placeholderOf(field: RenderFieldPlan): string {
  return props.fieldProps[field.key]?.placeholder ?? field.placeholder
}

/**
 * 是否为多选语义（唯一来源 `MULTIPLE_WIDGETS`，防两处清单漂移）。
 *
 * @param field 字段渲染项。
 */
function isMultiple(field: RenderFieldPlan): boolean {
  return MULTIPLE_WIDGETS.includes(field.widget)
}

/**
 * 控件附加属性（组织选择件透传 `kind`；其余为空）。
 *
 * @param field 字段渲染项。
 */
function extraProps(field: RenderFieldPlan): Record<string, unknown> {
  if (field.widget !== 'org-select') {
    return {}
  }
  return { kind: orgKindOfFieldType(field.base.type) ?? 'user' }
}

/**
 * 字段值变更（上抛宿主；只读时不下发）。
 *
 * @param field 字段渲染项。
 * @param value 新值。
 */
function onFieldInput(field: RenderFieldPlan, value: unknown): void {
  if (!field.editable) {
    return
  }
  emit('field-change', { field: field.key, value })
}

/**
 * 明细单元格变更。
 *
 * @param detailKey 明细页签键。
 * @param index 行下标。
 * @param fieldKey 字段键。
 * @param value 新值。
 */
function onCellChange(detailKey: string, index: number, fieldKey: string, value: unknown): void {
  const rows = (props.details[detailKey] ?? []).map((row, position) =>
    position === index ? { ...row, [fieldKey]: value } : { ...row },
  )
  emit('detail-change', { detailKey, rows })
}

/**
 * 追加明细行。
 *
 * @param detailKey 明细页签键。
 */
function onAddRow(detailKey: string): void {
  const rows = [...(props.details[detailKey] ?? []), {}]
  emit('detail-change', { detailKey, rows })
}

/**
 * 移除明细行。
 *
 * @param detailKey 明细页签键。
 * @param index 行下标。
 */
function onRemoveRow(detailKey: string, index: number): void {
  const rows = (props.details[detailKey] ?? []).filter((_, position) => position !== index)
  emit('detail-change', { detailKey, rows })
}

/**
 * 设置为只读回显（查看态由计划派生）。
 *
 * @param field 字段渲染项。
 */
function isDisplayOnly(field: RenderFieldPlan): boolean {
  const state = resolveFieldRenderState({
    field: field.base,
    mode: props.mode,
    permission: props.permissions[field.key],
  })
  return state.displayOnly || !field.editable
}
</script>

<template>
  <div
    class="bms-form-renderer-body"
    data-test="renderer-body"
    data-subpackage="renderer"
    :data-mode="mode"
    :data-label-position="labelPosition"
    :data-state="state"
    :data-readonly="forceReadOnly || plan?.readonly || mode === 'view'"
    :data-fallback="plan?.fallback || undefined"
  >
    <p v-if="state === 'empty'" data-test="renderer-empty">没有可渲染的字段</p>
    <p v-else data-test="renderer-note">按元数据渲染字段区域</p>

    <template v-for="section in sections" :key="section.key">
      <section
        class="bms-form-renderer__section"
        :data-test="`renderer-section-${section.key}`"
        :data-columns="section.columns"
        :data-groups="section.groups.length"
      >
        <h4 v-if="section.title" class="bms-form-renderer__section-title">{{ section.title }}</h4>

        <div
          v-if="section.ungroupedFields.some((item) => item.visible)"
          class="bms-form-renderer__grid"
          :style="{ '--bms-cols': section.columns }"
        >
          <div
            v-for="field in section.ungroupedFields.filter((item) => item.visible)"
            :key="field.key"
            class="bms-form-renderer__field"
            :data-test="`renderer-field-${field.key}`"
            :data-colspan="field.colSpan || undefined"
            :data-editable="field.editable"
            :data-required="field.required"
            :data-masked="field.masked"
          >
            <label :data-test="`renderer-field-label-${field.key}`">
              {{ field.label }}
              <span v-if="field.required" data-test="renderer-required">*</span>
            </label>
            <slot
              name="field"
              :field="field"
              :value="valueOf(field)"
              :set-value="(value: unknown) => onFieldInput(field, value)"
            >
              <p v-if="isDisplayOnly(field)" data-test="renderer-field-display">{{ textOf(field) }}</p>
              <component
                :is="componentOf(field)"
                v-else-if="componentOf(field)"
                :model-value="valueOf(field)"
                :multiple="isMultiple(field)"
                :disabled="field.disabled"
                :placeholder="placeholderOf(field)"
                :options="field.options"
                v-bind="extraProps(field)"
                @update:model-value="onFieldInput(field, $event)"
              />
              <p v-else :data-test="`renderer-field-plain-${field.key}`">{{ textOf(field) }}</p>
            </slot>
            <p v-if="fieldErrors[field.key]" :data-test="`renderer-field-error-${field.key}`">
              {{ fieldErrors[field.key] }}
            </p>
          </div>
        </div>

        <template v-for="group in section.groups" :key="group.key">
          <fieldset class="bms-form-renderer__group" :data-test="`renderer-group-${group.key}`">
            <legend v-if="group.title">{{ group.title }}</legend>
            <div class="bms-form-renderer__grid" :style="{ '--bms-cols': section.columns }">
              <div
                v-for="field in group.fields.filter((item) => item.visible)"
                :key="field.key"
                class="bms-form-renderer__field"
                :data-test="`renderer-field-${field.key}`"
                :data-colspan="field.colSpan || undefined"
                :data-editable="field.editable"
                :data-required="field.required"
                :data-masked="field.masked"
              >
                <label :data-test="`renderer-field-label-${field.key}`">
                  {{ field.label }}
                  <span v-if="field.required" data-test="renderer-required">*</span>
                </label>
                <slot
                  name="field"
                  :field="field"
                  :value="valueOf(field)"
                  :set-value="(value: unknown) => onFieldInput(field, value)"
                >
                  <p v-if="isDisplayOnly(field)" data-test="renderer-field-display">{{ textOf(field) }}</p>
                  <component
                    :is="componentOf(field)"
                    v-else-if="componentOf(field)"
                    :model-value="valueOf(field)"
                    :multiple="isMultiple(field)"
                    :disabled="field.disabled"
                    :placeholder="placeholderOf(field)"
                    :options="field.options"
                    v-bind="extraProps(field)"
                    @update:model-value="onFieldInput(field, $event)"
                  />
                  <p v-else :data-test="`renderer-field-plain-${field.key}`">{{ textOf(field) }}</p>
                </slot>
                <p v-if="fieldErrors[field.key]" :data-test="`renderer-field-error-${field.key}`">
                  {{ fieldErrors[field.key] }}
                </p>
              </div>
            </div>
          </fieldset>
        </template>
      </section>
    </template>

    <div v-if="detailKeys.length > 0" class="bms-form-renderer__detail" data-test="renderer-detail">
      <div class="bms-form-renderer__detail-tabs">
        <button
          v-for="key in detailKeys"
          :key="key"
          type="button"
          :data-test="`renderer-detail-tab-${key}`"
          :data-active="activeDetail === key"
          @click="activeDetail = key"
        >
          {{ key }}（{{ (details[key] ?? []).length }}）
        </button>
      </div>

      <template v-for="key in detailKeys" :key="key">
        <div v-if="activeDetail === key" :data-test="`renderer-detail-${key}`">
          <slot name="detail" :detail-key="key" :rows="details[key] ?? []">
            <data-table
              :ready="true"
              :columns="detailColumns.map((column) => ({ key: column.key, title: column.title, width: column.width }))"
              :data="details[key] ?? []"
              row-key="id"
            />
          </slot>
          <div class="bms-form-renderer__detail-actions">
            <button
              type="button"
              :data-test="`renderer-detail-add-${key}`"
              :disabled="plan?.readonly"
              @click="onAddRow(key)"
            >
              ＋ 明细行
            </button>
            <button
              v-for="(_, index) in details[key] ?? []"
              :key="`remove-${index}`"
              type="button"
              :data-test="`renderer-detail-remove-${key}-${index}`"
              :disabled="plan?.readonly"
              @click="onRemoveRow(key, index)"
            >
              移除 {{ index + 1 }}
            </button>
          </div>
          <div class="bms-form-renderer__detail-editor">
            <div
              v-for="(row, index) in details[key] ?? []"
              :key="`row-${index}`"
              :data-test="`renderer-detail-row-${key}-${index}`"
            >
              <label
                v-for="column in detailColumns"
                :key="column.key"
                :data-test="`renderer-detail-cell-${key}-${index}-${column.key}`"
                :data-error="detailErrorMap[`${key}:${index}:${column.key}`] || undefined"
              >
                <span>{{ column.title }}</span>
                <input
                  type="text"
                  :value="row[column.key] ?? ''"
                  :disabled="!column.editable"
                  @change="onCellChange(key, index, column.key, ($event.target as HTMLInputElement).value)"
                />
                <em
                  v-if="detailErrorMap[`${key}:${index}:${column.key}`]"
                  :data-test="`renderer-detail-error-${key}-${index}-${column.key}`"
                >
                  {{ detailErrorMap[`${key}:${index}:${column.key}`] }}
                </em>
              </label>
              <button
                type="button"
                :data-test="`renderer-detail-submit-${key}-${index}`"
                @click="emit('submit-row', { detailKey: key, index })"
              >
                校验行
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <p
      class="bms-form-renderer__counters"
      data-test="renderer-counters"
      :data-fields="visibleCount"
      :data-details="detailRowCount"
      :data-unknown="plan?.unknownFields.length ?? 0"
    >
      可见字段 {{ visibleCount }} / 失效 {{ plan?.unknownFields.length ?? 0 }} / 明细行 {{ detailRowCount }}
    </p>
  </div>
</template>
