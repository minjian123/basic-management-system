/**
 * 大屏设计器编排能力基类：组件与页面增删改 / 自由画布落点与层级 / 画布配置 / 脏基线 / 预览取数 / 保存发布另存。
 *
 * 组合权限、提示、数据状态、拖拽与异步任务能力基类；取数 / 保存 / 发布 / 另存 / 预览处理函数由宿主注入，
 * 未注入即占位（不请求、返回 `undefined` / `false`）；判定落在 `domain/screen-layout.ts`。
 */

import { BasePlaceholderState } from './placeholder-state'
import { BaseAccess } from './access'
import { BaseAsyncTask } from './async-task'
import { BaseDataState } from './data-state'
import { BaseDragDrop } from './drag-drop'
import { BaseNotice } from './notice'
import {
  addComponent,
  addPage,
  bringToTop,
  findComponent,
  findPage,
  isScreenDirty,
  lowerComponent,
  moveComponent,
  movePage,
  normalizeCanvasConfig,
  normalizePages,
  normalizeScreenDefinition,
  raiseComponent,
  removeComponent,
  removePage,
  renamePage,
  resizeComponent,
  sendToBottom,
  updateComponent,
  validateScreen,
  type ScreenCanvasConfig,
  type ScreenComponent,
  type ScreenComponentType,
  type ScreenDefinition,
  type ScreenPage,
  type ScreenValidationResult,
  SCREEN_DESIGN_PERM,
} from '../domain/screen-layout'
import type { ReportDataset, ReportField } from '../domain/report-layout'

/** 设计阶段。 */
export type ScreenDesignerPhase = 'idle' | 'loading' | 'saving' | 'publishing' | 'done' | 'failed'
/** 取数快照。 */
export interface ScreenSnapshot {
  /** 大屏编码。 */
  code: string
  /** 大屏名称。 */
  name: string
  /** 大屏定义（可选；缺省为空画布 + 一页）。 */
  definition?: Partial<ScreenDefinition>
}
/** 保存结果。 */
export interface ScreenSaveResult {
  /** 记录版本。 */
  recordVersion?: number
}
/** 预览取数结果。 */
export interface ScreenPreviewResult {
  /** 字段声明。 */
  columns: ReportField[]
  /** 数据行。 */
  rows: Record<string, unknown>[]
}
/** 注入的处理函数集（未注入即占位不请求）。 */
export interface ScreenDesignerJobs {
  /** 取数。 */
  load?: (input: { code?: string }) => Promise<ScreenSnapshot | undefined>
  /** 保存。 */
  save?: (input: ScreenDefinition) => Promise<ScreenSaveResult | undefined>
  /** 发布。 */
  publish?: (input: { code: string }) => Promise<void>
  /** 另存为。 */
  saveAs?: (input: ScreenDefinition) => Promise<ScreenSaveResult | undefined>
  /** 设计态预览取数（只读从库口径）。 */
  preview?: (input: { componentId: string; datasetId: string; params?: Record<string, unknown> }) => Promise<ScreenPreviewResult | undefined>
}
/** 脏数据拦截场景。 */
export type ScreenBlockAction = 'new' | 'open' | 'leave'

