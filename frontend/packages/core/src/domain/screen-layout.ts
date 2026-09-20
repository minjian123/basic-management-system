/**
 * 领域纯函数：大屏设计器领域模型（页面 / 组件 / 画布配置 / 序列化 / 校验 / 脏比对）。
 *
 * 设计态、保存载荷与播放态共用同一结构；框架无关、不触 DOM、不请求、不依赖第三方库，同输入同输出。
 * 图表配置沿用 `domain/chart.ts` 的 `ChartConfig` 口径，数据集沿用 `domain/report-layout.ts` 的 `ReportDataset`。
 */

import type { ChartConfig } from './chart'
import type { ReportDataset } from './report-layout'
import { stableStringify } from './serialize'

/** 大屏设计权限码。 */
export const SCREEN_DESIGN_PERM = 'rpt:design'
/** 大屏查看权限码。 */
export const SCREEN_VIEW_PERM = 'rpt:view'
/** 大屏设计器占位文案（数据通路未就绪）。 */
export const SCREEN_DESIGNER_PLACEHOLDER_TEXT = '大屏设计器未就绪（占位）'
/** 大屏播放占位文案（数据通路未就绪）。 */
export const SCREEN_PLAYER_PLACEHOLDER_TEXT = '大屏播放未就绪（占位）'
/** 默认画布分辨率（px）。 */
export const SCREEN_DEFAULT_RESOLUTION = { width: 1920, height: 1080 }

/** 画布默认背景色（设计态默认，与设计令牌 `--bms-color-bg` 一致）。 */
export const DEFAULT_CANVAS_BACKGROUND = '#ffffff'
/** 组件默认尺寸（px）。 */
export const SCREEN_DEFAULT_COMPONENT_SIZE = { w: 320, h: 200 }
/** 组件最小尺寸（px）。 */
export const SCREEN_MIN_COMPONENT_SIZE = { w: 40, h: 32 }
/** 组件类型集（组件库）。 */
export const SCREEN_COMPONENT_TYPES: ScreenComponentType[] = ['chart', 'table', 'metric', 'text', 'image', 'time', 'decor']

/** 大屏页。 */
export interface ScreenPage {
  /** 页标识。 */
  id: string
  /** 页名。 */
  name: string
  /** 单页停留时长（毫秒，可选）。 */
  duration?: number
}

/** 组件类型（大屏组件库）。 */
export type ScreenComponentType = 'chart' | 'table' | 'metric' | 'text' | 'image' | 'time' | 'decor'

/** 大屏组件（绝对定位；与 `08_01_03` 冻结契约同形 + 向后兼容可选字段）。 */
export interface ScreenComponent {
  /** 组件标识。 */
  id: string
  /** 组件类型。 */
  type: ScreenComponentType
  /** x 坐标（px）。 */
  x: number
  /** y 坐标（px）。 */
  y: number
  /** 宽（px）。 */
  w: number
  /** 高（px）。 */
  h: number
  /** 层级。 */
  z: number
  /** 引用数据集标识。 */
  datasetId?: string
  /** 图表类型。 */
  chartType?: string
  /** 文本内容。 */
  text?: string
  /** 图表配置（`ChartConfig`）。 */
  config?: Record<string, unknown>
  /** 组件属性（图片地址等）。 */
  props?: Record<string, unknown>
  /** 样式（字号 / 颜色 / 背景 / 边框 / 圆角）。 */
  style?: Record<string, unknown>
}

/** 画布配置。 */
export interface ScreenCanvasConfig {
  /** 设计分辨率宽。 */
  width: number
  /** 设计分辨率高。 */
  height: number
  /** 背景。 */
  background?: { color?: string; image?: string }
  /** 主题。 */
  theme?: 'light' | 'dark' | 'auto'
  /** 扩展属性。 */
  properties?: Record<string, unknown>
}

