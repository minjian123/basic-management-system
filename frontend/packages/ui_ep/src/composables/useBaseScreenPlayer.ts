/** 大屏播放投影：把核心能力基类 `BaseScreenPlayer` 投影为组合式（多页轮播 / 播放态 / 按组件取数）。 */

import {
  BaseScreenPlayer,
  type BaseAccess,
  type BaseAsyncTask,
  type BaseDataState,
  type BaseNotice,
  type ScreenCanvasConfig,
  type ScreenComponent,
  type ScreenPage,
  type ScreenPlaySnapshot,
  type ScreenPlayerJobs,
  type ScreenPlayerPhase,
  type ScreenPreviewResult,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体大屏播放件（可实例化）。 */
class ScreenPlayerState extends BaseScreenPlayer {}

/** 选项。 */
export interface UseBaseScreenPlayerOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 大屏编码。 */
  screenCode?: string
  /** 画布配置。 */
  canvas?: ScreenCanvasConfig
  /** 多页。 */
  pages?: readonly ScreenPage[]
  /** 各页组件。 */
  componentsByPage?: Record<string, readonly ScreenComponent[]>
  /** 当前页标识。 */
  activePageId?: string
  /** 是否自动播放。 */
  autoplay?: boolean
  /** 轮播间隔（毫秒）。 */
  interval?: number
  /** 是否全屏。 */
  fullscreen?: boolean
  /** 注入处理函数集（未注入即占位）。 */
  jobs?: ScreenPlayerJobs
  /** 权限上下文（未注入视为有权）。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
  /** 数据状态能力（组件取数）。 */
  dataState?: BaseDataState
  /** 异步任务能力。 */
  asyncTask?: BaseAsyncTask
}

/** `useBaseScreenPlayer` 返回面。 */
export interface UseBaseScreenPlayerResult {
  /** 大屏播放基类实例。 */
  player: BaseScreenPlayer
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（响应式）。 */
  degraded: Ref<boolean>
  /** 是否进行中（响应式）。 */
  busy: Ref<boolean>
  /** 当前阶段（响应式）。 */
  phase: Ref<ScreenPlayerPhase>
  /** 画布配置（响应式）。 */
  canvas: Ref<ScreenCanvasConfig>
  /** 多页（响应式）。 */
  pages: Ref<ScreenPage[]>
  /** 当前页组件（响应式）。 */
  components: Ref<ScreenComponent[]>
  /** 当前页标识（响应式）。 */
  activePageId: Ref<string>
  /** 是否播放中（响应式）。 */
  playing: Ref<boolean>
  /** 轮播间隔（响应式）。 */
  interval: Ref<number>
  /** 当前页生效停留时长（响应式）。 */
  currentInterval: Ref<number>
  /** 是否全屏（响应式）。 */
  fullscreen: Ref<boolean>
  /** 各组件取数结果（响应式）。 */
  data: Ref<Record<string, ScreenPreviewResult | undefined>>
  /** 错误文案（响应式）。 */
  errorMessage: Ref<string>
  /** 请求计数（响应式）。 */
  requestCount: Ref<number>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 注入处理函数集。 */
  setJobs: (jobs: ScreenPlayerJobs) => void
  /** 设置画布配置。 */
  setCanvas: (canvas: unknown) => void
  /** 设置页清单。 */
  setPages: (pages: readonly ScreenPage[]) => void
  /** 设置各页组件。 */
  setComponents: (componentsByPage: Record<string, readonly ScreenComponent[]>) => void
  /** 设置播放态。 */
  setPlaying: (value: boolean) => void
  /** 设置轮播间隔。 */
  setInterval: (value: unknown) => number
  /** 设置全屏态。 */
  setFullscreen: (value: boolean) => void
  /** 切换当前页。 */
  selectPage: (pageId: string) => boolean
  /** 下一页。 */
  next: () => string
  /** 上一页。 */
  prev: () => string
  /** 切换播放 / 暂停。 */
  toggle: (force?: boolean) => boolean
  /** 标记外部装载。 */
  markLoaded: () => void
  /** 定义取数。 */
  load: (input?: { code?: string }) => Promise<ScreenPlaySnapshot | undefined>
  /** 按组件取数。 */
  queryComponent: (componentId: string, pageId?: string, params?: Record<string, unknown>) => Promise<ScreenPreviewResult | undefined>
  /** 整页刷新。 */
  refreshPage: (pageId?: string) => Promise<number>
}

