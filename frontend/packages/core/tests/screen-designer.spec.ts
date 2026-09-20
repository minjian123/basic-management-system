// kiwi_id: 777
/** 大屏设计器能力基类用例（08-9-2）：契约套件 + 能力身份与依赖 + 拖拽广播 + 保存发布另存 + 预览。 */

import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseScreenDesigner,
  SCREEN_DESIGN_PERM,
  validateCapabilityGraph,
  type ScreenBlockAction,
  type ScreenDesignerJobs,
} from '../src'
import {
  createScreenDesignerJobs,
  describeScreenDesignerContract,
  SCREEN_CONTRACT_COMPONENTS,
  SCREEN_CONTRACT_DATASETS,
  SCREEN_CONTRACT_PAGES,
  type ScreenDesignerContractTarget,
} from '../testing'

/** 具体大屏设计器（可实例化）。 */
class DemoDesigner extends BaseScreenDesigner {}

/** 具体权限上下文（可实例化）。 */
class DemoAccess extends BaseAccess {}

/** 构造持设计权限的权限上下文。 */
function granted(): DemoAccess {
  const access = new DemoAccess()
  access.setCodes([SCREEN_DESIGN_PERM])
  return access
}

/** 契约目标工厂（适配器接核心基类）。 */
function makeTarget(): ScreenDesignerContractTarget {
  const designer = new DemoDesigner()
  designer.setDatasets(SCREEN_CONTRACT_DATASETS)
  designer.screenCode = 'screen_main'
  designer.screenName = '运营大屏'
  designer.canvas = { width: 1920, height: 1080, theme: 'dark' }
  designer.pages = SCREEN_CONTRACT_PAGES.map((page) => ({ ...page }))
  designer.componentsByPage = Object.fromEntries(
    Object.entries(SCREEN_CONTRACT_COMPONENTS).map(([key, list]) => [key, list.map((item) => ({ ...item }))]),
  )
  designer.activePageId = 'p1'
  designer.defaultPageId = 'p1'
  designer.setAccess(granted())
  designer.markBaseline()
  designer.setReady(true)
  return {
    get ready() {
      return designer.ready
    },
    get degraded() {
      return designer.degraded
    },
    get readonly() {
      return designer.readonly
    },
    get busy() {
      return designer.busy
    },
    get dirty() {
      return designer.dirty
    },
    get phase() {
      return designer.phase
    },
    get requestCount() {
      return designer.requestCount
    },
    pages: () => designer.pages,
    components: () => designer.activeComponents,
    selectedId: () => designer.selectedId,
    activePageId: () => designer.activePageId,
    validation: () => designer.validation,
    setReady: (value) => designer.setReady(value),
    setOperators: (input) => {
      if (input.codes === undefined) {
        designer.setAccess(undefined)
        return
      }
      const access = new DemoAccess()
      access.setCodes(input.codes)
      designer.setAccess(access)
    },
    setJobs: (jobs) => designer.setJobs(jobs as ScreenDesignerJobs),
    setDatasets: (datasets) => designer.setDatasets(datasets),
    setCanvas: (patch) => designer.setCanvas(patch),
    setPages: (pages) => designer.setPages(pages),
    selectPage: (pageId) => designer.selectPage(pageId),
    addPage: (input) => designer.addPage(input),
    removePage: (pageId) => designer.removePage(pageId),
    renamePage: (pageId, name) => designer.renamePage(pageId, name),
    movePage: (pageId, index) => designer.movePage(pageId, index),
    setDefaultPage: (pageId) => designer.setDefaultPage(pageId),
    addComponent: (input) => designer.addComponent(input),
    removeComponent: (id) => designer.removeComponent(id),
    updateComponent: (id, patch) => designer.updateComponent(id, patch),
    moveComponent: (id, x, y) => designer.moveComponent(id, x, y),
    resizeComponent: (id, w, h) => designer.resizeComponent(id, w, h),
    reorderComponent: (id, action) => designer.reorderComponent(id, action),
    selectComponent: (id) => designer.selectComponent(id),
    markBaseline: () => designer.markBaseline(),
    discard: () => designer.discard(),
    needsBlock: (action) => designer.needsBlock(action as ScreenBlockAction),
    load: (input) => designer.load(input),
    preview: (componentId, params) => designer.preview(componentId, params),
    save: () => designer.save(),
    publish: () => designer.publish(),
    saveAs: (code, name) => designer.saveAs(code, name),
  }
}

