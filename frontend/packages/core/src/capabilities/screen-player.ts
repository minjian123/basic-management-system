/**
 * 大屏播放编排能力基类：定义取数 / 多页轮播切页 / 播放态 / 按组件取数与整页刷新。
 *
 * 组合权限、提示、数据状态与异步任务能力基类；定义取数与组件取数处理函数由宿主注入，未注入即占位（不请求）；
 * 轮播切页与间隔判定落在 `domain/screen-play.ts`，页面与组件归一落在 `domain/screen-layout.ts`。
 */

import { BaseComponent } from '../base/BaseComponent'
import { BaseAccess } from './access'
import { BaseAsyncTask } from './async-task'
import { BaseDataState } from './data-state'
import { BaseNotice } from './notice'
import {
  findComponent,
  findPage,
  normalizeCanvasConfig,
  normalizeComponentsByPage,
  normalizePages,
  type ScreenCanvasConfig,
  type ScreenComponent,
  type ScreenPage,
  SCREEN_VIEW_PERM,
} from '../domain/screen-layout'
import { nextPageId, normalizePlayInterval, pageDuration, prevPageId } from '../domain/screen-play'
import type { ScreenPreviewResult } from './screen-designer'

/** 播放阶段。 */
export type ScreenPlayerPhase = 'idle' | 'loading' | 'ready' | 'failed'
/** 播放快照（定义取数结果）。 */
export interface ScreenPlaySnapshot {
  /** 大屏编码。 */
  code: string
  /** 大屏名称。 */
  name?: string
  /** 画布配置。 */
  canvas?: ScreenCanvasConfig
  /** 多页。 */
  pages?: readonly ScreenPage[]
  /** 各页组件（键为页标识）。 */
  componentsByPage?: Record<string, readonly ScreenComponent[]>
  /** 默认页标识。 */
  defaultPageId?: string
}
/** 注入的处理函数集（未注入即占位不请求）。 */
export interface ScreenPlayerJobs {
  /** 定义取数。 */
  load?: (input: { code?: string }) => Promise<ScreenPlaySnapshot | undefined>
  /** 按组件取数（只读从库口径）。 */
  componentData?: (input: { pageId: string; componentId: string; datasetId: string; params?: Record<string, unknown> }) => Promise<ScreenPreviewResult | undefined>
}

