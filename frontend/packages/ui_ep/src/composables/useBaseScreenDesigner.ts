/** 大屏设计器投影：把核心能力基类 `BaseScreenDesigner` 投影为组合式（页面 / 组件 / 画布 / 层级 / 脏基线 / 保存发布）。 */

import {
  BaseScreenDesigner,
  type BaseAccess,
  type BaseAsyncTask,
  type BaseDataState,
  type BaseDragDrop,
  type BaseNotice,
  type ScreenBlockAction,
  type ScreenCanvasConfig,
  type ScreenComponent,
  type ScreenComponentType,
  type ScreenDesignerJobs,
  type ScreenDesignerPhase,
  type ScreenPage,
  type ScreenPreviewResult,
  type ScreenSaveResult,
  type ScreenSnapshot,
  type ScreenValidationResult,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体大屏设计器件（可实例化）。 */
class ScreenDesignerState extends BaseScreenDesigner {}

/** 选项。 */
export interface UseBaseScreenDesignerOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 大屏编码。 */
  screenCode?: string
  /** 大屏名称。 */
  screenName?: string
  /** 画布配置。 */
  canvas?: ScreenCanvasConfig
  /** 多页。 */
  pages?: readonly ScreenPage[]
  /** 各页组件。 */
  componentsByPage?: Record<string, readonly ScreenComponent[]>
  /** 当前页标识。 */
  activePageId?: string
  /** 当前选中组件标识。 */
  selectedId?: string
  /** 数据集清单（校验用）。 */
  datasets?: import('@bms/core').ReportDataset[]
  /** 注入处理函数集（未注入即占位）。 */
  jobs?: ScreenDesignerJobs
  /** 权限上下文（未注入视为有权）。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
  /** 数据状态能力（预览取数）。 */
  dataState?: BaseDataState
  /** 拖拽能力（画布落点广播）。 */
  drag?: BaseDragDrop
  /** 异步任务能力。 */
  asyncTask?: BaseAsyncTask
}

