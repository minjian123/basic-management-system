<script setup lang="ts">
// 表单渲染器（占位版，08_01_02）：契约先行冻结；数据通路未就绪时不请求、只读 + 降级提示。渲染主体独立分包懒加载。
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import { useBaseFormMeta } from '../../composables/useBaseFormMeta'
import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

// 渲染主体独立分包（字段控件分发区，真实实现 08_06 接入）。
const FormRendererBody = defineAsyncComponent(() => import('./FormRendererBody.vue'))

/** 表单三态。 */
export type FormRenderMode = 'create' | 'edit' | 'view'

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
  mode?: FormRenderMode
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
  degradeText: '表单渲染器未就绪（占位）',
})

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
  change: [value: Record<string, unknown>]
  submit: [value: Record<string, unknown>]
  validate: [result: FormValidateResult]
  'field-change': [payload: { field: string; value: unknown }]
  retry: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const { meta: loadedMeta, load } = useBaseFormMeta()

const model = ref<Record<string, unknown>>({ ...props.modelValue })

watch(
  () => props.ready,
  (next) => {
    placeholder.setReady(next)
    if (next) {
      void load()
    }
  },
)

watch(
  () => props.modelValue,
  (next) => {
    model.value = { ...next }
  },
)

/** 生效只读（强制只读 / 查看态）。 */
const readonly = computed(() => props.forceReadOnly || props.mode === 'view')

/** 生效元数据（外部传入优先，否则取投影加载结果）。 */
const resolvedMeta = computed(() => props.meta ?? loadedMeta.value)

/** 取表单数据。 */
function getData(): Record<string, unknown> {
  return { ...model.value }
}

/** 设置表单数据。 */
function setData(value: Record<string, unknown>): void {
  model.value = { ...value }
  const data = getData()
  emit('update:modelValue', data)
  emit('change', data)
}

/** 重置字段。 */
function reset(): void {
  model.value = {}
  emit('update:modelValue', {})
}

/** 校验（占位：无规则，恒定通过）。 */
function validate(): FormValidateResult {
  const result: FormValidateResult = { valid: true, errors: [] }
  emit('validate', result)
  return result
}

/** 提交（占位：仅透传事件）。 */
function submit(): void {
  if (readonly.value) {
    return
  }
  const result = validate()
  if (!result.valid) {
    return
  }
  emit('submit', getData())
}

defineExpose({ validate, getData, setData, reset, submit })
</script>

<template>
  <div
    class="bms-form-renderer"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <component
          :is="FormRendererBody"
          :mode="mode"
          :meta="resolvedMeta"
          :model-value="model"
          :label-position="labelPosition"
          :force-read-only="forceReadOnly"
        />
        <div class="bms-form-renderer__actions" data-test="actions">
          <slot name="actions" :readonly="readonly">
            <button type="button" data-test="submit" :disabled="readonly" @click="submit">提交</button>
          </slot>
        </div>
      </slot>
    </template>
  </div>
</template>
