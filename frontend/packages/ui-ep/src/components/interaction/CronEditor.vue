<script setup lang="ts">
// cron 编辑器件（08_02）：5 段编辑 + 人类可读描述 + 常用模板 + 合法性校验。
import { computed, ref, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import {
  CRON_TEMPLATES,
  describeCron,
  formatCron,
  parseCron,
  validateCron,
  type CronFields,
  type CronValidateResult,
} from '../../utils/cron'

interface Props {
  /** 5 段 cron（受控）。 */
  modelValue?: string
  /** 只读。 */
  readOnly?: boolean
  /** 展示下次执行时间入口（占位）。 */
  showNext?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '0 0 * * *',
  readOnly: false,
  showNext: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  validate: [result: CronValidateResult]
}>()

/** 段定义。 */
const SEGMENTS: { key: keyof CronFields; label: string }[] = [
  { key: 'minute', label: '分' },
  { key: 'hour', label: '时' },
  { key: 'day', label: '日' },
  { key: 'month', label: '月' },
  { key: 'week', label: '周' },
]

const segments = ref<CronFields>(
  parseCron(props.modelValue) ?? { minute: '0', hour: '0', day: '*', month: '*', week: '*' },
)

watch(
  () => props.modelValue,
  (value) => {
    const parsed = parseCron(value)
    if (parsed) {
      segments.value = parsed
    }
  },
)

/** 当前表达式。 */
const expression = computed(() => formatCron(segments.value))

/** 人类可读描述。 */
const description = computed(() => describeCron(expression.value))

/** 校验结果。 */
const result = computed<CronValidateResult>(() => validateCron(expression.value))

const { state, setState } = useBaseDataState()
watch(
  result,
  (value) => {
    setState(value.valid ? 'ready' : 'error')
  },
  { immediate: true },
)

/** 更新某段。 */
function update(key: keyof CronFields, value: string): void {
  if (props.readOnly) {
    return
  }
  segments.value = { ...segments.value, [key]: value }
  const next = formatCron(segments.value)
  emit('update:modelValue', next)
  emit('change', next)
  emit('validate', validateCron(next))
}

/** 套用模板。 */
function applyTemplate(value: string): void {
  if (props.readOnly) {
    return
  }
  const parsed = parseCron(value)
  if (!parsed) {
    return
  }
  segments.value = parsed
  emit('update:modelValue', value)
  emit('change', value)
  emit('validate', validateCron(value))
}
</script>

<template>
  <div
    class="bms-cron-editor"
    data-test="cron-editor"
    :data-valid="result.valid"
    :data-state="state"
    :data-readonly="readOnly || undefined"
  >
    <div class="bms-cron-editor__segments" data-test="segments">
      <label v-for="segment in SEGMENTS" :key="segment.key">
        {{ segment.label }}
        <input
          :value="segments[segment.key]"
          :data-test="`cron-${segment.key}`"
          :readonly="readOnly"
          @input="update(segment.key, ($event.target as HTMLInputElement).value)"
        />
      </label>
    </div>

    <div class="bms-cron-editor__templates" data-test="templates">
      <button
        v-for="template in CRON_TEMPLATES"
        :key="template.key"
        type="button"
        :data-test="`cron-template-${template.key}`"
        :disabled="readOnly"
        @click="applyTemplate(template.expression)"
      >
        {{ template.label }}
      </button>
    </div>

    <p class="bms-cron-editor__expression" data-test="cron-expression">{{ expression }}</p>
    <p class="bms-cron-editor__description" data-test="cron-description">{{ description }}</p>
    <p v-if="!result.valid" class="bms-cron-editor__error" data-test="cron-error">{{ result.message }}</p>
  </div>
</template>
