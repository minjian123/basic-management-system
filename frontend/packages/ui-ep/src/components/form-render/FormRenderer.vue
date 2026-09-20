<script setup lang="ts">
// 表单渲染器（08-6-2）：三态（新增 / 编辑 / 查看）+ 布局元数据驱动渲染 + 字段权限叠加 + 校验与提交。
// 对外契约保持 08_01_02 冻结形状（导出名 / 既有 Props / 事件 / 插槽 / data-test / 分包入口不变），仅向后兼容新增可选项。
// 事件与注入双轨：点击一律保留既有事件上抛；仅当宿主注入 jobs 时件内才驱动真实编排（二选一，避免重复执行）。
import type {
  BaseAccess,
  BaseFieldPerm,
  BaseFormMeta,
  BaseNotice,
  BaseValidatable,
  FieldPermission,
  FieldRenderOverride,
  FieldRendererRegistry,
  FormRendererJobs,
  FormRenderMode as FormRenderModeCore,
  LayoutEffective,
  RenderMetadataInput,
  RenderPlan,
  SubmitResult,
} from '@bms/core'
import { RENDERER_PLACEHOLDER_TEXT } from '@bms/core'
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import { useBaseFormMeta } from '../../composables/useBaseFormMeta'
import { useBaseFormRenderer } from '../../composables/useBaseFormRenderer'
import type { BodyDetailChange } from './FormRendererBody.vue'

// 渲染主体独立分包（字段分发与明细区；`defineAsyncComponent` 且不进根出口，否则分包退化）。
const FormRendererBody = defineAsyncComponent(() => import('./FormRendererBody.vue'))

/** 表单三态（对外名保持 `08_01_02` 冻结形状）。 */
export type FormRenderMode = FormRenderModeCore

/** 校验结果。 */
export interface FormValidateResult {
  /** 是否通过。 */
  valid: boolean
  /** 字段级错误。 */
  errors: { field: string; message: string }[]
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 表单标识。 */
  formCode?: string
  /** 三态。 */
  mode?: FormRenderModeCore
  /** 记录数据（受控）。 */
  modelValue?: Record<string, unknown>
  /** 记录主键。 */
  recordId?: string | number
  /** 标签位置。 */
  labelPosition?: 'top' | 'left'
  /** 强制只读。 */
  forceReadOnly?: boolean
  /** 布局元数据（`layout-effective`）。 */
  meta?: unknown
  /** 降级文案。 */
  degradeText?: string
  /** 字段权限标记（新增，可选）。 */
  permissions?: Record<string, FieldPermission>
  /** 件层字段覆盖（新增，可选）。 */
  fieldProps?: Record<string, FieldRenderOverride>
  /** 只读字段集合（新增，可选）。 */
  readonlyFields?: string[]
  /** 注入的处理函数集（新增，可选；未注入即仅事件上抛）。 */
  jobs?: FormRendererJobs
  /** 权限上下文（新增，可选）。 */
  access?: BaseAccess
  /** 提示通知协作者（新增，可选）。 */
  notice?: BaseNotice
  /** 字段权限能力（新增，可选）。 */
  fieldPerm?: BaseFieldPerm
  /** 表单元数据能力（新增，可选）。 */
  formMeta?: BaseFormMeta
  /** 校验能力（新增，可选）。 */
  validatable?: BaseValidatable
  /** 字段渲染器注册表（新增，可选；自定义类型优先）。 */
  fieldRenderer?: FieldRendererRegistry
  /** 明细数据（新增，可选）。 */
  details?: Record<string, Record<string, unknown>[]>
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  formCode: '',
  mode: 'create',
  modelValue: () => ({}),
  recordId: undefined,
  labelPosition: 'top',
  forceReadOnly: false,
  meta: undefined,
  degradeText: RENDERER_PLACEHOLDER_TEXT,
  permissions: () => ({}),
  fieldProps: () => ({}),
  readonlyFields: () => [],
  jobs: undefined,
  access: undefined,
  notice: undefined,
  fieldPerm: undefined,
  formMeta: undefined,
  validatable: undefined,
  fieldRenderer: undefined,
  details: () => ({}),
})

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
  change: [value: Record<string, unknown>]
  submit: [value: Record<string, unknown>]
  validate: [result: FormValidateResult]
  'field-change': [payload: { field: string; value: unknown }]
  retry: []
  loaded: [metadata: LayoutEffective]
  submitted: [result: SubmitResult | undefined]
  failed: [payload: { message: string }]
  'field-error': [payload: { field: string; message: string }]
  'detail-change': [payload: { detailKey: string; rows: Record<string, unknown>[] }]
}>()

// 件层表单元数据投影（与 Props 的 `formMeta` 能力实例区分，避免 `vue/no-dupe-keys`）。
const formMetaState = useBaseFormMeta()

/** 生效元数据（宿主传入优先，否则取件内取数结果）。 */
const resolvedMeta = computed<unknown>(() => props.meta ?? formMetaState.meta.value)

