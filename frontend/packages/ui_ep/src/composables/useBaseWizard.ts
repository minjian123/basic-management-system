/** 向导编排投影：把核心向导编排能力基类 `BaseWizard` 投影为组合式（可见步骤 / 当前步 / 校验 / 跳转 / 草稿）。 */

import { BaseWizard, type WizardResult, type WizardStep, type WizardValidation } from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体向导编排（可实例化）。 */
class Wizard extends BaseWizard {}

/** 选项。 */
export interface UseBaseWizardOptions {
  /** 步骤定义。 */
  steps?: WizardStep[]
  /** 草稿键（空串不启用草稿）。 */
  draftKey?: string
  /** 草稿持久化能力（未注入时草稿仅内存）。 */
  draft?: BaseWizard['draft']
}

/** `useBaseWizard` 返回面。 */
export interface UseBaseWizardResult {
  /** 向导编排基类实例。 */
  wizard: BaseWizard
  /** 全部步骤（响应式）。 */
  steps: Ref<WizardStep[]>
  /** 可见步骤（响应式）。 */
  visibleSteps: Ref<WizardStep[]>
  /** 当前步骤键（响应式）。 */
  currentKey: Ref<string | undefined>
  /** 当前步骤序号（响应式）。 */
  currentIndex: Ref<number>
  /** 已到达步骤键（响应式）。 */
  visited: Ref<string[]>
  /** 当前步校验失败文案（响应式）。 */
  stepError: Ref<string>
  /** 结果态（响应式）。 */
  result: Ref<WizardResult | undefined>
  /** 是否首步（响应式）。 */
  isFirst: Ref<boolean>
  /** 是否末步（响应式）。 */
  isLast: Ref<boolean>
  /** 是否结果态（响应式）。 */
  isResult: Ref<boolean>
  /** 设置步骤集。 */
  setSteps: (steps: WizardStep[]) => void
  /** 设置某步可见性（分支步骤）。 */
  setVisible: (key: string, visible: boolean) => void
  /** 校验单个步骤。 */
  validateStep: (key: string) => Promise<WizardValidation>
  /** 下一步。 */
  next: () => Promise<boolean>
  /** 上一步。 */
  prev: () => boolean
  /** 跳转（仅已到达步）。 */
  goTo: (key: string) => boolean
  /** 整体校验。 */
  validateAll: () => Promise<WizardValidation>
  /** 完成（结果态）。 */
  complete: (result: WizardResult) => void
  /** 重置。 */
  reset: () => void
  /** 保存草稿。 */
  saveDraft: (value: unknown) => void
  /** 读取草稿。 */
  readDraft: () => unknown
  /** 清除草稿。 */
  clearDraft: () => void
}

/**
 * 使用向导编排投影。
 *
 * @param options 选项。
 * @returns 向导编排基类实例与响应式面。
 */
export function useBaseWizard(options: UseBaseWizardOptions = {}): UseBaseWizardResult {
  const wizard = new Wizard()
  if (options.draftKey !== undefined) {
    wizard.draftKey = options.draftKey
  }
  if (options.draft !== undefined) {
    // 跨实例基类对象不进入响应式（私有字段经代理读取会失效）。
    wizard.draft = markRaw(toRaw(options.draft))
  }
  wizard.setSteps(options.steps ?? [])

  const steps = ref<WizardStep[]>(wizard.steps)
  const visibleSteps = ref<WizardStep[]>(wizard.visibleSteps)
  const currentKey = ref<string | undefined>(wizard.currentKey)
  const currentIndex = ref(wizard.currentIndex)
  const visited = ref<string[]>([...wizard.visited])
  const stepError = ref(wizard.stepError)
  const result = ref<WizardResult | undefined>(wizard.result)
  const isFirst = ref(wizard.isFirst)
  const isLast = ref(wizard.isLast)
  const isResult = ref(wizard.isResult)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    steps.value = wizard.steps
    visibleSteps.value = wizard.visibleSteps
    currentKey.value = wizard.currentKey
    currentIndex.value = wizard.currentIndex
    visited.value = [...wizard.visited]
    stepError.value = wizard.stepError
    result.value = wizard.result
    isFirst.value = wizard.isFirst
    isLast.value = wizard.isLast
    isResult.value = wizard.isResult
  }

  const off = wizard.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    wizard,
    steps,
    visibleSteps,
    currentKey,
    currentIndex,
    visited,
    stepError,
    result,
    isFirst,
    isLast,
    isResult,
    setSteps: (next) => {
      wizard.setSteps(next)
      sync()
    },
    setVisible: (key, visible) => {
      wizard.setVisible(key, visible)
      sync()
    },
    validateStep: (key) => wizard.validateStep(key),
    next: async () => {
      const moved = await wizard.next()
      sync()
      return moved
    },
    prev: () => {
      const moved = wizard.prev()
      sync()
      return moved
    },
    goTo: (key) => {
      const moved = wizard.goTo(key)
      sync()
      return moved
    },
    validateAll: async () => {
      const validation = await wizard.validateAll()
      sync()
      return validation
    },
    complete: (next) => {
      wizard.complete(next)
      sync()
    },
    reset: () => {
      wizard.reset()
      sync()
    },
    saveDraft: (value) => wizard.saveDraft(value),
    readDraft: () => wizard.readDraft(),
    clearDraft: () => wizard.clearDraft(),
  }
}
