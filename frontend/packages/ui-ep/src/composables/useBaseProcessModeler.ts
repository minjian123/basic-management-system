/** 流程建模编排投影：把核心能力基类 `BaseProcessModeler` 投影为组合式（定义装载 / XML 更新与导入 / 校验合并 / 保存发布与幂等 / 脏基线与只读）。 */

import {
  BaseProcessModeler,
  type BpmnStructure,
  type BaseAccess,
  type BaseNotice,
  type ModelerDefinition,
  type ModelerDefinitionInput,
  type ModelerElement,
  type ModelerErrorTarget,
  type ModelerJobs,
  type ModelerPhase,
  type ModelerSubmitKind,
  type ModelerSubmitResult,
  type ModelerValidateResult,
} from '@bms/core'
import { computed, markRaw, onScopeDispose, ref, toRaw, type ComputedRef, type Ref } from 'vue'

/** 具体流程建模编排件（可实例化）。 */
class ProcessModelerState extends BaseProcessModeler {}

/** 选项。 */
export interface UseBaseProcessModelerOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 定义标识。 */
  definitionKey?: string
  /** 版本号。 */
  version?: number
  /** BPMN XML。 */
  xml?: string
  /** 只读（历史版本 / 无 `wf:define`）。 */
  readOnly?: boolean
  /** 注入的处理函数集（未注入即占位）。 */
  jobs?: ModelerJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知。 */
  notice?: BaseNotice
}

/** `useBaseProcessModeler` 返回面。 */
export interface UseBaseProcessModelerResult {
  /** 编排基类实例。 */
  modeler: BaseProcessModeler
  /** 数据通路是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（响应式）。 */
  degraded: Ref<boolean>
  /** 是否禁用（响应式）。 */
  disabled: Ref<boolean>
  /** 是否只读（响应式）。 */
  readOnly: Ref<boolean>
  /** 是否进行中（响应式）。 */
  busy: Ref<boolean>
  /** 编排阶段（响应式）。 */
  phase: Ref<ModelerPhase>
  /** 定义标识（响应式派生）。 */
  definitionKey: ComputedRef<string>
  /** 定义名称（响应式派生）。 */
  definitionName: ComputedRef<string>
  /** 版本号（响应式派生）。 */
  version: ComputedRef<number>
  /** BPMN XML（响应式）。 */
  xml: Ref<string>
  /** 是否有未保存变更（响应式）。 */
  dirty: Ref<boolean>
  /** 是否可编辑（响应式）。 */
  canEdit: Ref<boolean>
  /** 是否可发布（响应式）。 */
  canDeploy: Ref<boolean>
  /** 选中元素（响应式）。 */
  selected: Ref<ModelerElement | undefined>
  /** 校验结果（响应式）。 */
  validateResult: Ref<ModelerValidateResult | undefined>
  /** 失败文案（响应式）。 */
  errorMessage: Ref<string>
  /** 失败定位（响应式）。 */
  errorTarget: Ref<ModelerErrorTarget | undefined>
  /** 请求计数（响应式）。 */
  requestCount: Ref<number>
  /** 当前结构（函数式读取）。 */
  structure: () => BpmnStructure
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 切换只读。 */
  setReadOnly: (value: boolean) => void
  /** 注入处理函数集。 */
  setJobs: (jobs: ModelerJobs) => void
  /** 注入权限上下文。 */
  setAccess: (access?: BaseAccess) => void
  /** 注入提示通知。 */
  setNotice: (notice?: BaseNotice) => void
  /** 装载定义。 */
  applyDefinition: (input?: ModelerDefinitionInput) => void
  /** 取定义。 */
  load: (definitionKey?: string, version?: number) => Promise<boolean>
  /** 更新 XML。 */
  updateXml: (xml: string) => void
  /** 导入 XML（校验通过才生效）。 */
  importXml: (xml: string) => boolean
  /** 请求导入（待确认）。 */
  requestImport: (xml: string) => boolean
  /** 确认导入。 */
  confirmImport: () => boolean
  /** 取消导入。 */
  cancelImport: () => void
  /** 导出 XML。 */
  exportXml: () => string
  /** 设置选中元素。 */
  select: (elementId?: string) => ModelerElement | undefined
  /** 校验。 */
  validate: (options?: { engine?: boolean }) => Promise<ModelerValidateResult>
  /** 保存草稿。 */
  saveDraft: () => Promise<ModelerSubmitResult | undefined>
  /** 发布版本。 */
  deploy: () => Promise<ModelerSubmitResult | undefined>
  /** 重试失败提交。 */
  retry: () => Promise<ModelerSubmitResult | undefined>
  /** 派生幂等键。 */
  idempotencyKey: (kind: ModelerSubmitKind) => string
  /** 撤销未保存变更。 */
  discard: () => void
  /** 重置编排状态。 */
  reset: () => void
}

/**
 * 使用流程建模编排投影。
 *
 * @param options 选项。
 * @returns 编排基类实例与响应式面。
 */