/** 件层字段覆盖（含宿主只读字段集合）。 */
const overrides = computed<Record<string, FieldRenderOverride>>(() => {
  const result: Record<string, FieldRenderOverride> = { ...props.fieldProps }
  for (const key of props.readonlyFields) {
    result[key] = { ...result[key], readonly: true }
  }
  return result
})

const renderer = useBaseFormRenderer({
  ready: props.ready,
  formCode: props.formCode,
  mode: props.mode,
  recordId: props.recordId,
  forceReadOnly: props.forceReadOnly,
  access: props.access,
  notice: props.notice,
  fieldPerm: props.fieldPerm,
  validatable: props.validatable,
  jobs: props.jobs,
})

/** 件内工作副本（宿主未接 `modelValue` 时使用）。 */
const model = ref<Record<string, unknown>>({ ...props.modelValue })
/** 件内明细副本。 */
const detailState = ref<Record<string, Record<string, unknown>[]>>({ ...props.details })
/** 明细区错误定位（首个错误）。 */
const detailError = ref('')

watch(
  () => props.ready,
  (next) => {
    renderer.setReady(next)
    if (next) {
      void load()
    }
  },
  { immediate: true },
)

watch(
  () => props.formCode,
  (next) => {
    renderer.setFormCode(next)
  },
)

watch(
  () => props.mode,
  (next) => {
    renderer.setMode(next)
  },
)

watch(
  () => props.forceReadOnly,
  (next) => renderer.setForceReadOnly(next),
)

watch(
  () => props.modelValue,
  (next) => {
    model.value = { ...next }
    renderer.setData(next)
  },
  { immediate: true, deep: true },
)

watch(
  () => props.details,
  (next) => {
    detailState.value = { ...next }
    renderer.setDetails(next)
  },
  { deep: true },
)

watch(
  () => props.permissions,
  (next) => {
    // 宿主显式传入的权限标记优先于元数据下发（未传时不覆盖）。
    renderer.setPermissions({ ...renderer.renderer.permissions, ...next })
  },
  { deep: true },
)

watch(overrides, (next) => renderer.setOverrides(next), { deep: true, immediate: true })

watch(
  () => props.jobs,
  (next) => {
    if (next !== undefined) {
      renderer.setJobs(next)
    }
  },
)

/** 生效元数据装载（外部传入优先，否则经元数据投影取；下发权限与宿主权限合并）。 */
watch(
  resolvedMeta,
  (next) => {
    if (next === undefined || next === null) {
      return
    }
    renderer.setMeta(next as RenderMetadataInput | LayoutEffective)
    renderer.setPermissions({ ...renderer.renderer.permissions, ...props.permissions })
  },
  { immediate: true },
)

/** 生效只读（宿主强制只读 / 投影只读）。 */
const readonly = computed(() => props.forceReadOnly || renderer.readonly.value)
/** 生效计划（投影派生；宿主未注入时为空计划）。 */
const plan = computed<RenderPlan>(() => renderer.plan.value)
/** 生效明细数据（宿主受控优先，其次件内工作副本、再投影取数结果）。 */
const detailsValue = computed<Record<string, Record<string, unknown>[]>>(() => {
  if (Object.keys(props.details).length > 0) {
    return props.details
  }
  const state = detailState.value
  return Object.keys(state).length > 0 ? state : renderer.details.value
})
/** 是否有可渲染内容。 */
const hasContent = computed(
  () =>
    plan.value.sections.some((section) => section.fields.some((field) => field.visible)) ||
    Object.keys(detailsValue.value).length > 0,
)

/**
 * 取数（未注入 `jobs` 时仅经元数据投影，占位不发请求）。
 */
async function load(): Promise<void> {
  if (props.meta === undefined && props.jobs?.loadLayout !== undefined) {
    const loaded = await renderer.load()
    if (loaded !== undefined) {
      emit('loaded', loaded)
    }
    return
  }
  await formMetaState.load()
}

/**
 * 取表单数据。
 */
function getData(): Record<string, unknown> {
  return { ...model.value }
}

/**
 * 设置表单数据。
 *
 * @param value 数据。
 */
function setData(value: Record<string, unknown>): void {
  model.value = { ...value }
  renderer.setData(value)
  const data = getData()
  emit('update:modelValue', data)
  emit('change', data)
}

/**
 * 重置字段。
 */
function reset(): void {
  model.value = {}
  renderer.reset()
  emit('update:modelValue', {})
}

/**
 * 校验（投影全量校验；未注入时仍按计划规则校验）。
 */
function validate(): FormValidateResult {
  const result = renderer.validate()
  const payload: FormValidateResult = {
    valid: result.valid,
    errors: result.errors.map((error) => ({ field: error.field, message: error.message })),
  }
  if (!result.valid && result.firstField !== undefined) {
    emit('field-error', { field: result.firstField, message: result.errors[0]?.message ?? '' })
  }
  emit('validate', payload)
  return payload
}

/**
 * 字段值变更（受控回写 + 即时校验）。
 */