describeScreenDesignerContract('大屏设计器编排契约（BaseScreenDesigner）', makeTarget)

describe('能力身份与依赖', () => {
  it('能力键与依赖登记无环', () => {
    const designer = new DemoDesigner()
    expect(designer.identifier).toBe('screen-designer')
    expect(designer.depends).toEqual(['placeholder-state', 'access', 'notice', 'data-state', 'drag-drop', 'async-task'])
    const problems = validateCapabilityGraph().filter(
      (problem) => problem.key === 'screen-designer' || problem.detail.includes('screen-designer'),
    )
    expect(problems).toEqual([])
  })
})

describe('画布与页切换', () => {
  it('分支：切换大屏清空编辑态', () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.pages = [{ id: 'p1', name: '首页' }]
    designer.componentsByPage = { p1: [{ ...SCREEN_CONTRACT_COMPONENTS.p1[0] }] }
    designer.setScreenCode('other', '别的')
    expect(designer.screenCode).toBe('other')
    expect(designer.pages).toHaveLength(1)
    expect(designer.selectedId).toBe('')
  })

  it('画布更新与选中联动', () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.pages = [{ id: 'p1', name: '首页' }]
    designer.componentsByPage = { p1: [{ ...SCREEN_CONTRACT_COMPONENTS.p1[0] }] }
    designer.activePageId = 'p1'

    expect(designer.setCanvas({ width: 2560, theme: 'light' })).toBe(true)
    expect(designer.canvas.width).toBe(2560)

    designer.selectComponent('c1')
    expect(designer.selectedComponent?.id).toBe('c1')
    designer.selectComponent(null)
    expect(designer.selectedId).toBe('')
  })
})

describe('拖拽广播与保存发布', () => {
  it('拖拽能力未注入仍完成落点', () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.pages = [{ id: 'p1', name: '首页' }]
    designer.componentsByPage = { p1: [{ ...SCREEN_CONTRACT_COMPONENTS.p1[0] }] }
    designer.activePageId = 'p1'
    expect(designer.moveComponent('c1', 640, 360)).toBe(true)
    expect(designer.componentsByPage.p1[0].x).toBe(640)
  })

  it('发布依赖保存成功（件层先保存）；另存为不改当前编码', async () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.setDatasets(SCREEN_CONTRACT_DATASETS)
    designer.screenCode = 'screen_main'
    designer.pages = [{ id: 'p1', name: '首页' }]
    designer.componentsByPage = { p1: [{ ...SCREEN_CONTRACT_COMPONENTS.p1[0] }] }
    designer.activePageId = 'p1'
    designer.markBaseline()
    const jobs = createScreenDesignerJobs()
    designer.setJobs(jobs)

    expect(await designer.save()).toEqual({ recordVersion: 5 })
    expect(await designer.publish()).toBe(true)
    await designer.saveAs('copy_screen', '副本')
    expect(designer.screenCode).toBe('screen_main')
    expect(jobs.calls).toContain('publish')
    expect(jobs.calls).toContain('saveAs')
  })

  it('保存失败保留脏标记', async () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.pages = [{ id: 'p1', name: '首页' }]
    designer.componentsByPage = { p1: [] }
    designer.activePageId = 'p1'
    designer.markBaseline()
    designer.setJobs(
      createScreenDesignerJobs(async () => {
        throw new Error('network')
      }),
    )
    designer.addComponent({ type: 'text' })
    expect(designer.dirty).toBe(true)
    expect(await designer.save()).toBeUndefined()
    expect(designer.dirty).toBe(true)
    expect(designer.errorMessage).toBe('network')
  })

  it('needsBlock 与 discard', () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.pages = [{ id: 'p1', name: '首页' }]
    designer.componentsByPage = { p1: [] }
    designer.activePageId = 'p1'
    designer.markBaseline()
    expect(designer.needsBlock('leave')).toBe(false)
    designer.addComponent({ type: 'text' })
    expect(designer.needsBlock('open')).toBe(true)
    expect(designer.discard()).toBe(true)
    expect(designer.needsBlock('new')).toBe(false)
  })
})
