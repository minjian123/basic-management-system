// kiwi_id: 777
/** 大屏设计器与播放用例（08-9-2）：契约同实现（核心 + 投影）+ 两投影薄适配 + 七件真实实现 + 分包边界。 */

import { BaseAccess, type ReportDataset, type ScreenCanvasConfig, type ScreenComponent, type ScreenDesignerJobs, type ScreenPage, type ScreenPlayerJobs } from '@bms/core'
import {
  createScreenDesignerJobs,
  createScreenPlayerJobs,
  describeScreenDesignerContract,
  describeScreenPlayerContract,
  SCREEN_CONTRACT_COMPONENTS,
  SCREEN_CONTRACT_DATASETS,
  SCREEN_CONTRACT_PAGES,
  SCREEN_PLAY_CONTRACT_COMPONENTS,
  SCREEN_PLAY_CONTRACT_PAGES,
  type ScreenDesignerContractTarget,
  type ScreenPlayerContractTarget,
} from '@bms/core/testing'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import ComponentPalette from '../src/components/screen/ComponentPalette.vue'
import ScreenCanvas from '../src/components/screen/ScreenCanvas.vue'
import ScreenDesigner from '../src/components/screen/ScreenDesigner.vue'
import ScreenPlayer from '../src/components/screen/ScreenPlayer.vue'
import ScreenPropertyPanel from '../src/components/screen/ScreenPropertyPanel.vue'
import ScreenStage from '../src/components/screen/ScreenStage.vue'
import ScreenWidget from '../src/components/screen/ScreenWidget.vue'
import { useBaseScreenDesigner, useBaseScreenPlayer } from '../src'

/** 具体权限上下文。 */
class DemoAccess extends BaseAccess {}

/**
 * 构造权限上下文。
 *
 * @param codes 权限码。
 * @returns 权限上下文。
 */
function accessWith(codes: string[]): DemoAccess {
  const access = new DemoAccess()
  access.setCodes(codes)
  return access
}

/** 契约组件。 */
const components: ScreenComponent[] = [
  { id: 'c1', type: 'chart', x: 0, y: 0, w: 400, h: 300, z: 1, datasetId: 'd1', chartType: 'bar' },
  { id: 'c2', type: 'text', x: 420, y: 0, w: 200, h: 80, z: 2, text: '标题' },
]

/** 契约数据集。 */
const datasets: ReportDataset[] = SCREEN_CONTRACT_DATASETS

/** 大屏设计器契约目标（投影适配）。 */
function makeDesignerTarget(): ScreenDesignerContractTarget {
  const base = useBaseScreenDesigner({
    ready: true,
    screenCode: 'screen_main',
    screenName: '运营大屏',
    canvas: { width: 1920, height: 1080, theme: 'dark' },
    pages: SCREEN_CONTRACT_PAGES,
    componentsByPage: SCREEN_CONTRACT_COMPONENTS,
    activePageId: 'p1',
    datasets: SCREEN_CONTRACT_DATASETS,
    access: accessWith(['rpt:design']),
  })
  base.markBaseline()
  return {
    get ready() {
      return base.ready.value
    },
    get degraded() {
      return base.degraded.value
    },
    get readonly() {
      return base.readonly.value
    },
    get busy() {
      return base.busy.value
    },
    get dirty() {
      return base.dirty.value
    },
    get phase() {
      return base.phase.value
    },
    get requestCount() {
      return base.requestCount.value
    },
    pages: () => base.pages.value,
    components: () => base.components.value,
    selectedId: () => base.selectedId.value,
    activePageId: () => base.activePageId.value,
    validation: () => base.validation.value,
    setReady: (value) => base.setReady(value),
    setOperators: (input) => base.designer.setAccess(input.codes === undefined ? undefined : accessWith(input.codes)),
    setJobs: (jobs) => base.setJobs(jobs as ScreenDesignerJobs),
    setDatasets: (value) => base.setDatasets(value),
    setCanvas: (patch) => base.setCanvas(patch as Partial<ScreenCanvasConfig>),
    setPages: (value) => base.setPages(value),
    selectPage: (pageId) => base.selectPage(pageId),
    addPage: (input) => base.addPage(input),
    removePage: (pageId) => base.removePage(pageId),
    renamePage: (pageId, name) => base.renamePage(pageId, name),
    movePage: (pageId, index) => base.movePage(pageId, index),
    setDefaultPage: (pageId) => base.setDefaultPage(pageId),
    addComponent: (input) => base.addComponent(input),
    removeComponent: (id) => base.removeComponent(id),
    updateComponent: (id, patch) => base.updateComponent(id, patch),
    moveComponent: (id, x, y) => base.moveComponent(id, x, y),
    resizeComponent: (id, w, h) => base.resizeComponent(id, w, h),
    reorderComponent: (id, action) => base.reorderComponent(id, action),
    selectComponent: (id) => base.selectComponent(id),
    markBaseline: () => base.markBaseline(),
    discard: () => base.discard(),
    needsBlock: (action) => base.needsBlock(action),
    load: (input) => base.load(input),
    preview: (componentId, params) => base.preview(componentId, params),
    save: () => base.save(),
    publish: () => base.publish(),
    saveAs: (code, name) => base.saveAs(code, name),
  }
}