/** 大屏定义（保存载荷；`componentsByPage` 键为页标识）。 */
export interface ScreenDefinition {
  /** 大屏编码。 */
  code: string
  /** 大屏名称。 */
  name: string
  /** 画布配置。 */
  canvas: ScreenCanvasConfig
  /** 多页。 */
  pages: ScreenPage[]
  /** 各页组件（键为页标识）。 */
  componentsByPage: Record<string, ScreenComponent[]>
  /** 默认页标识。 */
  defaultPageId?: string
}

/** 校验问题种类。 */
export type ScreenIssueKind =
  | 'empty'
  | 'unknown-dataset'
  | 'disabled-dataset'
  | 'missing-mapping'
  | 'overflow'
  | 'duplicate-page'
  | 'invalid-page'

/** 校验问题。 */
export interface ScreenValidationIssue {
  /** 问题种类。 */
  kind: ScreenIssueKind
  /** 涉事页标识。 */
  pageId?: string
  /** 涉事组件标识。 */
  componentId?: string
  /** 说明。 */
  message: string
}

/** 校验结果（`overflow` 为警告，不阻断）。 */
export interface ScreenValidationResult {
  /** 是否通过。 */
  valid: boolean
  /** 问题清单。 */
  errors: ScreenValidationIssue[]
  /** 汇总文案。 */
  message: string
}

/**
 * 是否有限数值。
 *
 * @param value 待判定值。
 * @returns 是否有限数。
 */
function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/**
 * 是否普通对象。
 *
 * @param value 待判定值。
 * @returns 是否普通对象。
 */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 取正数（取整），否则回落。
 *
 * @param value 待取值。
 * @param fallback 回落值。
 * @returns 正整数值。
 */
function positiveInt(value: unknown, fallback: number): number {
  return isFiniteNumber(value) && value > 0 ? Math.round(value) : fallback
}

/**
 * 取非负数（取整），否则回落。
 *
 * @param value 待取值。
 * @param fallback 回落值。
 * @returns 非负整数值。
 */
function nonNegativeInt(value: unknown, fallback: number): number {
  return isFiniteNumber(value) ? Math.max(0, Math.round(value)) : fallback
}

/**
 * 归一分辨率。
 *
 * @param input 待归一值。
 * @returns 归一分辨率。
 */
export function normalizeResolution(input: unknown): { width: number; height: number } {
  const record = (input ?? {}) as { width?: unknown; height?: unknown }
  return {
    width: positiveInt(record.width, SCREEN_DEFAULT_RESOLUTION.width),
    height: positiveInt(record.height, SCREEN_DEFAULT_RESOLUTION.height),
  }
}

/**
 * 归一画布配置。
 *
 * @param input 待归一值。
 * @returns 画布配置。
 */
export function normalizeCanvasConfig(input: unknown): ScreenCanvasConfig {
  const record = (input ?? {}) as Partial<ScreenCanvasConfig>
  const resolution = normalizeResolution(record)
  const theme = record.theme === 'light' || record.theme === 'dark' || record.theme === 'auto' ? record.theme : 'auto'
  return {
    width: resolution.width,
    height: resolution.height,
    ...(isPlainObject(record.background)
      ? {
          background: {
            ...(typeof record.background.color === 'string' ? { color: record.background.color } : {}),
            ...(typeof record.background.image === 'string' ? { image: record.background.image } : {}),
          },
        }
      : {}),
    theme,
    ...(isPlainObject(record.properties) ? { properties: { ...record.properties } } : {}),
  }
}

/**
 * 归一页（缺标识丢弃）。
 *
 * @param value 待归一值。
 * @returns 归一页（缺标识返回 `undefined`）。
 */
export function normalizePage(value: unknown): ScreenPage | undefined {
  const record = (value ?? {}) as Partial<ScreenPage>
  const id = typeof record.id === 'string' && record.id !== '' ? record.id : undefined
  if (id === undefined) {
    return undefined
  }
  return {
    id,
    name: typeof record.name === 'string' && record.name !== '' ? record.name : `页 ${id}`,
    ...(isFiniteNumber(record.duration) && record.duration > 0 ? { duration: Math.round(record.duration) } : {}),
  }
}