function onFieldChange(payload: { field: string; value: unknown }): void {
  if (readonly.value) {
    return
  }
  if (renderer.setFieldValue(payload.field, payload.value)) {
    model.value = { ...renderer.data.value }
    emit('field-change', payload)
    const data = getData()
    emit('update:modelValue', data)
    emit('change', data)
    const message = renderer.validateField(payload.field)
    if (message !== undefined) {
      emit('field-error', { field: payload.field, message })
    }
  }
}

/**
 * 明细变更（受控回写）。
 */
function onDetailChange(payload: BodyDetailChange): void {
  if (readonly.value) {
    return
  }
  detailState.value = { ...detailState.value, [payload.detailKey]: payload.rows }
  renderer.setDetailRows(payload.detailKey, payload.rows)
  emit('detail-change', payload)
}

/**
 * 明细单行校验。
 */
function onSubmitRow(payload: { detailKey: string; index: number }): void {
  const result = renderer.validate()
  void payload
  detailError.value = result.valid ? '' : (renderer.detailErrors.value[0]?.message ?? '')
}

/**
 * 提交（保留既有 `submit` 事件上抛；注入 `jobs` 后驱动真实编排）。
 */
async function submit(): Promise<void> {
  if (readonly.value) {
    return
  }
  const result = validate()
  if (!result.valid) {
    emit('failed', { message: result.errors[0]?.message ?? '校验未通过' })
    return
  }
  if (props.jobs === undefined || props.jobs.submit === undefined) {
    emit('submit', getData())
    return
  }
  const submitted = await renderer.submit()
  if (submitted !== undefined) {
    emit('submitted', submitted)
    return
  }
  emit('failed', { message: renderer.errorMessage.value || '提交未完成' })
}

/**
 * 重试（保留既有 `retry` 事件上抛；注入后重放提交）。
 */
async function retry(): Promise<void> {
  emit('retry')
  if (props.jobs === undefined || props.jobs.submit === undefined) {
    return
  }
  const submitted = await renderer.retry()
  if (submitted !== undefined) {
    emit('submitted', submitted)
    return
  }
  emit('failed', { message: renderer.errorMessage.value || '提交未完成' })
}

defineExpose({
  renderer: renderer.renderer,
  validate,
  getData,
  setData,
  reset,
  submit,
  load,
  getPlan: () => renderer.plan.value,
  getDetailRows: (key: string) => detailsValue.value[key] ?? [],
  setDetailRows: (key: string, rows: Record<string, unknown>[]) => onDetailChange({ detailKey: key, rows }),
  getRenderer: () => renderer.renderer,
})
</script>

<template>
  <div
    class="bms-form-renderer"
    data-test="form-renderer"
    :data-ready="renderer.ready.value"
    :data-degraded="renderer.degraded.value"
    :data-mode="mode"
    :data-readonly="readonly"
    :data-label-position="labelPosition"
  >
    <slot v-if="renderer.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <p v-if="plan.fallback" data-test="renderer-fallback-hint">未配置布局，已按字段默认栅格渲染</p>
        <p v-if="readonly" data-test="renderer-readonly-hint">当前为只读态</p>

        <slot v-if="!hasContent" name="empty">
          <p data-test="renderer-empty">没有可渲染的字段</p>
        </slot>

        <component
          :is="FormRendererBody"
          :mode="mode"
          :meta="resolvedMeta"
          :plan="plan"
          :model-value="model"
          :label-position="labelPosition"
          :force-read-only="forceReadOnly"
          :permissions="permissions"
          :field-props="fieldProps"
          :registry="fieldRenderer"
          :details="detailsValue"
          :errors="renderer.errors.value"
          :detail-errors="renderer.detailErrors.value"
          @field-change="onFieldChange"
          @field-error="emit('field-error', $event)"
          @detail-change="onDetailChange"
          @submit-row="onSubmitRow"
        >
          <template #field="scope">
            <slot name="field" v-bind="scope" />
          </template>
          <template #detail="scope">
            <slot name="detail" v-bind="scope" />
          </template>
        </component>

        <p v-if="detailError" data-test="renderer-detail-error">{{ detailError }}</p>

        <p
          class="bms-form-renderer__summary"
          data-test="renderer-summary"
          :data-fields="plan.sections.length"
          :data-unknown="plan.unknownFields.length"
          :data-details="Object.keys(detailsValue).length"
        >
          分区 {{ plan.sections.length }} / 失效字段 {{ plan.unknownFields.length }} / 明细页签
          {{ Object.keys(detailsValue).length }}
        </p>

        <div class="bms-form-renderer__actions" data-test="actions">
          <slot name="actions" :readonly="readonly">
            <button type="button" data-test="submit" :disabled="readonly" @click="submit">提交</button>
            <button type="button" data-test="retry" :disabled="readonly" @click="retry">重试</button>
          </slot>
        </div>

        <slot name="footer" />
      </slot>
    </template>
  </div>
</template>
