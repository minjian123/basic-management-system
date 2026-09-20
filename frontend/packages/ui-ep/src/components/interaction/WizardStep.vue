<script setup lang="ts">
// 单步容器：步骤标题 / 序号 / 描述 + 内容插槽 + 步骤内错误汇总（校验触发归向导壳）。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 步骤标题。 */
  title?: string
  /** 步骤描述。 */
  description?: string
  /** 步骤内错误文案（非空时展示错误行并置错误态）。 */
  error?: string
  /** 步骤序号（从 1 开始，0 表示不显示）。 */
  index?: number
  /** 是否当前步。 */
  active?: boolean
  /** 禁用态。 */
  disabled?: boolean
  /** 只读态。 */
  readonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  description: '',
  error: '',
  index: 0,
  active: true,
  disabled: false,
  readonly: false,
})

const { state, setState } = useBaseDataState()
watch(
  () => props.error,
  (error) => setState(error === '' ? 'ready' : 'error'),
  { immediate: true },
)
</script>

<template>
  <section
    class="bms-wizard-step"
    :data-active="active ? 'true' : 'false'"
    :data-state="state"
    :data-disabled="disabled ? 'true' : 'false'"
    :data-readonly="readonly ? 'true' : 'false'"
  >
    <header class="bms-wizard-step__header">
      <div class="bms-wizard-step__title">
        <span v-if="index > 0" class="bms-wizard-step__index" data-test="wizard-step-index">{{ index }}</span>
        <slot name="title">{{ title }}</slot>
      </div>
      <div class="bms-wizard-step__extra">
        <slot name="extra" />
      </div>
    </header>
    <p v-if="description" class="bms-wizard-step__description" data-test="wizard-step-description">
      {{ description }}
    </p>
    <div class="bms-wizard-step__body">
      <slot />
    </div>
    <p v-if="error" class="bms-wizard-step__error" data-test="wizard-step-error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.bms-wizard-step__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bms-spacing-md, 8px);
}

.bms-wizard-step__title {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md, 8px);
  font-weight: 600;
}

.bms-wizard-step__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1px solid var(--bms-color-border);
  font-size: 12px;
  font-weight: 400;
}

.bms-wizard-step__description {
  margin: var(--bms-spacing-sm, 4px) 0 0;
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.bms-wizard-step__body {
  margin-top: var(--bms-spacing-lg, 16px);
}

.bms-wizard-step__error {
  margin: var(--bms-spacing-md, 8px) 0 0;
  color: var(--bms-color-danger);
  font-size: 12px;
}
</style>
