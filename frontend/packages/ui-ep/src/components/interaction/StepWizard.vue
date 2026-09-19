<script setup lang="ts">
// 向导壳：步骤条（横 / 纵 / 进度）+ 当前步内容 + 底部操作栏（上一步 / 下一步 / 提交 / 取消）+ 分支步骤 + 草稿提示 + 结果步；支持弹窗内紧凑模式与窄屏自动纵向。
import {
  stableStringify,
  type BasePersistedState,
  type WizardResult,
  type WizardStep as WizardStepDef,
  type WizardValidation,
} from '@bms/core'
import { ElButton, ElProgress, ElResult, ElStep, ElSteps } from 'element-plus'
import { computed, markRaw, ref, toRaw, watch } from 'vue'

import { useBaseWizard } from '../../composables/useBaseWizard'
import { useResponsive } from '../../composables/useResponsive'
import WizardStep from './WizardStep.vue'

interface Props {
  /** 步骤定义。 */
  steps: WizardStepDef[]
  /** 向导数据初始值（单向；步骤内容经插槽读写同一份数据）。 */
  modelValue?: Record<string, unknown>
  /** 步骤条形态（缺省 `horizontal`）。 */
  direction?: 'horizontal' | 'vertical' | 'progress'
  /** 弹窗内紧凑模式（步骤条简化、间距压缩）。 */
  compact?: boolean
  /** 是否显示步骤条（缺省 `true`；单步自动隐藏）。 */
  showSteps?: boolean
  /** 草稿键（空串不启用草稿）。 */
  draftKey?: string
  /** 草稿持久化能力（未注入时草稿仅内存）。 */
  persisted?: BasePersistedState
  /** 是否显示取消按钮（缺省 `true`）。 */
  showCancel?: boolean
  /** 提交按钮文案（缺省「提交」）。 */
  submitText?: string
  /** 提交加载态。 */
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  direction: 'horizontal',
  compact: false,
  showSteps: true,
  draftKey: '',
  persisted: undefined,
  showCancel: true,
  submitText: '提交',
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
  'step-change': [key: string, index: number]
  validate: [validation: WizardValidation]
  submit: [value: Record<string, unknown>]
  cancel: [payload: { dirty: boolean }]
  'draft-restore': [value: unknown]
  'draft-discard': []
}>()

const {
  wizard,
  visibleSteps,
  currentKey,
  currentIndex,
  stepError,
  result,
  isFirst,
  isLast,
  isResult,
  setSteps,
  validateAll,
  next,
  prev,
  goTo,
  reset,
  complete,
  saveDraft,
  readDraft,
  clearDraft,
} = useBaseWizard({ steps: props.steps, draftKey: props.draftKey, draft: props.persisted })

const { isNarrow } = useResponsive()

/** 向导数据（各步共用；经插槽下发，宿主与步骤内容读写同一份）。 */
const model = ref<Record<string, unknown>>({ ...(props.modelValue ?? {}) })
/** 初始数据快照（用于取消时的脏数据判定）。 */
const initialData = ref(stableStringify(model.value))

const currentStep = computed(() => visibleSteps.value[currentIndex.value])
/** 步骤条方向：窄屏自动转纵向。 */
const stepDirection = computed<'horizontal' | 'vertical'>(() =>
  props.direction === 'vertical' || isNarrow.value ? 'vertical' : 'horizontal',
)
/** 步骤条是否展示（单步自动隐藏）。 */
const stepsVisible = computed(() => props.showSteps && visibleSteps.value.length > 1)
/** 进度形态百分比。 */
const percentage = computed(() => {
  const total = visibleSteps.value.length - 1
  return total <= 0 ? 100 : Math.round((currentIndex.value / total) * 100)
})
/** 是否存在未提交修改（与初始数据比较）。 */
const isDirty = computed(() => stableStringify(model.value) !== initialData.value)

/** 草稿提示态。 */
const draftShown = ref(false)
/** 草稿数据。 */
const draftData = ref<unknown>(undefined)

watch(
  () => props.steps,
  (value) => setSteps(value),
)
watch(
  () => props.draftKey,
  (value) => {
    wizard.draftKey = value
  },
)
watch(
  () => props.persisted,
  (value) => {
    // 跨实例基类对象不进入响应式（私有字段经代理读取会失效）。
    wizard.draft = value === undefined ? undefined : markRaw(toRaw(value))
  },
)
watch(currentKey, (key) => {
  if (key === undefined) {
    return
  }
  emit('step-change', key, currentIndex.value)
  if (props.draftKey !== '') {
    saveDraft({ ...model.value })
  }
})

const existingDraft = readDraft()
if (existingDraft !== undefined && existingDraft !== null) {
  draftData.value = existingDraft
  draftShown.value = true
}

/** 进入下一步（先校验当前步，失败停在本步并提示）。 */
async function onNext(): Promise<void> {
  const key = currentKey.value
  const moved = await next()
  emit('validate', moved ? { valid: true } : { valid: false, stepKey: key, message: stepError.value })
}

/** 返回上一步（不校验）。 */
function onPrev(): void {
  prev()
}

/** 提交：整体校验通过后上抛数据（结果态由宿主经 `complete` 置入）。 */
async function onSubmit(): Promise<void> {
  const validation = await validateAll()
  emit('validate', validation)
  if (!validation.valid) {
    return
  }
  emit('update:modelValue', { ...model.value })
  emit('submit', { ...model.value })
}