/**
 * 使用大屏播放投影。
 *
 * @param options 选项。
 * @returns 大屏播放基类实例与响应式面。
 */
export function useBaseScreenPlayer(options: UseBaseScreenPlayerOptions = {}): UseBaseScreenPlayerResult {
  const player = new ScreenPlayerState()
  player.setReady(options.ready ?? false)
  if (options.screenCode !== undefined) {
    player.screenCode = options.screenCode
  }
  if (options.canvas !== undefined) {
    player.setCanvas(options.canvas)
  }
  if (options.pages !== undefined) {
    player.setPages(options.pages)
  }
  if (options.componentsByPage !== undefined) {
    player.setComponents(options.componentsByPage)
  }
  if (options.activePageId !== undefined && player.pages.some((page) => page.id === options.activePageId)) {
    player.activePageId = options.activePageId
  }
  if (options.autoplay !== undefined) {
    player.setPlaying(options.autoplay)
  }
  if (options.interval !== undefined) {
    player.setInterval(options.interval)
  }
  if (options.fullscreen !== undefined) {
    player.setFullscreen(options.fullscreen)
  }
  if (options.jobs !== undefined) {
    player.jobs = options.jobs
  }
  if (options.access !== undefined) {
    player.access = markRaw(toRaw(options.access))
  }
  if (options.notice !== undefined) {
    player.notice = markRaw(toRaw(options.notice))
  }
  if (options.dataState !== undefined) {
    player.dataState = markRaw(toRaw(options.dataState))
  }
  if (options.asyncTask !== undefined) {
    player.asyncTask = markRaw(toRaw(options.asyncTask))
  }

  const ready = ref(player.ready)
  const degraded = ref(player.degraded)
  const busy = ref(player.busy)
  const phase = ref<ScreenPlayerPhase>(player.phase)
  const canvas = ref<ScreenCanvasConfig>(player.canvas)
  const pages = ref<ScreenPage[]>([...player.pages])
  const components = ref<ScreenComponent[]>(player.currentComponents)
  const activePageId = ref(player.activePageId)
  const playing = ref(player.playing)
  const interval = ref(player.interval)
  const currentInterval = ref(player.currentInterval)
  const fullscreen = ref(player.fullscreen)
  const data = ref<Record<string, ScreenPreviewResult | undefined>>({ ...player.data })
  const errorMessage = ref(player.errorMessage)
  const requestCount = ref(player.requestCount)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = player.ready
    degraded.value = player.degraded
    busy.value = player.busy
    phase.value = player.phase
    canvas.value = player.canvas
    pages.value = [...player.pages]
    components.value = player.currentComponents
    activePageId.value = player.activePageId
    playing.value = player.playing
    interval.value = player.interval
    currentInterval.value = player.currentInterval
    fullscreen.value = player.fullscreen
    data.value = { ...player.data }
    errorMessage.value = player.errorMessage
    requestCount.value = player.requestCount
  }

  const off = player.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    player.dispose()
  })

  /** 包裹动作：执行后同步响应式面。 */
  const run = <T>(action: () => T): T => {
    const value = action()
    sync()
    return value
  }

  return {
    player,
    ready,
    degraded,
    busy,
    phase,
    canvas,
    pages,
    components,
    activePageId,
    playing,
    interval,
    currentInterval,
    fullscreen,
    data,
    errorMessage,
    requestCount,
    setReady: (value) => run(() => player.setReady(value)),
    setJobs: (jobs) => run(() => player.setJobs(jobs)),
    setCanvas: (value) => run(() => player.setCanvas(value)),
    setPages: (value) => run(() => player.setPages(value)),
    setComponents: (value) => run(() => player.setComponents(value)),
    setPlaying: (value) => run(() => player.setPlaying(value)),
    setInterval: (value) => run(() => player.setInterval(value)),
    setFullscreen: (value) => run(() => player.setFullscreen(value)),
    selectPage: (pageId) => run(() => player.selectPage(pageId)),
    next: () => run(() => player.next()),
    prev: () => run(() => player.prev()),
    toggle: (force) => run(() => player.toggle(force)),
    markLoaded: () => run(() => player.markLoaded()),
    load: async (input) => {
      const value = await player.load(input)
      sync()
      return value
    },
    queryComponent: async (componentId, pageId, params) => {
      const value = await player.queryComponent(componentId, pageId, params)
      sync()
      return value
    },
    refreshPage: async (pageId) => {
      const value = await player.refreshPage(pageId)
      sync()
      return value
    },
  }
}