/**
 * 归一页清单（剔除缺标识项，保留顺序）。
 *
 * @param value 待归一值。
 * @returns 页清单。
 */
export function normalizePages(value: unknown): ScreenPage[] {
  if (!Array.isArray(value)) {
    return []
  }
  const pages: ScreenPage[] = []
  for (const entry of value) {
    const page = normalizePage(entry)
    if (page !== undefined && !pages.some((item) => item.id === page.id)) {
      pages.push(page)
    }
  }
  return pages
}

/**
 * 归一组件类型（未知回落 `text`）。
 *
 * @param value 待归一值。
 * @returns 组件类型。
 */
export function normalizeComponentType(value: unknown): ScreenComponentType {
  return typeof value === 'string' && (SCREEN_COMPONENT_TYPES as readonly string[]).includes(value)
    ? (value as ScreenComponentType)
    : 'text'
}

/**
 * 归一组件（缺标识丢弃）。
 *
 * @param value 待归一值。
 * @returns 归一组件（缺标识返回 `undefined`）。
 */
export function normalizeComponent(value: unknown): ScreenComponent | undefined {
  const record = (value ?? {}) as Partial<ScreenComponent>
  const id = typeof record.id === 'string' && record.id !== '' ? record.id : undefined
  if (id === undefined) {
    return undefined
  }
  return {
    id,
    type: normalizeComponentType(record.type),
    x: nonNegativeInt(record.x, 0),
    y: nonNegativeInt(record.y, 0),
    w: Math.max(SCREEN_MIN_COMPONENT_SIZE.w, positiveInt(record.w, SCREEN_DEFAULT_COMPONENT_SIZE.w)),
    h: Math.max(SCREEN_MIN_COMPONENT_SIZE.h, positiveInt(record.h, SCREEN_DEFAULT_COMPONENT_SIZE.h)),
    z: nonNegativeInt(record.z, 0),
    ...(typeof record.datasetId === 'string' ? { datasetId: record.datasetId } : {}),
    ...(typeof record.chartType === 'string' ? { chartType: record.chartType } : {}),
    ...(typeof record.text === 'string' ? { text: record.text } : {}),
    ...(isPlainObject(record.config) ? { config: { ...record.config } } : {}),
    ...(isPlainObject(record.props) ? { props: { ...record.props } } : {}),
    ...(isPlainObject(record.style) ? { style: { ...record.style } } : {}),
  }
}

/**
 * 归一组件清单（剔除缺标识项，保留顺序）。
 *
 * @param value 待归一值。
 * @returns 组件清单。
 */
export function normalizeComponents(value: unknown): ScreenComponent[] {
  if (!Array.isArray(value)) {
    return []
  }
  const components: ScreenComponent[] = []
  for (const entry of value) {
    const component = normalizeComponent(entry)
    if (component !== undefined) {
      components.push(component)
    }
  }
  return components
}

/**
 * 归一「页 → 组件」映射。
 *
 * @param value 待归一值。
 * @param pageIds 页标识清单（缺省取对象键）。
 * @returns 归一映射。
 */
export function normalizeComponentsByPage(
  value: unknown,
  pageIds: readonly string[] = [],
): Record<string, ScreenComponent[]> {
  const record = isPlainObject(value) ? value : {}
  const keys = pageIds.length > 0 ? [...pageIds] : Object.keys(record)
  const result: Record<string, ScreenComponent[]> = {}
  for (const key of keys) {
    result[key] = normalizeComponents(record[key])
  }
  return result
}

/**
 * 归一完整大屏定义（保证至少一页与有效默认页）。
 *
 * @param value 待归一值。
 * @returns 大屏定义。
 */