/** `useBaseScreenDesigner` 返回面。 */
export interface UseBaseScreenDesignerResult {
  /** 大屏设计器基类实例。 */
  designer: BaseScreenDesigner
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（响应式）。 */
  degraded: Ref<boolean>
  /** 是否只读（响应式）。 */
  readonly: Ref<boolean>
  /** 是否进行中（响应式）。 */
  busy: Ref<boolean>
  /** 是否脏（响应式）。 */
  dirty: Ref<boolean>
  /** 当前阶段（响应式）。 */
  phase: Ref<ScreenDesignerPhase>
  /** 画布配置（响应式）。 */
  canvas: Ref<ScreenCanvasConfig>
  /** 多页（响应式）。 */
  pages: Ref<ScreenPage[]>
  /** 当前页组件（响应式）。 */
  components: Ref<ScreenComponent[]>
  /** 当前页标识（响应式）。 */
  activePageId: Ref<string>
  /** 当前选中标识（响应式）。 */
  selectedId: Ref<string>
  /** 当前选中组件（响应式）。 */
  selectedComponent: Ref<ScreenComponent | undefined>
  /** 校验结果（响应式）。 */
  validation: Ref<ScreenValidationResult>
  /** 错误文案（响应式）。 */
  errorMessage: Ref<string>
  /** 请求计数（响应式）。 */
  requestCount: Ref<number>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 注入处理函数集。 */
  setJobs: (jobs: ScreenDesignerJobs) => void
  /** 设置数据集清单。 */
  setDatasets: (datasets: readonly import('@bms/core').ReportDataset[]) => void
  /** 更新画布配置。 */
  setCanvas: (patch: Partial<ScreenCanvasConfig>) => boolean
  /** 设置页清单。 */
  setPages: (pages: readonly ScreenPage[]) => boolean
  /** 切换当前页。 */
  selectPage: (pageId: string) => boolean
  /** 新增页。 */
  addPage: (input?: { id?: string; name?: string; duration?: number }) => ScreenPage | undefined
  /** 移除页。 */
  removePage: (pageId: string) => boolean
  /** 重命名页。 */
  renamePage: (pageId: string, name: string) => boolean
  /** 移动页。 */
  movePage: (pageId: string, index: number) => boolean
  /** 设默认页。 */
  setDefaultPage: (pageId: string) => boolean
  /** 切换大屏。 */
  setScreenCode: (code: string, name?: string) => boolean
  /** 新增组件。 */
  addComponent: (input: { type: ScreenComponentType; datasetId?: string; chartType?: string; id?: string }) => ScreenComponent | undefined
  /** 移除组件。 */
  removeComponent: (id: string) => boolean
  /** 更新组件。 */
  updateComponent: (id: string, patch: Partial<Pick<ScreenComponent, 'type' | 'text' | 'chartType' | 'datasetId' | 'config' | 'props' | 'style'>>) => boolean
  /** 移动组件。 */
  moveComponent: (id: string, x: number, y: number) => boolean
  /** 缩放组件。 */
  resizeComponent: (id: string, w: number, h: number) => boolean
  /** 层级调整。 */
  reorderComponent: (id: string, action: 'raise' | 'lower' | 'top' | 'bottom') => boolean
  /** 选中组件。 */
  selectComponent: (id: string | null) => void
  /** 记脏基线。 */
  markBaseline: () => void
  /** 撤销。 */
  discard: () => boolean
  /** 是否拦截。 */
  needsBlock: (action: ScreenBlockAction) => boolean
  /** 取数。 */
  load: (input?: { code?: string }) => Promise<ScreenSnapshot | undefined>
  /** 预览取数。 */
  preview: (componentId: string, params?: Record<string, unknown>) => Promise<ScreenPreviewResult | undefined>
  /** 保存。 */
  save: () => Promise<ScreenSaveResult | undefined>
  /** 发布。 */
  publish: () => Promise<boolean>
  /** 另存为。 */
  saveAs: (code: string, name?: string) => Promise<ScreenSaveResult | undefined>
}

/**
 * 使用大屏设计器投影。
 *
 * @param options 选项。
 * @returns 大屏设计器基类实例与响应式面。
 */
