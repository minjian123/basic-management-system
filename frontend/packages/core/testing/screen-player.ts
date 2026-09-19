/**
 * 大屏播放编排契约（`@bms/core/testing`）。
 *
 * 大屏播放与后续同契约实现在本套件中传入适配器跑同一套断言：
 * 占位零请求、定义装载、多页环回切页、播放态切换、间隔归一、按组件取数与整页刷新容错、查看权限门控。
 */

import { describe, expect, it } from 'vitest'

import type { ScreenComponent, ScreenPage, ScreenPlaySnapshot, ScreenPlayerJobs, ScreenPreviewResult } from '../src'

/** 契约页。 */
export const SCREEN_PLAY_CONTRACT_PAGES: ScreenPage[] = [
  { id: 'p1', name: '首页' },
  { id: 'p2', name: '明细', duration: 3000 },
]

/** 契约组件（p1 含图表与文本；p2 含图表）。 */
export const SCREEN_PLAY_CONTRACT_COMPONENTS: Record<string, ScreenComponent[]> = {
  p1: [
    { id: 'c1', type: 'chart', x: 0, y: 0, w: 400, h: 300, z: 1, datasetId: 'd1', chartType: 'bar' },
    { id: 'c2', type: 'text', x: 420, y: 0, w: 200, h: 80, z: 2, text: '标题' },
  ],
  p2: [{ id: 'c3', type: 'chart', x: 0, y: 0, w: 400, h: 300, z: 1, datasetId: 'd1', chartType: 'line' }],
}

/** 契约播放快照。 */
export const SCREEN_PLAY_CONTRACT_SNAPSHOT: ScreenPlaySnapshot = {
  code: 'screen_main',
  name: '运营大屏',
  canvas: { width: 1920, height: 1080, theme: 'dark' },
  pages: SCREEN_PLAY_CONTRACT_PAGES,
  componentsByPage: SCREEN_PLAY_CONTRACT_COMPONENTS,
  defaultPageId: 'p1',
}

/** 大屏播放契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface ScreenPlayerContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级。 */
  readonly degraded: boolean
  /** 是否进行中。 */
  readonly busy: boolean
  /** 当前阶段。 */
  readonly phase: string
  /** 请求计数。 */
  readonly requestCount: number
  /** 是否播放中。 */
  readonly playing: boolean
  /** 轮播间隔（毫秒）。 */
  readonly interval: number
  /** 页清单。 */
  pages(): ScreenPage[]
  /** 当前页标识。 */
  activePageId(): string
  /** 当前页组件。 */
  components(): ScreenComponent[]
  /** 各组件取数结果。 */
  data(): Record<string, ScreenPreviewResult | undefined>
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入权限（`codes` 缺省视为有权）。 */
  setOperators(input: { codes?: string[] }): void
  /** 注入处理函数集。 */
  setJobs(jobs: ScreenPlayerJobs): void
  /** 设置页清单。 */
  setPages(pages: readonly ScreenPage[]): void
  /** 设置各页组件。 */
  setComponents(componentsByPage: Record<string, readonly ScreenComponent[]>): void
  /** 切换当前页。 */
  selectPage(pageId: string): boolean
  /** 下一页。 */
  next(): string
  /** 上一页。 */
  prev(): string
  /** 切换播放 / 暂停。 */
  toggle(force?: boolean): boolean
  /** 设置播放态。 */
  setPlaying(value: boolean): void
  /** 设置轮播间隔。 */
  setInterval(value: unknown): number
  /** 定义取数。 */
  load(input?: { code?: string }): Promise<ScreenPlaySnapshot | undefined>
  /** 按组件取数。 */
  queryComponent(componentId: string, pageId?: string): Promise<ScreenPreviewResult | undefined>
  /** 整页刷新。 */
  refreshPage(pageId?: string): Promise<number>
}

/** 契约处理函数（记录调用轨迹）。 */
export interface ScreenPlayerContractJobs extends ScreenPlayerJobs {
  /** 调用轨迹。 */
  calls: string[]
}

/**
 * 创建契约处理函数（记录调用轨迹）。
 *
 * @returns 处理函数集。
 */