export function normalizeScreenDefinition(value: unknown): ScreenDefinition {
  const record = (value ?? {}) as Partial<ScreenDefinition>
  const pages = normalizePages(record.pages)
  const effectivePages = pages.length > 0 ? pages : [{ id: 'p-1', name: '页 1' }]
  const componentsByPage = normalizeComponentsByPage(
    record.componentsByPage,
    effectivePages.map((page) => page.id),
  )
  const defaultPageId =
    typeof record.defaultPageId === 'string' && effectivePages.some((page) => page.id === record.defaultPageId)
      ? record.defaultPageId
      : effectivePages[0].id
  return {
    code: typeof record.code === 'string' ? record.code : '',
    name: typeof record.name === 'string' ? record.name : '',
    canvas: normalizeCanvasConfig(record.canvas),
    pages: effectivePages,
    componentsByPage,
    defaultPageId,
  }
}

/**
 * 生成下一个组件标识（`c-{n}` 递增不冲突）。
 *
 * @param components 现有组件。
 * @returns 新标识。
 */
export function nextComponentId(components: readonly ScreenComponent[]): string {
  const used = new Set(components.map((item) => item.id))
  let index = components.length + 1
  while (used.has(`c-${index}`)) {
    index += 1
  }
  return `c-${index}`
}

/**
 * 生成下一个页标识（`p-{n}` 递增不冲突）。
 *
 * @param pages 现有页。
 * @returns 新标识。
 */
export function nextPageId(pages: readonly ScreenPage[]): string {
  const used = new Set(pages.map((item) => item.id))
  let index = pages.length + 1
  while (used.has(`p-${index}`)) {
    index += 1
  }
  return `p-${index}`
}

/**
 * 查找组件。
 *
 * @param components 组件清单。
 * @param id 标识。
 * @returns 组件（不存在 `undefined`）。
 */
export function findComponent(components: readonly ScreenComponent[], id: string): ScreenComponent | undefined {
  return components.find((item) => item.id === id)
}

/**
 * 查找页。
 *
 * @param pages 页清单。
 * @param id 标识。
 * @returns 页（不存在 `undefined`）。
 */
export function findPage(pages: readonly ScreenPage[], id: string): ScreenPage | undefined {
  return pages.find((item) => item.id === id)
}

/**
 * 取某页组件。
 *
 * @param definition 大屏定义。
 * @param pageId 页标识。
 * @returns 组件清单（不存在返回空数组）。
 */
export function componentsOf(definition: ScreenDefinition, pageId: string): ScreenComponent[] {
  const list = definition.componentsByPage[pageId]
  return list !== undefined ? list : []
}

/**
 * 收集被引用的数据集标识（去重保序）。
 *
 * @param definition 大屏定义。
 * @returns 数据集标识清单。
 */
export function collectUsedDatasets(definition: ScreenDefinition): string[] {
  const result: string[] = []
  for (const page of definition.pages) {
    for (const component of componentsOf(definition, page.id)) {
      if (component.datasetId !== undefined && component.datasetId !== '' && !result.includes(component.datasetId)) {
        result.push(component.datasetId)
      }
    }
  }
  return result
}

/**
 * 按类型生成默认字段。
 *
 * @param type 组件类型。
 * @returns 默认字段。
 */
function defaultsForType(type: ScreenComponentType): Partial<ScreenComponent> {
  switch (type) {
    case 'chart':
      return { chartType: 'line' }
    case 'text':
      return { text: '文本' }
    case 'metric':
      return { text: '指标' }
    case 'image':
      return { props: { src: '' } }
    default:
      return {}
  }
}

/**
 * 新增组件（不可变；阶梯落位、层级置顶）。
 *
 * @param components 现有组件。
 * @param input 新增入参。
 * @returns 新组件清单。
 */