describeScreenDesignerContract('大屏设计器编排契约（ui-ep 投影）', makeDesignerTarget)

/** 大屏播放契约目标（投影适配）。 */
function makePlayerTarget(): ScreenPlayerContractTarget {
  const base = useBaseScreenPlayer({ ready: true, access: accessWith(['rpt:view']) })
  return {
    get ready() {
      return base.ready.value
    },
    get degraded() {
      return base.degraded.value
    },
    get busy() {
      return base.busy.value
    },
    get phase() {
      return base.phase.value
    },
    get requestCount() {
      return base.requestCount.value
    },
    get playing() {
      return base.playing.value
    },
    get interval() {
      return base.interval.value
    },
    pages: () => base.pages.value,
    activePageId: () => base.activePageId.value,
    components: () => base.components.value,
    data: () => base.data.value,
    setReady: (value) => base.setReady(value),
    setOperators: (input) => base.player.setAccess(input.codes === undefined ? undefined : accessWith(input.codes)),
    setJobs: (jobs) => base.setJobs(jobs as ScreenPlayerJobs),
    setPages: (value) => base.setPages(value),
    setComponents: (value) => base.setComponents(value),
    selectPage: (pageId) => base.selectPage(pageId),
    next: () => base.next(),
    prev: () => base.prev(),
    toggle: (force) => base.toggle(force),
    setPlaying: (value) => base.setPlaying(value),
    setInterval: (value) => base.setInterval(value),
    load: (input) => base.load(input),
    queryComponent: (componentId, pageId) => base.queryComponent(componentId, pageId),
    refreshPage: (pageId) => base.refreshPage(pageId),
  }
}

describeScreenPlayerContract('大屏播放编排契约（ui-ep 投影）', makePlayerTarget)

describe('投影薄适配', () => {
  it('设计器投影：占位零请求，注入后取数与结构操作', async () => {
    const empty = useBaseScreenDesigner()
    expect(empty.degraded.value).toBe(true)
    await empty.load()
    expect(empty.requestCount.value).toBe(0)

    const jobs = createScreenDesignerJobs()
    const base = useBaseScreenDesigner({ ready: true, pages: SCREEN_CONTRACT_PAGES, componentsByPage: SCREEN_CONTRACT_COMPONENTS, activePageId: 'p1', datasets, jobs })
    await base.load()
    expect(base.requestCount.value).toBe(1)
    expect(base.pages.value).toHaveLength(2)

    base.addComponent({ type: 'text' })
    expect(base.components.value).toHaveLength(3)
  })

  it('播放投影：装载与按组件取数', async () => {
    const base = useBaseScreenPlayer({ ready: true, pages: SCREEN_PLAY_CONTRACT_PAGES, componentsByPage: SCREEN_PLAY_CONTRACT_COMPONENTS, jobs: createScreenPlayerJobs() })
    await base.load()
    expect(base.pages.value).toHaveLength(2)

    await base.queryComponent('c1')
    expect(base.data.value.c1).toBeDefined()
  })

  it('播放投影：setInterval 归一', () => {
    const base = useBaseScreenPlayer({ ready: true })
    expect(base.setInterval(200)).toBe(1000)
    expect(base.interval.value).toBe(1000)
  })
})

describe('ComponentPalette 组件面板', () => {
  it('渲染分组并可点击新增 / 拖拽', async () => {
    const wrapper = mount(ComponentPalette, { props: {} })
    expect(wrapper.find('[data-test="component-palette"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="palette-group-图表"]').exists()).toBe(true)

    await wrapper.find('[data-test="palette-chart"]').trigger('click')
    expect(wrapper.emitted('add')?.[0]).toEqual(['chart'])
    await wrapper.find('[data-test="palette-chart"]').trigger('dragstart')
    expect(wrapper.emitted('drag-start')?.[0]).toEqual(['chart'])
  })

  it('只读禁用', () => {
    const wrapper = mount(ComponentPalette, { props: { readOnly: true } })
    expect(wrapper.find('[data-test="palette-text"]').attributes('disabled')).toBeDefined()
  })
})

