/**
 * 流程建模编排能力基类：定义装载、XML 更新 / 导入（两段确认）/ 导出、结构校验与引擎预解析合并、
 * 保存草稿与版本发布（内容派生幂等键 / 防重复提交）、脏基线与只读判定、错误码定位与重试。
 *
 * **数据通路由宿主注入**（取定义、存草稿、发布、引擎预解析）——未注入即占位：不发请求、返回 `undefined`、
 * 写占位文案。**画布与命令栈归件层 bpmn-js**；核心只持 XML 与结构结论；不触 DOM、不依赖第三方库。
 */

import { BaseComponent } from '../base/BaseComponent'
import {
  MODELER_DEFINE_PERM,
  MODELER_PLACEHOLDER_TEXT,
  deriveModelerKey,
  extractBpmnStructure,
  mergeValidateResults,
  nextVersion,
  normalizeDefinition,
  resolveModelerErrorCode,
  resolveModelerErrorTarget,
  structureKey,
  validateBpmnStructure,
  type BpmnStructure,
  type ModelerDefinition,
  type ModelerDefinitionInput,
  type ModelerElement,
  type ModelerErrorTarget,
  type ModelerPhase,
  type ModelerSubmitResult,
  type ModelerValidateResult,
} from '../domain/process-modeler'
import type { BaseAccess } from './access'
import type { BaseNotice } from './notice'

/** 取定义处理函数（宿主注入；未注入即占位）。 */
export type ModelerLoadHandler = (input: {
  /** 定义标识。 */
  definitionKey: string
  /** 版本号（历史版本载入）。 */
  version?: number
}) => Promise<ModelerDefinitionInput | undefined>

/** 保存草稿处理函数（宿主注入；未注入即占位）。 */
export type ModelerSaveHandler = (input: {
  /** 定义标识。 */
  definitionKey: string
  /** 定义名称。 */
  name: string
  /** BPMN XML。 */
  xml: string
  /** 版本号。 */
  version: number
  /** 幂等键（`Idempotency-Key`）。 */
  idempotencyKey: string
}) => Promise<ModelerSubmitResult | undefined>

/** 发布处理函数（宿主注入；未注入即占位）。 */
export type ModelerDeployHandler = (input: {
  /** 定义标识。 */
  definitionKey: string
  /** BPMN XML。 */
  xml: string
  /** 版本号。 */
  version: number
  /** 幂等键（`Idempotency-Key`）。 */
  idempotencyKey: string
}) => Promise<ModelerSubmitResult | undefined>

/** 引擎预解析处理函数（宿主注入；未注入即跳过引擎段）。 */
export type ModelerValidateHandler = (input: {
  /** BPMN XML。 */
  xml: string
}) => Promise<ModelerValidateResult | undefined>

/** 注入的处理函数集（未注入的项按占位：不请求、不动作）。 */
export interface ModelerJobs {
  /** 取定义（含版本与 XML）。 */
  loadDefinition?: ModelerLoadHandler
  /** 保存草稿。 */
  saveDraft?: ModelerSaveHandler
  /** 发布版本。 */
  deploy?: ModelerDeployHandler
  /** 引擎预解析（发布前校验）。 */
  validate?: ModelerValidateHandler
}

/** 提交种类（保存草稿 / 发布）。 */
export type ModelerSubmitKind = 'draft' | 'deploy'