export function addComponent(
  components: readonly ScreenComponent[],
  input: { type: ScreenComponentType; id?: string; x?: number; y?: number; w?: number; h?: number },
): ScreenComponent[] {
  const id = input.id !== undefined && input.id !== '' ? input.id : nextComponentId(components)
  const offset = (components.length % 8) * 24
  const z = components.reduce((max, item) => Math.max(max, item.z), 0) + 1
  const component: ScreenComponent = {
    id,
    type: input.type,
    x: input.x !== undefined ? Math.max(0, Math.round(input.x)) : offset,
    y: input.y !== undefined ? Math.max(0, Math.round(input.y)) : offset,
    w: Math.max(SCREEN_MIN_COMPONENT_SIZE.w, positiveInt(input.w, SCREEN_DEFAULT_COMPONENT_SIZE.w)),
    h: Math.max(SCREEN_MIN_COMPONENT_SIZE.h, positiveInt(input.h, SCREEN_DEFAULT_COMPONENT_SIZE.h)),
    z,
    ...defaultsForType(input.type),
  }
  return [...components, component]
}

/**
 * 移除组件（幂等）。
 *
 * @param components 组件清单。
 * @param id 标识。
 * @returns 新组件清单。
 */
export function removeComponent(components: readonly ScreenComponent[], id: string): ScreenComponent[] {
  return components.filter((item) => item.id !== id)
}

/**
 * 更新组件（类型 / 文案 / 图表类型 / 数据集 / 配置 / 属性 / 样式）。
 *
 * @param components 组件清单。
 * @param id 标识。
 * @param patch 变更。
 * @returns 新组件清单。
 */
export function updateComponent(
  components: readonly ScreenComponent[],
  id: string,
  patch: Partial<Pick<ScreenComponent, 'type' | 'text' | 'chartType' | 'datasetId' | 'config' | 'props' | 'style'>>,
): ScreenComponent[] {
  return components.map((item) => {
    if (item.id !== id) {
      return item
    }
    return {
      ...item,
      ...(patch.type !== undefined ? { type: normalizeComponentType(patch.type) } : {}),
      ...(patch.text !== undefined ? { text: patch.text } : {}),
      ...(patch.chartType !== undefined ? { chartType: patch.chartType } : {}),
      ...(patch.datasetId !== undefined ? { datasetId: patch.datasetId } : {}),
      ...(patch.config !== undefined ? { config: { ...patch.config } } : {}),
      ...(patch.props !== undefined ? { props: { ...patch.props } } : {}),
      ...(patch.style !== undefined ? { style: { ...patch.style } } : {}),
    }
  })
}

/**
 * 移动组件（仅夹取非负；越界由校验提示）。
 *
 * @param components 组件清单。
 * @param id 标识。
 * @param x 目标 x。
 * @param y 目标 y。
 * @returns 新组件清单。
 */
export function moveComponent(components: readonly ScreenComponent[], id: string, x: number, y: number): ScreenComponent[] {
  return components.map((item) => {
    if (item.id !== id) {
      return item
    }
    return { ...item, x: nonNegativeInt(x, item.x), y: nonNegativeInt(y, item.y) }
  })
}

/**
 * 缩放组件（夹取最小尺寸）。
 *
 * @param components 组件清单。
 * @param id 标识。
 * @param w 目标宽。
 * @param h 目标高。
 * @returns 新组件清单。
 */
export function resizeComponent(components: readonly ScreenComponent[], id: string, w: number, h: number): ScreenComponent[] {
  return components.map((item) => {
    if (item.id !== id) {
      return item
    }
    return {
      ...item,
      w: Math.max(SCREEN_MIN_COMPONENT_SIZE.w, positiveInt(w, item.w)),
      h: Math.max(SCREEN_MIN_COMPONENT_SIZE.h, positiveInt(h, item.h)),
    }
  })
}

/**
 * 按层级升序排序（副本）。
 *
 * @param components 组件清单。
 * @returns 排序后组件清单。
 */
export function sortByZ(components: readonly ScreenComponent[]): ScreenComponent[] {
  return [...components].sort((a, b) => a.z - b.z)
}