describe('ScreenPropertyPanel 属性面板', () => {
  it('选中组件渲染坐标并上抛移动 / 更新', async () => {
    const wrapper = mount(ScreenPropertyPanel, { props: { component: components[0], datasets } })
    expect(wrapper.find('[data-test="prop-x"]').exists()).toBe(true)
    await wrapper.find('[data-test="prop-x"]').setValue('120')
    expect(wrapper.emitted('move')?.[0]?.[0]).toMatchObject({ id: 'c1', x: 120 })
    await wrapper.find('[data-test="prop-text"]').setValue('改名')
    expect(wrapper.emitted('update')?.[0]?.[0]).toMatchObject({ id: 'c1', patch: { text: '改名' } })
  })

  it('未选中渲染画布级配置', async () => {
    const wrapper = mount(ScreenPropertyPanel, { props: { canvas: { width: 2560, height: 1440, theme: 'dark' } } })
    expect(wrapper.find('[data-test="prop-resolution"]').exists()).toBe(true)
    await wrapper.find('[data-test="prop-theme"]').setValue('light')
    expect(wrapper.emitted('canvas-update')?.[0]).toEqual([{ theme: 'light' }])
  })
})

describe('ScreenWidget 组件渲染', () => {
  it('按类型渲染（文本 / 指标 / 装饰 / 图表）', () => {
    const text = mount(ScreenWidget, { props: { component: { id: 'c1', type: 'text', x: 0, y: 0, w: 1, h: 1, z: 1, text: '你好' } } })
    expect(text.find('[data-test="widget-text"]').text()).toBe('你好')

    const metric = mount(ScreenWidget, {
      props: { component: { id: 'c2', type: 'metric', x: 0, y: 0, w: 1, h: 1, z: 1, text: '万元' }, data: { columns: [], rows: [{ value: 42 }] } },
    })
    expect(metric.find('[data-test="widget-metric"]').text()).toContain('42')

    const decor = mount(ScreenWidget, { props: { component: { id: 'c3', type: 'decor', x: 0, y: 0, w: 1, h: 1, z: 1 } } })
    expect(decor.find('[data-test="widget-decor"]').exists()).toBe(true)

    const chart = mount(ScreenWidget, { props: { component: components[0], datasets } })
    expect(chart.find('[data-test="widget-chart"]').exists()).toBe(true)
  })
})

describe('ScreenCanvas 自由画布', () => {
  it('空态与分包标记；组件渲染与删除', async () => {
    const empty = mount(ScreenCanvas, { props: { components: [] } })
    expect(empty.attributes('data-subpackage')).toBe('screen')
    expect(empty.find('[data-test="canvas-empty"]').exists()).toBe(true)

    const wrapper = mount(ScreenCanvas, { props: { components, datasets, selectedId: 'c1' } })
    await vi.dynamicImportSettled()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.find('[data-test="component-c1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="component-c1"]').attributes('data-selected')).toBe('true')
    await wrapper.find('[data-test="remove-c1"]').trigger('click')
    expect(wrapper.emitted('remove-component')?.[0]).toEqual(['c1'])
  })
})

describe('ScreenStage 播放舞台', () => {
  it('空态与分包标记；组件按层级渲染', () => {
    const empty = mount(ScreenStage, { props: { components: [] } })
    expect(empty.attributes('data-subpackage')).toBe('screen-player')
    expect(empty.find('[data-test="stage-empty"]').exists()).toBe(true)

    const wrapper = mount(ScreenStage, { props: { components, datasets, activePageId: 'p1' } })
    expect(wrapper.find('[data-test="stage-c1"]').exists()).toBe(true)
  })
})