export function useBaseScreenDesigner(options: UseBaseScreenDesignerOptions = {}): UseBaseScreenDesignerResult {
  const designer = new ScreenDesignerState()
  designer.setReady(options.ready ?? false)
  if (options.screenCode !== undefined) {
    designer.screenCode = options.screenCode
  }
  if (options.screenName !== undefined) {
    designer.screenName = options.screenName
  }
  if (options.canvas !== undefined) {
    designer.setCanvas(options.canvas)
  }
  if (options.pages !== undefined) {
    designer.setPages(options.pages)
  }
  if (options.componentsByPage !== undefined) {
    designer.componentsByPage = Object.fromEntries(
      Object.entries(options.componentsByPage).map(([key, list]) => [key, list.map((item) => ({ ...item }))]),
    )
  }
  if (options.activePageId !== undefined && designer.pages.some((page) => page.id === options.activePageId)) {
    designer.activePageId = options.activePageId
  }
  if (options.selectedId !== undefined) {
    designer.selectedId = options.selectedId
  }
  if (options.datasets !== undefined) {
    designer.setDatasets(options.datasets)
  }
  if (options.jobs !== undefined) {
    designer.jobs = options.jobs
  }
  if (options.access !== undefined) {
    designer.access = markRaw(toRaw(options.access))
  }
  if (options.notice !== undefined) {
    designer.notice = markRaw(toRaw(options.notice))
  }
  if (options.dataState !== undefined) {
    designer.dataState = markRaw(toRaw(options.dataState))
  }
  if (options.drag !== undefined) {
    designer.drag = markRaw(toRaw(options.drag))
  }
  if (options.asyncTask !== undefined) {
    designer.asyncTask = markRaw(toRaw(options.asyncTask))
  }

  const ready = ref(designer.ready)
  const degraded = ref(designer.degraded)
  const readonly = ref(designer.readonly)
  const busy = ref(designer.busy)
  const dirty = ref(designer.dirty)
  const phase = ref<ScreenDesignerPhase>(designer.phase)
  const canvas = ref<ScreenCanvasConfig>(designer.canvas)
  const pages = ref<ScreenPage[]>([...designer.pages])
  const components = ref<ScreenComponent[]>(designer.activeComponents)
  const activePageId = ref(designer.activePageId)
  const selectedId = ref(designer.selectedId)
  const selectedComponent = ref<ScreenComponent | undefined>(designer.selectedComponent)
  const validation = ref<ScreenValidationResult>(designer.validation)
  const errorMessage = ref(designer.errorMessage)
  const requestCount = ref(designer.requestCount)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = designer.ready
    degraded.value = designer.degraded
    readonly.value = designer.readonly
    busy.value = designer.busy
    dirty.value = designer.dirty
    phase.value = designer.phase
    canvas.value = designer.canvas
    pages.value = [...designer.pages]
    components.value = designer.activeComponents
    activePageId.value = designer.activePageId
    selectedId.value = designer.selectedId
    selectedComponent.value = designer.selectedComponent
    validation.value = designer.validation
    errorMessage.value = designer.errorMessage
    requestCount.value = designer.requestCount
  }

  const off = designer.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    designer.dispose()
  })

  /** 包裹动作：执行后同步响应式面。 */
  const run = <T>(action: () => T): T => {
    const value = action()
    sync()
    return value
  }

  return {
    designer,
    ready,
    degraded,
    readonly,
    busy,
    dirty,
    phase,
    canvas,
    pages,
    components,
    activePageId,
    selectedId,
    selectedComponent,
    validation,
    errorMessage,
    requestCount,
    setReady: (value) => run(() => designer.setReady(value)),
    setJobs: (jobs) => run(() => designer.setJobs(jobs)),
    setDatasets: (value) => run(() => designer.setDatasets(value)),
    setCanvas: (patch) => run(() => designer.setCanvas(patch)),
    setPages: (value) => run(() => designer.setPages(value)),
    selectPage: (pageId) => run(() => designer.selectPage(pageId)),
    addPage: (input) => run(() => designer.addPage(input)),
    removePage: (pageId) => run(() => designer.removePage(pageId)),
    renamePage: (pageId, name) => run(() => designer.renamePage(pageId, name)),
    movePage: (pageId, index) => run(() => designer.movePage(pageId, index)),
    setDefaultPage: (pageId) => run(() => designer.setDefaultPage(pageId)),
    setScreenCode: (code, name) => run(() => designer.setScreenCode(code, name)),
    addComponent: (input) => run(() => designer.addComponent(input)),
    removeComponent: (id) => run(() => designer.removeComponent(id)),
    updateComponent: (id, patch) => run(() => designer.updateComponent(id, patch)),
    moveComponent: (id, x, y) => run(() => designer.moveComponent(id, x, y)),
    resizeComponent: (id, w, h) => run(() => designer.resizeComponent(id, w, h)),
    reorderComponent: (id, action) => run(() => designer.reorderComponent(id, action)),
    selectComponent: (id) => run(() => designer.selectComponent(id)),
    markBaseline: () => run(() => designer.markBaseline()),
    discard: () => run(() => designer.discard()),
    needsBlock: (action) => designer.needsBlock(action),
    load: async (input) => {
      const value = await designer.load(input)
      sync()
      return value
    },
    preview: async (componentId, params) => {
      const value = await designer.preview(componentId, params)
      sync()
      return value
    },
    save: async () => {
      const value = await designer.save()
      sync()
      return value
    },
    publish: async () => {
      const value = await designer.publish()
      sync()
      return value
    },
    saveAs: async (code, name) => {
      const value = await designer.saveAs(code, name)
      sync()
      return value
    },
  }
}