/**
 * 重排层级为 `1..n`（保持数组顺序）。
 *
 * @param components 组件清单。
 * @returns 重排后组件清单。
 */
function reindexZ(components: readonly ScreenComponent[]): ScreenComponent[] {
  return components.map((item, index) => ({ ...item, z: index + 1 }))
}

/**
 * 置顶组件。
 *
 * @param components 组件清单。
 * @param id 标识。
 * @returns 新组件清单。
 */
export function bringToTop(components: readonly ScreenComponent[], id: string): ScreenComponent[] {
  const sorted = sortByZ(components)
  const index = sorted.findIndex((item) => item.id === id)
  if (index < 0) {
    return [...components]
  }
  const [target] = sorted.splice(index, 1)
  sorted.push(target)
  return reindexZ(sorted)
}

/**
 * 置底组件。
 *
 * @param components 组件清单。
 * @param id 标识。
 * @returns 新组件清单。
 */
export function sendToBottom(components: readonly ScreenComponent[], id: string): ScreenComponent[] {
  const sorted = sortByZ(components)
  const index = sorted.findIndex((item) => item.id === id)
  if (index < 0) {
    return [...components]
  }
  const [target] = sorted.splice(index, 1)
  sorted.unshift(target)
  return reindexZ(sorted)
}

/**
 * 上移一层。
 *
 * @param components 组件清单。
 * @param id 标识。
 * @returns 新组件清单。
 */
export function raiseComponent(components: readonly ScreenComponent[], id: string): ScreenComponent[] {
  const sorted = sortByZ(components)
  const index = sorted.findIndex((item) => item.id === id)
  if (index < 0 || index === sorted.length - 1) {
    return reindexZ(sorted)
  }
  const next = sorted[index + 1]
  sorted[index + 1] = sorted[index]
  sorted[index] = next
  return reindexZ(sorted)
}

/**
 * 下移一层。
 *
 * @param components 组件清单。
 * @param id 标识。
 * @returns 新组件清单。
 */
export function lowerComponent(components: readonly ScreenComponent[], id: string): ScreenComponent[] {
  const sorted = sortByZ(components)
  const index = sorted.findIndex((item) => item.id === id)
  if (index <= 0) {
    return reindexZ(sorted)
  }
  const prev = sorted[index - 1]
  sorted[index - 1] = sorted[index]
  sorted[index] = prev
  return reindexZ(sorted)
}

/**
 * 新增页。
 *
 * @param pages 现有页。
 * @param input 新增入参。
 * @returns 新页清单。
 */
export function addPage(
  pages: readonly ScreenPage[],
  input: { id?: string; name?: string; duration?: number } = {},
): ScreenPage[] {
  const id = input.id !== undefined && input.id !== '' ? input.id : nextPageId(pages)
  const name = input.name !== undefined && input.name !== '' ? input.name : `页 ${pages.length + 1}`
  return [
    ...pages,
    {
      id,
      name,
      ...(isFiniteNumber(input.duration) && input.duration > 0 ? { duration: Math.round(input.duration) } : {}),
    },
  ]
}

/**
 * 移除页（保底一页）。
 *
 * @param pages 页清单。
 * @param id 标识。
 * @returns 新页清单。
 */
export function removePage(pages: readonly ScreenPage[], id: string): ScreenPage[] {
  if (pages.length <= 1 || !pages.some((page) => page.id === id)) {
    return [...pages]
  }
  return pages.filter((page) => page.id !== id)
}

/**
 * 重命名页。
 *
 * @param pages 页清单。
 * @param id 标识。
 * @param name 新页名。
 * @returns 新页清单。
 */
export function renamePage(pages: readonly ScreenPage[], id: string, name: string): ScreenPage[] {
  return pages.map((page) => (page.id === id ? { ...page, name: name !== '' ? name : page.name } : page))
}

/**
 * 移动页到指定位置（夹取索引）。
 *
 * @param pages 页清单。
 * @param id 标识。
 * @param index 目标索引。
 * @returns 新页清单。
 */