export function useBaseProcessModeler(options: UseBaseProcessModelerOptions = {}): UseBaseProcessModelerResult {
  const modeler = new ProcessModelerState()
  if (options.jobs !== undefined) {
    modeler.setJobs(options.jobs)
  }
  if (options.access !== undefined) {
    modeler.setAccess(markRaw(toRaw(options.access)))
  }
  if (options.notice !== undefined) {
    modeler.setNotice(markRaw(toRaw(options.notice)))
  }
  modeler.applyDefinition({
    definitionKey: options.definitionKey,
    version: options.version,
    xml: options.xml,
  })
  modeler.setReadOnly(options.readOnly ?? false)
  modeler.setReady(options.ready ?? false)

  const ready = ref(modeler.ready)
  const degraded = ref(modeler.degraded)
  const disabled = ref(modeler.disabled)
  const readOnly = ref(modeler.readOnly)
  const busy = ref(modeler.busy)
  const phase = ref<ModelerPhase>(modeler.phase)
  const definition = ref<ModelerDefinition>(modeler.definition)
  const xml = ref(modeler.xml)
  const dirty = ref(modeler.dirty)
  const canEdit = ref(modeler.canEdit)
  const canDeploy = ref(modeler.canDeploy)
  const selected = ref<ModelerElement | undefined>(modeler.selected)
  const validateResult = ref<ModelerValidateResult | undefined>(modeler.validateResult)
  const errorMessage = ref(modeler.errorMessage)
  const errorTarget = ref<ModelerErrorTarget | undefined>(modeler.errorTarget)
  const requestCount = ref(modeler.requestCount)

  /** 定义标识（响应式派生）。 */
  const definitionKey = computed(() => definition.value.definitionKey)
  /** 定义名称（响应式派生）。 */
  const definitionName = computed(() => definition.value.name)
  /** 版本号（响应式派生）。 */
  const version = computed(() => definition.value.version)

  /** 从编排基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = modeler.ready
    degraded.value = modeler.degraded
    disabled.value = modeler.disabled
    readOnly.value = modeler.readOnly
    busy.value = modeler.busy
    phase.value = modeler.phase
    definition.value = modeler.definition
    xml.value = modeler.xml
    dirty.value = modeler.dirty
    canEdit.value = modeler.canEdit
    canDeploy.value = modeler.canDeploy
    selected.value = modeler.selected
    validateResult.value = modeler.validateResult
    errorMessage.value = modeler.errorMessage
    errorTarget.value = modeler.errorTarget
    requestCount.value = modeler.requestCount
  }

  const off = modeler.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    modeler,
    ready,
    degraded,
    disabled,
    readOnly,
    busy,
    phase,
    definitionKey,
    definitionName,
    version,
    xml,
    dirty,
    canEdit,
    canDeploy,
    selected,
    validateResult,
    errorMessage,
    errorTarget,
    requestCount,
    structure: () => modeler.structure,
    setReady: (value) => {
      modeler.setReady(value)
      sync()
    },
    setReadOnly: (value) => {
      modeler.setReadOnly(value)
      sync()
    },
    setJobs: (jobs) => {
      modeler.setJobs(jobs)
      sync()
    },
    setAccess: (access) => {
      modeler.setAccess(access === undefined ? undefined : markRaw(toRaw(access)))
      sync()
    },
    setNotice: (notice) => {
      modeler.setNotice(notice === undefined ? undefined : markRaw(toRaw(notice)))
      sync()
    },
    applyDefinition: (input) => {
      modeler.applyDefinition(input)
      sync()
    },
    load: async (definitionKey, version) => {
      const result = await modeler.load(definitionKey, version)
      sync()
      return result
    },
    updateXml: (next) => {
      modeler.updateXml(next)
      sync()
    },
    importXml: (next) => {
      const result = modeler.importXml(next)
      sync()
      return result
    },
    requestImport: (next) => {
      const result = modeler.requestImport(next)
      sync()
      return result
    },
    confirmImport: () => {
      const result = modeler.confirmImport()
      sync()
      return result
    },
    cancelImport: () => {
      modeler.cancelImport()
      sync()
    },
    exportXml: () => modeler.exportXml(),
    select: (elementId) => {
      const result = modeler.select(elementId)
      sync()
      return result
    },
    validate: async (validateOptions) => {
      const result = await modeler.validate(validateOptions)
      sync()
      return result
    },
    saveDraft: async () => {
      const result = await modeler.saveDraft()
      sync()
      return result
    },
    deploy: async () => {
      const result = await modeler.deploy()
      sync()
      return result
    },
    retry: async () => {
      const result = await modeler.retry()
      sync()
      return result
    },
    idempotencyKey: (kind) => modeler.idempotencyKey(kind),
    discard: () => {
      modeler.discard()
      sync()
    },
    reset: () => {
      modeler.reset()
      sync()
    },
  }
}