/** 流程建模编排能力基类（抽象）。 */
export abstract class BaseProcessModeler extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'process-modeler'
  /** 依赖能力键。 */
  override readonly depends = ['access', 'notice']
  /** 当前定义。 */
  definition: ModelerDefinition = normalizeDefinition()
  /** 数据通路是否就绪（占位语义开关）。 */
  ready = false
  /** 占位态强制禁用（随就绪态联动）。 */
  override disabled = true
  /** 只读（历史版本 / 无 `wf:define`）。 */
  readOnly = false
  /** 实际发起的请求计数（就绪且注入处理函数时才计数）。 */
  requestCount = 0
  /** 编排阶段。 */
  phase: ModelerPhase = 'idle'
  /** 选中元素标识（空串表示未选中）。 */
  selectedId = ''
  /** 最近一次提交结果。 */
  lastResult: ModelerSubmitResult | undefined
  /** 失败文案。 */
  errorMessage = ''
  /** 失败定位（按错误码解析）。 */
  errorTarget: ModelerErrorTarget | undefined
  /** 待确认覆盖的导入 XML（空串表示无待确认导入）。 */
  importPending = ''
  /** 最近一次校验结果。 */
  validateResult: ModelerValidateResult | undefined
  /** 权限上下文（未注入不校验）。 */
  access: BaseAccess | undefined
  /** 提示通知（未注入不发通知）。 */
  notice: BaseNotice | undefined
  /** 宿主注入的处理函数集。 */
  jobs: ModelerJobs = {}
  /** 脏基线结构键（装载 / 提交成功 / 撤销时更新）。 */
  #baselineKey = ''
  /** 提交进行中标记（防重复提交）。 */
  #submitting = false
  /** 基线 XML（`discard` 回滚目标）。 */
  #baselineXml = ''
  /** 重试种类（失败提交的最近一次）。 */
  #retryKind: ModelerSubmitKind | undefined

  /** 是否降级（占位）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 是否进行中（取数 / 提交 / 校验）。 */
  get busy(): boolean {
    return this.#submitting || this.phase === 'loading' || this.phase === 'validating'
  }

  /** 是否存在未保存变更（未装载时恒为假）。 */
  get dirty(): boolean {
    return this.#baselineKey !== '' && this.#baselineKey !== structureKey(this.structure)
  }

  /** 是否可编辑（就绪 ∧ 非只读 ∧ 有权）。 */
  get canEdit(): boolean {
    return this.ready && !this.readOnly && this.#allowed()
  }

  /** 是否可发布（可编辑 ∧ 非进行中）。 */
  get canDeploy(): boolean {
    return this.canEdit && !this.busy
  }

  /** 当前 BPMN 结构（零依赖提取）。 */
  get structure(): BpmnStructure {
    return extractBpmnStructure(this.definition.xml)
  }

  /** 当前 XML。 */
  get xml(): string {
    return this.definition.xml
  }

  /** 下一版本号。 */
  get nextVersion(): number {
    return nextVersion(this.definition.version)
  }

  /** 选中元素（未选中返回 `undefined`）。 */
  get selected(): ModelerElement | undefined {
    return this.structure.elements.find((element) => element.id === this.selectedId)
  }

  /** 取数处理是否已注入。 */
  get loadReady(): boolean {
    return this.jobs.loadDefinition !== undefined
  }

  /** 保存处理是否已注入。 */
  get saveReady(): boolean {
    return this.jobs.saveDraft !== undefined
  }

  /** 发布处理是否已注入。 */
  get deployReady(): boolean {
    return this.jobs.deploy !== undefined
  }

  /**
   * 切换数据通路就绪态（占位语义开关）。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    this.ready = value
    this.disabled = !value
    this.touch()
  }

  /**
   * 切换只读（历史版本 / 无权限）。
   *
   * @param value 是否只读。
   */
  setReadOnly(value: boolean): void {
    this.readOnly = value
    this.touch()
  }

  /**
   * 注入处理函数集（未注入的项按占位）。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: ModelerJobs): void {
    this.jobs = jobs
    this.touch()
  }

  /**
   * 注入权限上下文（未注入视为有权，后端兜底）。
   *
   * @param access 权限上下文。
   */
  setAccess(access: BaseAccess | undefined): void {
    this.access = access
    this.touch()
  }

  /**
   * 注入提示通知（未注入不发通知）。
   *
   * @param notice 提示通知。
   */
  setNotice(notice: BaseNotice | undefined): void {
    this.notice = notice
    this.touch()
  }

  /**
   * 装载定义（XML 为空回落空流程模板；以结构键记脏基线）。
   *
   * @param input 定义装载输入。
   */
  applyDefinition(input?: ModelerDefinitionInput): void {
    this.definition = normalizeDefinition(input)
    this.#baselineXml = this.definition.xml
    this.#baselineKey = structureKey(this.structure)
    this.selectedId = ''
    this.validateResult = undefined
    this.errorMessage = ''
    this.errorTarget = undefined
    this.importPending = ''
    this.touch()
  }

  /**
   * 取定义（未就绪 / 未注入处理函数时不发请求）。
   *
   * @param definitionKey 定义标识（缺省用当前值）。
   * @param version 版本号（历史版本载入）。
   * @returns 是否装载成功。
   */
  async load(definitionKey?: string, version?: number): Promise<boolean> {
    if (!this.ready || !this.loadReady) {
      return false
    }
    const key = definitionKey ?? this.definition.definitionKey
    this.phase = 'loading'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.requestCount += 1
    this.touch()
    try {
      const input = await this.jobs.loadDefinition?.({ definitionKey: key, version })
      if (this.isDisposed) {
        return false
      }
      if (input !== undefined) {
        this.applyDefinition({ ...input, definitionKey: input.definitionKey ?? key })
        this.readOnly = input.status === 'published' && version !== undefined ? this.readOnly : this.readOnly
      }
      this.phase = 'done'
      this.touch()
      return input !== undefined
    } catch (error) {
      this.fail(error)
      return false
    }
  }

  /**
   * 更新 XML（件层画布变更回传入口）。
   *
   * @param xml BPMN XML。
   */
  updateXml(xml: string): void {
    this.definition = { ...this.definition, xml: String(xml ?? '') }
    this.validateResult = undefined
    this.errorMessage = ''
    this.errorTarget = undefined
    this.touch()
  }

  /**
   * 导入 XML（结构校验通过才生效）。
   *
   * @param xml BPMN XML。
   * @returns 是否生效。
   */
  importXml(xml: string): boolean {
    const source = String(xml ?? '')
    const check = validateBpmnStructure(source)
    if (!check.valid) {
      this.validateResult = check
      this.phase = 'failed'
      this.errorMessage = check.errors[0]?.message ?? '导入的 BPMN XML 非法'
      this.errorTarget = check.errors[0]?.elementId === undefined ? undefined : { code: 60006, elementId: check.errors[0].elementId, i18nKey: 'error.60006', refresh: false }
      this.touch()
      return false
    }
    this.definition = { ...this.definition, xml: source }
    this.selectedId = ''
    this.validateResult = check
    this.phase = 'idle'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.importPending = ''
    this.touch()
    return true
  }

  /**
   * 请求导入（置待确认；由件层二次确认后调用 `confirmImport`）。
   *
   * @param xml BPMN XML。
   * @returns 是否已置待确认（非编辑态返回 `false`）。
   */
  requestImport(xml: string): boolean {
    if (!this.canEdit) {
      return false
    }
    this.importPending = String(xml ?? '')
    this.touch()
    return true
  }

  /**
   * 确认导入（生效待确认的 XML）。
   *
   * @returns 是否生效。
   */
  confirmImport(): boolean {
    if (this.importPending === '') {
      return false
    }
    return this.importXml(this.importPending)
  }

  /** 取消导入（清空待确认；保持原画布）。 */
  cancelImport(): void {
    this.importPending = ''
    this.touch()
  }

  /**
   * 导出当前 XML（只读态同样可用）。
   *
   * @returns 当前 BPMN XML。
   */
  exportXml(): string {
    return this.definition.xml
  }

  /**
   * 设置选中元素（`elementId` 为空或未命中则清空）。
   *
   * @param elementId 元素标识。
   * @returns 选中元素；未命中返回 `undefined`。
   */
  select(elementId?: string): ModelerElement | undefined {
    const target =
      elementId === undefined || elementId === ''
        ? undefined
        : this.structure.elements.find((element) => element.id === elementId)
    this.selectedId = target?.id ?? ''
    this.touch()
    return target
  }

  /**
   * 校验（前端结构校验 + 注入式引擎预解析合并）。
   *
   * @param options 选项（`engine` 为真时追加引擎预解析；缺省为真）。
   * @returns 校验结果。
   */
  async validate(options: { engine?: boolean } = {}): Promise<ModelerValidateResult> {
    const structure = validateBpmnStructure(this.definition.xml)
    const handler = this.jobs.validate
    if (options.engine === false || !this.ready || handler === undefined) {
      this.validateResult = structure
      this.phase = structure.valid ? 'idle' : 'failed'
      this.touch()
      return structure
    }
    this.phase = 'validating'
    this.requestCount += 1
    this.touch()
    try {
      const engine = await handler({ xml: this.definition.xml })
      if (this.isDisposed) {
        return structure
      }
      const merged = mergeValidateResults(
        structure,
        engine === undefined ? undefined : { ...engine, source: 'engine' },
      )
      this.validateResult = merged
      this.phase = merged.valid ? 'idle' : 'failed'
      if (!merged.valid) {
        const first = merged.errors[0]
        this.errorMessage = first?.message ?? 'BPMN 校验未通过'
        this.errorTarget = resolveModelerErrorTarget(60006, this.structure, first?.elementId)
      }
      this.touch()
      return merged
    } catch (error) {
      this.fail(error)
      return structure
    }
  }

  /**
   * 保存草稿（校验通过才提交；携带内容派生幂等键）。
   *
   * @returns 提交结果；占位 / 只读 / 进行中 / 校验失败 / 失败时返回 `undefined`。
   */
  async saveDraft(): Promise<ModelerSubmitResult | undefined> {
    return this.submit('draft')
  }

  /**
   * 发布版本（校验通过才提交；成功后版本推进）。
   *
   * @returns 提交结果；占位 / 只读 / 进行中 / 校验失败 / 失败时返回 `undefined`。
   */
  async deploy(): Promise<ModelerSubmitResult | undefined> {
    return this.submit('deploy')
  }

  /**
   * 重试上次失败提交（复用同一幂等键）。
   *
   * @returns 提交结果；非失败态时返回 `undefined`。
   */
  async retry(): Promise<ModelerSubmitResult | undefined> {
    if (this.phase !== 'failed' || this.#retryKind === undefined) {
      return undefined
    }
    this.phase = 'idle'
    return this.submit(this.#retryKind)
  }

  /**
   * 派生幂等键（内容派生：同内容同键、内容变更换键）。
   *
   * @param kind 提交种类。
   * @returns 幂等键。
   */
  idempotencyKey(kind: ModelerSubmitKind): string {
    const version = kind === 'draft' ? this.definition.version : this.nextVersion
    return deriveModelerKey(this.definition.definitionKey, version, this.structure)
  }

  /** 撤销未保存变更（从基线 XML 回滚并清脏）。 */
  discard(): void {
    if (this.#baselineXml === '') {
      return
    }
    this.definition = { ...this.definition, xml: this.#baselineXml }
    this.selectedId = ''
    this.validateResult = undefined
    this.errorMessage = ''
    this.errorTarget = undefined
    this.touch()
  }

  /** 重置编排状态（阶段回 `idle` 并清错误，保留定义与基线）。 */
  reset(): void {
    this.phase = 'idle'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.importPending = ''
    this.#retryKind = undefined
    this.touch()
  }

  /** 是否具备定义与版本管理权限（未注入权限上下文视为有权，后端兜底）。 */
  #allowed(): boolean {
    if (this.access === undefined) {
      return true
    }
    return this.access.has(MODELER_DEFINE_PERM)
  }

  /**
   * 提交（保存草稿 / 发布）：校验通过才请求。
   *
   * @param kind 提交种类。
   * @returns 提交结果。
   */
  private async submit(kind: ModelerSubmitKind): Promise<ModelerSubmitResult | undefined> {
    if (!this.ready) {
      return undefined
    }
    const handler = kind === 'draft' ? this.jobs.saveDraft : this.jobs.deploy
    if (handler === undefined) {
      this.errorMessage = MODELER_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    // 先占位再校验：校验为异步（可含引擎预解析），若不先置提交中，并发重复提交会双双穿过 `busy` 判定。
    if (!this.canEdit || this.busy) {
      return undefined
    }
    this.#submitting = true
    this.#retryKind = kind
    this.phase = kind === 'draft' ? 'saving' : 'deploying'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.touch()
    try {
      const check = await this.validate({ engine: kind === 'deploy' })
      if (!check.valid) {
        this.phase = 'failed'
        return undefined
      }
      const payload = {
        definitionKey: this.definition.definitionKey,
        name: this.definition.name,
        xml: this.definition.xml,
        version: kind === 'draft' ? this.definition.version : this.nextVersion,
        idempotencyKey: this.idempotencyKey(kind),
      }
      this.requestCount += 1
      this.touch()
      const result = await handler(payload)
      if (this.isDisposed) {
        return undefined
      }
      this.lastResult = result ?? {}
      if (kind === 'deploy') {
        this.definition = {
          ...this.definition,
          version: result?.version ?? this.nextVersion,
          status: 'published',
        }
      }
      this.#baselineXml = this.definition.xml
      this.#baselineKey = structureKey(this.structure)
      this.#retryKind = undefined
      this.phase = 'done'
      this.notice?.enqueue(kind === 'draft' ? '草稿已保存' : `已发布版本 v${this.definition.version}`, 'success')
      return this.lastResult
    } catch (error) {
      this.fail(error)
      return undefined
    } finally {
      this.#submitting = false
      this.touch()
    }
  }

  /** 记失败（阶段 `failed` + 错误码定位 + 提示）。 */
  private fail(error: unknown): void {
    if (this.isDisposed) {
      return
    }
    const code = resolveModelerErrorCode(error)
    const elementId = (error as { elementId?: unknown } | null)?.elementId
    this.phase = 'failed'
    this.errorMessage = error instanceof Error && error.message !== '' ? error.message : '流程建模操作失败'
    this.errorTarget = resolveModelerErrorTarget(
      code,
      this.structure,
      typeof elementId === 'string' ? elementId : undefined,
    )
    this.notice?.enqueue(this.errorMessage, 'error')
    this.touch()
  }

  /** 广播生命周期更新。 */
  private touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