/** 大屏设计器编排能力基类（抽象）。 */
export abstract class BaseScreenDesigner extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'screen-designer'
  /** 依赖登记。 */
  override readonly depends = ['placeholder-state', 'access', 'notice', 'data-state', 'drag-drop', 'async-task']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 大屏编码。 */
  screenCode = ''
  /** 大屏名称。 */
  screenName = ''
  /** 画布配置。 */
  canvas: ScreenCanvasConfig = normalizeCanvasConfig(undefined)
  /** 多页。 */
  pages: ScreenPage[] = [{ id: 'p-1', name: '页 1' }]
  /** 各页组件（键为页标识）。 */
  componentsByPage: Record<string, ScreenComponent[]> = { 'p-1': [] }
  /** 当前页标识。 */
  activePageId = 'p-1'
  /** 默认页标识。 */
  defaultPageId = 'p-1'
  /** 当前选中组件标识。 */
  selectedId = ''
  /** 脏基线定义。 */
  baseline: ScreenDefinition | undefined = undefined
  /** 当前阶段。 */
  phase: ScreenDesignerPhase = 'idle'
  /** 错误文案。 */
  errorMessage = ''
  /** 注入的处理函数集。 */
  jobs: ScreenDesignerJobs = {}
  /** 数据集清单（校验用）。 */
  datasets: ReportDataset[] = []
  /** 权限上下文。 */
  access: BaseAccess | undefined = undefined
  /** 提示通知协作者。 */
  notice: BaseNotice | undefined = undefined
  /** 数据状态能力（预览取数）。 */
  dataState: BaseDataState | undefined = undefined
  /** 拖拽能力（画布落点广播）。 */
  drag: BaseDragDrop | undefined = undefined
  /** 异步任务能力。 */
  asyncTask: BaseAsyncTask | undefined = undefined
  /** 是否进行中。 */
  #busy = false


  /** 是否只读（占位 / 无权限）。 */
  get readonly(): boolean {
    return this.degraded || !this.#hasDesign()
  }

  /** 是否可编辑。 */
  get canEdit(): boolean {
    return !this.readonly && !this.#busy
  }

  /** 是否进行中。 */
  get busy(): boolean {
    return this.#busy
  }

  /** 是否脏。 */
  get dirty(): boolean {
    return isScreenDirty(this.definition, this.baseline)
  }

  /** 是否可保存。 */
  get canSave(): boolean {
    return this.canEdit && this.validation.valid
  }

  /** 校验结果。 */
  get validation(): ScreenValidationResult {
    return validateScreen(this.definition, this.datasets)
  }

  /** 当前大屏定义。 */
  get definition(): ScreenDefinition {
    const componentsByPage: Record<string, ScreenComponent[]> = {}
    for (const page of this.pages) {
      componentsByPage[page.id] = (this.componentsByPage[page.id] ?? []).map((item) => ({ ...item }))
    }
    return {
      code: this.screenCode,
      name: this.screenName,
      canvas: this.canvas,
      pages: this.pages,
      componentsByPage,
      defaultPageId: this.#defaultPage(),
    }
  }

  /** 当前页。 */
  get activePage(): ScreenPage | undefined {
    return findPage(this.pages, this.activePageId)
  }

  /** 当前页组件。 */
  get activeComponents(): ScreenComponent[] {
    return [...(this.componentsByPage[this.activePageId] ?? [])]
  }

  /** 当前选中组件。 */
  get selectedComponent(): ScreenComponent | undefined {
    return findComponent(this.componentsByPage[this.activePageId] ?? [], this.selectedId)
  }


  /**
   * 注入处理函数集。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: ScreenDesignerJobs): void {
    this.jobs = jobs
    this.notifyLifecycle('update')
  }

  /**
   * 注入权限上下文。
   *
   * @param access 权限上下文。
   */
  setAccess(access: BaseAccess | undefined): void {
    this.access = access
    this.notifyLifecycle('update')
  }

  /**
   * 注入提示通知。
   *
   * @param notice 提示通知。
   */
  setNotice(notice: BaseNotice | undefined): void {
    this.notice = notice
    this.notifyLifecycle('update')
  }

  /**
   * 注入数据状态能力。
   *
   * @param state 数据状态能力。
   */
  setDataState(state: BaseDataState | undefined): void {
    this.dataState = state
    this.notifyLifecycle('update')
  }

  /**
   * 注入拖拽能力。
   *
   * @param drag 拖拽能力。
   */
  setDrag(drag: BaseDragDrop | undefined): void {
    this.drag = drag
    this.notifyLifecycle('update')
  }

  /**
   * 注入异步任务能力。
   *
   * @param task 异步任务能力。
   */
  setAsyncTask(task: BaseAsyncTask | undefined): void {
    this.asyncTask = task
    this.notifyLifecycle('update')
  }

  /**
   * 设置数据集清单（校验用）。
   *
   * @param datasets 数据集清单。
   */
  setDatasets(datasets: readonly ReportDataset[]): void {
    this.datasets = [...datasets]
    this.notifyLifecycle('update')
  }

  /**
   * 更新画布配置（合并归一）。
   *
   * @param patch 画布变更。
   * @returns 是否生效。
   */
  setCanvas(patch: Partial<ScreenCanvasConfig>): boolean {
    if (!this.canEdit) {
      return false
    }
    this.canvas = normalizeCanvasConfig({ ...this.canvas, ...patch })
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 设置页清单（当前页失效时回落默认页 / 首页）。
   *
   * @param pages 页清单。
   * @returns 是否生效。
   */
  setPages(pages: readonly ScreenPage[]): boolean {
    if (pages.length === 0) {
      return false
    }
    this.pages = normalizePages(pages)
    const nextByPage: Record<string, ScreenComponent[]> = {}
    for (const page of this.pages) {
      nextByPage[page.id] = this.componentsByPage[page.id] ?? []
    }
    this.componentsByPage = nextByPage
    if (!this.pages.some((page) => page.id === this.activePageId)) {
      this.activePageId = this.#defaultPage()
      this.selectedId = ''
    }
    if (!this.pages.some((page) => page.id === this.defaultPageId)) {
      this.defaultPageId = this.pages[0].id
    }
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 切换大屏（脏数据时不切换并返回 `false`）。
   *
   * @param code 大屏编码。
   * @param name 大屏名称。
   * @returns 是否切换成功。
   */
  setScreenCode(code: string, name = ''): boolean {
    if (this.dirty) {
      return false
    }
    this.screenCode = code
    this.screenName = name
    this.selectedId = ''
    this.pages = [{ id: 'p-1', name: '页 1' }]
    this.componentsByPage = { 'p-1': [] }
    this.activePageId = 'p-1'
    this.defaultPageId = 'p-1'
    this.baseline = undefined
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 切换当前页。
   *
   * @param pageId 页标识。
   * @returns 是否切换成功。
   */
  selectPage(pageId: string): boolean {
    if (!this.pages.some((page) => page.id === pageId)) {
      return false
    }
    this.activePageId = pageId
    this.selectedId = ''
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 新增页。
   *
   * @param input 新增入参。
   * @returns 新增页（只读 / 占位返回 `undefined`）。
   */
  addPage(input: { id?: string; name?: string; duration?: number } = {}): ScreenPage | undefined {
    if (!this.canEdit) {
      return undefined
    }
    const next = addPage(this.pages, input)
    const created = next[next.length - 1]
    this.pages = next
    this.componentsByPage = { ...this.componentsByPage, [created.id]: [] }
    this.notifyLifecycle('update')
    return created
  }

  /**
   * 移除页（保底一页）。
   *
   * @param pageId 页标识。
   * @returns 是否生效。
   */
  removePage(pageId: string): boolean {
    if (!this.canEdit || this.pages.length <= 1 || !this.pages.some((page) => page.id === pageId)) {
      return false
    }
    this.pages = removePage(this.pages, pageId)
    const nextByPage = { ...this.componentsByPage }
    delete nextByPage[pageId]
    this.componentsByPage = nextByPage
    if (this.activePageId === pageId) {
      this.activePageId = this.#defaultPage()
      this.selectedId = ''
    }
    if (this.defaultPageId === pageId) {
      this.defaultPageId = this.pages[0].id
    }
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 重命名页。
   *
   * @param pageId 页标识。
   * @param name 新页名。
   * @returns 是否生效。
   */
  renamePage(pageId: string, name: string): boolean {
    if (!this.canEdit || !this.pages.some((page) => page.id === pageId)) {
      return false
    }
    this.pages = renamePage(this.pages, pageId, name)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 移动页。
   *
   * @param pageId 页标识。
   * @param index 目标索引。
   * @returns 是否生效。
   */
  movePage(pageId: string, index: number): boolean {
    if (!this.canEdit || !this.pages.some((page) => page.id === pageId)) {
      return false
    }
    this.pages = movePage(this.pages, pageId, index)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 设默认页。
   *
   * @param pageId 页标识。
   * @returns 是否生效。
   */
  setDefaultPage(pageId: string): boolean {
    if (!this.canEdit || !this.pages.some((page) => page.id === pageId)) {
      return false
    }
    this.defaultPageId = pageId
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 新增组件（落到当前页并选中）。
   *
   * @param input 新增入参。
   * @returns 新增组件（只读 / 占位返回 `undefined`）。
   */
  addComponent(input: { type: ScreenComponentType; datasetId?: string; chartType?: string; id?: string }): ScreenComponent | undefined {
    if (!this.canEdit) {
      return undefined
    }
    const current = this.componentsByPage[this.activePageId] ?? []
    const next = addComponent(current, { type: input.type, ...(input.id !== undefined ? { id: input.id } : {}) })
    const created = next[next.length - 1]
    const patched =
      input.datasetId !== undefined || input.chartType !== undefined
        ? updateComponent(next, created.id, {
            ...(input.datasetId !== undefined ? { datasetId: input.datasetId } : {}),
            ...(input.chartType !== undefined ? { chartType: input.chartType } : {}),
          })
        : next
    this.componentsByPage = { ...this.componentsByPage, [this.activePageId]: patched }
    this.selectedId = created.id
    this.notifyLifecycle('update')
    return findComponent(patched, created.id)
  }

  /**
   * 移除组件。
   *
   * @param id 标识。
   * @returns 是否生效。
   */
  removeComponent(id: string): boolean {
    if (!this.canEdit || findComponent(this.componentsByPage[this.activePageId] ?? [], id) === undefined) {
      return false
    }
    const next = removeComponent(this.componentsByPage[this.activePageId] ?? [], id)
    this.componentsByPage = { ...this.componentsByPage, [this.activePageId]: next }
    if (this.selectedId === id) {
      this.selectedId = ''
    }
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 更新组件。
   *
   * @param id 标识。
   * @param patch 变更。
   * @returns 是否生效。
   */
  updateComponent(id: string, patch: Partial<Pick<ScreenComponent, 'type' | 'text' | 'chartType' | 'datasetId' | 'config' | 'props' | 'style'>>): boolean {
    if (!this.canEdit || findComponent(this.componentsByPage[this.activePageId] ?? [], id) === undefined) {
      return false
    }
    const next = updateComponent(this.componentsByPage[this.activePageId] ?? [], id, patch)
    this.componentsByPage = { ...this.componentsByPage, [this.activePageId]: next }
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 移动组件（绝对坐标落点）。
   *
   * @param id 标识。
   * @param x 目标 x。
   * @param y 目标 y。
   * @returns 是否生效。
   */
  moveComponent(id: string, x: number, y: number): boolean {
    if (!this.canEdit || findComponent(this.componentsByPage[this.activePageId] ?? [], id) === undefined) {
      return false
    }
    const next = moveComponent(this.componentsByPage[this.activePageId] ?? [], id, x, y)
    this.componentsByPage = { ...this.componentsByPage, [this.activePageId]: next }
    this.#emitDrop(id)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 缩放组件。
   *
   * @param id 标识。
   * @param w 目标宽。
   * @param h 目标高。
   * @returns 是否生效。
   */
  resizeComponent(id: string, w: number, h: number): boolean {
    if (!this.canEdit || findComponent(this.componentsByPage[this.activePageId] ?? [], id) === undefined) {
      return false
    }
    const next = resizeComponent(this.componentsByPage[this.activePageId] ?? [], id, w, h)
    this.componentsByPage = { ...this.componentsByPage, [this.activePageId]: next }
    this.#emitDrop(id)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 层级调整（上移 / 下移 / 置顶 / 置底）。
   *
   * @param id 标识。
   * @param action 动作。
   * @returns 是否生效。
   */
  reorderComponent(id: string, action: 'raise' | 'lower' | 'top' | 'bottom'): boolean {
    const current = this.componentsByPage[this.activePageId] ?? []
    if (!this.canEdit || findComponent(current, id) === undefined) {
      return false
    }
    const next =
      action === 'top'
        ? bringToTop(current, id)
        : action === 'bottom'
          ? sendToBottom(current, id)
          : action === 'raise'
            ? raiseComponent(current, id)
            : lowerComponent(current, id)
    this.componentsByPage = { ...this.componentsByPage, [this.activePageId]: next }
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 选中组件。
   *
   * @param id 标识（`null` 清空）。
   */
  selectComponent(id: string | null): void {
    this.selectedId = id ?? ''
    this.notifyLifecycle('update')
  }

  /** 记脏基线。 */
  markBaseline(): void {
    this.baseline = this.#cloneDefinition()
    this.notifyLifecycle('update')
  }

  /**
   * 撤销未保存变更（回到基线）。
   *
   * @returns 是否发生回滚。
   */
  discard(): boolean {
    if (this.baseline === undefined || !this.dirty) {
      return false
    }
    this.#apply(this.baseline)
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 是否需要拦截（脏数据）。
   *
   * @param action 动作。
   * @returns 是否拦截。
   */
  needsBlock(action: ScreenBlockAction): boolean {
    void action
    return this.dirty
  }

  /**
   * 取数（占位 / 未注入处理函数时零请求）。
   *
   * @param input 入参。
   * @returns 快照（占位 / 失败返回 `undefined`）。
   */
  async load(input: { code?: string } = {}): Promise<ScreenSnapshot | undefined> {
    if (this.degraded || this.jobs.load === undefined || this.#busy) {
      return undefined
    }
    this.#busy = true
    this.errorMessage = ''
    this.requestCount += 1
    this.phase = 'loading'
    const token = this.dataState?.begin()
    this.notifyLifecycle('update')
    try {
      const snapshot = await this.jobs.load(input)
      if (snapshot !== undefined) {
        this.#apply(
          normalizeScreenDefinition({
            code: snapshot.code,
            name: snapshot.name,
            ...(snapshot.definition ?? {}),
          }),
        )
        this.markBaseline()
      }
      if (token !== undefined) {
        this.dataState?.settle(token, snapshot !== undefined ? 'ready' : 'empty')
      }
      this.phase = 'done'
      this.notifyLifecycle('update')
      return snapshot
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      if (token !== undefined) {
        this.dataState?.settle(token, 'error')
      }
      this.phase = 'failed'
      this.reportError(error, { scope: 'BaseScreenDesigner.load' })
      this.notifyLifecycle('update')
      return undefined
    } finally {
      this.#busy = false
    }
  }

  /**
   * 设计态预览取数（只读从库口径）。
   *
   * @param componentId 组件标识。
   * @param params 查询参数。
   * @returns 取数结果（占位 / 失败 / 无数据集返回 `undefined`）。
   */
  async preview(componentId: string, params?: Record<string, unknown>): Promise<ScreenPreviewResult | undefined> {
    if (this.degraded || this.jobs.preview === undefined || this.#busy) {
      return undefined
    }
    const component = findComponent(this.componentsByPage[this.activePageId] ?? [], componentId)
    if (component === undefined || component.datasetId === undefined || component.datasetId === '') {
      return undefined
    }
    this.requestCount += 1
    const token = this.dataState?.begin()
    try {
      const result = await this.jobs.preview({ componentId, datasetId: component.datasetId, params })
      if (token !== undefined) {
        this.dataState?.settle(token, result !== undefined ? 'ready' : 'empty')
      }
      return result
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      if (token !== undefined) {
        this.dataState?.settle(token, 'error')
      }
      this.reportError(error, { scope: 'BaseScreenDesigner.preview' })
      return undefined
    }
  }

  /**
   * 保存（覆盖式提交）。
   *
   * @returns 保存结果（不可保存 / 未注入返回 `undefined`）。
   */
  async save(): Promise<ScreenSaveResult | undefined> {
    if (!this.canSave || this.jobs.save === undefined) {
      return undefined
    }
    this.#busy = true
    this.errorMessage = ''
    this.phase = 'saving'
    this.notifyLifecycle('update')
    try {
      const result = await this.jobs.save(this.#cloneDefinition())
      this.markBaseline()
      this.phase = 'done'
      this.notifyLifecycle('update')
      return result
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.phase = 'failed'
      this.reportError(error, { scope: 'BaseScreenDesigner.save' })
      this.notifyLifecycle('update')
      return undefined
    } finally {
      this.#busy = false
    }
  }

  /**
   * 发布（依赖保存成功，由件层先保存）。
   *
   * @returns 是否发布成功。
   */
  async publish(): Promise<boolean> {
    if (this.degraded || this.jobs.publish === undefined || this.#busy) {
      return false
    }
    this.#busy = true
    this.phase = 'publishing'
    this.notifyLifecycle('update')
    try {
      await this.jobs.publish({ code: this.screenCode })
      this.phase = 'done'
      this.notifyLifecycle('update')
      return true
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.phase = 'failed'
      this.reportError(error, { scope: 'BaseScreenDesigner.publish' })
      this.notifyLifecycle('update')
      return false
    } finally {
      this.#busy = false
    }
  }

  /**
   * 另存为（以当前定义新建大屏）。
   *
   * @param code 新大屏编码。
   * @param name 新大屏名称。
   * @returns 保存结果（未注入返回 `undefined`）。
   */
  async saveAs(code: string, name = ''): Promise<ScreenSaveResult | undefined> {
    if (this.degraded || this.jobs.saveAs === undefined || this.#busy) {
      return undefined
    }
    this.#busy = true
    this.phase = 'saving'
    this.notifyLifecycle('update')
    try {
      const result = await this.jobs.saveAs({ ...this.#cloneDefinition(), code, name })
      this.phase = 'done'
      this.notifyLifecycle('update')
      return result
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      this.phase = 'failed'
      this.reportError(error, { scope: 'BaseScreenDesigner.saveAs' })
      this.notifyLifecycle('update')
      return undefined
    } finally {
      this.#busy = false
    }
  }

  /** 生效默认页（默认页非法时回落首页）。 */
  #defaultPage(): string {
    return this.pages.some((page) => page.id === this.defaultPageId) ? this.defaultPageId : (this.pages[0]?.id ?? '')
  }

  /** 是否持设计权限。 */
  #hasDesign(): boolean {
    return this.access === undefined || this.access.has(SCREEN_DESIGN_PERM)
  }

  /** 应用定义到状态（基线记录 / 撤销回滚共用）。 */
  #apply(definition: ScreenDefinition): void {
    this.screenCode = definition.code
    this.screenName = definition.name
    this.canvas = definition.canvas
    this.pages = definition.pages
    this.componentsByPage = definition.componentsByPage
    this.defaultPageId = definition.defaultPageId ?? definition.pages[0]?.id ?? 'p-1'
    this.activePageId = this.#defaultPage()
    this.selectedId = ''
  }

  /** 深拷贝当前定义（保存载荷与基线隔离）。 */
  #cloneDefinition(): ScreenDefinition {
    return normalizeScreenDefinition({
      code: this.screenCode,
      name: this.screenName,
      canvas: { ...this.canvas, ...(this.canvas.background !== undefined ? { background: { ...this.canvas.background } } : {}) },
      pages: this.pages.map((page) => ({ ...page })),
      componentsByPage: Object.fromEntries(
        this.pages.map((page) => [page.id, (this.componentsByPage[page.id] ?? []).map((item) => ({ ...item }))]),
      ),
      defaultPageId: this.defaultPageId,
    })
  }

  /**
   * 广播画布落点（拖拽能力未注入仍完成落点）。
   *
   * @param id 标识。
   */
  #emitDrop(id: string): void {
    this.drag?.emitDrag({ phase: 'drop', source: id, crossZone: false })
  }
}
