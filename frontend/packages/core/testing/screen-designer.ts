/**
 * 大屏设计器编排契约（`@bms/core/testing`）。
 *
 * 大屏设计器与后续同契约实现（宿主 / 移动端跨端件）在本套件中传入适配器跑同一套断言：
 * 占位零请求、取数基线、只读不动作、组件与页面增删改、自由画布落点与层级、脏拦截、保存发布另存、预览、防重复。
 */

import { describe, expect, it } from 'vitest'

import type {
  ReportDataset,
  ScreenBlockAction,
  ScreenComponent,
  ScreenComponentType,
  ScreenDesignerJobs,
  ScreenPage,
  ScreenPreviewResult,
  ScreenSaveResult,
  ScreenSnapshot,
  ScreenValidationResult,
} from '../src'

/** 契约页。 */
export const SCREEN_CONTRACT_PAGES: ScreenPage[] = [
  { id: 'p1', name: '首页' },
  { id: 'p2', name: '明细' },
]

/** 契约数据集。 */
export const SCREEN_CONTRACT_DATASETS: ReportDataset[] = [
  {
    id: 'd1',
    code: 'sales_monthly',
    name: '销售月报',
    status: 'enabled',
    fields: [
      { name: 'month', type: 'text' },
      { name: 'receipt', type: 'number' },
    ],
  },
  { id: 'd2', code: 'stopped', name: '已停用', status: 'disabled', fields: [{ name: 'region', type: 'text' }] },
]

/** 契约初始组件。 */
export const SCREEN_CONTRACT_COMPONENTS: Record<string, ScreenComponent[]> = {
  p1: [
    { id: 'c1', type: 'chart', x: 0, y: 0, w: 400, h: 300, z: 1, datasetId: 'd1', chartType: 'bar' },
    { id: 'c2', type: 'text', x: 420, y: 0, w: 200, h: 80, z: 2, text: '标题' },
  ],
  p2: [],
}

/** 契约取数快照。 */
export const SCREEN_CONTRACT_SNAPSHOT: ScreenSnapshot = {
  code: 'screen_main',
  name: '运营大屏',
  definition: {
    canvas: { width: 1920, height: 1080, theme: 'dark' },
    pages: SCREEN_CONTRACT_PAGES,
    componentsByPage: SCREEN_CONTRACT_COMPONENTS,
    defaultPageId: 'p1',
  },
}

/** 大屏设计器契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface ScreenDesignerContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级。 */
  readonly degraded: boolean
  /** 是否只读。 */
  readonly readonly: boolean
  /** 是否进行中。 */
  readonly busy: boolean
  /** 是否脏。 */
  readonly dirty: boolean
  /** 当前阶段。 */
  readonly phase: string
  /** 请求计数。 */
  readonly requestCount: number
  /** 页清单。 */
  pages(): ScreenPage[]
  /** 当前页组件。 */
  components(): ScreenComponent[]
  /** 当前选中组件标识。 */
  selectedId(): string
  /** 当前页标识。 */
  activePageId(): string
  /** 校验结果。 */
  validation(): ScreenValidationResult
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入权限（`codes` 缺省视为有权）。 */
  setOperators(input: { codes?: string[] }): void
  /** 注入处理函数集。 */
  setJobs(jobs: ScreenDesignerJobs): void
  /** 设置数据集清单。 */
  setDatasets(datasets: readonly ReportDataset[]): void
  /** 更新画布配置。 */
  setCanvas(patch: { width?: number; height?: number; theme?: 'light' | 'dark' | 'auto' }): boolean
  /** 设置页清单。 */
  setPages(pages: readonly ScreenPage[]): boolean
  /** 切换当前页。 */
  selectPage(pageId: string): boolean
  /** 新增页。 */
  addPage(input?: { id?: string; name?: string; duration?: number }): ScreenPage | undefined
  /** 移除页。 */
  removePage(pageId: string): boolean
  /** 重命名页。 */
  renamePage(pageId: string, name: string): boolean
  /** 移动页。 */
  movePage(pageId: string, index: number): boolean
  /** 设默认页。 */
  setDefaultPage(pageId: string): boolean
  /** 新增组件。 */
  addComponent(input: { type: ScreenComponentType; datasetId?: string; chartType?: string; id?: string }): ScreenComponent | undefined
  /** 移除组件。 */
  removeComponent(id: string): boolean
  /** 更新组件。 */
  updateComponent(id: string, patch: { type?: ScreenComponentType; text?: string; chartType?: string; datasetId?: string }): boolean
  /** 移动组件。 */
  moveComponent(id: string, x: number, y: number): boolean
  /** 缩放组件。 */
  resizeComponent(id: string, w: number, h: number): boolean
  /** 层级调整。 */
  reorderComponent(id: string, action: 'raise' | 'lower' | 'top' | 'bottom'): boolean
  /** 选中组件。 */
  selectComponent(id: string | null): void
  /** 记脏基线。 */
  markBaseline(): void
  /** 撤销。 */
  discard(): boolean
  /** 是否拦截。 */
  needsBlock(action: ScreenBlockAction): boolean
  /** 取数。 */
  load(input?: { code?: string }): Promise<ScreenSnapshot | undefined>
  /** 预览取数。 */
  preview(componentId: string, params?: Record<string, unknown>): Promise<ScreenPreviewResult | undefined>
  /** 保存。 */
  save(): Promise<ScreenSaveResult | undefined>
  /** 发布。 */
  publish(): Promise<boolean>
  /** 另存为。 */
  saveAs(code: string, name?: string): Promise<ScreenSaveResult | undefined>
}