export function movePage(pages: readonly ScreenPage[], id: string, index: number): ScreenPage[] {
  const current = pages.findIndex((page) => page.id === id)
  if (current < 0) {
    return [...pages]
  }
  const next = [...pages]
  const [target] = next.splice(current, 1)
  const targetIndex = Math.min(Math.max(0, Math.round(index)), next.length)
  next.splice(targetIndex, 0, target)
  return next
}

/**
 * 设默认页（不存在时不改）。
 *
 * @param definition 大屏定义。
 * @param pageId 页标识。
 * @returns 新大屏定义。
 */
export function setDefaultPage(definition: ScreenDefinition, pageId: string): ScreenDefinition {
  if (!definition.pages.some((page) => page.id === pageId)) {
    return definition
  }
  return { ...definition, defaultPageId: pageId }
}

/**
 * 组件面板分组。
 *
 * @returns 分组清单。
 */
export function paletteGroups(): { category: string; items: { type: ScreenComponentType; label: string }[] }[] {
  return [
    { category: '图表', items: [{ type: 'chart', label: '图表' }] },
    {
      category: '数据',
      items: [
        { type: 'table', label: '数据表' },
        { type: 'metric', label: '指标卡' },
      ],
    },
    {
      category: '内容',
      items: [
        { type: 'text', label: '文本' },
        { type: 'image', label: '图片' },
      ],
    },
    {
      category: '辅助',
      items: [
        { type: 'time', label: '时间' },
        { type: 'decor', label: '装饰' },
      ],
    },
  ]
}

/**
 * 组件类型中文名。
 *
 * @param type 组件类型。
 * @returns 中文名。
 */
export function componentLabel(type: ScreenComponentType): string {
  const labels: Record<ScreenComponentType, string> = {
    chart: '图表',
    table: '数据表',
    metric: '指标卡',
    text: '文本',
    image: '图片',
    time: '时间',
    decor: '装饰',
  }
  return labels[type]
}

/**
 * 组件绝对定位样式（供画布与舞台复用）。
 *
 * @param component 组件。
 * @returns 内联样式。
 */
export function canvasStyle(component: ScreenComponent): Record<string, string | number> {
  return {
    position: 'absolute',
    left: `${component.x}px`,
    top: `${component.y}px`,
    width: `${component.w}px`,
    height: `${component.h}px`,
    zIndex: component.z,
  }
}

/**
 * 校验大屏定义（`overflow` 为警告，不阻断）。
 *
 * @param definition 大屏定义。
 * @param datasets 数据集清单。
 * @returns 校验结果。
 */