/** 大屏播放编排能力基类（抽象）。 */
export abstract class BaseScreenPlayer extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'screen-player'
  /** 依赖登记。 */
  override readonly depends = ['access', 'notice', 'data-state', 'async-task']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 占位态请求计数（占位态恒 0）。 */
  requestCount = 0
  /** 大屏编码。 */
  screenCode = ''
  /** 画布配置。 */
  canvas: ScreenCanvasConfig = normalizeCanvasConfig(undefined)
  /** 多页。 */
  pages: ScreenPage[] = []
  /** 各页组件（键为页标识）。 */
  componentsByPage: Record<string, ScreenComponent[]> = {}
  /** 当前页标识。 */
  activePageId = ''
  /** 是否播放中。 */
  playing = false
  /** 轮播间隔（毫秒）。 */
  interval: number = normalizePlayInterval(undefined)
  /** 是否全屏。 */
  fullscreen = false
  /** 各组件取数结果（键为组件标识）。 */
  data: Record<string, ScreenPreviewResult | undefined> = {}
  /** 当前阶段。 */
  phase: ScreenPlayerPhase = 'idle'
  /** 错误文案。 */
  errorMessage = ''
  /** 注入的处理函数集。 */
  jobs: ScreenPlayerJobs = {}
  /** 权限上下文。 */
  access: BaseAccess | undefined = undefined
  /** 提示通知协作者。 */
  notice: BaseNotice | undefined = undefined
  /** 数据状态能力（组件取数）。 */
  dataState: BaseDataState | undefined = undefined
  /** 异步任务能力。 */
  asyncTask: BaseAsyncTask | undefined = undefined
  /** 是否进行中（定义取数）。 */
  #busy = false

  /** 是否降级（占位）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 是否进行中。 */
  get busy(): boolean {
    return this.#busy
  }

  /** 当前页。 */
  get activePage(): ScreenPage | undefined {
    return findPage(this.pages, this.activePageId)
  }

  /** 当前页组件。 */
  get currentComponents(): ScreenComponent[] {
    return [...(this.componentsByPage[this.activePageId] ?? [])]
  }

  /** 页数量。 */
  get pageCount(): number {
    return this.pages.length
  }

  /** 是否有上一页。 */
  get hasPrev(): boolean {
    return this.pages.length > 1
  }

  /** 是否有下一页。 */
  get hasNext(): boolean {
    return this.pages.length > 1
  }

  /** 当前页生效停留时长（毫秒）。 */
  get currentInterval(): number {
    return pageDuration(this.activePage, this.interval)
  }

  /**
   * 切换就绪态。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    if (this.ready === value) {
      return
    }
    this.ready = value
    this.notifyLifecycle('update')
  }

  /**
   * 注入处理函数集。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: ScreenPlayerJobs): void {
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
   * 注入异步任务能力。
   *
   * @param task 异步任务能力。
   */
  setAsyncTask(task: BaseAsyncTask | undefined): void {
    this.asyncTask = task
    this.notifyLifecycle('update')
  }

  /**
   * 设置画布配置。
   *
   * @param canvas 画布配置。
   */
  setCanvas(canvas: unknown): void {
    this.canvas = normalizeCanvasConfig(canvas)
    this.notifyLifecycle('update')
  }

  /**
   * 设置页清单（当前页失效时回落首页）。
   *
   * @param pages 页清单。
   */
  setPages(pages: readonly ScreenPage[]): void {
    this.pages = normalizePages(pages)
    if (this.pages.length === 0) {
      this.pages = [{ id: 'p-1', name: '页 1' }]
    }
    if (!this.pages.some((page) => page.id === this.activePageId)) {
      this.activePageId = this.pages[0].id
    }
    this.notifyLifecycle('update')
  }

  /**
   * 设置各页组件。
   *
   * @param componentsByPage 各页组件。
   */
  setComponents(componentsByPage: Record<string, readonly ScreenComponent[]>): void {
    this.componentsByPage = normalizeComponentsByPage(componentsByPage, this.pages.map((page) => page.id))
    this.notifyLifecycle('update')
  }

  /**
   * 设置播放态。
   *
   * @param value 是否播放中。
   */
  setPlaying(value: boolean): void {
    if (this.playing === value) {
      return
    }
    this.playing = value
    this.notifyLifecycle('update')
  }

  /**
   * 设置轮播间隔（归一）。
   *
   * @param value 间隔（毫秒）。
   * @returns 生效间隔。
   */
  setInterval(value: unknown): number {
    this.interval = normalizePlayInterval(value)
    this.notifyLifecycle('update')
    return this.interval
  }

  /**
   * 设置全屏态。
   *
   * @param value 是否全屏。
   */
  setFullscreen(value: boolean): void {
    if (this.fullscreen === value) {
      return
    }
    this.fullscreen = value
    this.notifyLifecycle('update')
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
    this.notifyLifecycle('update')
    return true
  }

  /**
   * 下一页（环回）。
   *
   * @returns 生效页标识。
   */
  next(): string {
    const target = nextPageId(this.pages, this.activePageId, true)
    if (target !== this.activePageId && this.pages.some((page) => page.id === target)) {
      this.activePageId = target
      this.notifyLifecycle('update')
    }
    return this.activePageId
  }

  /**
   * 上一页（环回）。
   *
   * @returns 生效页标识。
   */
  prev(): string {
    const target = prevPageId(this.pages, this.activePageId, true)
    if (target !== this.activePageId && this.pages.some((page) => page.id === target)) {
      this.activePageId = target
      this.notifyLifecycle('update')
    }
    return this.activePageId
  }

  /**
   * 切换播放 / 暂停。
   *
   * @param force 显式设定（缺省取反）。
   * @returns 生效播放态。
   */
  toggle(force?: boolean): boolean {
    if (this.degraded) {
      return this.playing
    }
    const nextValue = force ?? !this.playing
    if (nextValue !== this.playing) {
      this.playing = nextValue
      this.notifyLifecycle('update')
    }
    return this.playing
  }

  /** 标记一次外部装载（宿主自行取数时使用）。 */
  markLoaded(): void {
    if (!this.ready) {
      return
    }
    this.requestCount += 1
    this.notifyLifecycle('update')
  }

  /**
   * 定义取数（占位 / 未注入处理函数时零请求）。
   *
   * @param input 入参。
   * @returns 快照（占位 / 失败返回 `undefined`）。
   */
  async load(input: { code?: string } = {}): Promise<ScreenPlaySnapshot | undefined> {
    if (this.degraded || this.jobs.load === undefined || this.#busy || !this.#hasView()) {
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
        this.screenCode = snapshot.code
        this.canvas = normalizeCanvasConfig(snapshot.canvas)
        this.pages = normalizePages(snapshot.pages)
        if (this.pages.length === 0) {
          this.pages = [{ id: 'p-1', name: '页 1' }]
        }
        this.componentsByPage = normalizeComponentsByPage(
          snapshot.componentsByPage,
          this.pages.map((page) => page.id),
        )
        this.activePageId =
          snapshot.defaultPageId !== undefined && this.pages.some((page) => page.id === snapshot.defaultPageId)
            ? snapshot.defaultPageId
            : this.pages[0].id
      }
      if (token !== undefined) {
        this.dataState?.settle(token, snapshot !== undefined ? 'ready' : 'empty')
      }
      this.phase = 'ready'
      this.notifyLifecycle('update')
      return snapshot
    } catch (error) {
      this.errorMessage = error instanceof Error ? error.message : String(error)
      if (token !== undefined) {
        this.dataState?.settle(token, 'error')
      }
      this.phase = 'failed'
      this.reportError(error, { scope: 'BaseScreenPlayer.load' })
      this.notifyLifecycle('update')
      return undefined
    } finally {
      this.#busy = false
    }
  }

  /**
   * 按组件取数（无数据集组件不请求）。
   *
   * @param componentId 组件标识。
   * @param pageId 页标识（缺省当前页）。
   * @param params 查询参数。
   * @returns 取数结果（占位 / 失败 / 无数据集返回 `undefined`）。
   */
  async queryComponent(componentId: string, pageId?: string, params?: Record<string, unknown>): Promise<ScreenPreviewResult | undefined> {
    const targetPageId = pageId ?? this.activePageId
    if (this.degraded || this.jobs.componentData === undefined || !this.#hasView()) {
      return undefined
    }
    const component = findComponent(this.componentsByPage[targetPageId] ?? [], componentId)
    if (component === undefined || component.datasetId === undefined || component.datasetId === '') {
      return undefined
    }
    this.requestCount += 1
    const token = this.dataState?.begin()
    try {
      const result = await this.jobs.componentData({
        pageId: targetPageId,
        componentId,
        datasetId: component.datasetId,
        params,
      })
      this.data = { ...this.data, [componentId]: result }
      if (token !== undefined) {
        this.dataState?.settle(token, result !== undefined ? 'ready' : 'empty')
      }
      this.notifyLifecycle('update')
      return result
    } catch (error) {
      this.data = { ...this.data, [componentId]: undefined }
      this.errorMessage = error instanceof Error ? error.message : String(error)
      if (token !== undefined) {
        this.dataState?.settle(token, 'error')
      }
      this.reportError(error, { scope: 'BaseScreenPlayer.queryComponent' })
      this.notifyLifecycle('update')
      return undefined
    }
  }

  /**
   * 整页刷新（并行取数，单组件失败不阻断）。
   *
   * @param pageId 页标识（缺省当前页）。
   * @returns 发起的取数数量。
   */
  async refreshPage(pageId?: string): Promise<number> {
    const targetPageId = pageId ?? this.activePageId
    const targets = (this.componentsByPage[targetPageId] ?? []).filter(
      (component) => component.datasetId !== undefined && component.datasetId !== '',
    )
    if (targets.length === 0) {
      return 0
    }
    await Promise.all(targets.map((component) => this.queryComponent(component.id, targetPageId)))
    return targets.length
  }

  /** 是否持查看权限。 */
  #hasView(): boolean {
    return this.access === undefined || this.access.has(SCREEN_VIEW_PERM)
  }
}
