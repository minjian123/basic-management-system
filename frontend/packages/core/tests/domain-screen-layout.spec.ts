// kiwi_id: 777
/** 大屏布局领域用例（08-9-2）：归一 / 组件与页操作 / 层级 / 校验 / 序列化与脏比对。 */

import { describe, expect, it } from 'vitest'

import {
  addComponent,
  addPage,
  bringToTop,
  componentLabel,
  componentsOf,
  isScreenDirty,
  lowerComponent,
  moveComponent,
  movePage,
  nextComponentId,
  nextScreenPageId,
  normalizeCanvasConfig,
  normalizeComponent,
  normalizeComponentType,
  normalizeComponents,
  normalizePages,
  normalizeResolution,
  normalizeScreenDefinition,
  paletteGroups,
  raiseComponent,
  removeComponent,
  removePage,
  renamePage,
  resizeComponent,
  screenDefinitionsEqual,
  sendToBottom,
  serializeCanvasConfig,
  serializeScreen,
  setDefaultPage,
  validateScreen,
  type ScreenComponent,
  type ScreenDefinition,
} from '../src'

/** 契约组件。 */
const components: ScreenComponent[] = [
  { id: 'c1', type: 'chart', x: 0, y: 0, w: 400, h: 300, z: 1, datasetId: 'd1' },
  { id: 'c2', type: 'text', x: 420, y: 0, w: 200, h: 80, z: 2, text: '标题' },
]

/** 契约数据集。 */
const datasets = [
  {
    id: 'd1',
    code: 'sales',
    name: '销售',
    status: 'enabled' as const,
    fields: [{ name: 'month', type: 'text' }],
  },
  { id: 'd2', code: 'stock', name: '库存', status: 'disabled' as const },
]

describe('归一', () => {
  it('分辨率：正数取整、缺失回落', () => {
    expect(normalizeResolution({ width: 1280.4, height: 720 })).toEqual({ width: 1280, height: 720 })
    expect(normalizeResolution(undefined)).toEqual({ width: 1920, height: 1080 })
  })

  it('画布：主题限值、背景保留', () => {
    const canvas = normalizeCanvasConfig({ theme: 'dark', background: { color: '#000' } })
    expect(canvas.theme).toBe('dark')
    expect(canvas.background?.color).toBe('#000')
    expect(normalizeCanvasConfig({ theme: 'weird' }).theme).toBe('auto')
  })

  it('页：缺标识丢弃、名称回落、重复剔除', () => {
    expect(normalizePages([{ id: 'p1' }, { name: '无标识' }, { id: 'p1', name: '重复' }])).toEqual([
      { id: 'p1', name: '页 p1' },
    ])
  })

  it('组件：类型未知回落 text、尺寸夹取最小、缺标识丢弃', () => {
    expect(normalizeComponentType('unknown')).toBe('text')
    const component = normalizeComponent({ id: 'c1', type: 'weird', w: 1, h: 1 })
    expect(component?.type).toBe('text')
    expect(component?.w).toBe(40)
    expect(component?.h).toBe(32)
    expect(normalizeComponent({ type: 'text' })).toBeUndefined()
    expect(normalizeComponents([{ id: 'c1' }, { id: '' }])).toHaveLength(1)
  })

  it('完整定义：保证至少一页与有效默认页', () => {
    const definition = normalizeScreenDefinition({ code: 's1', pages: [], defaultPageId: 'ghost' })
    expect(definition.pages).toHaveLength(1)
    expect(definition.defaultPageId).toBe(definition.pages[0].id)
    expect(definition.componentsByPage[definition.pages[0].id]).toEqual([])
  })
})