describe('ScreenDesigner 大屏设计器', () => {
  const pages: ScreenPage[] = [{ id: 'p1', name: '首页' }]

  it('未就绪降级占位', () => {
    const wrapper = mount(ScreenDesigner, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('大屏设计器未就绪')
  })

  it('就绪态三区渲染与事件上抛', async () => {
    const wrapper = mount(ScreenDesigner, { props: { ready: true, screenCode: 's1', pages, activePageId: 'p1', components, dirty: true } })
    await vi.dynamicImportSettled()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.find('[data-test="screen-code"]').text()).toBe('s1')
    expect(wrapper.find('[data-test="dirty"]').exists()).toBe(true)

    await wrapper.find('[data-test="palette-metric"]').trigger('click')
    expect(wrapper.emitted('add-component')?.[0]).toEqual(['metric'])
    expect(wrapper.attributes('data-dragging')).toBe('true')

    await wrapper.find('[data-test="page-p1"]').trigger('click')
    expect(wrapper.emitted('page-change')?.[0]).toEqual(['p1'])

    expect(wrapper.find('[data-test="screen-canvas"]').attributes('data-subpackage')).toBe('screen')
    await wrapper.find('[data-test="component-c1"]').trigger('click')
    expect(wrapper.find('[data-test="properties-selected"]').text()).toBe('chart')
    await wrapper.find('[data-test="remove-c1"]').trigger('click')
    expect(wrapper.emitted('remove-component')?.[0]).toEqual(['c1'])
    await wrapper.find('[data-test="save"]').trigger('click')
    expect(wrapper.emitted('save')).toHaveLength(1)
  })

  it('只读禁用组件拖入与保存', () => {
    const wrapper = mount(ScreenDesigner, { props: { ready: true, readOnly: true } })
    expect(wrapper.find('[data-test="palette-chart"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="save"]').attributes('disabled')).toBeDefined()
  })

  it('注入处理函数驱动保存发布与脏拦截', async () => {
    const jobs = createScreenDesignerJobs()
    const wrapper = mount(ScreenDesigner, {
      props: { ready: true, screenCode: 's1', pages, activePageId: 'p1', components, datasets: SCREEN_CONTRACT_DATASETS, jobs },
    })
    await vi.dynamicImportSettled()
    await new Promise((resolve) => setTimeout(resolve, 0))

    await wrapper.find('[data-test="open"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(jobs.calls).toContain('load')

    await wrapper.find('[data-test="palette-text"]').trigger('click')
    await wrapper.find('[data-test="new"]').trigger('click')
    expect(wrapper.emitted('dirty-block')?.[0]).toEqual([{ action: 'new' }])

    await wrapper.find('[data-test="save"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(jobs.calls).toContain('save')
    expect(wrapper.emitted('saved')).toBeTruthy()

    await wrapper.find('[data-test="publish"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(jobs.calls).toContain('publish')
  })

  it('预览播放切换内置舞台', async () => {
    const wrapper = mount(ScreenDesigner, { props: { ready: true, pages, activePageId: 'p1', components } })
    await vi.dynamicImportSettled()
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.find('[data-test="preview-play"]').trigger('click')
    expect(wrapper.find('[data-test="preview-stage"]').exists()).toBe(true)
    await wrapper.find('[data-test="preview-close"]').trigger('click')
    expect(wrapper.find('[data-test="preview-stage"]').exists()).toBe(false)
  })
})

describe('ScreenPlayer 大屏播放', () => {
  it('未就绪降级占位', () => {
    const wrapper = mount(ScreenPlayer, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('大屏播放未就绪')
  })

  it('就绪态控制与分包舞台、轮播事件', async () => {
    const wrapper = mount(ScreenPlayer, {
      props: { ready: true, screenCode: 's1', activePageId: 'p1', autoplay: true, pages: [{ id: 'p1', name: '首页' }], components },
    })
    await vi.dynamicImportSettled()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.find('[data-test="screen-stage"]').attributes('data-subpackage')).toBe('screen-player')

    await wrapper.find('[data-test="next"]').trigger('click')
    expect(wrapper.emitted('next')).toHaveLength(1)
    await wrapper.find('[data-test="toggle"]').trigger('click')
    expect(wrapper.emitted('toggle')?.[0]).toEqual([false])
    await wrapper.find('[data-test="refresh"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('注入处理函数驱动装载与按组件取数', async () => {
    const jobs = createScreenPlayerJobs()
    const wrapper = mount(ScreenPlayer, {
      props: {
        ready: true,
        activePageId: 'p1',
        pages: SCREEN_PLAY_CONTRACT_PAGES,
        components: SCREEN_PLAY_CONTRACT_COMPONENTS.p1,
        jobs,
      },
    })
    await vi.dynamicImportSettled()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(jobs.calls).toContain('load')

    await wrapper.find('[data-test="refresh"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.emitted('data-refresh')).toBeTruthy()
  })
})