export function createScreenPlayerJobs(): ScreenPlayerContractJobs {
  const calls: string[] = []
  return {
    calls,
    load: async () => {
      calls.push('load')
      return SCREEN_PLAY_CONTRACT_SNAPSHOT
    },
    componentData: async (input) => {
      calls.push(`componentData:${input.componentId}`)
      if (input.componentId === 'boom') {
        throw new Error('90003')
      }
      return { columns: [{ name: 'month', type: 'text' }], rows: [{ month: '1月' }] }
    },
  }
}

/**
 * 大屏播放编排契约（`08-9-2`）。
 *
 * 断言：占位零请求；就绪装载定义；多页环回切页；播放态切换；间隔归一；
 * 按组件取数（无数据集组件不请求）；整页并行刷新与单组件失败容错；查看权限门控。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeScreenPlayerContract(name: string, create: () => ScreenPlayerContractTarget): void {
  describe(name, () => {
    it('未就绪时降级，取数零请求', async () => {
      const target = create()
      target.setReady(false)
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)

      await target.load()
      await target.queryComponent('c1')
      expect(target.requestCount).toBe(0)
    })

    it('就绪后不再降级，未注入处理函数仍零请求', async () => {
      const target = create()
      target.setReady(true)
      expect(target.degraded).toBe(false)
      await target.load()
      expect(target.requestCount).toBe(0)
    })

    it('定义取数装载页与组件', async () => {
      const target = create()
      const jobs = createScreenPlayerJobs()
      target.setJobs(jobs)
      await target.load()

      expect(target.requestCount).toBe(1)
      expect(target.pages()).toHaveLength(2)
      expect(target.activePageId()).toBe('p1')
      expect(target.components()).toHaveLength(2)
      expect(target.phase).toBe('ready')
      expect(jobs.calls).toContain('load')
    })

    it('多页环回切页', () => {
      const target = create()
      target.setPages(SCREEN_PLAY_CONTRACT_PAGES)
      target.selectPage('p1')

      expect(target.next()).toBe('p2')
      expect(target.next()).toBe('p1')
      expect(target.prev()).toBe('p2')
      expect(target.selectPage('ghost')).toBe(false)
    })

    it('播放态切换与间隔归一', () => {
      const target = create()
      expect(target.toggle()).toBe(true)
      expect(target.toggle()).toBe(false)
      expect(target.toggle(true)).toBe(true)

      expect(target.setInterval(0)).toBe(5000)
      expect(target.setInterval(500)).toBe(1000)
      expect(target.setInterval(8000)).toBe(8000)
    })

    it('按组件取数（无数据集组件不请求）与整页刷新', async () => {
      const target = create()
      const jobs = createScreenPlayerJobs()
      target.setJobs(jobs)
      target.setPages(SCREEN_PLAY_CONTRACT_PAGES)
      target.setComponents(SCREEN_PLAY_CONTRACT_COMPONENTS)

      const result = await target.queryComponent('c1')
      expect(result?.rows).toHaveLength(1)
      expect(target.data().c1).toBeDefined()

      const before = target.requestCount
      await expect(target.queryComponent('c2')).resolves.toBeUndefined()
      expect(target.requestCount).toBe(before)

      const count = await target.refreshPage('p1')
      expect(count).toBe(1)
      expect(jobs.calls).toContain('componentData:c1')
    })

    it('单组件失败不阻断整页刷新', async () => {
      const target = create()
      const jobs = createScreenPlayerJobs()
      target.setJobs(jobs)
      target.setComponents({
        p1: [
          { id: 'boom', type: 'chart', x: 0, y: 0, w: 100, h: 100, z: 1, datasetId: 'd1' },
          { id: 'ok', type: 'chart', x: 0, y: 0, w: 100, h: 100, z: 2, datasetId: 'd1' },
        ],
      })
      target.setPages([{ id: 'p1', name: '首页' }])
      target.selectPage('p1')

      const count = await target.refreshPage('p1')
      expect(count).toBe(2)
      expect(target.data().ok).toBeDefined()
      expect(target.data().boom).toBeUndefined()
    })

    it('无查看权限时不请求', async () => {
      const target = create()
      const jobs = createScreenPlayerJobs()
      target.setJobs(jobs)
      target.setPages(SCREEN_PLAY_CONTRACT_PAGES)
      target.setComponents(SCREEN_PLAY_CONTRACT_COMPONENTS)
      target.setOperators({ codes: [] })

      await expect(target.load()).resolves.toBeUndefined()
      await expect(target.queryComponent('c1')).resolves.toBeUndefined()
      expect(target.requestCount).toBe(0)
    })
  })
}