/** 取消（携带脏数据标记，二次确认由承载壳或宿主处置）。 */
function onCancel(): void {
  emit('cancel', { dirty: isDirty.value })
}

/** 跳转到已到达步骤。 */
function onGoto(key: string): void {
  goTo(key)
}

/** 恢复草稿到向导数据。 */
function onRestoreDraft(): void {
  const value = draftData.value
  if (typeof value === 'object' && value !== null) {
    model.value = { ...(value as Record<string, unknown>) }
    emit('update:modelValue', { ...model.value })
  }
  emit('draft-restore', value)
  draftShown.value = false
}

/** 丢弃草稿。 */
function onDiscardDraft(): void {
  clearDraft()
  emit('draft-discard')
  draftShown.value = false
}

/** 保存当前向导数据为草稿。 */
function onSaveDraft(): void {
  saveDraft({ ...model.value })
}

defineExpose({
  next: onNext,
  prev: onPrev,
  goTo: onGoto,
  validateAll,
  reset,
  complete,
  saveDraft: onSaveDraft,
  getData: () => ({ ...model.value }),
  currentKey,
  visibleSteps,
  wizard,
})

/** 结果态（供模板判定图标）。 */
const resultInfo = computed(() => result.value ?? ({ status: 'success' } as WizardResult))
</script>

<template>
  <div class="bms-step-wizard" :data-direction="direction" :data-compact="compact ? 'true' : 'false'">
    <slot name="draft" :restore="onRestoreDraft" :discard="onDiscardDraft" :value="draftData">
      <div v-if="draftShown" class="bms-step-wizard__draft" data-test="wizard-draft">
        <span class="bms-step-wizard__draft-text">检测到未提交的草稿</span>
        <el-button link type="primary" data-test="draft-restore" @click="onRestoreDraft">恢复</el-button>
        <el-button link data-test="draft-discard" @click="onDiscardDraft">丢弃</el-button>
      </div>
    </slot>

    <el-steps
      v-if="stepsVisible && direction !== 'progress'"
      class="bms-step-wizard__steps"
      data-test="wizard-steps"
      :active="currentIndex"
      :direction="stepDirection"
      :simple="compact"
      finish-status="success"
      align-center
    >
      <el-step
        v-for="step in visibleSteps"
        :key="step.key"
        :title="step.title"
        :description="compact ? '' : step.description"
        :data-test="`wizard-step-tab-${step.key}`"
        class="bms-step-wizard__step"
        @click="onGoto(step.key)"
      />
    </el-steps>

    <el-progress
      v-else-if="stepsVisible"
      class="bms-step-wizard__progress"
      data-test="wizard-progress"
      :percentage="percentage"
      :show-text="false"
    />

    <div v-if="!isResult" class="bms-step-wizard__body" data-test="wizard-body">
      <slot name="step" :step="currentStep" :index="currentIndex" :model="model" :error="stepError">
        <wizard-step
          :index="visibleSteps.length > 1 ? currentIndex + 1 : 0"
          :title="currentStep?.title ?? ''"
          :description="currentStep?.description ?? ''"
          :error="stepError"
        >
          <slot :step="currentStep" :index="currentIndex" :model="model" :error="stepError" />
        </wizard-step>
      </slot>
    </div>

    <div v-else class="bms-step-wizard__result" data-test="wizard-result">
      <slot name="result" :result="result">
        <el-result
          :icon="resultInfo.status === 'success' ? 'success' : 'error'"
          :title="resultInfo.title ?? (resultInfo.status === 'success' ? '提交成功' : '提交失败')"
          :sub-title="resultInfo.message ?? ''"
        >
          <template #extra>
            <slot name="result-extra" :result="result" />
          </template>
        </el-result>
      </slot>
    </div>

    <div v-if="!isResult" class="bms-step-wizard__actions" data-test="wizard-actions">
      <slot name="actions" :next="onNext" :prev="onPrev" :submit="onSubmit" :cancel="onCancel" :is-last="isLast">
        <el-button v-if="showCancel" data-test="wizard-cancel" @click="onCancel">取消</el-button>
        <el-button :disabled="isFirst" data-test="wizard-prev" @click="onPrev">上一步</el-button>
        <el-button v-if="!isLast" type="primary" data-test="wizard-next" @click="onNext">下一步</el-button>
        <el-button v-else type="primary" :loading="loading" data-test="wizard-submit" @click="onSubmit">
          {{ submitText }}
        </el-button>
      </slot>
    </div>
  </div>
</template>

<style scoped>
.bms-step-wizard__draft {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md, 8px);
  padding: var(--bms-spacing-md, 8px) var(--bms-spacing-lg, 16px);
  margin-bottom: var(--bms-spacing-md, 8px);
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-md, 4px);
}

.bms-step-wizard__draft-text {
  flex: 1;
  font-size: 12px;
  color: var(--bms-color-text-secondary, #909399);
}

.bms-step-wizard__body {
  margin-top: var(--bms-spacing-lg, 16px);
}

.bms-step-wizard__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--bms-spacing-md, 8px);
  margin-top: var(--bms-spacing-lg, 16px);
}
</style>
