<script setup lang="ts">
// cron 编辑器件（08_02）：5 段编辑 + 人类可读描述 + 常用模板 + 合法性校验。
// 样式（11-01）：段编辑改 el-input（prepend 段名）、模板改 el-button，补 <style scoped> 消费 --bms-* 令牌。
import { ElButton, ElInput } from 'element-plus'
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
      <label v-for="segment in SEGMENTS" :key="segment.key" class="bms-cron-editor__segment">
        <span class="bms-cron-editor__segment-label">{{ segment.label }}</span>
        <el-input
          :data-test="`cron-${segment.key}`"
          class="bms-cron-editor__segment-input"
          :model-value="segments[segment.key]"
          size="small"
          :readonly="readOnly"
          @update:model-value="(value: string) => update(segment.key, value)"
        />
      </label>
    </div>

    <div class="bms-cron-editor__templates" data-test="templates">
      <el-button
        v-for="template in CRON_TEMPLATES"
        :key="template.key"
        :data-test="`cron-template-${template.key}`"
        size="small"
        :disabled="readOnly"
        @click="applyTemplate(template.expression)"
      >
        {{ template.label }}
      </el-button>
    </div>

    <p class="bms-cron-editor__expression" data-test="cron-expression">{{ expression }}</p>
    <p class="bms-cron-editor__description" data-test="cron-description">{{ description }}</p>
    <p v-if="!result.valid" class="bms-cron-editor__error" data-test="cron-error">{{ result.message }}</p>
  </div>
</template>

<style scoped>
.bms-cron-editor {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-cron-editor__segments {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2) var(--bms-space-3);
}

.bms-cron-editor__segment {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-2);
}

.bms-cron-editor__segment-label {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.bms-cron-editor__segment-input {
  width: 120px;
}

.bms-cron-editor__templates {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
}

.bms-cron-editor__expression {
  margin: 0;
  padding: var(--bms-space-2) var(--bms-space-3);
  font-family: var(--bms-font-family-mono, monospace);
  font-size: var(--bms-font-size-sm);
  background: var(--bms-color-fill);
  border-radius: var(--bms-radius-md);
}

.bms-cron-editor__description {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.bms-cron-editor[data-valid='true'] .bms-cron-editor__expression {
  border-left: 2px solid var(--bms-color-success);
}

.bms-cron-editor[data-valid='false'] .bms-cron-editor__expression {
  border-left: 2px solid var(--bms-color-danger);
}

.bms-cron-editor__error {
  margin: 0;
  color: var(--bms-color-danger);
  font-size: var(--bms-font-size-sm);
}
</style>