describe('组件操作', () => {
  it('标识递增不冲突', () => {
    expect(nextComponentId([{ id: 'c-1', type: 'text', x: 0, y: 0, w: 40, h: 40, z: 1 }])).toBe('c-2')
    expect(nextScreenPageId([{ id: 'p-1', name: 'a' }])).toBe('p-2')
  })

  it('新增：阶梯落位、层级置顶', () => {
    const next = addComponent(components, { type: 'metric' })
    expect(next).toHaveLength(3)
    expect(next[2].z).toBe(3)
    expect(next[2].type).toBe('metric')
  })

  it('移动与缩放夹取（允许越界但非负 / 最小尺寸）', () => {
    const moved = moveComponent(components, 'c1', -10, 5)
    expect(moved[0].x).toBe(0)
    expect(moved[0].y).toBe(5)
    const resized = resizeComponent(components, 'c1', 5, 5)
    expect(resized[0].w).toBe(40)
    expect(resized[0].h).toBe(32)
  })

  it('层级重排（置顶 / 置底 / 上移 / 下移）', () => {
    const top = bringToTop(components, 'c1')
    expect(top[top.length - 1].id).toBe('c1')
    expect(top[top.length - 1].z).toBe(2)

    const bottom = sendToBottom(components, 'c2')
    expect(bottom[0].id).toBe('c2')

    const raised = raiseComponent(components, 'c1')
    expect(raised[1].id).toBe('c1')
    const lowered = lowerComponent(components, 'c2')
    expect(lowered[0].id).toBe('c2')
    expect(removeComponent(components, 'ghost')).toHaveLength(2)
  })
})

describe('页操作', () => {
  it('增删改移与保底一页', () => {
    const pages = [{ id: 'p1', name: '首页' }, { id: 'p2', name: '明细' }]
    const added = addPage(pages, { name: '新增' })
    expect(added).toHaveLength(3)
    expect(added[2].name).toBe('新增')

    expect(renamePage(pages, 'p1', '改后')[0].name).toBe('改后')
    expect(movePage(pages, 'p2', 0)[0].id).toBe('p2')

    expect(removePage(pages, 'p1')).toHaveLength(1)
    expect(removePage([{ id: 'p1', name: 'a' }], 'p1')).toHaveLength(1)
  })

  it('设默认页（不存在不改）', () => {
    const definition: ScreenDefinition = {
      code: 's1',
      name: '大屏',
      canvas: normalizeCanvasConfig(undefined),
      pages: [{ id: 'p1', name: '首页' }],
      componentsByPage: { p1: components },
      defaultPageId: 'p1',
    }
    expect(setDefaultPage(definition, 'p1').defaultPageId).toBe('p1')
    expect(setDefaultPage(definition, 'ghost')).toBe(definition)
  })
})

describe('校验与序列化', () => {
  /** 契约定义。 */
  const definition: ScreenDefinition = {
    code: 's1',
    name: '大屏',
    canvas: { width: 1920, height: 1080, theme: 'auto' },
    pages: [{ id: 'p1', name: '首页' }],
    componentsByPage: { p1: components },
    defaultPageId: 'p1',
  }

  it('空大屏 / 停用数据集 / 越界', () => {
    const empty: ScreenDefinition = { ...definition, componentsByPage: { p1: [] } }
    expect(validateScreen(empty, datasets).errors.some((issue) => issue.kind === 'empty')).toBe(true)

    const disabled: ScreenDefinition = {
      ...definition,
      componentsByPage: { p1: [{ id: 'c1', type: 'chart', x: 0, y: 0, w: 100, h: 100, z: 1, datasetId: 'd2' }] },
    }
    const disabledResult = validateScreen(disabled, datasets)
    expect(disabledResult.valid).toBe(false)
    expect(disabledResult.errors.some((issue) => issue.kind === 'disabled-dataset')).toBe(true)

    const overflow: ScreenDefinition = {
      ...definition,
      componentsByPage: { p1: [{ id: 'c1', type: 'text', x: 1900, y: 0, w: 400, h: 300, z: 1 }] },
    }
    const overflowResult = validateScreen(overflow, datasets)
    expect(overflowResult.valid).toBe(true)
    expect(overflowResult.errors.some((issue) => issue.kind === 'overflow')).toBe(true)
  })

  it('序列化稳定、等价比对与脏判定', () => {
    expect(serializeCanvasConfig(definition).version).toBe(1)
    expect(serializeScreen(definition)).toContain('canvas_config')
    expect(screenDefinitionsEqual(definition, { ...definition })).toBe(true)
    expect(isScreenDirty(definition, definition)).toBe(false)
    expect(isScreenDirty(definition, undefined)).toBe(false)
    expect(isScreenDirty(definition, { ...definition, name: '别的' })).toBe(true)
  })

  it('组件面板分组与中文名', () => {
    expect(paletteGroups().flatMap((group) => group.items)).toHaveLength(7)
    expect(componentLabel('chart')).toBe('图表')
    expect(componentsOf(definition, 'p1')).toHaveLength(2)
  })
})