/** 契约处理函数（记录调用轨迹）。 */
export interface ScreenDesignerContractJobs extends ScreenDesignerJobs {
  /** 调用轨迹。 */
  calls: string[]
}

/**
 * 创建契约处理函数（记录调用轨迹）。
 *
 * @param onSave 保存钩子（失败用例可抛错）。
 * @returns 处理函数集。
 */
export function createScreenDesignerJobs(onSave?: () => Promise<ScreenSaveResult | undefined>): ScreenDesignerContractJobs {
  const calls: string[] = []
  return {
    calls,
    load: async () => {
      calls.push('load')
      return SCREEN_CONTRACT_SNAPSHOT
    },
    save: async () => {
      calls.push('save')
      return onSave !== undefined ? onSave() : { recordVersion: 5 }
    },
    publish: async () => {
      calls.push('publish')
    },
    saveAs: async () => {
      calls.push('saveAs')
      return { recordVersion: 1 }
    },
    preview: async () => {
      calls.push('preview')
      return { columns: [{ name: 'month', type: 'text' }], rows: [{ month: '1月' }] }
    },
  }
}

/**
 * 大屏设计器编排契约（`08-9-2`）。
 *
 * 断言：占位零请求；就绪未注入处理函数零请求；取数装载与基线；只读不动作不写脏；
 * 组件增删改与移动缩放；层级重排；页增删改与切换；脏判定与拦截；保存成功清脏 / 失败保留；发布与另存；预览；防重复。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeScreenDesignerContract(name: string, create: () => ScreenDesignerContractTarget): void {
  describe(name, () => {
    it('未就绪时降级，取数 / 保存 / 发布零请求', async () => {
      const target = create()
      target.setReady(false)
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      expect(target.requestCount).toBe(0)

      await target.load()
      await target.save()
      await target.publish()
      expect(target.requestCount).toBe(0)
    })

    it('就绪后不再降级，未注入处理函数仍零请求', async () => {
      const target = create()
      target.setReady(true)
      expect(target.degraded).toBe(false)

      await target.load()
      expect(target.requestCount).toBe(0)
    })

    it('取数装载页与组件并记基线', async () => {
      const target = create()
      const jobs = createScreenDesignerJobs()
      target.setJobs(jobs)
      await target.load()

      expect(target.requestCount).toBe(1)
      expect(target.pages()).toHaveLength(2)
      expect(target.activePageId()).toBe('p1')
      expect(target.components()).toHaveLength(2)
      expect(target.dirty).toBe(false)
      expect(jobs.calls).toContain('load')
    })

    it('只读（无权限）时结构操作不动作且不写脏', () => {
      const target = create()
      target.setOperators({ codes: [] })
      const before = target.components().length

      expect(target.addComponent({ type: 'text' })).toBeUndefined()
      expect(target.removeComponent('c1')).toBe(false)
      expect(target.addPage()).toBeUndefined()
      expect(target.components()).toHaveLength(before)
      target.markBaseline()
      expect(target.dirty).toBe(false)
    })

    it('组件增删改与移动缩放（夹取最小尺寸）', () => {
      const target = create()
      target.setOperators({ codes: ['rpt:design'] })
      const created = target.addComponent({ type: 'chart', datasetId: 'd1', chartType: 'bar' })
      expect(created).toBeDefined()
      expect(target.components()).toHaveLength(3)

      const id = created?.id ?? ''
      expect(target.moveComponent(id, 1500, 900)).toBe(true)
      const moved = target.components().find((item) => item.id === id)
      expect(moved?.x).toBe(1500)

      expect(target.resizeComponent(id, 10, 10)).toBe(true)
      const resized = target.components().find((item) => item.id === id)
      expect(resized?.w).toBe(40)

      expect(target.updateComponent(id, { text: '改名' })).toBe(true)
      expect(target.components().find((item) => item.id === id)?.text).toBe('改名')

      expect(target.removeComponent(id)).toBe(true)
      expect(target.components().some((item) => item.id === id)).toBe(false)
    })

    it('层级重排（置顶后层级最大）', () => {
      const target = create()
      target.setOperators({ codes: ['rpt:design'] })
      target.addComponent({ type: 'text' })
      const first = target.components()[0]
      expect(target.reorderComponent(first.id, 'top')).toBe(true)
      const after = target.components()
      const top = after[after.length - 1]
      expect(top.id).toBe(first.id)
      expect(top.z).toBe(after.length)

      expect(target.reorderComponent(first.id, 'bottom')).toBe(true)
      expect(target.components()[0].id).toBe(first.id)
    })

    it('页增删改与切换（保底一页）', () => {
      const target = create()
      target.setOperators({ codes: ['rpt:design'] })
      const page = target.addPage({ name: '新增页' })
      expect(page).toBeDefined()
      expect(target.pages()).toHaveLength(3)

      const pageId = page?.id ?? ''
      expect(target.renamePage(pageId, '改名')).toBe(true)
      expect(target.selectPage(pageId)).toBe(true)
      expect(target.activePageId()).toBe(pageId)

      expect(target.movePage(pageId, 0)).toBe(true)
      expect(target.pages()[0].id).toBe(pageId)
      expect(target.setDefaultPage(pageId)).toBe(true)

      expect(target.removePage(pageId)).toBe(true)
      expect(target.pages()).toHaveLength(2)
      expect(target.removePage(target.pages()[0].id)).toBe(true)
      expect(target.removePage(target.pages()[0].id)).toBe(false)
    })

    it('脏判定与拦截与撤销', () => {
      const target = create()
      target.setOperators({ codes: ['rpt:design'] })
      target.markBaseline()
      expect(target.dirty).toBe(false)

      target.addComponent({ type: 'text' })
      expect(target.dirty).toBe(true)
      expect(target.needsBlock('leave')).toBe(true)

      expect(target.discard()).toBe(true)
      expect(target.dirty).toBe(false)
    })

    it('保存成功清脏、失败保留本地与脏标记', async () => {
      const target = create()
      target.setOperators({ codes: ['rpt:design'] })
      target.setJobs(createScreenDesignerJobs())
      target.markBaseline()
      target.addComponent({ type: 'text' })
      expect(target.dirty).toBe(true)

      const result = await target.save()
      expect(result).toEqual({ recordVersion: 5 })
      expect(target.dirty).toBe(false)

      const failing = create()
      failing.setOperators({ codes: ['rpt:design'] })
      failing.setJobs(
        createScreenDesignerJobs(async () => {
          throw new Error('500')
        }),
      )
      failing.markBaseline()
      failing.addComponent({ type: 'text' })
      const failed = await failing.save()
      expect(failed).toBeUndefined()
      expect(failing.dirty).toBe(true)
    })

    it('发布与另存为', async () => {
      const target = create()
      const jobs = createScreenDesignerJobs()
      target.setJobs(jobs)
      expect(await target.publish()).toBe(true)
      expect(await target.saveAs('copy_screen', '副本')).toEqual({ recordVersion: 1 })
      expect(jobs.calls).toContain('publish')
      expect(jobs.calls).toContain('saveAs')
    })

    it('预览取数（无数据集组件不请求）', async () => {
      const target = create()
      const jobs = createScreenDesignerJobs()
      target.setJobs(jobs)
      const result = await target.preview('c1')
      expect(result?.rows).toHaveLength(1)
      expect(jobs.calls).toContain('preview')

      const before = target.requestCount
      await expect(target.preview('c2')).resolves.toBeUndefined()
      expect(target.requestCount).toBe(before)

      const noJobs = create()
      await expect(noJobs.preview('c1')).resolves.toBeUndefined()
    })

    it('校验：停用数据集阻断、越界为警告', () => {
      const target = create()
      target.setOperators({ codes: ['rpt:design'] })
      expect(target.validation().valid).toBe(true)

      target.addComponent({ type: 'metric', datasetId: 'd2' })
      expect(target.validation().valid).toBe(false)
      expect(target.validation().errors.some((issue) => issue.kind === 'disabled-dataset')).toBe(true)

      target.moveComponent('c1', 2000, 1200)
      expect(target.validation().errors.some((issue) => issue.kind === 'overflow')).toBe(true)
    })
  })
}