export function validateScreen(definition: ScreenDefinition, datasets: readonly ReportDataset[]): ScreenValidationResult {
  const errors: ScreenValidationIssue[] = []
  const pageIds = definition.pages.map((page) => page.id)
  if (new Set(pageIds).size !== pageIds.length) {
    errors.push({ kind: 'duplicate-page', message: '页标识重复' })
  }
  if (definition.defaultPageId !== undefined && !pageIds.includes(definition.defaultPageId)) {
    errors.push({ kind: 'invalid-page', pageId: definition.defaultPageId, message: '默认页不存在' })
  }
  const total = definition.pages.reduce((sum, page) => sum + componentsOf(definition, page.id).length, 0)
  if (total === 0) {
    errors.push({ kind: 'empty', message: '空大屏：请先添加组件' })
  }
  const datasetMap = new Map(datasets.map((dataset) => [dataset.id, dataset]))
  for (const page of definition.pages) {
    for (const component of componentsOf(definition, page.id)) {
      const needsDataset = component.type === 'chart' || component.type === 'table' || component.type === 'metric'
      if (needsDataset && component.datasetId !== undefined && component.datasetId !== '') {
        const dataset = datasetMap.get(component.datasetId)
        if (dataset === undefined) {
          errors.push({ kind: 'unknown-dataset', pageId: page.id, componentId: component.id, message: `组件 ${component.id} 引用的数据集不存在` })
        } else if (dataset.status !== 'enabled') {
          errors.push({ kind: 'disabled-dataset', pageId: page.id, componentId: component.id, message: `组件 ${component.id} 引用的数据集已停用` })
        }
      }
      if (component.type === 'chart') {
        const config = component.config as unknown as Partial<ChartConfig> | undefined
        if (config !== undefined && config.mapping !== undefined && (config.mapping.metrics ?? []).length === 0) {
          errors.push({ kind: 'missing-mapping', pageId: page.id, componentId: component.id, message: `组件 ${component.id} 缺少度量映射` })
        }
      }
      if (
        component.x + component.w > definition.canvas.width ||
        component.y + component.h > definition.canvas.height
      ) {
        errors.push({ kind: 'overflow', pageId: page.id, componentId: component.id, message: `组件 ${component.id} 超出画布范围（警告）` })
      }
    }
  }
  const blocking = errors.filter((issue) => issue.kind !== 'overflow')
  return {
    valid: blocking.length === 0,
    errors,
    message: blocking.length === 0 ? '校验通过' : blocking.map((issue) => issue.message).join('；'),
  }
}

/**
 * 序列化画布配置（稳定结构）。
 *
 * @param definition 大屏定义。
 * @returns 画布配置结构。
 */
export function serializeCanvasConfig(definition: ScreenDefinition): Record<string, unknown> {
  return {
    version: 1,
    resolution: { width: definition.canvas.width, height: definition.canvas.height },
    background: definition.canvas.background ?? {},
    theme: definition.canvas.theme ?? 'auto',
    pages: definition.pages.map((page) => ({
      id: page.id,
      name: page.name,
      ...(page.duration !== undefined ? { duration: page.duration } : {}),
    })),
    components: definition.pages.map((page) => ({
      pageId: page.id,
      items: componentsOf(definition, page.id).map((item) => ({
        id: item.id,
        type: item.type,
        x: item.x,
        y: item.y,
        w: item.w,
        h: item.h,
        z: item.z,
        datasetId: item.datasetId ?? '',
        chartType: item.chartType ?? '',
        text: item.text ?? '',
        config: item.config ?? {},
        props: item.props ?? {},
        style: item.style ?? {},
      })),
    })),
    defaultPageId: definition.defaultPageId ?? '',
  }
}

/**
 * 序列化完整大屏定义（覆盖式提交载荷结构）。
 *
 * @param definition 大屏定义。
 * @returns 定义结构。
 */
export function serializeScreenDefinition(definition: ScreenDefinition): Record<string, unknown> {
  return {
    code: definition.code,
    name: definition.name,
    canvas_config: serializeCanvasConfig(definition),
  }
}

/**
 * 序列化大屏定义（稳定 JSON 字符串）。
 *
 * @param definition 大屏定义。
 * @returns 稳定 JSON 字符串。
 */
export function serializeScreen(definition: ScreenDefinition): string {
  return stableStringify(serializeScreenDefinition(definition))
}

/**
 * 大屏定义是否等价（键序无关）。
 *
 * @param a 定义甲。
 * @param b 定义乙。
 * @returns 是否等价。
 */
export function screenDefinitionsEqual(a: ScreenDefinition, b: ScreenDefinition): boolean {
  return stableStringify(serializeScreenDefinition(a)) === stableStringify(serializeScreenDefinition(b))
}

/**
 * 是否脏（与基线比对；基线缺失视为不脏）。
 *
 * @param current 当前定义。
 * @param baseline 基线定义。
 * @returns 是否脏。
 */
export function isScreenDirty(current: ScreenDefinition | undefined, baseline: ScreenDefinition | undefined): boolean {
  if (current === undefined || baseline === undefined) {
    return false
  }
  return !screenDefinitionsEqual(current, baseline)
}
